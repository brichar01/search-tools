from pathlib import Path

from conftest import require_program
from search_tool.config import Location
from search_tool.runner import Search, plan_searches, run_search, targets


def test_targets_without_a_subdir(tmp_path):
    location = Location("source", ("rg",), tmp_path)
    assert targets(location, None) == [tmp_path]
    assert targets(Location("man", ("man",)), None) == [None]


def test_targets_keeps_matching_subdirectories(tmp_path):
    (tmp_path / "am100-analyser").mkdir()
    (tmp_path / "am100-recorder").mkdir()
    (tmp_path / "other").mkdir()
    (tmp_path / "am100-notes.txt").write_text("")
    location = Location("source", ("rg",), tmp_path)
    assert targets(location, "am100-*") == [
        tmp_path / "am100-analyser",
        tmp_path / "am100-recorder",
    ]
    assert targets(location, "none-*") == []


def test_plan_searches_covers_every_tool_and_target(tmp_path):
    (tmp_path / "one").mkdir()
    (tmp_path / "two").mkdir()
    locations = [
        Location("source", ("rg", "ck"), tmp_path),
        Location("confluence", ("rovo",)),
    ]
    searches = plan_searches(locations, "probe", [], "*")
    assert [(search.tool, search.directory) for search in searches] == [
        ("rg", tmp_path / "one"),
        ("rg", tmp_path / "two"),
        ("ck", tmp_path / "one"),
        ("ck", tmp_path / "two"),
        ("rovo", None),
    ]


def test_plan_searches_filters_by_kind(tmp_path):
    locations = [Location("source", ("rg", "ck", "ast"), tmp_path)]
    searches = plan_searches(locations, "probe", ["semantic", "ast"], None)
    assert [search.tool for search in searches] == ["ck", "ast"]
    assert searches[0].command == [["ck", "--sem", "probe", str(tmp_path)]]


def test_run_search_collects_output():
    require_program("printf")
    search = Search("here", "rg", "regex", Path("/tmp"), [["printf", "a\nb\n"]])
    result = run_search(search)
    assert result.lines == ["a", "b"]
    assert result.exit_code == 0
    assert result.matched


def test_run_search_reports_the_highest_pipeline_exit_code():
    require_program("printf")
    require_program("grep")
    search = Search(
        "here",
        "rg-files",
        "files",
        Path("/tmp"),
        [["printf", "a\n"], ["grep", "zzz"]],
    )
    result = run_search(search)
    assert result.lines == []
    assert result.exit_code == 1
    assert not result.matched


def test_run_search_reports_a_missing_program():
    search = Search(
        "here", "ck", "semantic", Path("/tmp"), [["not-installed-anywhere"]]
    )
    result = run_search(search)
    assert result.exit_code == 127
    assert "not installed" in result.stderr
