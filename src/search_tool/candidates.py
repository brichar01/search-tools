"""Merge the hits of every search into one deduplicated set of candidates."""

from dataclasses import dataclass, field

from search_tool.parsers import Hit
from search_tool.runner import Result
from search_tool.tools import TOOLS


@dataclass(frozen=True)
class Source:
    """One tool that reported a candidate.

    Attributes:
        location: Name of the location the tool searched.
        tool: Canonical tool name.
        directory: Directory searched, or `None` for a system or remote source.
        rank: Position in the output of that search, counting from one.
        score: Relevance the tool reported, where it reports one.
    """

    location: str
    tool: str
    directory: str | None
    rank: int
    score: float | None


@dataclass
class Candidate:
    """A file span, manual page or remote page, and every tool that found it.

    Attributes:
        key: Absolute path or URL the candidate lives at.
        kind: `file`, `manual` or `remote`.
        line: First line of the merged span, or `None` for a whole file or page.
        end_line: Last line of the merged span.
        text: Longest text any source reported, for a later ranking stage.
        sources: Every tool that reported the candidate, in the order they ran.
    """

    key: str
    kind: str
    line: int | None
    end_line: int | None
    text: str
    sources: list[Source] = field(default_factory=list)

    def absorb(self, hit: Hit, source: Source) -> None:
        """Merge an overlapping hit into this candidate."""
        self.end_line = max(self.end_line, hit.end_line or hit.line)
        if len(hit.text) > len(self.text):
            self.text = hit.text
        self.sources.append(source)


def _group(results: list[Result]) -> dict[str, list[tuple[Hit, Source]]]:
    """Return every hit of every result, keyed by what it identifies."""
    grouped: dict[str, list[tuple[Hit, Source]]] = {}
    for result in results:
        search = result.search
        hits = TOOLS[search.tool].parse(result.stdout)
        for rank, hit in enumerate(hits, start=1):
            source = Source(
                location=search.location,
                tool=search.tool,
                directory=None if search.directory is None else str(search.directory),
                rank=rank,
                score=hit.score,
            )
            grouped.setdefault(hit.key, []).append((hit, source))
    return grouped


def build_candidates(results: list[Result]) -> list[Candidate]:
    """Return one candidate per distinct result, ordered by key then line.

    Hits that share a key merge where their line spans overlap, so the line one
    tool matched and the chunk another returned around it become one candidate.
    A hit that names a whole file or page merges with every other hit that names
    no span, and keeps its own candidate.
    """
    candidates = []
    for key, entries in sorted(_group(results).items()):
        whole: Candidate | None = None
        spanned: list[Candidate] = []
        for hit, source in sorted(
            entries, key=lambda entry: (entry[0].line is not None, entry[0].line or 0)
        ):
            if hit.line is None:
                if whole is None:
                    whole = Candidate(key, hit.kind, None, None, hit.text, [source])
                else:
                    whole.sources.append(source)
                continue
            end_line = hit.end_line or hit.line
            if spanned and hit.line <= spanned[-1].end_line:
                spanned[-1].absorb(hit, source)
            else:
                spanned.append(
                    Candidate(key, hit.kind, hit.line, end_line, hit.text, [source])
                )
        if whole is not None:
            candidates.append(whole)
        candidates.extend(spanned)
    return candidates
