"""Score each file, command or page by the searches that agree on it.

Summing the tools that agree favours whatever lives where the most tools run: a
file nine searches cover collects votes a manual page one search covers can
never collect. Each sum is taken over the searches that could have returned the
target instead, so every target is scored out of its own reach.

The unit scored is the key, not the span. Spans agree only where they overlap,
so two tools that both found a file corroborate each other only where their
chunk boundaries happen to meet, and a tool that names whole files never
corroborates anything. A key is the one identity every tool reports.
"""

from dataclasses import dataclass, field
from pathlib import Path

from search_tool.candidates import Candidate, Source
from search_tool.runner import Result
from search_tool.tools import TOOLS

PRIOR = 1.0
"""Weight of one notional search that found nothing.

Dividing by the reach alone lets a target one search of one found outscore a
target three searches of four found.
"""

Reach = tuple[str, str, str | None]
"""Location, tool and directory of one search."""


@dataclass
class Target:
    """One file, command, manual page or remote page, and what it scored.

    Attributes:
        key: Absolute path, command text or URL the searches agree on.
        kind: `file`, `command`, `manual` or `remote`.
        votes: Weighted vote of every search that found it, one vote each.
        reach: Summed weight of the searches that could have returned it.
        relevance: Votes over the reach and the prior.
        candidates: The spans the searches reported, the strongest first.
    """

    key: str
    kind: str
    votes: float = 0.0
    reach: float = 0.0
    relevance: float = 0.0
    candidates: list[Candidate] = field(default_factory=list)


def _source_key(source: Source) -> Reach:
    """Return the search a source came from."""
    return (source.location, source.tool, source.directory)


def _search_key(result: Result) -> Reach:
    """Return the search a result came from."""
    search = result.search
    return (
        search.location,
        search.tool,
        None if search.directory is None else str(search.directory),
    )


def _weight(tool: str, weights: dict[str, float]) -> float:
    """Return what one vote of a tool is worth, as the config file sets it."""
    return weights.get(tool, TOOLS[tool].weight)


def _spans(candidates: list[Candidate]) -> dict[Reach, tuple[float, float]]:
    """Return the lowest and highest score of each search that scores its hits.

    A synthesised score is left out. It is already written on the scale every
    tool shares, so spreading it over the run would hand a search that found
    nothing but poor matches the same top vote as one that found a perfect one.
    """
    scores: dict[Reach, list[float]] = {}
    for candidate in candidates:
        for source in candidate.sources:
            if source.score is not None and TOOLS[source.tool].rank is None:
                scores.setdefault(_source_key(source), []).append(source.score)
    return {key: (min(found), max(found)) for key, found in scores.items()}


def _vote(source: Source, spans: dict[Reach, tuple[float, float]]) -> float:
    """Return what one hit says, on the scale every tool shares.

    A tool that reports no score reports a match and nothing else, so its hit
    says one. Its ordering stands in for nothing: ripgrep returns files in the
    order it walked them, so a rank read off that output carries no relevance. A
    tool that scores its hits is spread across the same range by the run of
    scores it returned, because two tools that both score do not share a scale.
    A score the run synthesised is taken as it stands.
    """
    if source.score is None:
        return 1.0
    span = spans.get(_source_key(source))
    if span is None:
        return source.score
    low, high = span
    if high == low:
        return 1.0
    return (source.score - low) / (high - low)


def _reaches(result: Result, target: Target) -> bool:
    """Whether one search could have returned one target.

    A skipped search and a failed search reach nothing, so their silence votes
    against nothing. A search that ran and found nothing reaches what it covered.
    """
    search = result.search
    if search.skipped is not None or result.exit_code > 1:
        return False
    if TOOLS[search.tool].finds != target.kind:
        return False
    if target.kind != "file" or search.directory is None:
        return True
    return Path(target.key).is_relative_to(search.directory)


def _best(
    target: Target, spans: dict[Reach, tuple[float, float]]
) -> dict[Reach, float]:
    """Return the strongest hit each search reported against one target.

    One search votes once however many hits it returned, because ripgrep reports
    every matching line of a file and a semantic search reports the few chunks
    it ranked. Summing the hits would score a file by how loudly one tool
    matched it rather than by how many tools agreed, so each search is taken at
    its best hit.
    """
    best: dict[Reach, float] = {}
    for candidate in target.candidates:
        for source in candidate.sources:
            key = _source_key(source)
            best[key] = max(best.get(key, 0.0), _vote(source, spans))
    return best


def _reach(target: Target, results: list[Result], weights: dict[str, float]) -> float:
    """Return the summed weight of the searches that could return a target.

    A search that reported the target counts whatever the reach test makes of
    it, so a target is never scored out of less than the agreement it drew.
    """
    reached = {
        _source_key(source)
        for candidate in target.candidates
        for source in candidate.sources
    }
    for result in results:
        if _reaches(result, target):
            reached.add(_search_key(result))
    return sum(_weight(tool, weights) for _, tool, _ in reached)


def score_targets(
    candidates: list[Candidate],
    results: list[Result],
    prior: float = PRIOR,
    weights: dict[str, float] | None = None,
) -> list[Target]:
    """Group the candidates by key, score each key and return them in rank order.

    Args:
        candidates: The merged candidates, in key then line order.
        results: Every search of the run, the skipped and failed ones included,
            which reach nothing.
        prior: Weight of a notional search that found nothing. Zero scores the
            agreement as a bare rate, where one source of one reaches the top.
        weights: What one vote of a tool is worth, overriding the weight the
            tool declares. A weight counts into the reach as well as the vote,
            so downweighting a tool does not cap the score of a location that
            uses it.

    Returns:
        One target per key, the highest score first and then by key. Each
        holds its spans, the strongest first and a span before a whole file, so
        a caller can offer the line or chunk behind the score.
    """
    weights = weights or {}
    spans = _spans(candidates)
    targets: dict[str, Target] = {}
    for candidate in candidates:
        target = targets.setdefault(
            candidate.key, Target(candidate.key, candidate.kind)
        )
        target.candidates.append(candidate)
    for target in targets.values():
        best = _best(target, spans)
        target.votes = sum(
            vote * _weight(tool, weights) for (_, tool, _), vote in best.items()
        )
        target.reach = _reach(target, results, weights)
        target.relevance = target.votes / (target.reach + prior)
        for candidate in target.candidates:
            candidate.votes = sum(
                _vote(source, spans) * _weight(source.tool, weights)
                for source in candidate.sources
            )
        target.candidates.sort(
            key=lambda span: (-span.votes, span.line is None, span.line or 0)
        )
    return sorted(targets.values(), key=lambda target: (-target.relevance, target.key))
