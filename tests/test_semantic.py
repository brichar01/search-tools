import io
import json

import numpy as np

from conftest import require_model
from search_tool.semantic import DEFAULT_MODEL, Line, main, rank, read_lines


def test_read_lines_reads_stdin_where_no_paths_are_given():
    stdin = io.StringIO("first\n\n   \nthird\n")
    assert read_lines([], stdin) == [Line("-", 1, "first"), Line("-", 4, "third")]


def test_read_lines_walks_directories_and_skips_dot_paths(tmp_path):
    (tmp_path / "notes.txt").write_text("alpha\nbeta\n")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("gamma\n")
    (tmp_path / "image.bin").write_bytes(b"\xff\xfe\x00binary")

    lines = read_lines([tmp_path], io.StringIO())

    assert [(line.number, line.text) for line in lines] == [(1, "alpha"), (2, "beta")]
    assert lines[0].source == str(tmp_path / "notes.txt")


def test_read_lines_prunes_skipped_directory_names(tmp_path):
    (tmp_path / "notes.txt").write_text("alpha\n")
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "bundle.txt").write_text("beta\n")
    (tmp_path / "src" / "dist").mkdir(parents=True)
    (tmp_path / "src" / "dist" / "nested.txt").write_text("gamma\n")

    lines = read_lines([tmp_path], io.StringIO(), ["dist"])

    assert [line.text for line in lines] == ["alpha"]


def test_read_lines_reads_a_file_named_directly(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("alpha\n")
    assert read_lines([path], io.StringIO()) == [Line(str(path), 1, "alpha")]


def test_rank_puts_the_closest_line_first():
    model = require_model(DEFAULT_MODEL)
    lines = [
        Line("-", 1, "the cat sat on the mat"),
        Line("-", 2, "database connection pooling"),
        Line("-", 3, "a walk along the beach"),
    ]

    hits = rank(model, "storing records", lines, top_k=2, threshold=-1.0)

    assert len(hits) == 2
    assert hits[0][0].number == 2
    assert hits[0][1] > hits[1][1]


def test_rank_drops_lines_below_the_threshold():
    model = require_model(DEFAULT_MODEL)
    lines = [Line("-", 1, "the cat sat on the mat")]
    assert rank(model, "storing records", lines, top_k=10, threshold=0.9) == []


def test_rank_returns_nothing_for_no_lines():
    assert rank(None, "storing records", [], top_k=10, threshold=0.0) == []


def test_main_writes_json_records_for_stdin(monkeypatch, capsys):
    require_model(DEFAULT_MODEL)
    monkeypatch.setattr("sys.stdin", io.StringIO("database connection pooling\n"))

    status = main(
        query="storing records",
        paths=[],
        top_k=1,
        threshold=0.0,
        model=DEFAULT_MODEL,
        json_output=True,
        skip=[],
    )

    record = json.loads(capsys.readouterr().out)
    assert status == 0
    assert record["path"] == "-"
    assert record["line"] == 1
    assert record["text"] == "database connection pooling"
    assert 0.0 < record["score"] <= 1.0


def test_main_reports_a_model_it_cannot_load(capsys):
    status = main(
        query="storing records",
        paths=[],
        top_k=1,
        threshold=0.0,
        model="minishlab/no-such-model",
        json_output=False,
        skip=[],
    )
    assert status == 2
    assert "no-such-model" in capsys.readouterr().err


def test_main_exits_one_where_nothing_ranks(monkeypatch, capsys):
    require_model(DEFAULT_MODEL)
    monkeypatch.setattr("sys.stdin", io.StringIO("the cat sat on the mat\n"))

    status = main(
        query="storing records",
        paths=[],
        top_k=1,
        threshold=0.99,
        model=DEFAULT_MODEL,
        json_output=False,
        skip=[],
    )

    assert status == 1
    assert capsys.readouterr().out == ""


class Recorder:
    """A model that keeps what it was asked to embed."""

    def __init__(self):
        self.seen = []

    def encode(self, texts):
        """Record the texts and return one unit vector each."""
        self.seen.extend(texts)
        return np.ones((len(texts), 3))


def test_rank_folds_the_query_and_the_lines_by_default():
    model = Recorder()
    lines = [Line("-", 1, "Mixed Case Line")]

    hits = rank(model, "Mixed Query", lines, top_k=1, threshold=-1.0)

    assert model.seen == ["mixed query", "mixed case line"]
    assert hits[0][0].text == "Mixed Case Line"


def test_rank_keeps_the_case_where_asked():
    model = Recorder()
    lines = [Line("-", 1, "Mixed Case Line")]

    rank(model, "Mixed Query", lines, top_k=1, threshold=-1.0, case_sensitive=True)

    assert model.seen == ["Mixed Query", "Mixed Case Line"]
