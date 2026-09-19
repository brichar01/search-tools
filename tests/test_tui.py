import asyncio

import pytest
import yaml
from textual.widgets import DataTable, Input, SelectionList, Static

from conftest import require_program
from search_tool.candidates import Candidate, Source
from search_tool.config import Location, load_config, select_locations
from search_tool.fusion import Target
from search_tool.tui import (
    DEBOUNCE,
    SearchTool,
    describe,
    editor_command,
    first_line,
    narrow,
    preview,
    search,
    shorten,
    status,
    voters,
)


@pytest.fixture
def workspace(tmp_path):
    """A config file with one leaf holding one matching file."""
    directory = tmp_path / "src"
    directory.mkdir()
    (directory / "reading.py").write_text("saturation = 0.9\n")
    config = tmp_path / "config.yml"
    config.write_text(
        yaml.safe_dump(
            {
                "source": {"directory": str(directory), "tools": ["rg", "rg-files"]},
                "man": {"tools": ["man"]},
            }
        )
    )
    return config, directory


def target(key="/home/you/src/reading.py", tool="rg"):
    source = Source("source", tool, "/home/you/src", 1, None)
    candidate = Candidate(key, "file", 3, 4, "saturation = 0.9", [source], 1.0)
    return Target(key, "file", 1.0, 2.0, 0.333, [candidate])


def test_narrow_cuts_each_location_to_the_enabled_tools(tmp_path):
    locations = [
        Location("source", ("rg", "ck"), tmp_path),
        Location("man", ("man",)),
    ]
    assert narrow(locations, {"rg", "man"}) == [
        Location("source", ("rg",), tmp_path),
        Location("man", ("man",)),
    ]


def test_narrow_drops_a_location_with_nothing_enabled(tmp_path):
    assert narrow([Location("source", ("rg", "ck"), tmp_path)], {"man"}) == []


def test_search_ranks_what_the_enabled_tools_found(workspace):
    require_program("rg")
    config, directory = workspace
    chosen = select_locations(load_config(config), ["source"])
    outcome = search(chosen, "saturation", None, False, 1.0, {})
    assert [one.key for one in outcome.targets] == [str(directory / "reading.py")]
    assert outcome.ran == 2
    assert outcome.failed == []


def test_search_reports_a_skipped_tool(workspace):
    require_program("rg")
    config, _ = workspace
    chosen = narrow(select_locations(load_config(config), ["source"]), {"rg-files"})
    outcome = search(chosen, "saturation -drift", None, False, 1.0, {})
    assert outcome.skipped == 1
    assert outcome.ran == 0
    assert outcome.targets == []


def test_shorten_writes_the_home_directory_as_a_tilde(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert shorten(f"{tmp_path}/src/reading.py") == "~/src/reading.py"
    assert shorten("/etc/hosts") == "/etc/hosts"


def test_voters_names_each_search_once():
    one = target()
    one.candidates[0].sources.append(Source("source", "rg", "/home/you/src", 2, None))
    assert voters(one) == "rg"


def test_describe_writes_the_name_before_the_directory():
    written = describe(target()).plain
    assert written.startswith("reading.py")
    assert written.endswith("/home/you/src")


def test_preview_holds_the_key_the_score_and_the_span():
    written = preview(target()).plain
    assert "reading.py" in written
    assert "relevance 0.333" in written
    assert "3-4" in written
    assert "saturation = 0.9" in written


def test_status_counts_what_ran():
    from search_tool.tui import Outcome

    written = status(Outcome([target()], 4, 1, ["man[man]: boom"])).plain
    assert "1 targets" in written
    assert "4 searches" in written
    assert "1 skipped" in written
    assert "1 failed" in written


def test_first_line_takes_the_strongest_span_that_holds_one():
    one = target()
    assert first_line(one) == 3
    one.candidates[0].line = None
    assert first_line(one) is None


def test_editor_command_opens_at_the_line_where_the_editor_can():
    assert editor_command("vim", "/src/a.py", 12) == ["vim", "+12", "/src/a.py"]
    assert editor_command("/usr/bin/nvim", "/src/a.py", 12) == [
        "/usr/bin/nvim",
        "+12",
        "/src/a.py",
    ]
    assert editor_command("code", "/src/a.py", 12) == [
        "code",
        "-g",
        "/src/a.py:12",
    ]
    assert editor_command("hx", "/src/a.py", 12) == ["hx", "/src/a.py:12"]
    assert editor_command("ed", "/src/a.py", 12) == ["ed", "/src/a.py"]


def test_editor_command_keeps_the_arguments_the_setting_carries():
    assert editor_command("nvim -u NONE", "/src/a.py", None) == [
        "nvim",
        "-u",
        "NONE",
        "/src/a.py",
    ]


def run(app, scenario):
    """Drive one app to completion, without a pytest asyncio plugin."""

    async def driver():
        async with app.run_test() as pilot:
            await scenario(pilot)

    asyncio.run(driver())


def test_app_ranks_the_query_it_opened_with(workspace):
    require_program("rg")
    config, directory = workspace
    chosen = select_locations(load_config(config), ["source"])
    app = SearchTool(chosen=chosen, weights={}, query="saturation")

    async def scenario(pilot):
        await pilot.app.workers.wait_for_complete()
        await pilot.pause()
        table = pilot.app.query_one("#targets", DataTable)
        assert table.row_count == 1
        assert str(directory / "reading.py") in pilot.app.targets
        assert "reading.py" in pilot.app.query_one("#span", Static).content.plain

    run(app, scenario)


def test_app_searches_again_when_a_tool_is_switched_off(workspace):
    require_program("rg")
    config, _ = workspace
    chosen = select_locations(load_config(config), ["source"])
    app = SearchTool(chosen=chosen, weights={}, query="saturation")

    async def scenario(pilot):
        await pilot.app.workers.wait_for_complete()
        await pilot.pause()
        pilot.app.query_one("#tools", SelectionList).deselect_all()
        await pilot.pause(DEBOUNCE + 0.5)
        assert pilot.app.query_one("#targets", DataTable).row_count == 0
        assert (
            "nothing is switched on"
            in pilot.app.query_one("#status", Static).content.plain
        )

    run(app, scenario)


def test_app_reports_a_broken_query(workspace):
    config, _ = workspace
    chosen = select_locations(load_config(config), ["source"])
    app = SearchTool(chosen=chosen, weights={})

    async def scenario(pilot):
        pilot.app.query_one("#query", Input).value = '"unclosed'
        await pilot.press("enter")
        await pilot.app.workers.wait_for_complete()
        await pilot.pause()
        assert pilot.app.query_one("#targets", DataTable).row_count == 0
        assert pilot.app.query_one("#status", Static).content.plain

    run(app, scenario)


def test_enter_on_a_target_opens_the_editor_at_its_span(workspace, monkeypatch):
    require_program("rg")
    config, directory = workspace
    monkeypatch.setenv("EDITOR", "vim")
    monkeypatch.delenv("VISUAL", raising=False)
    opened = []
    monkeypatch.setattr(
        SearchTool, "edit", lambda self, command: opened.append(command)
    )
    chosen = select_locations(load_config(config), ["source"])
    app = SearchTool(chosen=chosen, weights={}, query="saturation")

    async def scenario(pilot):
        await pilot.app.workers.wait_for_complete()
        await pilot.pause()
        pilot.app.query_one("#targets", DataTable).focus()
        await pilot.press("enter")
        await pilot.pause()
        assert opened == [["vim", "+1", str(directory / "reading.py")]]

    run(app, scenario)


def test_enter_says_so_where_no_editor_is_set(workspace, monkeypatch):
    require_program("rg")
    config, _ = workspace
    monkeypatch.delenv("EDITOR", raising=False)
    monkeypatch.delenv("VISUAL", raising=False)
    chosen = select_locations(load_config(config), ["source"])
    app = SearchTool(chosen=chosen, weights={}, query="saturation")

    async def scenario(pilot):
        await pilot.app.workers.wait_for_complete()
        await pilot.pause()
        pilot.app.query_one("#targets", DataTable).focus()
        await pilot.press("enter")
        await pilot.pause()
        written = pilot.app.query_one("#status", Static).content.plain
        assert "neither VISUAL nor EDITOR is set" in written

    run(app, scenario)


def test_typing_waits_for_the_debounce(workspace):
    require_program("rg")
    config, _ = workspace
    chosen = select_locations(load_config(config), ["source"])
    app = SearchTool(chosen=chosen, weights={})

    async def scenario(pilot):
        pilot.app.query_one("#query", Input).value = "saturation"
        await pilot.pause()
        assert pilot.app.query_one("#targets", DataTable).row_count == 0
        assert pilot.app.pending is not None
        await pilot.pause(DEBOUNCE + 0.5)
        await pilot.app.workers.wait_for_complete()
        await pilot.pause()
        assert pilot.app.query_one("#targets", DataTable).row_count == 1

    run(app, scenario)


def test_enter_in_the_query_box_searches_without_waiting(workspace):
    require_program("rg")
    config, _ = workspace
    chosen = select_locations(load_config(config), ["source"])
    app = SearchTool(chosen=chosen, weights={})

    async def scenario(pilot):
        pilot.app.query_one("#query", Input).value = "saturation"
        await pilot.press("enter")
        await pilot.app.workers.wait_for_complete()
        await pilot.pause()
        assert pilot.app.pending is None
        assert pilot.app.query_one("#targets", DataTable).row_count == 1

    run(app, scenario)


def test_the_query_the_command_line_carried_searches_once(workspace):
    require_program("rg")
    config, _ = workspace
    chosen = select_locations(load_config(config), ["source"])
    app = SearchTool(chosen=chosen, weights={}, query="saturation")

    async def scenario(pilot):
        await pilot.app.workers.wait_for_complete()
        await pilot.pause(DEBOUNCE + 0.5)
        assert pilot.app.pending is None
        assert pilot.app.query_one("#targets", DataTable).row_count == 1

    run(app, scenario)


def test_typing_an_edit_back_to_what_ran_drops_the_pending_search(workspace):
    require_program("rg")
    config, _ = workspace
    chosen = select_locations(load_config(config), ["source"])
    app = SearchTool(chosen=chosen, weights={}, query="saturation")

    async def scenario(pilot):
        await pilot.app.workers.wait_for_complete()
        await pilot.pause()
        box = pilot.app.query_one("#query", Input)
        box.value = "saturatio"
        await pilot.pause()
        assert pilot.app.pending is not None
        box.value = "saturation"
        await pilot.pause()
        assert pilot.app.pending is None

    run(app, scenario)
