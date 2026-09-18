"""Plan the searches a run performs, and run them."""

import subprocess
from dataclasses import dataclass
from pathlib import Path

from search_tool.config import Location
from search_tool.tools import TOOLS, Command


@dataclass(frozen=True)
class Search:
    """One tool run against one directory.

    Attributes:
        location: Name of the location that selected the tool.
        tool: Canonical tool name.
        kind: Search kind of the tool.
        directory: Directory searched, or `None` for a system or remote source.
        command: The pipeline to run.
    """

    location: str
    tool: str
    kind: str
    directory: Path | None
    command: Command


@dataclass(frozen=True)
class Result:
    """What one search produced.

    Attributes:
        search: The search that ran.
        exit_code: Highest exit code in the pipeline, or 127 where the program
            is not installed.
        stdout: Standard output of the last stage.
        stderr: Standard error of every stage, joined.
    """

    search: Search
    exit_code: int
    stdout: str
    stderr: str

    @property
    def lines(self) -> list[str]:
        """Standard output, without trailing newlines."""
        return self.stdout.splitlines()

    @property
    def matched(self) -> bool:
        """Whether the search produced output and no error."""
        return self.exit_code == 0 and bool(self.stdout.strip())


def targets(location: Location, subdir: str | None) -> list[Path | None]:
    """Return the directories to search for a location.

    Args:
        location: The location being searched.
        subdir: Glob matched against the location directory, or `None` for the
            whole directory. A glob that matches no subdirectory searches nothing.
    """
    if location.directory is None:
        return [None]
    if subdir is None:
        return [location.directory]
    return sorted(path for path in location.directory.glob(subdir) if path.is_dir())


def plan_searches(
    locations: list[Location],
    query: str,
    kinds: list[str],
    subdir: str | None,
    structured: bool = False,
) -> list[Search]:
    """Return every search to run, in location then tool order.

    Args:
        locations: The selected locations.
        query: The text, pattern or AST pattern to search for.
        kinds: Search kinds to keep. Empty keeps every kind.
        subdir: Glob limiting each location to matching subdirectories.
        structured: Ask each tool for the output its parser reads, rather than
            the output written for a person.
    """
    searches = []
    for location in locations:
        for name in location.tools:
            tool = TOOLS[name]
            if kinds and tool.kind not in kinds:
                continue
            build = tool.build_json if structured else tool.build
            for directory in targets(
                location, subdir if tool.needs_directory else None
            ):
                searches.append(
                    Search(
                        location=location.name,
                        tool=tool.name,
                        kind=tool.kind,
                        directory=directory,
                        command=build(query, directory, location.ignore),
                    )
                )
    return searches


def run_search(search: Search) -> Result:
    """Run one search and collect its output.

    A pipeline stage that exits non-zero does not stop the stages after it, so
    the exit code reported is the highest of them all.
    """
    processes = []
    stdin = None
    try:
        for argv in search.command:
            process = subprocess.Popen(
                argv,
                stdin=stdin,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                errors="replace",
            )
            if stdin is not None:
                stdin.close()
            stdin = process.stdout
            processes.append(process)
    except FileNotFoundError as error:
        for process in processes:
            process.kill()
        return Result(search, 127, "", f"{error.filename}: not installed")

    stdout, stderr = processes[-1].communicate()
    errors = [stderr]
    for process in processes[:-1]:
        errors.append(process.stderr.read())
        process.stderr.close()
        process.wait()
    return Result(
        search=search,
        exit_code=max(process.returncode for process in processes),
        stdout=stdout,
        stderr="".join(errors),
    )
