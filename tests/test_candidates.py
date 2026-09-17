import json
from pathlib import Path

from search_tool.candidates import build_candidates
from search_tool.runner import Result, Search


def result(tool, stdout, location="source", directory=Path("/src")):
    search = Search(location, tool, "regex", directory, [["fake"]])
    return Result(search, 0, stdout, "")


def ripgrep_match(path, line, text):
    return json.dumps(
        {
            "type": "match",
            "data": {
                "path": {"text": path},
                "lines": {"text": f"{text}\n"},
                "line_number": line,
            },
        }
    )


def ck_chunk(path, start, end, snippet, score):
    return json.dumps(
        {
            "path": path,
            "span": {"line_start": start, "line_end": end},
            "snippet": snippet,
            "score": score,
        }
    )


def test_overlapping_spans_of_two_tools_merge():
    results = [
        result("rg", ripgrep_match("/src/a.py", 2, "    connect()")),
        result("ck", ck_chunk("/src/a.py", 1, 4, "def open_db():\n    connect()", 0.8)),
    ]
    (candidate,) = build_candidates(results)
    assert (candidate.line, candidate.end_line) == (1, 4)
    assert candidate.text == "def open_db():\n    connect()"
    assert [
        (source.tool, source.rank, source.score) for source in candidate.sources
    ] == [
        ("ck", 1, 0.8),
        ("rg", 1, None),
    ]


def test_separate_spans_of_one_file_stay_apart():
    stdout = "\n".join(
        [
            ripgrep_match("/src/a.py", 1, "first"),
            ripgrep_match("/src/a.py", 40, "later"),
        ]
    )
    first, second = build_candidates([result("rg", stdout)])
    assert (first.line, second.line) == (1, 40)
    assert [source.rank for source in second.sources] == [2]


def test_whole_file_hits_merge_with_each_other_and_keep_their_candidate():
    results = [
        result("rg-files", "/src/a.py\n"),
        result("rg-files", "/src/a.py\n", location="notes"),
        result("rg", ripgrep_match("/src/a.py", 3, "match")),
    ]
    whole, spanned = build_candidates(results)
    assert (whole.line, whole.end_line) == (None, None)
    assert [source.location for source in whole.sources] == ["source", "notes"]
    assert spanned.line == 3


def test_candidates_are_ordered_by_key_then_line():
    stdout = "\n".join(
        [
            ripgrep_match("/src/b.py", 9, "b nine"),
            ripgrep_match("/src/a.py", 2, "a two"),
        ]
    )
    candidates = build_candidates([result("rg", stdout)])
    assert [(c.key, c.line) for c in candidates] == [("/src/a.py", 2), ("/src/b.py", 9)]


def test_different_files_never_merge():
    stdout = "\n".join(
        [
            ripgrep_match("/src/a.py", 1, "one"),
            ripgrep_match("/other/a.py", 1, "one"),
        ]
    )
    assert len(build_candidates([result("rg", stdout)])) == 2


def test_no_results_make_no_candidates():
    assert build_candidates([]) == []
    assert build_candidates([result("rg", "")]) == []
