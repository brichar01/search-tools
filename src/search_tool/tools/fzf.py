"""Fuzzy path search with fzf."""

from pathlib import Path

from search_tool.tools.ripgrep import parse_paths, rg_globs
from search_tool.tools.tools_base import Command, Tool


def _fzf(
    query: str, directory: Path | None, ignore: tuple[str, ...], case_sensitive: bool
) -> Command:
    # The _fzf walker only runs on a TTY stdin and reads no .gitignore,
    # so ripgrep lists the paths and prunes them.
    # fzf matches smart case unless -i or +i says otherwise.
    return [
        ["rg", "--files", *rg_globs(ignore), str(directory)],
        ["fzf", "+i" if case_sensitive else "-i", "--filter", query],
    ]


FZF = Tool("fzf", "files", True, _fzf, _fzf, parse_paths)
