"""The search tools the aggregator wraps, gathered into one registry."""

from search_tool.tools.ast_grep import AST
from search_tool.tools.ck import CK
from search_tool.tools.fzf import FZF
from search_tool.tools.history import HIST
from search_tool.tools.manual import MAN
from search_tool.tools.ripgrep import RG, RG_FILES
from search_tool.tools.rovo import ROVO
from search_tool.tools.semantic import M2V
from search_tool.tools.tools_base import Tool

TOOLS: dict[str, Tool] = {
    tool.name: tool for tool in (RG, RG_FILES, FZF, CK, M2V, AST, HIST, MAN, ROVO)
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
