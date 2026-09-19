"""The search tools the aggregator wraps, gathered into one registry."""

from search_tool.tools.ast_grep import AST
from search_tool.tools.ck import CK, CK_LEX
from search_tool.tools.fzf import FZF
from search_tool.tools.history import HIST
from search_tool.tools.manual import MAN
from search_tool.tools.ripgrep import RG, RG_FILES
from search_tool.tools.rovo import ROVO
from search_tool.tools.tools_base import Tool

TOOLS: dict[str, Tool] = {
    tool.name: tool for tool in (RG, RG_FILES, FZF, CK, CK_LEX, AST, HIST, MAN, ROVO)
}

ALIASES = {
    "ripgrep": "rg",
    "ripgrep-files": "rg-files",
    "fuzzy": "fzf",
    "ast-grep": "ast",
    "sg": "ast",
    "confluence": "rovo",
}

KINDS = sorted({tool.kind for tool in TOOLS.values()})

KIND_FLAGS = [*KINDS, *(f"!{kind}" for kind in KINDS)]
"""Every `--kind` value, each kind on its own and negated."""

ASKED_FOR = frozenset({"ast"})
"""Kinds that run only where they are named. An ast-grep pattern is its own language."""


def resolve_kinds(kinds: list[str]) -> set[str]:
    """Return the search kinds to run.

    Args:
        kinds: Kind names as `--kind` takes them, each either a kind or a kind
            prefixed with `!` to drop it.

    Returns:
        The named kinds less the negated ones. Naming no kind to keep starts
        from every kind but the ones in `ASKED_FOR`, so `!remote` alone runs
        everything else and `ast` runs only where it is named.
    """
    dropped = {kind[1:] for kind in kinds if kind.startswith("!")}
    kept = {kind for kind in kinds if not kind.startswith("!")}
    return (kept or set(KINDS) - ASKED_FOR) - dropped


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
