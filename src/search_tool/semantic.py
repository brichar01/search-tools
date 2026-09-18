"""Rank lines by meaning, using a model2vec static embedding model.

Embeds every line of the files given, or of standard input where none are, and
writes the lines closest to the query. The model is a static lookup table, so
there is no index to build and a stream can be searched as it arrives.
"""

import argparse
import json
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

import numpy as np
from huggingface_hub.utils import disable_progress_bars
from model2vec import StaticModel

DEFAULT_MODEL = "minishlab/potion-base-8M"
STDIN_SOURCE = "-"


@dataclass(frozen=True)
class Line:
    """One line of the input.

    Attributes:
        source: Path the line came from, or `-` for standard input.
        number: Line number, counting from one.
        text: The line, without its newline.
    """

    source: str
    number: int
    text: str


def find_files(paths: Iterable[Path]) -> Iterator[Path]:
    """Yield the files to read, walking each directory given.

    Args:
        paths: Files and directories named on the command line.

    Yields:
        Every file under a directory whose path holds no dot component, and
        every file named directly.
    """
    for path in paths:
        if not path.is_dir():
            yield path
            continue
        for child in sorted(path.rglob("*")):
            parts = child.relative_to(path).parts
            if child.is_file() and not any(part.startswith(".") for part in parts):
                yield child


def read_lines(paths: list[Path], stdin: TextIO) -> list[Line]:
    """Return every line worth embedding, from the paths or from standard input.

    Args:
        paths: Files and directories to read. Empty reads `stdin` instead.
        stdin: Stream read where no path is given.

    Returns:
        The lines that hold something other than whitespace. A file that is not
        text, or cannot be read, is skipped.
    """
    if not paths:
        return [
            Line(STDIN_SOURCE, number, text)
            for number, text in enumerate(stdin.read().splitlines(), 1)
            if text.strip()
        ]
    lines = []
    for path in find_files(paths):
        try:
            content = path.read_text()
        except OSError, UnicodeDecodeError:
            continue
        lines.extend(
            Line(str(path), number, text)
            for number, text in enumerate(content.splitlines(), 1)
            if text.strip()
        )
    return lines


def rank(
    model: StaticModel,
    query: str,
    lines: list[Line],
    top_k: int,
    threshold: float,
) -> list[tuple[Line, float]]:
    """Return the lines closest to the query, best first.

    Args:
        model: The loaded embedding model.
        query: Text to match the lines against.
        lines: The lines to rank.
        top_k: How many lines to return at most.
        threshold: Lowest cosine similarity to return.

    Returns:
        Each line with its cosine similarity to the query, highest first.
    """
    if not lines:
        return []
    query_vector = model.encode([query])[0]
    query_norm = np.linalg.norm(query_vector)
    if query_norm == 0:
        return []
    vectors = model.encode([line.text for line in lines])
    norms = np.linalg.norm(vectors, axis=1)
    # A line the tokeniser drops entirely embeds to zero.
    norms[norms == 0] = 1.0
    scores = vectors @ query_vector / (norms * query_norm)
    order = np.argsort(-scores)[:top_k]
    return [
        (lines[index], float(scores[index]))
        for index in order
        if scores[index] >= threshold
    ]


def write_hits(
    hits: list[tuple[Line, float]], json_output: bool, stream: TextIO
) -> None:
    """Write each ranked line, as `source:line:text` or as a JSON record.

    Args:
        hits: The ranked lines and their scores.
        json_output: Write one JSON object per line rather than text.
        stream: Where to write.
    """
    for line, score in hits:
        if json_output:
            record = {
                "path": line.source,
                "line": line.number,
                "text": line.text,
                "score": score,
            }
            print(json.dumps(record), file=stream)
        else:
            print(f"{line.source}:{line.number}:{line.text}", file=stream)


def parse_args() -> argparse.Namespace:
    """Return the parsed command line."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("query", help="Text to match lines against")
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Files and directories to search, standard input by default",
    )
    parser.add_argument(
        "-k",
        "--top-k",
        type=int,
        default=10,
        help="How many lines to return at most (default: %(default)s)",
    )
    parser.add_argument(
        "-t",
        "--threshold",
        type=float,
        default=0.0,
        help="Lowest cosine similarity to return (default: %(default)s)",
    )
    parser.add_argument(
        "-m",
        "--model",
        default=DEFAULT_MODEL,
        help="Embedding model to load (default: %(default)s)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Write one JSON record per ranked line",
    )
    return parser.parse_args()


def main(
    query: str,
    paths: list[Path],
    top_k: int,
    threshold: float,
    model: str,
    json_output: bool,
) -> int:
    """Rank the lines of the input against the query and write the closest.

    Args:
        query: Text to match lines against.
        paths: Files and directories to search. Empty searches standard input.
        top_k: How many lines to return at most.
        threshold: Lowest cosine similarity to return.
        model: Embedding model to load, by Hugging Face name or local path.
        json_output: Write JSON records rather than `source:line:text`.

    Returns:
        2 where the model cannot be loaded, 0 where anything ranked above the
        threshold, otherwise 1.
    """
    disable_progress_bars()
    try:
        embedder = StaticModel.from_pretrained(model)
    except OSError as error:
        print(f"{model}: {error}", file=sys.stderr)
        return 2
    hits = rank(embedder, query, read_lines(paths, sys.stdin), top_k, threshold)
    write_hits(hits, json_output, sys.stdout)
    return 0 if hits else 1


def run() -> None:
    """Parse the command line and exit with the status of the search."""
    arguments = parse_args()
    sys.exit(
        main(
            query=arguments.query,
            paths=arguments.paths,
            top_k=arguments.top_k,
            threshold=arguments.threshold,
            model=arguments.model,
            json_output=arguments.json_output,
        )
    )


if __name__ == "__main__":
    run()
