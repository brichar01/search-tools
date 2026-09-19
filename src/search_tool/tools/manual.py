"""Keyword search over the installed manual pages."""

from pathlib import Path

from search_tool.tools.tools_base import Command, Hit, Tool


def _manual(
    query: str, directory: Path | None, ignore: tuple[str, ...], case_sensitive: bool
) -> Command:
    return [["man", "-K", "-w", "--regex", "-I" if case_sensitive else "-i", query]]


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


MAN = Tool("man", "regex", False, _manual, _manual, parse_man)
