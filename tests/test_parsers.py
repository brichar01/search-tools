import json

from search_tool.parsers import (
    parse_ast_grep,
    parse_ck,
    parse_man,
    parse_paths,
    parse_ripgrep,
    parse_rovo,
)

MATCH = json.dumps(
    {
        "type": "match",
        "data": {
            "path": {"text": "/src/a.py"},
            "lines": {"text": "def connect_db():\n"},
            "line_number": 1,
            "submatches": [{"match": {"text": "connect"}, "start": 4, "end": 11}],
        },
    }
)
BEGIN = json.dumps({"type": "begin", "data": {"path": {"text": "/src/a.py"}}})
SUMMARY = json.dumps({"type": "summary", "data": {"stats": {"matches": 1}}})
RIPGREP = f"{BEGIN}\n{MATCH}\n{SUMMARY}"

CK = json.dumps(
    {
        "path": "/src/a.py",
        "span": {"byte_start": 0, "byte_end": 26, "line_start": 1, "line_end": 2},
        "language": "python",
        "snippet": "def connect_db():\n    pass",
        "score": 0.8417218,
    }
)

AST_GREP = json.dumps(
    [
        {
            "text": "def connect_db():\n    pass",
            "range": {
                "byteOffset": {"start": 0, "end": 26},
                "start": {"line": 0, "column": 0},
                "end": {"line": 1, "column": 8},
            },
            "file": "/src/a.py",
            "language": "Python",
        }
    ]
)


def test_parse_ripgrep_keeps_only_matches():
    (hit,) = parse_ripgrep(RIPGREP)
    assert hit.key == "/src/a.py"
    assert hit.kind == "file"
    assert (hit.line, hit.end_line) == (1, 1)
    assert hit.text == "def connect_db():"
    assert hit.score is None


def test_parse_ck_keeps_the_span_and_score():
    (hit,) = parse_ck(CK)
    assert hit.key == "/src/a.py"
    assert (hit.line, hit.end_line) == (1, 2)
    assert hit.text == "def connect_db():\n    pass"
    assert hit.score == 0.8417218


def test_parse_ast_grep_counts_lines_from_one():
    (hit,) = parse_ast_grep(AST_GREP)
    assert hit.key == "/src/a.py"
    assert (hit.line, hit.end_line) == (1, 2)


def test_parse_ast_grep_without_matches():
    assert parse_ast_grep("[]") == []
    assert parse_ast_grep("") == []


def test_parse_paths_names_whole_files():
    (hit,) = parse_paths("/src/a.py\n\n")
    assert hit.key == "/src/a.py"
    assert (hit.line, hit.end_line) == (None, None)
    assert hit.text == "/src/a.py"


def test_parse_man_names_the_page_and_section():
    hits = parse_man(
        "/usr/share/man/man1/git-archive.1.gz\n/usr/share/man/man5/tar.5\n"
    )
    assert [hit.text for hit in hits] == ["git-archive(1)", "tar(5)"]
    assert hits[0].kind == "manual"
    assert hits[0].key == "/usr/share/man/man1/git-archive.1.gz"


def test_parse_rovo_reads_plain_json():
    stdout = json.dumps(
        {
            "items": [
                {
                    "id": "ari:page/1",
                    "title": "Auto Detection 2.1.0 Release Notes",
                    "text": "Stereo matching was reworked",
                    "url": "https://example.atlassian.net/wiki/1",
                }
            ]
        }
    )
    (hit,) = parse_rovo(stdout)
    assert hit.key == "https://example.atlassian.net/wiki/1"
    assert hit.kind == "remote"
    assert (
        hit.text == "Auto Detection 2.1.0 Release Notes\nStereo matching was reworked"
    )


def test_parse_rovo_follows_the_envelope_to_the_payload(tmp_path):
    payload = tmp_path / "stdout.json"
    payload.write_text(
        json.dumps({"items": [{"id": "ari:page/2", "title": "Sizing", "snippet": "a"}]})
    )
    stdout = f'output_files:\n  stdout: "{payload}"\n  stdout_lines: 3\n---END---\n'
    (hit,) = parse_rovo(stdout)
    assert hit.key == "ari:page/2"
    assert hit.text == "Sizing\na"


def test_parse_rovo_falls_back_to_the_inline_items():
    stdout = (
        'output_files:\n  stdout: "/absent/stdout.json"\n'
        'stdout_inline:\n  items:\n    -\n      id: "ari:page/3"\n'
        '      title: "Sizing"\n      snippet: "b"\n---END---\n'
    )
    (hit,) = parse_rovo(stdout)
    assert hit.key == "ari:page/3"
    assert hit.text == "Sizing\nb"


def test_parse_rovo_without_results():
    assert parse_rovo("") == []
    assert parse_rovo("not json or yaml: [") == []
