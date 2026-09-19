r"""One query language, parsed once and lowered onto the syntax of each tool.

A query is an implicit AND of clauses. A clause is one atom, or several atoms
joined by `OR`, and `-` in front of it drops what it matches. An atom is a bare
word, a `"quoted phrase"`, a `/regular expression/`, or a `path:` glob naming
the files to search. Whitespace separates atoms everywhere but inside quotes,
so a regular expression writes a space as `\s`.

Lowering a query raises `Unsupported` where the tool has no way to write that
part of it, and the search is skipped rather than widened.
"""

import re
from dataclasses import dataclass
from itertools import permutations

AND_LIMIT = 3
"""Clauses a regex lowering will permute. Six alternatives at three."""

PATH_FIELDS = ("path:", "file:")
JOIN = {"OR", "|"}
NEGATE = {"NOT", "-", "!"}

_META = r"\.^$*+?()[]{}|"
_NAMES = {
    "and": "several terms at once",
    "literal": "a word",
    "not": "negation",
    "or": "OR",
    "path": "a path filter",
    "phrase": "a quoted phrase",
    "regex": "a regular expression",
}
_WORD = re.compile(r"[A-Z]+(?![a-z])|[A-Z][a-z0-9]*|[a-z0-9]+")


class QueryError(ValueError):
    """The query is not written in the query language."""


class Unsupported(Exception):
    """A tool cannot express part of a query. The message names the part."""


@dataclass(frozen=True)
class Atom:
    """One thing to match.

    Attributes:
        text: The word, the phrase without its quotes, or the pattern without
            its slashes.
        regex: The atom was written as `/pattern/` and holds a regex.
        phrase: The atom was written as `"text"` and matches literally.
    """

    text: str
    regex: bool = False
    phrase: bool = False


@dataclass(frozen=True)
class Clause:
    """Atoms joined by `OR`, and whether the clause is negated.

    Attributes:
        atoms: The alternatives, one of which has to match.
        negated: The clause was written with `-` or `NOT`, so a result matching
            it is dropped.
    """

    atoms: tuple[Atom, ...]
    negated: bool = False


@dataclass(frozen=True)
class Query:
    """A parsed query.

    Attributes:
        clauses: Every clause, all of which have to match.
        paths: Globs from `path:` filters, any of which a file may match.
        text: The query as typed, less its path filters, for the tools that
            take their own syntax whole.
    """

    clauses: tuple[Clause, ...]
    paths: tuple[str, ...]
    text: str

    @property
    def features(self) -> frozenset[str]:
        """Return the parts of the language this query uses."""
        found = set()
        if len(self.clauses) > 1:
            found.add("and")
        if self.paths:
            found.add("path")
        for clause in self.clauses:
            if clause.negated:
                found.add("not")
            if len(clause.atoms) > 1:
                found.add("or")
            for atom in clause.atoms:
                if atom.regex:
                    found.add("regex")
                elif atom.phrase:
                    found.add("phrase")
                else:
                    found.add("literal")
        return frozenset(found)


@dataclass(frozen=True)
class Lowered:
    """A query written the way one tool takes it.

    Attributes:
        query: The query text that tool understands.
        globs: Path globs to pass as the include flag of that tool.
    """

    query: str
    globs: tuple[str, ...] = ()


# ------- Parsing -------


def _scan(text: str) -> list[str]:
    """Split a query into tokens, keeping a quoted phrase whole.

    Raises:
        QueryError: A quote is left open.
    """
    tokens: list[str] = []
    current: list[str] = []
    quoted = False
    for char in text:
        if char == '"':
            quoted = not quoted
            current.append(char)
        elif char.isspace() and not quoted:
            if current:
                tokens.append("".join(current))
                current = []
        else:
            current.append(char)
    if quoted:
        raise QueryError("The query leaves a quote open")
    if current:
        tokens.append("".join(current))
    return tokens


def _unquote(body: str) -> tuple[str, bool]:
    """Return the text of a token and whether it was written as a phrase."""
    if len(body) > 1 and body.startswith('"') and body.endswith('"'):
        return body[1:-1], True
    return body, False


def _atom(body: str) -> Atom:
    """Return the atom a token holds.

    A token slashed at both ends is a regex, one quoted at both ends is a
    phrase, and anything else is a bare word.

    Raises:
        QueryError: The token holds no text to match.
    """
    if len(body) > 1 and body.startswith("/") and body.endswith("/"):
        pattern = body[1:-1]
        if not pattern:
            raise QueryError("The query holds an empty regular expression")
        return Atom(pattern, regex=True)
    text, phrase = _unquote(body)
    if not text:
        raise QueryError("The query holds an empty term")
    return Atom(text, phrase=phrase)


def normalise_glob(glob: str) -> str:
    """Return a path glob every tool matches the same way.

    ripgrep and ast-grep match a glob holding a `/` against the path as
    printed, which is absolute here, so `src/**` would match nothing while the
    same glob matches the walked tree of `search-tool-semantic`. Prefixing
    `**/` makes all three read it as a path at any depth, because `**` matches
    no segment as readily as several.

    Args:
        glob: The glob as written after `path:`.

    Returns:
        The glob, prefixed where it names a path rather than a file name.
    """
    if "/" not in glob or glob.startswith(("**/", "/")):
        return glob
    return f"**/{glob}"


def _path_prefix(body: str) -> str | None:
    """Return the `path:` prefix a token carries, where it carries one."""
    lowered = body.lower()
    return next((name for name in PATH_FIELDS if lowered.startswith(name)), None)


def parse(text: str) -> Query:
    """Return the query a command line holds.

    Args:
        text: The query as typed.

    Returns:
        The parsed query, with its path filters held apart from its clauses.

    Raises:
        QueryError: The query is unparsable, or names nothing to match.
    """
    clauses: list[Clause] = []
    paths: list[str] = []
    written: list[str] = []
    negated = False
    joining = False
    for token in _scan(text):
        if token in JOIN:
            if not clauses:
                raise QueryError("OR needs a term before it")
            joining = True
            continue
        if token in NEGATE:
            negated = True
            continue
        body = token
        if body[0] in "-!" and not body.startswith('"'):
            negated = True
            body = body[1:]
        prefix = _path_prefix(body)
        if prefix is not None:
            if negated or joining:
                raise QueryError("A path filter takes neither OR nor negation")
            glob, _ = _unquote(body[len(prefix) :])
            if not glob:
                raise QueryError(f"{prefix} needs a glob")
            paths.append(normalise_glob(glob))
            continue
        atom = _atom(body)
        written.append(token)
        if joining:
            last = clauses[-1]
            clauses[-1] = Clause(last.atoms + (atom,), last.negated)
            joining = False
        else:
            clauses.append(Clause((atom,), negated))
        negated = False
    if joining:
        raise QueryError("OR needs a term after it")
    if negated:
        raise QueryError("NOT needs a term after it")
    if not clauses:
        raise QueryError("The query names nothing to match")
    return Query(tuple(clauses), tuple(paths), " ".join(written))


# ------- Lowering -------


def escape(text: str) -> str:
    """Return text that matches itself, in both POSIX and Rust regex syntax."""
    return "".join("\\" + char if char in _META else char for char in text)


def words(text: str) -> list[str]:
    """Return the words an identifier holds, splitting case and punctuation.

    `build_candidates` and `buildCandidates` both give `build candidates`, so
    an embedding sees words rather than one token it has never met.
    """
    return _WORD.findall(text)


def to_regex(query: Query) -> str:
    """Return the query as one regular expression matching a single line.

    Clauses are permuted rather than anchored, because a line holding both
    terms may hold them in either order, and neither POSIX nor the Rust regex
    engine has lookaround to say it more directly.

    Raises:
        Unsupported: The query negates a clause, or holds more clauses than
            `AND_LIMIT`.
    """
    for clause in query.clauses:
        if clause.negated:
            raise Unsupported("negation")
    if len(query.clauses) > AND_LIMIT:
        raise Unsupported(f"more than {AND_LIMIT} terms at once")
    groups = []
    for clause in query.clauses:
        patterns = [
            atom.text if atom.regex else escape(atom.text) for atom in clause.atoms
        ]
        if len(patterns) > 1:
            groups.append("(" + "|".join(patterns) + ")")
        elif len(query.clauses) > 1:
            groups.append(f"({patterns[0]})")
        else:
            return patterns[0]
    return "|".join(".*".join(order) for order in permutations(groups))


def to_words(query: Query) -> str:
    """Return the query as the words a semantic search embeds.

    AND and OR both flatten, because a dense ranking holds no operators, and
    every atom is split into words.

    Raises:
        Unsupported: The query negates a clause or holds a regular expression,
            neither of which a ranking by meaning can express.
    """
    found: list[str] = []
    for clause in query.clauses:
        if clause.negated:
            raise Unsupported("negation")
        for atom in clause.atoms:
            if atom.regex:
                raise Unsupported("a regular expression")
            for word in words(atom.text) or [atom.text]:
                if word not in found:
                    found.append(word)
    return " ".join(found)


def to_fzf(query: Query) -> str:
    """Return the query in the extended search syntax of fzf.

    A bare word stays fuzzy, which is what fzf is there for, and a quoted
    phrase becomes an exact term.

    Raises:
        Unsupported: The query holds a regular expression, or a term with a
            space in it, neither of which an fzf term can hold.
    """
    terms = []
    for clause in query.clauses:
        written = []
        for atom in clause.atoms:
            if atom.regex:
                raise Unsupported("a regular expression")
            if any(char.isspace() for char in atom.text) or "|" in atom.text:
                raise Unsupported("a term with a space in it")
            written.append(f"'{atom.text}" if atom.phrase else atom.text)
        if clause.negated:
            # fzf inverts an exact term only, and !a !b is NOT (a OR b).
            terms.extend(f"!{atom.text}" for atom in clause.atoms)
        else:
            terms.append(" | ".join(written))
    return " ".join(terms)


def to_cql(query: Query) -> str:
    """Return the query in the text syntax Confluence searches with.

    Raises:
        Unsupported: The query holds a regular expression, which Confluence
            does not match.
    """
    parts = []
    for clause in query.clauses:
        written = []
        for atom in clause.atoms:
            if atom.regex:
                raise Unsupported("a regular expression")
            quote = atom.phrase or any(char.isspace() for char in atom.text)
            written.append(f'"{atom.text}"' if quote else atom.text)
        group = written[0] if len(written) == 1 else "(" + " OR ".join(written) + ")"
        parts.append(f"NOT {group}" if clause.negated else group)
    return " AND ".join(parts)


def to_text(query: Query, allowed: frozenset[str]) -> str:
    """Return the query as typed, for a tool that parses its own syntax.

    Args:
        query: The parsed query.
        allowed: The features the tool can be handed raw.

    Raises:
        Unsupported: The query uses a feature outside `allowed`.
    """
    extra = query.features - allowed
    if extra:
        raise Unsupported(" and ".join(_NAMES[name] for name in sorted(extra)))
    return query.text


def no_paths(query: Query) -> tuple[str, ...]:
    """Return no globs, and refuse a query that filters by path.

    Raises:
        Unsupported: The query holds a path filter and the tool takes none.
    """
    if query.paths:
        raise Unsupported("a path filter")
    return ()
