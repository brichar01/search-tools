"""The search tools the aggregator wraps, and the commands they run."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from search_tool.parsers import (
    Hit,
    parse_ast_grep,
    parse_ck,
    parse_history,
    parse_man,
    parse_paths,
    parse_ripgrep,
    parse_rovo,
    parse_semantic,
)

Command = list[list[str]]
"""A pipeline of argument lists, each stage reading the stdout of the one before."""

Build = Callable[[str, Path | None, tuple[str, ...]], Command]
"""Takes the query, the directory and the ignored directory names."""


@dataclass(frozen=True)
class Tool:
    """One wrapped search program.

    Attributes:
        name: Canonical name, as a config file writes it.
        kind: Search kind, used by the `--kind` filter.
        needs_directory: Whether the tool searches a directory on disk.
        build: Takes the query, the directory and the directory names to ignore,
            and returns the command pipeline.
        build_json: The same for the machine-readable mode of the tool. Tools
            that only ever list paths use the one command for both.
        parse: Turns the standard output of `build_json` into hits.
    """

    name: str
    kind: str
    needs_directory: bool
    build: Build
    build_json: Build
    parse: Callable[[str], list[Hit]]


def _rg_globs(ignore: tuple[str, ...]) -> list[str]:
    """Return the ripgrep globs that prune each ignored directory name."""
    return [f"--glob=!{name}/" for name in ignore]


def _ck_excludes(ignore: tuple[str, ...]) -> list[str]:
    """Return the ck flags that prune each ignored directory name."""
    return [argument for name in ignore for argument in ("--exclude", name)]


def _ast_globs(ignore: tuple[str, ...]) -> list[str]:
    """Return the ast-grep globs that prune each ignored directory name."""
    return [f"--globs=!{name}/" for name in ignore]


def _skips(ignore: tuple[str, ...]) -> list[str]:
    """Return the search-tool-semantic flags that prune each ignored name."""
    return [argument for name in ignore for argument in ("--skip", name)]


def _ripgrep(query: str, directory: Path | None, ignore: tuple[str, ...]) -> Command:
    return [
        [
            "rg",
            "--color",
            "never",
            "--line-number",
            "--with-filename",
            *_rg_globs(ignore),
            "--",
            query,
            str(directory),
        ]
    ]


def _ripgrep_files(
    query: str, directory: Path | None, ignore: tuple[str, ...]
) -> Command:
    return [
        ["rg", "--files", *_rg_globs(ignore), str(directory)],
        ["rg", "--color", "never", "--", query],
    ]


def _fzf(query: str, directory: Path | None, ignore: tuple[str, ...]) -> Command:
    # The fzf walker only runs on a TTY stdin and reads no .gitignore,
    # so ripgrep lists the paths and prunes them.
    return [
        ["rg", "--files", *_rg_globs(ignore), str(directory)],
        ["fzf", "--filter", query],
    ]


def _ripgrep_json(
    query: str, directory: Path | None, ignore: tuple[str, ...]
) -> Command:
    return [["rg", "--json", *_rg_globs(ignore), "--", query, str(directory)]]


def _ck_semantic(
    query: str, directory: Path | None, ignore: tuple[str, ...]
) -> Command:
    return [["ck", "--sem", *_ck_excludes(ignore), query, str(directory)]]


def _ck_semantic_json(
    query: str, directory: Path | None, ignore: tuple[str, ...]
) -> Command:
    return [["ck", "--sem", "--jsonl", *_ck_excludes(ignore), query, str(directory)]]


def _semantic(query: str, directory: Path | None, ignore: tuple[str, ...]) -> Command:
    return [["search-tool-semantic", *_skips(ignore), query, str(directory)]]


def _semantic_json(
    query: str, directory: Path | None, ignore: tuple[str, ...]
) -> Command:
    return [["search-tool-semantic", "--json", *_skips(ignore), query, str(directory)]]


def _ast_grep(query: str, directory: Path | None, ignore: tuple[str, ...]) -> Command:
    return [
        [
            "ast-grep",
            "run",
            "--color",
            "never",
            *_ast_globs(ignore),
            "--pattern",
            query,
            str(directory),
        ]
    ]


def _ast_grep_json(
    query: str, directory: Path | None, ignore: tuple[str, ...]
) -> Command:
    return [
        [
            "ast-grep",
            "run",
            "--json=compact",
            *_ast_globs(ignore),
            "--pattern",
            query,
            str(directory),
        ]
    ]


# Strips the zsh extended-history prefix, then keeps the first run of each
# command, so a command repeated across the file reports once.
_HISTORY_TIDY = '{sub(/^: [0-9]+:[0-9]+;/, "")} !seen[$0]++'


def _history(query: str, directory: Path | None, ignore: tuple[str, ...]) -> Command:
    return [
        [
            "rg",
            "--color",
            "never",
            "--no-filename",
            "--no-line-number",
            "--",
            query,
            str(directory),
        ],
        ["awk", _HISTORY_TIDY],
    ]


def _manual(query: str, directory: Path | None, ignore: tuple[str, ...]) -> Command:
    return [["man", "-K", "-w", "--regex", query]]


def _rovo(query: str, directory: Path | None, ignore: tuple[str, ...]) -> Command:
    return [["twg", "rovo", "search", query, "--app", "confluence"]]


def _rovo_json(query: str, directory: Path | None, ignore: tuple[str, ...]) -> Command:
    return [[*_rovo(query, directory, ignore)[0], "--output", "json"]]


TOOLS = {
    tool.name: tool
    for tool in (
        Tool("rg", "regex", True, _ripgrep, _ripgrep_json, parse_ripgrep),
        Tool("rg-files", "files", True, _ripgrep_files, _ripgrep_files, parse_paths),
        Tool("fzf", "files", True, _fzf, _fzf, parse_paths),
        Tool("ck", "semantic", True, _ck_semantic, _ck_semantic_json, parse_ck),
        Tool("m2v", "semantic", True, _semantic, _semantic_json, parse_semantic),
        Tool("ast", "ast", True, _ast_grep, _ast_grep_json, parse_ast_grep),
        Tool("hist", "regex", True, _history, _history, parse_history),
        Tool("man", "regex", False, _manual, _manual, parse_man),
        Tool("rovo", "remote", False, _rovo, _rovo_json, parse_rovo),
    )
}

ALIASES = {
    "ripgrep": "rg",
    "ripgrep-files": "rg-files",
    "model2vec": "m2v",
    "fuzzy": "fzf",
    "ast-grep": "ast",
    "sg": "ast",
    "confluence": "rovo",
}

KINDS = sorted({tool.kind for tool in TOOLS.values()})

KIND_FLAGS = [*KINDS, *(f"!{kind}" for kind in KINDS)]
"""Every `--kind` value, each kind on its own and negated."""


def resolve_kinds(kinds: list[str]) -> set[str]:
    """Return the search kinds to run.

    Args:
        kinds: Kind names as `--kind` takes them, each either a kind or a kind
            prefixed with `!` to drop it.

    Returns:
        The named kinds less the negated ones. Naming no kind to keep starts
        from every kind, so `!remote` alone runs everything else.
    """
    dropped = {kind[1:] for kind in kinds if kind.startswith("!")}
    kept = {kind for kind in kinds if not kind.startswith("!")}
    return (kept or set(KINDS)) - dropped


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
