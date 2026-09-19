"""Regex search over the shell history file."""

from pathlib import Path

from search_tool.query import Lowered, Query, no_paths, to_regex
from search_tool.tools.ripgrep import rg_case
from search_tool.tools.tools_base import Command, Hit, Tool

# Strips the zsh extended-history prefix, then keeps the first run of each
# command, so a command repeated across the file reports once.
_HISTORY_TIDY = '{sub(/^: [0-9]+:[0-9]+;/, "")} !seen[$0]++'


def _lower(query: Query) -> Lowered:
    """Return the query as a regex. The history is one file, so it takes no glob."""
    return Lowered(to_regex(query), no_paths(query))


def _history(
    lowered: Lowered, directory: Path | None, ignore: tuple[str, ...], case: bool
) -> Command:
    return [
        [
            "rg",
            "--color",
            "never",
            "--no-filename",
            "--no-line-number",
            *rg_case(case),
            "--",
            lowered.query,
            str(directory),
        ],
        ["awk", _HISTORY_TIDY],
    ]


def parse_history(stdout: str) -> list[Hit]:
    """Return one hit per shell command listed.

    The command text is the key, so the same command run many times merges into
    one candidate.
    """
    return [
        Hit(key=line, kind="command", line=None, end_line=None, text=line)
        for line in stdout.splitlines()
        if line.strip()
    ]


HIST = Tool("hist", "regex", "command", True, _lower, _history, _history, parse_history)
