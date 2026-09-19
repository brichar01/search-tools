from conftest import require_program
from search_tool import help_index
from search_tool.help_index import (
    MAX_BYTES,
    clean,
    current,
    harvest,
    packaged_commands,
    read_commands,
)


def test_read_commands_keeps_one_name_per_line_in_order():
    document = "# a list\nls\n\nrg  # the fast one\nls\nnot a name\n../escape\n"
    assert read_commands(document) == ["ls", "rg"]


def test_packaged_commands_lists_the_common_ones():
    names = read_commands(packaged_commands())
    assert {"git", "man", "rg", "nvim"} <= set(names)


def test_clean_strips_colour_and_the_overstrike_man_writes():
    assert clean("\x1b[1mNAME\x1b[0m") == "NAME"
    assert clean("N\x08NA\x08AM\x08ME\x08E") == "NAME"
    assert clean("_\x08N_\x08A") == "NA"


def test_clean_truncates_a_runaway_page():
    cleaned = clean("x" * (MAX_BYTES + 10))
    assert cleaned.endswith("\n[truncated]")
    assert len(cleaned) == MAX_BYTES + len("\n[truncated]")


def test_current_compares_the_page_against_what_it_came_from(tmp_path):
    page = tmp_path / "ls_help.txt"
    source = tmp_path / "ls"
    source.write_text("")
    assert not current(page, source)
    page.write_text("")
    assert current(page, source)
    source.touch()
    assert not current(page, source)
    assert current(page, tmp_path / "gone")


def test_harvest_skips_a_command_that_is_not_installed(tmp_path):
    result = harvest("no-such-command", tmp_path, 1.0, False, False)
    assert not result.installed
    assert list(tmp_path.iterdir()) == []


def test_harvest_writes_the_help_page_with_its_header(tmp_path):
    require_program("ls")
    result = harvest("ls", tmp_path, 10.0, False, False)
    assert "help" in result.written
    page = (tmp_path / "ls_help.txt").read_text()
    assert page.startswith("# ls --help\n\n")
    assert "Usage" in page


def test_harvest_writes_the_manual_page_beside_the_help_page(tmp_path):
    require_program("man")
    result = harvest("man", tmp_path, 30.0, False, False)
    assert "man" in result.written
    page = (tmp_path / "man_man.txt").read_text()
    assert page.startswith("# man man\n\n")
    assert "\x08" not in page


def test_harvest_leaves_a_current_page_alone(tmp_path):
    require_program("ls")
    harvest("ls", tmp_path, 10.0, False, False)
    written = (tmp_path / "ls_help.txt").read_text()
    (tmp_path / "ls_help.txt").write_text("stale")
    assert "help" in harvest("ls", tmp_path, 10.0, False, False).current
    assert (tmp_path / "ls_help.txt").read_text() == "stale"
    assert "help" in harvest("ls", tmp_path, 10.0, True, False).written
    assert (tmp_path / "ls_help.txt").read_text() == written


def test_harvest_writes_nothing_on_a_dry_run(tmp_path):
    require_program("ls")
    result = harvest("ls", tmp_path, 10.0, False, True)
    assert "help" in result.written
    assert list(tmp_path.iterdir()) == []


def test_a_halting_command_is_never_given_the_short_flag(monkeypatch):
    tried = []

    def record(argv, timeout):
        tried.append(argv)
        return ""

    monkeypatch.setattr(help_index, "capture", record)
    assert help_index.help_text("shutdown", 1.0) is None
    assert tried == [["shutdown", "--help"]]
    tried.clear()
    assert help_index.help_text("ls", 1.0) is None
    assert tried == [["ls", "--help"], ["ls", "-h"]]


def test_a_rejected_flag_falls_back_and_keeps_the_longest_usage(monkeypatch):
    answers = {"--help": "grim: invalid option -- '-'", "-h": "usage: grim [-h]"}
    monkeypatch.setattr(help_index, "capture", lambda argv, timeout: answers[argv[1]])
    assert help_index.help_text("grim", 1.0) == ("-h", "usage: grim [-h]")

    answers["-h"] = "lua: invalid option '-h'"
    answers["--help"] = "lua: unrecognized option '--help'\nusage: lua [options]"
    flag, text = help_index.help_text("lua", 1.0)
    assert flag == "--help"
    assert "usage: lua" in text
