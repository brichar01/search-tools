"""Save the help text of common commands where the search tools can read it.

Each command in the list writes `<cmd>_help.txt` from its `--help` output, and
`<cmd>_man.txt` from its manual page where it has one, into one directory. This
searches nothing. Point a config leaf at the directory and `rg`, `fzf` and `ck`
search it like any other.
"""

import argparse
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from importlib.resources import files
from os import environ
from pathlib import Path

DEFAULT_TIMEOUT = 5.0
HELP_FLAGS = ("--help", "-h")
SHORT_HELP_UNSAFE = frozenset({"shutdown", "reboot", "poweroff", "halt", "dd"})
"""Commands where `-h` acts rather than writing usage, so only `--help` is tried."""
MAX_BYTES = 1_048_576
NAME = re.compile(r"[A-Za-z0-9._+-]+")
ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
OVERSTRIKE = re.compile(r"[^\n]\x08")
REJECTED = re.compile(r"(invalid|unknown|unrecognized|illegal) option", re.IGNORECASE)
"""How a command says it does not take the flag it was given."""


@dataclass(frozen=True)
class Harvest:
    """What one command produced.

    Attributes:
        command: Name the command is called by.
        installed: Whether the command is on the path. A command that is not
            installed is skipped, so a list can name more than a machine has.
        written: Page suffixes written this run, `help` and `man`.
        current: Page suffixes already newer than what they were captured from.
    """

    command: str
    installed: bool
    written: tuple[str, ...] = ()
    current: tuple[str, ...] = ()


def default_output() -> Path:
    """Return the directory the pages are written to by default."""
    cache = environ.get("XDG_CACHE_HOME")
    root = Path(cache) if cache else Path.home() / ".cache"
    return root / "search-tool" / "help"


def packaged_commands() -> str:
    """Return the command list that ships with the package."""
    return (files("search_tool") / "help_commands.txt").read_text()


def read_commands(document: str) -> list[str]:
    """Return the command names a list holds, in file order.

    Args:
        document: Text holding one command name per line. A `#` starts a
            comment, and blank lines are skipped.

    Returns:
        Each name once, less anything holding a character a file name cannot
        hold, because the name becomes part of the written path.
    """
    names = []
    for line in document.splitlines():
        name = line.split("#", 1)[0].strip()
        if not name or name in names or not NAME.fullmatch(name):
            continue
        names.append(name)
    return names


def child_environment() -> dict[str, str]:
    """Return the environment each captured command runs in.

    Colour, pagers and the terminal width all change what a program writes, so
    each is pinned rather than inherited.
    """
    return dict(environ) | {
        "COLUMNS": "80",
        "GROFF_NO_SGR": "1",
        "MANPAGER": "cat",
        "MANWIDTH": "80",
        "NO_COLOR": "1",
        "PAGER": "cat",
        "TERM": "dumb",
    }


def clean(text: str) -> str:
    """Return text without colour codes or the overstrike `man` writes for bold."""
    text = ANSI.sub("", OVERSTRIKE.sub("", text)).strip()
    if len(text) > MAX_BYTES:
        return text[:MAX_BYTES] + "\n[truncated]"
    return text


def capture(argv: list[str], timeout: float) -> str:
    """Return what a command wrote, standard output and standard error together.

    Args:
        argv: The command to run. Standard input is closed, so a program that
            reads it stops rather than waiting.
        timeout: Seconds to wait before killing the command.

    Returns:
        The cleaned output, or nothing where the command could not run, timed
        out or wrote nothing. The exit status is not read, because plenty of
        programs write their usage and exit non-zero.
    """
    try:
        finished = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            timeout=timeout,
            env=child_environment(),
            check=False,
        )
    except OSError, subprocess.TimeoutExpired:
        return ""
    return clean(finished.stdout)


def manual_source(command: str, timeout: float) -> Path | None:
    """Return the file holding the manual page of a command, or `None`."""
    try:
        finished = subprocess.run(
            ["man", "-w", command],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=timeout,
            env=child_environment(),
            check=False,
        )
    except OSError, subprocess.TimeoutExpired:
        return None
    first = finished.stdout.split("\n", 1)[0].strip()
    if finished.returncode != 0 or not first:
        return None
    return Path(first)


def help_text(command: str, timeout: float) -> tuple[str, str] | None:
    """Return the flag that made a command write its usage, and what it wrote.

    Args:
        command: Name the command is called by.
        timeout: Seconds to wait for each flag.

    Returns:
        The first of `--help` and `-h` the command accepts, or the longest
        output of the flags it rejects, because plenty of programs answer an
        unknown flag with their usage anyway. `None` where neither flag writes
        anything. A command that halts the machine on `-h` is only ever given
        `--help`.
    """
    flags = ("--help",) if command in SHORT_HELP_UNSAFE else HELP_FLAGS
    rejected = None
    for flag in flags:
        text = capture([command, flag], timeout)
        if not text:
            continue
        if not REJECTED.search(text.split("\n", 1)[0]):
            return flag, text
        if rejected is None or len(text) > len(rejected[1]):
            rejected = (flag, text)
    return rejected


def current(path: Path, source: Path | None) -> bool:
    """Whether a written page is at least as new as what it was captured from."""
    if not path.is_file():
        return False
    if source is None or not source.exists():
        return True
    return path.stat().st_mtime >= source.stat().st_mtime


def write_page(path: Path, header: str, text: str) -> None:
    """Write one page, header first, so a match carries what it came from."""
    path.write_text(f"{header}\n\n{text}\n")


def harvest(
    command: str, output: Path, timeout: float, force: bool, dry_run: bool
) -> Harvest:
    """Capture the help and manual pages of one command.

    Args:
        command: Name the command is called by.
        output: Directory the pages are written to.
        timeout: Seconds to wait for each command run.
        force: Recapture pages that are already current.
        dry_run: Report what would be captured without running the command or
            writing anything. A command that turns out to write no usage is
            still reported, because only running it settles that.

    Returns:
        What the command produced.
    """
    program = shutil.which(command)
    if program is None:
        return Harvest(command, installed=False)

    written = []
    already = []
    help_path = output / f"{command}_help.txt"
    if not force and current(help_path, Path(program)):
        already.append("help")
    elif dry_run:
        written.append("help")
    else:
        found = help_text(command, timeout)
        if found is not None:
            flag, text = found
            write_page(help_path, f"# {command} {flag}", text)
            written.append("help")

    source = manual_source(command, timeout)
    if source is not None:
        manual_path = output / f"{command}_man.txt"
        if not force and current(manual_path, source):
            already.append("man")
        elif dry_run:
            written.append("man")
        else:
            text = capture(["man", "-P", "cat", command], timeout)
            if text:
                write_page(manual_path, f"# man {command}", text)
                written.append("man")

    return Harvest(command, True, tuple(written), tuple(already))


def parse_args() -> argparse.Namespace:
    """Return the parsed command line."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "commands",
        nargs="*",
        help="Commands to capture, every command in the list by default",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=default_output(),
        help="Directory to write the pages to (default: %(default)s)",
    )
    parser.add_argument(
        "-l",
        "--list",
        type=Path,
        dest="command_list",
        help="File of command names, one per line, the packaged one by default",
    )
    parser.add_argument(
        "-t",
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help="Seconds to wait for each command (default: %(default)s)",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Recapture pages that are already current",
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Write what would be captured without capturing it",
    )
    return parser.parse_args()


def main(
    commands: list[str],
    output: Path,
    command_list: Path | None,
    timeout: float,
    force: bool,
    dry_run: bool,
) -> int:
    """Capture the help and manual pages of every command named.

    Args:
        commands: Commands to capture. Empty captures the whole list.
        output: Directory the pages are written to.
        command_list: File of command names, or `None` for the packaged list.
        timeout: Seconds to wait for each command run.
        force: Recapture pages that are already current.
        dry_run: Report what would be captured without capturing it.

    Returns:
        0. Where the list cannot be read, or the output directory cannot be
        made, it exits 1 with the reason instead.
    """
    try:
        document = (
            packaged_commands() if command_list is None else command_list.read_text()
        )
    except OSError as error:
        sys.exit(f"{command_list}: {error.strerror}")
    names = commands or read_commands(document)
    if not dry_run:
        try:
            output.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            sys.exit(f"{output}: {error.strerror}")

    written = 0
    missing = []
    for name in names:
        result = harvest(name, output, timeout, force, dry_run)
        if not result.installed:
            missing.append(name)
            continue
        written += len(result.written)
        state = ", ".join(
            [*result.written, *(f"{s} (current)" for s in result.current)]
        )
        print(f"{name}: {state or 'nothing'}", flush=True)
    verb = "would write" if dry_run else "wrote"
    print(f"{output}: {verb} {written} pages for {len(names) - len(missing)} commands")
    if missing:
        print(f"not installed: {' '.join(missing)}")
    return 0


def run() -> None:
    """Parse the command line and exit with the status of the capture."""
    arguments = parse_args()
    sys.exit(
        main(
            commands=arguments.commands,
            output=arguments.output,
            command_list=arguments.command_list,
            timeout=arguments.timeout,
            force=arguments.force,
            dry_run=arguments.dry_run,
        )
    )


if __name__ == "__main__":
    run()
