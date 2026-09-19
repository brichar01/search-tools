"""Search several places with several tools from one command line.

Reads a YAML config file that names each place to search and the tools that
search it, then runs every selected tool and labels its output.
"""

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from search_tool.candidates import build_candidates
from search_tool.config import (
    ConfigError,
    Location,
    default_config_path,
    load_config,
    load_weights,
    select_locations,
    write_starter_config,
)
from search_tool.fusion import PRIOR, Target, score_targets
from search_tool.precache import main as run_precache
from search_tool.query import QueryError, parse
from search_tool.runner import Result, plan_searches, run_search
from search_tool.tools import KIND_FLAGS, KINDS

ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def parse_args() -> argparse.Namespace:
    """Return the parsed command line."""
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Every location comes from the config file. Run --init to write "
            "the example one, then edit it."
        ),
    )
    parser.add_argument(
        "query",
        nargs="?",
        help=(
            "Words to match, all of them. A quoted phrase matches literally, "
            "/slashes/ hold a regular expression, OR joins terms, - drops one "
            "and path:GLOB names the files. A location with --precache"
        ),
    )
    parser.add_argument(
        "locations", nargs="*", help="Config leaves to search, all of them by default"
    )
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=default_config_path(),
        help="YAML config file (default: %(default)s)",
    )
    parser.add_argument(
        "-s",
        "--subdir",
        help="Glob limiting each location to matching subdirectories",
    )
    parser.add_argument(
        "-k",
        "--kind",
        action="append",
        choices=KIND_FLAGS,
        dest="kinds",
        metavar="KIND",
        help=(
            "Only run tools of this kind, repeatable. Prefix with ! to drop a "
            "kind instead, as in !remote. ast runs only where it is named. "
            f"One of: {', '.join(KINDS)}"
        ),
    )
    parser.add_argument(
        "-S",
        "--case-sensitive",
        action="store_true",
        help="Match the case of the query, which every tool folds by default",
    )
    parser.add_argument(
        "--prior",
        type=float,
        default=PRIOR,
        help=(
            "Weight of a search that found nothing when scoring a target "
            "against the searches that could have found it (default: %(default)s)"
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Write JSON records for each search and each scored target",
    )
    parser.add_argument(
        "-t",
        "--tui",
        action="store_true",
        help=(
            "Open the app instead, which takes the query in a box and ranks "
            "what it finds"
        ),
    )
    parser.add_argument(
        "-p",
        "--precache",
        action="store_true",
        help="Build the index of every semantic tool and search nothing",
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Write the example config file to --config and search nothing",
    )
    arguments = parser.parse_args()
    arguments.kinds = arguments.kinds or []
    if arguments.init:
        arguments.query = None
    elif arguments.tui:
        pass
    elif arguments.precache:
        if arguments.query is not None:
            arguments.locations.insert(0, arguments.query)
            arguments.query = None
    elif arguments.query is None:
        parser.error("a query is required")
    return arguments


def label(result: Result) -> str:
    """Return the header that names the tool and directory of a search."""
    parts = [f"[{result.search.location}]", result.search.tool]
    if result.search.directory is not None:
        parts.append(str(result.search.directory))
    return f"== {' '.join(parts)} =="


def write_text(result: Result, stream) -> None:
    """Write one result as a labelled block."""
    print(label(result), file=stream)
    if result.search.skipped is not None:
        print(f"skipped: {result.search.skipped}", file=stream)
    for line in result.lines:
        print(line, file=stream)
    print(file=stream)


def write_search(result: Result, candidates: int, stream) -> None:
    """Write what one search ran and produced, as a single line of JSON."""
    search = result.search
    record = {
        "type": "search",
        "location": search.location,
        "tool": search.tool,
        "kind": search.kind,
        "directory": None if search.directory is None else str(search.directory),
        "command": search.command,
        "skipped": search.skipped,
        "exit_code": result.exit_code,
        "candidates": candidates,
        "stderr": ANSI.sub("", result.stderr),
    }
    print(json.dumps(record), file=stream)


def write_target(target: Target, query: str, stream) -> None:
    """Write one scored target and the spans behind it, as one line of JSON."""
    record = {"type": "target", "query": query} | asdict(target)
    for candidate in record["candidates"]:
        candidate["text"] = ANSI.sub("", candidate["text"])
    print(json.dumps(record), file=stream)


def write_records(
    results: list[Result],
    query: str,
    prior: float,
    weights: dict[str, float],
    stream,
) -> int:
    """Write a record per search and per target, and return the targets written.

    Every search is reported before the targets, because a target merges hits
    from searches that ran at different times.
    """
    candidates = build_candidates(results)
    targets = score_targets(candidates, results, prior, weights)
    counts = Counter(
        (source.location, source.tool, source.directory)
        for candidate in candidates
        for source in candidate.sources
    )
    for result in results:
        search = result.search
        directory = None if search.directory is None else str(search.directory)
        key = (search.location, search.tool, directory)
        write_search(result, counts[key], stream)
    for target in targets:
        write_target(target, query, stream)
    return len(targets)


def main(
    query: str | None,
    locations: list[str],
    config: Path,
    subdir: str | None,
    kinds: list[str],
    case_sensitive: bool,
    json_output: bool,
    precache: bool,
    init: bool,
    tui: bool = False,
    prior: float = PRIOR,
) -> int:
    """Run every selected search and write the results to stdout.

    Args:
        query: The query, in the language `parse` reads. Ignored where
            `precache` is set.
        locations: Config leaves to search. Empty searches every location.
        config: YAML config file naming each location and its tools.
        subdir: Glob limiting each location to matching subdirectories.
        kinds: Search kinds to run, each optionally negated with `!`. Empty
            runs every kind but `ast`, which runs only where it is named.
        case_sensitive: Match the case of the query, rather than folding it.
        json_output: Write JSON records for each search and each scored
            target, rather than the labelled output of each tool.
        precache: Build the index of every semantic tool instead of searching.
        init: Write the example config file instead of searching.
        tui: Open the app instead of writing the results, which takes the
            query in a box and ranks what it finds. An empty `query` opens it
            with an empty box.
        prior: Weight of a search that found nothing, which sets how far
            agreement outranks a target only one search could reach.

    Returns:
        2 where a tool failed, 0 where anything matched, otherwise 1. A tool
        that cannot express the query is skipped, which is neither. Where
        `precache` is set, 2 where an index build failed, otherwise 0. Where
        `init` is set, 0 where the file was written.
    """
    if init:
        try:
            write_starter_config(config)
        except (ConfigError, OSError) as error:
            sys.exit(str(error.args[0]))
        print(f"Wrote {config}")
        return 0

    if tui:
        from search_tool.tui import run_app

        return run_app(
            query=query,
            locations=locations,
            config=config,
            subdir=subdir,
            kinds=kinds,
            case_sensitive=case_sensitive,
            prior=prior,
        )

    if precache:
        return run_precache(
            locations=locations,
            config=config,
            subdir=subdir,
            dry_run=False,
        )

    try:
        known: dict[str, Location] = load_config(config)
        chosen = select_locations(known, locations)
        weights = load_weights(config)
    except ConfigError as error:
        sys.exit(error.args[0])

    try:
        parsed = parse(query)
    except QueryError as error:
        sys.exit(error.args[0])

    failed = False
    matched = False
    results = []
    for search in plan_searches(
        chosen,
        parsed,
        kinds,
        subdir,
        structured=json_output,
        case_sensitive=case_sensitive,
    ):
        result = run_search(search)
        results.append(result)
        if not json_output:
            write_text(result, sys.stdout)
            matched = matched or result.matched
        if result.exit_code > 1:
            failed = True
            if result.stderr:
                print(f"{label(result)} {result.stderr.strip()}", file=sys.stderr)
    if json_output:
        matched = write_records(results, query, prior, weights, sys.stdout) > 0
    if failed:
        return 2
    return 0 if matched else 1


def run() -> None:
    """Parse the command line and exit with the status of the search."""
    arguments = parse_args()
    sys.exit(
        main(
            query=arguments.query,
            locations=arguments.locations,
            config=arguments.config,
            subdir=arguments.subdir,
            kinds=arguments.kinds,
            case_sensitive=arguments.case_sensitive,
            json_output=arguments.json_output,
            precache=arguments.precache,
            init=arguments.init,
            tui=arguments.tui,
            prior=arguments.prior,
        )
    )


if __name__ == "__main__":
    run()
