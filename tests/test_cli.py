import json

import pytest
import yaml

from conftest import require_program
from search_tool.cli import default_config_path, default_tldr_dir, main


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
        "json_output": False,
        "tldr_dir": tmp_path / "tldr",
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


def test_an_unknown_location_exits(workspace, tmp_path):
    with pytest.raises(SystemExit, match="Unknown location"):
        search(workspace, tmp_path, locations=["nope"])


def test_defaults_come_from_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("SEARCH_TOOL_CONFIG", str(tmp_path / "config.yml"))
    monkeypatch.setenv("SEARCH_TOOL_TLDR_DIR", str(tmp_path / "pages"))
    assert default_config_path() == tmp_path / "config.yml"
    assert default_tldr_dir() == tmp_path / "pages"


def test_the_default_config_follows_xdg(monkeypatch, tmp_path):
    monkeypatch.delenv("SEARCH_TOOL_CONFIG", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert default_config_path() == tmp_path / "search-tool" / "config.yml"
