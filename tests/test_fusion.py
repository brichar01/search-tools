import json
from pathlib import Path

from search_tool.candidates import build_candidates
from search_tool.fusion import score_targets
from search_tool.runner import Result, Search


def result(
    tool,
    stdout,
    location="source",
    directory=Path("/src"),
    kind="regex",
    exit_code=0,
    skipped=None,
):
    search = Search(location, tool, kind, directory, [["fake"]], skipped)
    return Result(search, exit_code, stdout, "")


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


def scored(results, prior=1.0, weights=None):
    return score_targets(build_candidates(results), results, prior, weights or {})


ONE = {"ck": 1.0, "ck-lex": 1.0}
"""Weights that drop the shared-index discount, so a test reads as a count."""


def test_two_tools_that_agree_outscore_one():
    results = [
        result(
            "rg",
            "\n".join(
                [
                    ripgrep_match("/src/a.py", 2, "    connect()"),
                    ripgrep_match("/src/b.py", 9, "    connect()"),
                ]
            ),
        ),
        result("ck", ck_chunk("/src/a.py", 1, 4, "def open_db():", 0.8)),
    ]
    both, one = scored(results, weights=ONE)
    assert (both.key, both.votes, both.reach) == ("/src/a.py", 2.0, 2.0)
    assert (one.key, one.votes, one.reach) == ("/src/b.py", 1.0, 2.0)
    assert (both.relevance, one.relevance) == (2 / 3, 1 / 3)


def test_a_whole_file_search_votes_on_the_same_target_as_a_span_search():
    results = [
        result("rg", ripgrep_match("/src/a.py", 2, "cache")),
        result("rg-files", "/src/a.py\n", kind="files"),
    ]
    (target,) = scored(results)
    assert (target.votes, target.reach) == (2.0, 2.0)
    assert [(c.line, c.end_line) for c in target.candidates] == [(2, 2), (None, None)]


def test_one_search_votes_once_however_many_hits_it_returned():
    stdout = "\n".join(
        ripgrep_match("/src/a.py", line, "cache") for line in (1, 10, 20, 30)
    )
    (target,) = scored([result("rg", stdout)])
    assert target.votes == 1.0
    assert len(target.candidates) == 4


def test_a_target_is_scored_only_against_the_searches_that_reach_it():
    results = [
        result("man", "/usr/share/man/man1/tar.1.gz"),
        result("rg", ripgrep_match("/src/a.py", 2, "tar")),
        result("ck", "", exit_code=1),
        result("rg", "", directory=Path("/other")),
    ]
    page, spanned = scored(results, weights=ONE)
    assert (page.kind, page.reach) == ("manual", 1.0)
    assert (spanned.kind, spanned.reach) == ("file", 2.0)
    assert (page.relevance, spanned.relevance) == (0.5, 1 / 3)


def test_a_skipped_search_reaches_nothing():
    results = [
        result("rg", ripgrep_match("/src/a.py", 2, "cache")),
        result("ck", "", skipped="cannot express negation"),
    ]
    (target,) = scored(results)
    assert (target.reach, target.relevance) == (1.0, 0.5)


def test_a_failed_search_reaches_nothing():
    results = [
        result("rg", ripgrep_match("/src/a.py", 2, "cache")),
        result("ck", "", exit_code=127),
    ]
    (target,) = scored(results)
    assert (target.reach, target.relevance) == (1.0, 0.5)


def test_a_search_that_ran_and_found_nothing_counts():
    results = [
        result("rg", ripgrep_match("/src/a.py", 2, "cache")),
        result("ck", "", exit_code=1),
    ]
    (target,) = scored(results, weights=ONE)
    assert (target.reach, target.relevance) == (2.0, 1 / 3)


def test_a_scoring_tool_spreads_its_hits_over_the_range_it_returned():
    stdout = "\n".join(
        [
            ck_chunk("/src/a.py", 1, 2, "closest", 0.9),
            ck_chunk("/src/b.py", 1, 2, "middle", 0.5),
            ck_chunk("/src/c.py", 1, 2, "furthest", 0.1),
        ]
    )
    closest, middle, furthest = scored([result("ck", stdout)], weights=ONE)
    assert [t.key for t in (closest, middle, furthest)] == [
        "/src/a.py",
        "/src/b.py",
        "/src/c.py",
    ]
    assert [t.votes for t in (closest, middle, furthest)] == [1.0, 0.5, 0.0]


def test_the_spans_of_a_target_come_out_strongest_first():
    stdout = "\n".join(
        [
            ck_chunk("/src/a.py", 40, 44, "furthest", 0.2),
            ck_chunk("/src/a.py", 1, 4, "closest", 0.9),
            ck_chunk("/src/a.py", 20, 24, "middle", 0.5),
        ]
    )
    (target,) = scored([result("ck", stdout)], weights=ONE)
    assert [c.line for c in target.candidates] == [1, 20, 40]
    assert [c.text for c in target.candidates] == ["closest", "middle", "furthest"]
    assert target.votes == 1.0


def test_a_weight_counts_into_the_vote_and_the_reach():
    results = [
        result("rg", ripgrep_match("/src/a.py", 2, "cache")),
        result("ck", ck_chunk("/src/a.py", 1, 4, "cache", 0.8)),
    ]
    (discounted,) = scored(results)
    assert (discounted.votes, discounted.reach) == (1.6, 1.6)
    assert discounted.relevance == 1.6 / 2.6

    (level,) = scored(results, weights=ONE)
    assert (level.votes, level.reach) == (2.0, 2.0)


def test_a_weight_of_zero_drops_a_tool_from_the_score():
    results = [
        result("rg", ripgrep_match("/src/a.py", 2, "cache")),
        result("ck", ck_chunk("/src/a.py", 1, 4, "cache", 0.8)),
    ]
    (target,) = scored(results, weights={"ck": 0.0})
    assert (target.votes, target.reach) == (1.0, 1.0)
    assert len(target.candidates) == 1


def test_a_downweighted_tool_that_agrees_alone_scores_below_a_full_one():
    agreed = scored(
        [result("ck", ck_chunk("/src/a.py", 1, 4, "cache", 0.8))],
    )
    assert agreed[0].relevance == 0.6 / 1.6

    full = scored([result("rg", ripgrep_match("/src/a.py", 2, "cache"))])
    assert full[0].relevance == 0.5


def test_the_prior_sets_how_far_agreement_beats_a_narrow_reach():
    results = [
        result("rg", ripgrep_match("/src/a.py", 2, "tar")),
        result("ck", ck_chunk("/src/a.py", 1, 4, "def tar():", 0.8)),
        result("ck-lex", ck_chunk("/src/a.py", 1, 4, "def tar():", 0.8)),
        result("ast", "", kind="ast", exit_code=1),
        result("man", "/usr/share/man/man1/tar.1.gz"),
    ]
    agreed, narrow = scored(results, weights=ONE)
    assert (agreed.votes, agreed.reach) == (3.0, 4.0)
    assert (narrow.votes, narrow.reach) == (1.0, 1.0)
    assert (agreed.relevance, narrow.relevance) == (0.6, 0.5)

    first, second = scored(results, prior=0.0, weights=ONE)
    assert (first.key, first.relevance) == (narrow.key, 1.0)
    assert (second.key, second.relevance) == (agreed.key, 0.75)


def test_targets_of_one_score_stay_ordered_by_key():
    stdout = "\n".join(
        [
            ripgrep_match("/src/b.py", 9, "b nine"),
            ripgrep_match("/src/a.py", 40, "a forty"),
        ]
    )
    assert [t.key for t in scored([result("rg", stdout)])] == ["/src/a.py", "/src/b.py"]


def test_nothing_found_scores_nothing():
    assert scored([]) == []
