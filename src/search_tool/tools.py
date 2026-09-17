"""The search tools the aggregator wraps, and the commands they run."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from search_tool.parsers import (
    Hit,
    parse_ast_grep,
    parse_ck,
    parse_man,
    parse_paths,
    parse_ripgrep,
    parse_rovo,
)

Command = list[list[str]]
"""A pipeline of argument lists, each stage reading the stdout of the one before."""


@dataclass(frozen=True)
class Tool:
    """One wrapped search program.

    Attributes:
        name: Canonical name, as a config file writes it.
        kind: Search kind, used by the `--kind` filter.
        needs_directory: Whether the tool searches a directory on disk.
        build: Takes the query and the directory and returns the command pipeline.
        build_json: The same for the machine-readable mode of the tool. Tools
            that only ever list paths use the one command for both.
        parse: Turns the standard output of `build_json` into hits.
    """

    name: str
    kind: str
    needs_directory: bool
    build: Callable[[str, Path | None], Command]
    build_json: Callable[[str, Path | None], Command]
    parse: Callable[[str], list[Hit]]


def _ripgrep(query: str, directory: Path | None) -> Command:
    return [
        [
            "rg",
            "--color",
            "never",
            "--line-number",
            "--with-filename",
            "--",
            query,
            str(directory),
        ]
    ]


def _ripgrep_files(query: str, directory: Path | None) -> Command:
    return [
        ["rg", "--files", str(directory)],
        ["rg", "--color", "never", "--", query],
    ]


def _ripgrep_json(query: str, directory: Path | None) -> Command:
    return [["rg", "--json", "--", query, str(directory)]]


def _ck_semantic(query: str, directory: Path | None) -> Command:
    return [["ck", "--sem", query, str(directory)]]


def _ck_semantic_json(query: str, directory: Path | None) -> Command:
    return [["ck", "--sem", "--jsonl", query, str(directory)]]


def _ast_grep(query: str, directory: Path | None) -> Command:
    return [["ast-grep", "run", "--color", "never", "--pattern", query, str(directory)]]


def _ast_grep_json(query: str, directory: Path | None) -> Command:
    return [["ast-grep", "run", "--json=compact", "--pattern", query, str(directory)]]


def _manual(query: str, directory: Path | None) -> Command:
    return [["man", "-K", "-w", "--regex", query]]


def _rovo(query: str, directory: Path | None) -> Command:
    return [["twg", "rovo", "search", query, "--app", "confluence"]]


def _rovo_json(query: str, directory: Path | None) -> Command:
    return [[*_rovo(query, directory)[0], "--output", "json"]]


TOOLS = {
    tool.name: tool
    for tool in (
        Tool("rg", "regex", True, _ripgrep, _ripgrep_json, parse_ripgrep),
        Tool("rg-files", "files", True, _ripgrep_files, _ripgrep_files, parse_paths),
        Tool("ck", "semantic", True, _ck_semantic, _ck_semantic_json, parse_ck),
        Tool("ast", "ast", True, _ast_grep, _ast_grep_json, parse_ast_grep),
        Tool("man", "regex", False, _manual, _manual, parse_man),
        Tool("rovo", "remote", False, _rovo, _rovo_json, parse_rovo),
    )
}

ALIASES = {
    "ripgrep": "rg",
    "ripgrep-files": "rg-files",
    "ast-grep": "ast",
    "sg": "ast",
    "confluence": "rovo",
}

KINDS = sorted({tool.kind for tool in TOOLS.values()})


def resolve_tool(name: str) -> Tool:
    """Return the tool a config file names.

    Args:
        name: Canonical name or alias.

    Returns:
        The matching tool.

    Raises:
        KeyError: The name is neither a tool nor an alias.
    """
    canonical = ALIASES.get(name, name)
    if canonical not in TOOLS:
        known = ", ".join(sorted(TOOLS) + sorted(ALIASES))
        raise KeyError(f"Unknown tool {name!r}. Known tools: {known}")
    return TOOLS[canonical]
