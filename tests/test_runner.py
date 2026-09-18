from pathlib import Path

from conftest import require_program
from search_tool.config import Location
from search_tool.runner import Search, plan_searches, run_search, targets
from search_tool.tools import KINDS, resolve_kinds


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


def test_resolve_kinds_without_a_flag_keeps_every_kind():
    assert resolve_kinds([]) == set(KINDS)


def test_resolve_kinds_drops_a_negated_kind():
    assert resolve_kinds(["!remote"]) == set(KINDS) - {"remote"}
    assert resolve_kinds(["!remote", "!ast"]) == set(KINDS) - {"remote", "ast"}


def test_resolve_kinds_negates_within_the_named_kinds():
    assert resolve_kinds(["regex", "semantic", "!semantic"]) == {"regex"}
    assert resolve_kinds(["remote", "!remote"]) == set()


def test_plan_searches_drops_a_negated_kind(tmp_path):
    locations = [
        Location("source", ("rg", "ck", "ast"), tmp_path),
        Location("confluence", ("rovo",)),
    ]
    searches = plan_searches(locations, "probe", ["!remote", "!ast"], None)
    assert [search.tool for search in searches] == ["rg", "ck"]


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


def test_plan_searches_pipes_paths_through_fzf(tmp_path):
    locations = [Location("source", ("fzf",), tmp_path)]
    (search,) = plan_searches(locations, "probe", [], None)
    assert search.command == [
        ["rg", "--files", str(tmp_path)],
        ["fzf", "--filter", "probe"],
    ]


def test_plan_searches_prunes_the_ignored_directories(tmp_path):
    locations = [
        Location(
            "source",
            ("rg", "rg-files", "fzf", "ck", "m2v", "ast"),
            tmp_path,
            (".venv", "dist"),
        )
    ]
    commands = {
        search.tool: search.command
        for search in plan_searches(locations, "probe", [], None)
    }
    assert commands["rg"][0][5:7] == ["--glob=!.venv/", "--glob=!dist/"]
    assert commands["rg-files"][0] == [
        "rg",
        "--files",
        "--glob=!.venv/",
        "--glob=!dist/",
        str(tmp_path),
    ]
    assert commands["fzf"][0] == commands["rg-files"][0]
    assert commands["ck"][0] == [
        "ck",
        "--sem",
        "--exclude",
        ".venv",
        "--exclude",
        "dist",
        "probe",
        str(tmp_path),
    ]
    assert commands["m2v"][0] == [
        "search-tool-semantic",
        "--skip",
        ".venv",
        "--skip",
        "dist",
        "probe",
        str(tmp_path),
    ]
    assert commands["ast"][0][4:6] == ["--globs=!.venv/", "--globs=!dist/"]


def test_plan_searches_leaves_directoryless_tools_alone(tmp_path):
    locations = [Location("man", ("man",), None, (".venv",))]
    (search,) = plan_searches(locations, "probe", [], None)
    assert search.command == [["man", "-K", "-w", "--regex", "probe"]]


def test_plan_searches_tidies_the_shell_history(tmp_path):
    history = tmp_path / "history"
    (search,) = plan_searches(
        [Location("history", ("hist",), history)], "git", [], None
    )
    assert search.command[0] == [
        "rg",
        "--color",
        "never",
        "--no-filename",
        "--no-line-number",
        "--",
        "git",
        str(history),
    ]
    assert search.command[1][0] == "awk"
