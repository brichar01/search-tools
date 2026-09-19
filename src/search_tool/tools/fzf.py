"""Fuzzy path search with fzf."""

from dataclasses import replace
from math import log10
from pathlib import Path

from search_tool.query import Lowered, Query, to_fzf
from search_tool.tools.ripgrep import parse_paths, rg_globs, rg_include
from search_tool.tools.tools_base import Command, Hit, Tool

LIMIT = 20
"""Paths one fuzzy search returns. fzf matches almost every path of a tree."""

FLOOR = 9
"""Scaled edits at which a path stops counting, where log10(10 - 9) is zero.

A term nothing of the path matches sits here, whatever the length of the term.
"""


def _lower(query: Query) -> Lowered:
    return Lowered(to_fzf(query), query.paths)


def _fzf(
    lowered: Lowered, directory: Path | None, ignore: tuple[str, ...], case: bool
) -> Command:
    # The fzf walker only runs on a TTY stdin and reads no .gitignore,
    # so ripgrep lists the paths and prunes them.
    # fzf matches smart case unless -i or +i says otherwise.
    return [
        [
            "rg",
            "--files",
            *rg_globs(ignore),
            *rg_include(lowered.globs),
            str(directory),
        ],
        ["fzf", "+i" if case else "-i", "--filter", lowered.query],
        # fzf sorts its matches, so the cap keeps the best of them. awk reads
        # the whole list, where head would close the pipe and fzf would die
        # on SIGPIPE with the status the runner reads as a failure.
        ["awk", f"NR<={LIMIT}"],
    ]


def _terms(query: str) -> list[str]:
    """Return the words of a lowered fzf query that a path has to match.

    A negated term says what a path does not hold, so how far a path sits from
    it says nothing about the match.
    """
    terms = []
    for word in query.split():
        if word == "|" or word.startswith("!"):
            continue
        term = word.lstrip("'^").rstrip("$").casefold()
        if term:
            terms.append(term)
    return terms


def _distance(term: str, path: str) -> int:
    """Return the fewest edits from a term to any window of a path its length.

    fzf matches a subsequence anywhere in a path, so a term is measured against
    the part of the path it matched rather than against the whole of it.
    """
    # nltk costs half a second to import, which a run without fzf never pays.
    from nltk.metrics.distance import edit_distance

    path = path.casefold()
    width = len(term)
    if len(path) <= width:
        return edit_distance(term, path)
    return min(
        edit_distance(term, path[start : start + width])
        for start in range(len(path) - width + 1)
    )


def _score(edits: int, width: int) -> float:
    """Return what a path that many edits from a term that long is worth.

    The edits are scaled by the length of the term, because the furthest a term
    can sit from a window of a path is its own length, and an absolute count
    leaves a term of three letters worth 0.85 at its very worst. The curve is
    flat over a typo and steep past it: one letter of six is worth 0.93 of a
    whole vote, half the term is worth 0.74, and the whole of it is worth
    nothing.
    """
    scaled = FLOOR * edits / width
    if scaled >= FLOOR:
        return 0.0
    return log10(10 - scaled)


def rank_paths(hits: list[Hit], query: str) -> list[Hit]:
    """Return the paths fzf listed, each scored by how far it sits from a term.

    fzf reports no score and matches almost every path of a tree, so its hits
    would each carry the whole vote a match carries. Scoring a path by the
    edits between it and the nearest query term keeps a typo near that vote and
    drops a path a few edits out to nothing. A path is taken at the term it
    matched best, since a term scores against its own length.
    """
    terms = _terms(query)
    if not terms:
        return hits
    return [
        replace(
            hit,
            score=max(_score(_distance(term, hit.key), len(term)) for term in terms),
        )
        for hit in hits
    ]


FZF = Tool(
    "fzf", "files", "file", True, _lower, _fzf, _fzf, parse_paths, rank=rank_paths
)
