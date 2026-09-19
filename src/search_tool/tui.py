"""The same searches as the command line, ranked and browsable on a screen.

The command line writes what each tool returned. This runs the same plan, ranks
the targets the way `--json` does, and shows the spans behind whichever target
is selected. The locations and tools a search covers are toggled while it runs.
"""

import shlex
import subprocess
import sys
from dataclasses import dataclass, replace
from os import environ
from pathlib import Path
from typing import ClassVar

from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.theme import Theme
from textual.timer import Timer
from textual.widgets import DataTable, Footer, Header, Input, SelectionList, Static
from textual.widgets.selection_list import Selection

from search_tool.candidates import build_candidates
from search_tool.cli import ANSI
from search_tool.config import (
    ConfigError,
    Location,
    load_config,
    load_weights,
    select_locations,
)
from search_tool.fusion import PRIOR, Target, score_targets
from search_tool.query import QueryError, parse
from search_tool.runner import Result, plan_searches, run_search
from search_tool.tools import KINDS, TOOLS, resolve_kinds

# ------- Palette -------

NORDFOX = {
    "bg0": "#232831",
    "bg1": "#2e3440",
    "bg2": "#39404f",
    "bg3": "#3b4252",
    "bg4": "#444c5e",
    "fg1": "#cdcecf",
    "fg2": "#abb1bb",
    "fg3": "#60728a",
    "sel": "#3e4a5b",
    "red": "#bf616a",
    "orange": "#c9826b",
    "yellow": "#ebcb8b",
    "green": "#a3be8c",
    "cyan": "#88c0d0",
    "blue": "#81a1c1",
    "purple": "#b48ead",
    "pink": "#d092ce",
    "white": "#e5e9f0",
}
"""The nordfox palette, as NordFox/theme.css writes it."""

DEBOUNCE = 1.0
"""Seconds the query box waits for the typing to stop before it searches."""

PLUS = frozenset(
    {"vi", "vim", "nvim", "view", "gvim", "nano", "pico", "emacs", "emacsclient", "kak"}
)
"""Editors that open at a line given as `+17` before the path."""

GOTO = frozenset({"code", "codium", "code-insiders"})
"""Editors that open at a line given as `-g path:17`."""

COLON = frozenset({"hx", "helix", "subl", "sublime_text", "micro"})
"""Editors that open at a line given as `path:17`."""

KIND_COLOURS = {
    "file": NORDFOX["blue"],
    "command": NORDFOX["green"],
    "manual": NORDFOX["yellow"],
    "remote": NORDFOX["purple"],
}


def nordfox() -> Theme:
    """Return the nordfox palette as a Textual theme."""
    return Theme(
        name="nordfox",
        primary=NORDFOX["blue"],
        secondary=NORDFOX["cyan"],
        accent=NORDFOX["purple"],
        warning=NORDFOX["yellow"],
        error=NORDFOX["red"],
        success=NORDFOX["green"],
        foreground=NORDFOX["fg1"],
        background=NORDFOX["bg1"],
        surface=NORDFOX["bg0"],
        panel=NORDFOX["bg3"],
        dark=True,
        variables={
            "border": NORDFOX["bg4"],
            "border-blurred": NORDFOX["bg2"],
            "text-muted": NORDFOX["fg2"],
            "text-disabled": NORDFOX["fg3"],
            "block-cursor-background": NORDFOX["blue"],
            "block-cursor-foreground": NORDFOX["bg0"],
            "block-cursor-text-style": "none",
            "input-selection-background": NORDFOX["sel"],
            "footer-key-foreground": NORDFOX["cyan"],
            "scrollbar": NORDFOX["bg3"],
            "scrollbar-hover": NORDFOX["bg4"],
            "scrollbar-active": NORDFOX["blue"],
        },
    )


# ------- Searching -------


@dataclass(frozen=True)
class Outcome:
    """What one run of the selected searches produced.

    Attributes:
        targets: The scored targets, the highest first.
        ran: Searches that ran a tool.
        skipped: Searches whose tool could not express the query.
        failed: One message per search whose tool failed.
    """

    targets: list[Target]
    ran: int
    skipped: int
    failed: list[str]


def narrow(locations: list[Location], tools: set[str]) -> list[Location]:
    """Return the locations holding an enabled tool, each cut to those tools.

    Args:
        locations: The locations to narrow.
        tools: Canonical names of the enabled tools.
    """
    narrowed = []
    for location in locations:
        kept = tuple(name for name in location.tools if name in tools)
        if kept:
            narrowed.append(replace(location, tools=kept))
    return narrowed


def why(result: Result) -> str:
    """Return the first line a failed search wrote, or its exit code."""
    stderr = result.stderr.strip()
    return stderr.splitlines()[0] if stderr else f"exit {result.exit_code}"


def search(
    locations: list[Location],
    query: str,
    subdir: str | None,
    case_sensitive: bool,
    prior: float,
    weights: dict[str, float],
) -> Outcome:
    """Run every search the locations plan and score what came back.

    Args:
        locations: The locations to search, already cut to the enabled tools.
        query: The query, in the language `parse` reads.
        subdir: Glob limiting each location to matching subdirectories.
        case_sensitive: Match the case of the query.
        prior: Weight of a search that found nothing.
        weights: What one vote of a tool is worth.

    Raises:
        QueryError: The query is not written in the query language.
    """
    parsed = parse(query)
    searches = plan_searches(
        locations,
        parsed,
        list(KINDS),
        subdir,
        structured=True,
        case_sensitive=case_sensitive,
    )
    results = [run_search(one) for one in searches]
    targets = score_targets(build_candidates(results), results, prior, weights)
    failed = [
        f"{result.search.tool}[{result.search.location}]: {why(result)}"
        for result in results
        if result.exit_code > 1
    ]
    skipped = sum(1 for result in results if result.search.skipped is not None)
    return Outcome(targets, len(results) - skipped, skipped, failed)


# ------- Display -------


def shorten(key: str) -> str:
    """Return a path under the home directory written with `~`."""
    home = str(Path.home())
    if key.startswith(f"{home}/"):
        return f"~{key[len(home) :]}"
    return key


def voters(target: Target) -> str:
    """Return the tools that voted for a target, each named once."""
    named = {
        source.tool: None
        for candidate in target.candidates
        for source in candidate.sources
    }
    return " ".join(named)


def describe(target: Target) -> Text:
    """Return the name of a target, with where it lives written after it.

    A pane narrower than the path cuts the end off, so the directory is
    written last and the name of the file stays in view.
    """
    if target.kind != "file":
        return Text(target.key, style=NORDFOX["fg1"])
    path = Path(target.key)
    text = Text(path.name, style=NORDFOX["fg1"])
    text.append(f"  {shorten(str(path.parent))}", style=NORDFOX["fg3"])
    return text


def first_line(target: Target) -> int | None:
    """Return the line to open a target at, or `None` for the top of the file.

    The strongest span comes first, and a tool that names whole files reports
    no line at all, so the first span that holds one is the best line there is.
    """
    for candidate in target.candidates:
        if candidate.line is not None:
            return candidate.line
    return None


def editor_command(editor: str, path: str, line: int | None) -> list[str]:
    """Return the command that opens a path in an editor.

    Args:
        editor: The `VISUAL` or `EDITOR` setting, which may carry arguments.
        path: The file to open.
        line: Line to open at, or `None` for the top of the file.

    Returns:
        The argument list to run. An editor with no known way to take a line
        opens the file at the top.
    """
    argv = shlex.split(editor)
    program = Path(argv[0]).name
    if line is None:
        return [*argv, path]
    if program in PLUS:
        return [*argv, f"+{line}", path]
    if program in GOTO:
        return [*argv, "-g", f"{path}:{line}"]
    if program in COLON:
        return [*argv, f"{path}:{line}"]
    return [*argv, path]


def preview(target: Target) -> Text:
    """Return the spans behind one target, the strongest first."""
    text = Text()
    text.append(f"{shorten(target.key)}\n", style=f"bold {NORDFOX['white']}")
    text.append(
        f"{target.kind}  relevance {target.relevance:.3f}  "
        f"votes {target.votes:.2f}  reach {target.reach:.2f}\n",
        style=NORDFOX["fg3"],
    )
    for candidate in target.candidates:
        text.append("\n")
        if candidate.line is None:
            where = "whole"
        elif candidate.end_line and candidate.end_line > candidate.line:
            where = f"{candidate.line}-{candidate.end_line}"
        else:
            where = str(candidate.line)
        text.append(f"{where}", style=f"bold {NORDFOX['cyan']}")
        text.append(f"  {candidate.votes:.2f}  ", style=NORDFOX["fg3"])
        text.append(
            " ".join(
                f"{source.tool}[{source.location}]" for source in candidate.sources
            )
            + "\n",
            style=NORDFOX["purple"],
        )
        for line in ANSI.sub("", candidate.text).splitlines():
            text.append(f"  {line}\n", style=NORDFOX["fg1"])
    return text


def status(outcome: Outcome) -> Text:
    """Return the line under the results summarising a run."""
    text = Text()
    text.append(f"{len(outcome.targets)} targets", style=NORDFOX["green"])
    text.append(f"  {outcome.ran} searches", style=NORDFOX["fg2"])
    if outcome.skipped:
        text.append(f"  {outcome.skipped} skipped", style=NORDFOX["yellow"])
    if outcome.failed:
        text.append(f"  {len(outcome.failed)} failed: ", style=NORDFOX["red"])
        text.append("  ".join(outcome.failed), style=NORDFOX["fg3"])
    return text


# ------- App -------


class SearchTool(App):
    """The search tool as a screen: a query, the ranked targets and the spans."""

    TITLE = "search-tool"

    CSS = """
    Screen { background: $background; }

    #query {
        border: tall $border-blurred;
        background: $surface;
        margin: 0 1;
    }
    #query:focus { border: tall $primary; }

    #body { height: 1fr; }

    #filters { width: 28; margin: 0 0 0 1; }
    #filters.hidden { display: none; }
    #locations { height: 40%; }
    #tools { height: 1fr; }

    SelectionList {
        border: round $border-blurred;
        background: $surface;
        padding: 0 1;
    }
    SelectionList:focus { border: round $primary; }

    #targets {
        width: 1fr;
        border: round $border-blurred;
        background: $surface;
    }
    #targets:focus { border: round $primary; }
    #targets > .datatable--header { color: $secondary; background: $surface; }
    #targets > .datatable--cursor { color: $background; background: $secondary; }

    #preview {
        width: 1fr;
        border: round $border-blurred;
        background: $surface;
        margin: 0 1 0 0;
        padding: 0 1;
    }
    #preview:focus { border: round $primary; }

    #status { height: 1; padding: 0 2; background: $background; }
    """

    BINDINGS: ClassVar[list] = [
        ("ctrl+r", "rerun", "Search"),
        ("ctrl+f", "focus_query", "Query"),
        ("ctrl+b", "toggle_filters", "Filters"),
    ]

    def __init__(
        self,
        chosen: list[Location],
        weights: dict[str, float],
        query: str | None = None,
        subdir: str | None = None,
        kinds: list[str] | None = None,
        case_sensitive: bool = False,
        prior: float = PRIOR,
    ) -> None:
        """Hold the run the command line asked for.

        Args:
            chosen: The locations the command line selected.
            weights: What one vote of a tool is worth.
            query: The query to run at startup, or `None` to open empty.
            subdir: Glob limiting each location to matching subdirectories.
            kinds: Search kinds, as `--kind` takes them, which set the tools
                switched on at startup.
            case_sensitive: Match the case of the query.
            prior: Weight of a search that found nothing.
        """
        super().__init__()
        self.chosen = chosen
        self.weights = weights
        self.opening = query
        self.subdir = subdir
        self.case_sensitive = case_sensitive
        self.prior = prior
        self.available = sorted(
            {name for location in chosen for name in location.tools}
        )
        wanted = resolve_kinds(kinds or [])
        self.starting = {name for name in self.available if TOOLS[name].kind in wanted}
        self.targets: dict[str, Target] = {}
        self.searched: str | None = None
        self.pending: Timer | None = None
        self.ready = False

    def compose(self) -> ComposeResult:
        """Lay out the query, the filters, the ranked targets and the spans."""
        yield Header()
        yield Input(value=self.opening or "", placeholder="query", id="query")
        with Horizontal(id="body"):
            with Vertical(id="filters"):
                yield SelectionList[str](
                    *(
                        Selection(location.name, location.name, True)
                        for location in self.chosen
                    ),
                    id="locations",
                )
                yield SelectionList[str](
                    *(
                        Selection(
                            f"{name} ({TOOLS[name].kind})",
                            name,
                            name in self.starting,
                        )
                        for name in self.available
                    ),
                    id="tools",
                )
            yield DataTable(id="targets")
            with VerticalScroll(id="preview"):
                yield Static(id="span")
        yield Static(id="status")
        yield Footer()

    def on_mount(self) -> None:
        """Dress the panes, then run the query the command line carried."""
        self.register_theme(nordfox())
        self.theme = "nordfox"
        self.query_one("#locations", SelectionList).border_title = "locations"
        self.query_one("#tools", SelectionList).border_title = "tools"
        self.query_one("#preview", VerticalScroll).border_title = "spans"
        table = self.query_one("#targets", DataTable)
        table.border_title = "targets"
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_column("score", width=5)
        table.add_column("kind", width=7)
        table.add_column("by", width=16)
        table.add_column("target")
        self.query_one("#query", Input).focus()
        self.ready = True
        if self.opening:
            self.start()

    # ------- Events -------

    @on(Input.Changed, "#query")
    def on_typing(self, event: Input.Changed) -> None:
        """Wait out the typing before searching for it.

        The box holds what was searched last where the query came from the
        command line, or where an edit was typed and then taken back.
        """
        if not self.ready:
            return
        if event.value.strip() == self.searched:
            self.stop_pending()
            return
        self.schedule()

    @on(Input.Submitted, "#query")
    def on_query(self, event: Input.Submitted) -> None:
        """Search for what was typed, without waiting out the debounce."""
        self.start()

    @on(SelectionList.SelectedChanged)
    def on_filters(self, event: SelectionList.SelectedChanged) -> None:
        """Run the query again over whatever is switched on now."""
        if self.ready:
            self.schedule()

    @on(DataTable.RowHighlighted, "#targets")
    def on_target(self, event: DataTable.RowHighlighted) -> None:
        """Show the spans of the highlighted target."""
        target = self.targets.get(str(event.row_key.value))
        span = self.query_one("#span", Static)
        span.update(Text() if target is None else preview(target))

    @on(DataTable.RowSelected, "#targets")
    def on_open(self, event: DataTable.RowSelected) -> None:
        """Open the selected target in the editor, at its strongest span."""
        target = self.targets.get(str(event.row_key.value))
        if target is None:
            return
        if target.kind != "file":
            self.note(f"a {target.kind} target is not a file", NORDFOX["yellow"])
            return
        editor = environ.get("VISUAL") or environ.get("EDITOR")
        if not editor:
            self.note("neither VISUAL nor EDITOR is set", NORDFOX["yellow"])
            return
        self.edit(editor_command(editor, target.key, first_line(target)))

    def action_rerun(self) -> None:
        """Run the query in the box again."""
        self.start()

    def action_focus_query(self) -> None:
        """Put the cursor back in the query box."""
        self.query_one("#query", Input).focus()

    def action_toggle_filters(self) -> None:
        """Show or hide the location and tool lists."""
        self.query_one("#filters").toggle_class("hidden")

    # ------- Running -------

    def selected(self) -> list[Location]:
        """Return the locations to search, cut to the tools switched on."""
        locations = set(self.query_one("#locations", SelectionList).selected)
        tools = set(self.query_one("#tools", SelectionList).selected)
        return narrow(
            [location for location in self.chosen if location.name in locations],
            tools,
        )

    def schedule(self) -> None:
        """Search once nothing has changed for `DEBOUNCE` seconds.

        Every tool is a process, so a search costs more than a keystroke.
        """
        self.stop_pending()
        self.pending = self.set_timer(DEBOUNCE, self.start)

    def stop_pending(self) -> None:
        """Drop the search the typing scheduled, where one is waiting."""
        if self.pending is not None:
            self.pending.stop()
            self.pending = None

    def start(self) -> None:
        """Run the query in the background, or say why nothing will run."""
        self.stop_pending()
        query = self.query_one("#query", Input).value.strip()
        if not query:
            return
        self.searched = query
        locations = self.selected()
        if not locations:
            self.clear("nothing is switched on", NORDFOX["yellow"])
            return
        self.query_one("#targets", DataTable).loading = True
        self.run_searches(locations, query)

    def edit(self, command: list[str]) -> None:
        """Hand the terminal to an editor until it exits."""
        try:
            with self.suspend():
                subprocess.call(command)
        except OSError as error:
            self.note(f"{command[0]}: {error.strerror}", NORDFOX["red"])

    @work(thread=True, exclusive=True)
    def run_searches(self, locations: list[Location], query: str) -> None:
        """Run the searches off the event loop and hand back what they found."""
        try:
            outcome = search(
                locations,
                query,
                self.subdir,
                self.case_sensitive,
                self.prior,
                self.weights,
            )
        except QueryError as error:
            self.call_from_thread(self.clear, error.args[0], NORDFOX["red"])
            return
        self.call_from_thread(self.show, outcome)

    def note(self, message: str, colour: str) -> None:
        """Write one line under the results, leaving them where they are."""
        self.query_one("#status", Static).update(Text(message, style=colour))

    def clear(self, message: str, colour: str) -> None:
        """Empty the results and write one line in their place."""
        table = self.query_one("#targets", DataTable)
        table.loading = False
        table.clear()
        self.targets = {}
        self.query_one("#span", Static).update(Text())
        self.note(message, colour)

    def show(self, outcome: Outcome) -> None:
        """Fill the table with the ranked targets and select the first."""
        table = self.query_one("#targets", DataTable)
        table.loading = False
        table.clear()
        self.targets = {target.key: target for target in outcome.targets}
        for target in outcome.targets:
            table.add_row(
                Text(f"{target.relevance:.2f}", style=NORDFOX["green"]),
                Text(
                    target.kind,
                    style=KIND_COLOURS.get(target.kind, NORDFOX["fg2"]),
                ),
                Text(voters(target), style=NORDFOX["fg3"]),
                describe(target),
                key=target.key,
            )
        self.query_one("#status", Static).update(status(outcome))
        self.query_one("#span", Static).update(
            preview(outcome.targets[0]) if outcome.targets else Text()
        )


def run_app(
    query: str | None,
    locations: list[str],
    config: Path,
    subdir: str | None,
    kinds: list[str],
    case_sensitive: bool,
    prior: float = PRIOR,
) -> int:
    """Open the app over the locations the command line named.

    Args:
        query: The query to run at startup, or `None` to open empty.
        locations: Config leaves to search. Empty offers every location.
        config: YAML config file naming each location and its tools.
        subdir: Glob limiting each location to matching subdirectories.
        kinds: Search kinds, as `--kind` takes them, which set the tools
            switched on at startup.
        case_sensitive: Match the case of the query.
        prior: Weight of a search that found nothing.

    Returns:
        0 once the app closes.
    """
    try:
        known = load_config(config)
        chosen = select_locations(known, locations)
        weights = load_weights(config)
    except ConfigError as error:
        sys.exit(error.args[0])
    app = SearchTool(
        chosen=chosen,
        weights=weights,
        query=query,
        subdir=subdir,
        kinds=kinds,
        case_sensitive=case_sensitive,
        prior=prior,
    )
    app.sub_title = str(config)
    app.run()
    return 0
