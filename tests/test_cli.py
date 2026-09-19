import json
import sys

import pytest
import yaml

from conftest import require_program
from search_tool.cli import main, parse_args
from search_tool.config import default_config_path, starter_config


@pytest.fixture
def workspace(tmp_path):
    """A config file with one leaf holding one matching file."""
    directory = tmp_path / "src"
    (directory / "probe").mkdir(parents=True)
    (directory / "probe" / "reading.py").write_text("saturation = 0.9\n")
    config = tmp_path / "config.yml"
    config.write_text(
        yaml.safe_dump({"source": {"directory": str(directory), "tools": ["rg"]}})
    )
    return config, directory


def search(workspace, tmp_path, **overrides):
    config, _ = workspace
    arguments = {
        "query": "saturation",
        "locations": ["source"],
        "config": config,
        "subdir": None,
        "kinds": [],
        "case_sensitive": False,
        "json_output": False,
        "precache": False,
        "init": False,
    }
    return main(**(arguments | overrides))


def test_text_output_labels_the_tool_and_directory(workspace, tmp_path, capsys):
    require_program("rg")
    _, directory = workspace
    assert search(workspace, tmp_path) == 0
    out = capsys.readouterr().out
    assert out.startswith(f"== [source] rg {directory} ==")
    assert "saturation = 0.9" in out


def records(capsys):
    return [json.loads(line) for line in capsys.readouterr().out.splitlines()]


def test_json_output_reports_every_search_then_the_candidates(
    workspace, tmp_path, capsys
):
    require_program("rg")
    _, directory = workspace
    assert search(workspace, tmp_path, json_output=True) == 0
    written = records(capsys)
    assert [record["type"] for record in written] == ["search", "candidate"]

    ran, candidate = written
    assert ran["tool"] == "rg"
    assert ran["kind"] == "regex"
    assert ran["directory"] == str(directory)
    assert ran["candidates"] == 1
    assert ran["exit_code"] == 0

    assert candidate["query"] == "saturation"
    assert candidate["key"] == str(directory / "probe" / "reading.py")
    assert candidate["kind"] == "file"
    assert candidate["line"] == 1
    assert candidate["end_line"] == 1
    assert candidate["text"] == "saturation = 0.9"
    assert candidate["sources"] == [
        {
            "location": "source",
            "tool": "rg",
            "directory": str(directory),
            "rank": 1,
            "score": None,
        }
    ]


def test_subdir_limits_the_search(workspace, tmp_path, capsys):
    require_program("rg")
    _, directory = workspace
    assert search(workspace, tmp_path, subdir="probe", json_output=True) == 0
    ran = records(capsys)[0]
    assert ran["directory"] == str(directory / "probe")


def test_a_subdir_matching_nothing_searches_nothing(workspace, tmp_path, capsys):
    assert search(workspace, tmp_path, subdir="absent") == 1
    assert capsys.readouterr().out == ""


def test_a_kind_filter_drops_every_tool(workspace, tmp_path, capsys):
    assert search(workspace, tmp_path, kinds=["semantic"]) == 1
    assert capsys.readouterr().out == ""


def test_a_negated_kind_drops_every_tool(workspace, tmp_path, capsys):
    assert search(workspace, tmp_path, kinds=["!regex"]) == 1
    assert capsys.readouterr().out == ""


def test_the_kind_flag_takes_a_negated_kind(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["search-tool", "-k", "!remote", "probe"])
    assert parse_args().kinds == ["!remote"]


def test_the_kind_flag_rejects_an_unknown_kind(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["search-tool", "-k", "!nope", "probe"])
    with pytest.raises(SystemExit):
        parse_args()


def test_history_dedupes_repeated_commands(tmp_path, capsys):
    require_program("rg")
    require_program("awk")
    history = tmp_path / "history"
    history.write_text(
        ": 1699999999:0;git status\n: 1700000000:0;git commit\n"
        ": 1700000001:5;git status\nls\n"
    )
    config = tmp_path / "config.yml"
    config.write_text(
        yaml.safe_dump({"history": {"directory": str(history), "tools": ["hist"]}})
    )
    status = main(
        query="git",
        locations=[],
        config=config,
        subdir=None,
        kinds=[],
        case_sensitive=False,
        json_output=True,
        precache=False,
        init=False,
    )
    assert status == 0
    keys = [
        record["key"] for record in records(capsys) if record["type"] == "candidate"
    ]
    assert sorted(keys) == ["git commit", "git status"]


def test_an_unknown_location_exits(workspace, tmp_path):
    with pytest.raises(SystemExit, match="Unknown location"):
        search(workspace, tmp_path, locations=["nope"])


def test_the_config_default_comes_from_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("SEARCH_TOOL_CONFIG", str(tmp_path / "config.yml"))
    assert default_config_path() == tmp_path / "config.yml"


def test_init_writes_the_example_config(tmp_path, capsys):
    path = tmp_path / "nested" / "config.yml"
    status = main(
        query=None,
        locations=[],
        config=path,
        subdir=None,
        kinds=[],
        case_sensitive=False,
        json_output=False,
        precache=False,
        init=True,
    )
    assert status == 0
    assert path.read_text() == starter_config()
    assert str(path) in capsys.readouterr().out


def test_init_refuses_to_overwrite(tmp_path):
    path = tmp_path / "config.yml"
    path.write_text("notes: {tools: [rg]}\n")
    with pytest.raises(SystemExit, match="already exists"):
        main(
            query=None,
            locations=[],
            config=path,
            subdir=None,
            kinds=[],
            case_sensitive=False,
            json_output=False,
            precache=False,
            init=True,
        )


def test_init_takes_no_query(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["search-tool", "--init"])
    arguments = parse_args()
    assert arguments.init
    assert arguments.query is None


def test_a_config_naming_nothing_points_at_init(tmp_path):
    with pytest.raises(SystemExit, match="--init"):
        main(
            query="saturation",
            locations=[],
            config=tmp_path / "absent.yml",
            subdir=None,
            kinds=[],
            case_sensitive=False,
            json_output=False,
            precache=False,
            init=False,
        )


def test_the_default_config_sits_under_the_home_config_directory(monkeypatch, tmp_path):
    monkeypatch.delenv("SEARCH_TOOL_CONFIG", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert default_config_path() == tmp_path / ".config" / "search-tool" / "config.yml"


def test_precache_reads_the_first_positional_as_a_location(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["search-tool", "--precache", "source", "notes"])
    arguments = parse_args()
    assert arguments.query is None
    assert arguments.locations == ["source", "notes"]


def test_a_search_without_a_query_exits(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["search-tool"])
    with pytest.raises(SystemExit):
        parse_args()


def test_precache_indexes_instead_of_searching(workspace, tmp_path, capsys):
    assert search(workspace, tmp_path, query=None, precache=True) == 0
    assert capsys.readouterr().out == ""


def test_the_search_folds_case_by_default(workspace, tmp_path, capsys):
    require_program("rg")
    assert search(workspace, tmp_path, query="SATURATION") == 0
    assert "saturation = 0.9" in capsys.readouterr().out


def test_case_sensitive_drops_the_mismatched_query(workspace, tmp_path, capsys):
    require_program("rg")
    assert search(workspace, tmp_path, query="SATURATION", case_sensitive=True) == 1
    assert "saturation = 0.9" not in capsys.readouterr().out
