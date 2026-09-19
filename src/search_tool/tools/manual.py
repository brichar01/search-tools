"""Keyword search over the installed manual pages."""

from pathlib import Path

from search_tool.query import Lowered, Query, no_paths, to_regex
from search_tool.tools.tools_base import Command, Hit, Tool


def _lower(query: Query) -> Lowered:
    """Return the query as a regex. `man` searches the installed pages, not a tree."""
    return Lowered(to_regex(query), no_paths(query))


def _manual(
    lowered: Lowered, directory: Path | None, ignore: tuple[str, ...], case: bool
) -> Command:
    return [["man", "-K", "-w", "--regex", "-I" if case else "-i", lowered.query]]


def parse_man(stdout: str) -> list[Hit]:
    """Return one hit per manual page path, named the way `man` is called."""
    hits = []
    for line in stdout.splitlines():
        path = line.strip()
        if not path:
            continue
        name = Path(path).name
        name = name.removesuffix(".gz")
        stem, _, section = name.rpartition(".")
        hits.append(
            Hit(
                key=path,
                kind="manual",
                line=None,
                end_line=None,
                text=f"{stem}({section})" if stem else name,
            )
        )
    return hits


MAN = Tool("man", "regex", "manual", False, _lower, _manual, _manual, parse_man)
