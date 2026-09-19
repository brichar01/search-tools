# search-tool

One command that searches several places with several tools and labels every
result with the tool and directory it came from.

A YAML config file names each place, called a location, and the tools that
search it. Every location comes from that file, so what a search covers is
whatever the file says and nothing else.

It is a jumping off point for the times you cannot remember where something
was, or where you noted it down. Code, notes, shell history, cheatsheets,
manual pages, command help and Confluence each have their own search, and this
runs them together so the answer comes back with the place attached. Searching
that place properly is the step after, not this one.

## Install

The cheatsheets are a submodule, so clone with them:

```sh
git clone --recurse-submodules git@github.com:brichar01/search-tools.git search-tool
cd search-tool
uv sync
```

An existing checkout picks them up with
`git submodule update --init --depth 1`.

To put `search-tool`, `search-tool-precache`, `search-tool-semantic` and
`search-tool-help-index` on the path, install the checkout as a tool. `uv`
writes each script to `~/.local/bin`:

```sh
uv tool install --editable ~/src/search-tool
```

An update is a pull, and the installed scripts follow the checkout:

```sh
git -C ~/src/search-tool pull --recurse-submodules
```

Reinstall with `uv tool install --editable ~/src/search-tool --reinstall` where
a pull adds a dependency or a script.

Installing from GitHub without a checkout works too, and updates with
`uv tool upgrade search-tool`:

```sh
uv tool install git+ssh://git@github.com/brichar01/search-tools.git
git clone --depth 1 https://github.com/tldr-pages/tldr.git ~/.local/share/tldr
```

That install carries the package alone, so the cheatsheets have to be cloned
separately and the `tldr` leaf pointed at them.

## Configure

Start from the example, which lists every location and is written to
`--config`, or to `~/.config/search-tool/config.yml` where that is not given:

```sh
search-tool --init
```

It refuses to overwrite a file that is already there. Then edit it: delete the
locations this machine cannot reach, because a leaf naming a program that is
not installed fails the run.

Each top-level key is a location, apart from `weights`, which holds the tool
weights described under Weights. `directory` is the root to search and accepts
`~` and environment variables. `tools` lists the tools that run there, in order.
`ignore` lists directory names every tool prunes, matched at any depth.

```yaml
source:
  directory: $HOME/src
  tools: [ripgrep, ripgrep-files]
  ignore: [.venv, node_modules, target]

notes:
  directory: $HOME/personal
  tools: [ck, rg]
```

`ast` is left out of the example, because it takes an ast-grep pattern rather
than the query language and runs only under `--kind ast`. Add it to a leaf you
search with patterns.

Delete a leaf, or comment it out, to stop searching that location.

`ignore` takes bare directory names, not paths. Each tool prunes them with its
own flag: `rg --glob=!name/`, `ck --exclude name`, `ast-grep --globs=!name/` and
`search-tool-semantic --skip name`. `man` and `rovo` search no directory, so
they ignore it.

Tool weights are global rather than per location, so `weights` sits beside the
locations rather than inside one.

The file is read from `--config`, from `$SEARCH_TOOL_CONFIG`, or from
`$HOME/.config/search-tool/config.yml`, in that order. Where no file is found,
or it names no location, the search stops and says to run `--init`.

## Shell history

The `hist` tool searches a shell history file. It is `rg` followed by an `awk`
stage that strips the zsh extended-history prefix, so `: 1700000000:0;git
status` reads as `git status`, and keeps the first run of each command, so a
command run fifty times reports once. The command text is the candidate key
rather than a path and line.

Point a leaf at the history file, because `HISTFILE` is a shell variable and is
not exported, so search-tool cannot read it:

```yaml
history:
  directory: $HOME/.histfile
  tools: [hist]
```

The example writes `$HOME/.zsh_history`, which is the zsh default. Change it
where your shell keeps history elsewhere.

## Help pages

`search-tool-help-index` captures the help text of the commands you use and
writes it where the directory tools can search it. Each command writes
`<cmd>_help.txt` from its `--help` output, and `<cmd>_man.txt` from its manual
page where it has one, into `~/.cache/search-tool/help`:

```sh
search-tool-help-index                  # every command in the list
search-tool-help-index git podman       # only these
search-tool-help-index --dry-run
```

Point a leaf at that directory to search it:

```yaml
help:
  directory: $HOME/.cache/search-tool/help
  tools: [fzf, rg, ck, ck-lex]
```

`fzf` matches the file name, so it answers which command it was, `rg` matches
the text of the pages, `ck-lex` ranks them by word frequency and `ck` matches
their meaning. Run `search-tool --precache help` after a capture, because `ck`
indexes the directory.

| Option | Does |
|---|---|
| `-o`, `--output` | Directory to write to, `~/.cache/search-tool/help` by default |
| `-l`, `--list` | File of command names, one per line, the packaged list by default |
| `-t`, `--timeout` | Seconds to wait for each command, 5.0 by default |
| `-f`, `--force` | Recapture pages that are already current |
| `-n`, `--dry-run` | Write what would be captured without capturing it |

A page is recaptured where the program, or the manual page, is newer than what
was written from it, so a second run costs almost nothing. A command that is
not installed is skipped, so one list serves several machines.

The packaged list holds around 200 common commands. Copy it and pass `--list`
to search your own set:

```sh
search-tool-help-index --list ~/.config/search-tool/commands.txt
```

Capturing runs each command. `--help` comes first, and `-h` follows only where
that writes nothing or is rejected, because a program that rejects `--help`
often writes its usage anyway. `shutdown`, `reboot`, `poweroff`, `halt` and
`dd` are never given `-h`, because it acts rather than writing usage. Each run
gets the `--timeout`, closed standard input and a plain terminal.

Only the top-level manual page of a command is captured, so `git_man.txt` holds
`man git` and not `man git-push`. The `man` leaf covers the rest, because
`man -K` searches every installed page.

## Tools

| Tool | Kind | Runs |
|---|---|---|
| `rg`, `ripgrep` | regex | `rg` over the directory |
| `ripgrep-files` | files | `rg --files` over the directory, filtered by the query |
| `fzf`, `fuzzy` | files | `rg --files` over the directory, fuzzy-filtered by the query, best 20, scored by edit distance |
| `ck` | semantic | `ck --sem` over the directory |
| `ck-lex` | lexical | `ck --lex` over the directory, ranked by BM25 |
| `ast`, `ast-grep` | ast | `ast-grep run --pattern` over the directory |
| `hist` | regex | `rg` over the shell history, one hit per distinct command |
| `man` | regex | `man -K -w --regex`, which lists matching manual pages |
| `rovo`, `confluence` | remote | `twg rovo search --app confluence` |

`man` and `rovo` search no directory, so a location that uses only those needs
no `directory`.

`--json` runs each tool in its machine-readable mode instead: `rg --json`,
`ck --jsonl`, `search-tool-semantic --json`, `ast-grep run --json=compact` and
`twg rovo search --output json`.
`ripgrep-files`, `fzf`, `hist` and `man` list their output either way. Some `twg` versions write the
search payload to a temporary file and print an envelope naming it, which the
parser follows.

## Search

```sh
search-tool "saturation" source notes        # two locations
search-tool "saturation"                     # every location in the config
search-tool "saturation" source --subdir 'proj-*'
search-tool "saturation" history                # what you ran before
search-tool "saturation" --kind semantic --kind regex
search-tool "saturation" --kind '!remote'
search-tool 'def $F($$$)' source --kind ast   # an ast-grep pattern
search-tool "Saturation" --case-sensitive
search-tool "saturation" --json
```

The first positional is the query, written in the language the next section
describes. The rest name the locations to search, and naming none searches
them all.

`--subdir` is a glob matched against each location directory, so `proj-*`
picks children and `*/tests` picks a level deeper. It only limits tools that
search a directory. A location with no matching subdirectory is not searched.

`--kind` is repeatable and limits the run to those kinds of search. Without it
every kind but `ast` runs, because an ast-grep pattern is a language of its
own. `--kind ast` searches with one.

A kind prefixed with `!` is dropped instead, so `--kind '!remote'` runs every
kind but `remote` and `ast`. Naming no kind to keep starts from every kind but
`ast`, and naming some starts from those, so `--kind regex --kind '!regex'`
runs nothing. Quote the argument, because an unquoted `!` is history expansion
in bash and zsh.

## App

`--tui` opens the same searches on a screen instead of writing them out. It
takes the command line the search takes, and the query is optional, so
`search-tool --tui` opens with an empty box:

```sh
search-tool --tui "saturation"
search-tool --tui "saturation" source notes
search-tool --tui
```

The query box searches a second after the typing stops, and Enter searches
without waiting. The targets come back ranked the way `--json` ranks them, and
the pane beside them holds the spans behind whichever target is selected, each
labelled with the searches that reported it.

Enter on a target opens it in `$VISUAL`, or `$EDITOR` where that is unset, at
the line of its strongest span. The app steps aside until the editor exits.
`vi`, `vim`, `nvim`, `view`, `gvim`, `nano`, `pico`, `emacs`, `emacsclient` and
`kak` are opened at the line with `+17`, `code`, `codium` and `code-insiders`
with `-g`, and `hx`, `helix`, `subl`, `sublime_text` and `micro` with
`path:17`. Any other editor opens the file at the top. A target that is not a
file has nothing to open, so a shell command, a manual page and a Confluence
page say so instead.

The two lists on the left switch the locations and the tools on and off, and
switching one searches again after the same wait. They start from what the
command line selected, so `--kind` sets which tools are on at startup and `ast`
is off until it is switched on.

| Key | Does |
|---|---|
| `enter` | Search for what is in the box, or open the selected target |
| `ctrl+r` | Search again |
| `ctrl+f` | Put the cursor back in the box |
| `ctrl+b` | Show or hide the two lists |
| `ctrl+q` | Quit |

The colours are the nordfox palette.

## Query

The query is one language, parsed once and written out again in the syntax of
each tool:

```sh
search-tool 'cache size'                     # both words, in either order
search-tool '"open file"'                    # the phrase, matched literally
search-tool '/def\s\w+_files/'               # a regular expression
search-tool 'read OR write'                  # either word
search-tool 'cache -test'                    # cache, where test does not match
search-tool 'cache NOT test'                 # the same, written out
search-tool 'path:*.py cache'                # only the Python files
search-tool 'path:src/** cache'              # only the files under src
search-tool 'path:*.py read OR write'       # forms combine
```

| Written | Means |
|---|---|
| `word` | Match the word. Several words all have to match, within one line where the tool matches lines |
| `"a phrase"` | Match the text as written |
| `/pattern/` | Match the regular expression. Whitespace separates terms, so a space is written `\s` |
| `a OR b` | Match either. `OR` binds tighter than the space between terms |
| `-word`, `NOT word` | Drop what matches it |
| `path:GLOB`, `file:GLOB` | Search only the files the glob names. A glob holding no `/` matches the file name, and one holding a `/` matches a path at any depth |

Quote the whole query in the shell, because `*`, `!` and `$` are the shell's
before they are the query's.

A path glob is read at any depth, so `path:src/**` is every `src` directory
under the location rather than one at its root. `--subdir` is the flag that
narrows to a directory at the root. ripgrep and ast-grep match a glob against
the path they print, which is absolute here, so the glob carries a `**/` into
each of them and reads the same way in all three.

Each tool is handed as much of that language as it writes itself:

| Tool | Given | Cannot express |
|---|---|---|
| `rg`, `ripgrep-files`, `hist`, `man` | One regular expression, each literal escaped | negation, more than three terms at once |
| `fzf` | The extended search syntax, a word fuzzy and a phrase exact | a regular expression, a term holding a space |
| `ck`, `ck-lex` | The words of the query, split out of each identifier | negation, a regular expression, a path filter |
| `rovo` | Confluence text search, with its own `AND`, `OR` and `NOT` | a regular expression, a path filter |
| `ast` | The query as typed | anything but words and a path filter |

Two words are one regular expression matching a line that holds both in either
order, so `cache size` runs as `(cache).*(size)|(size).*(cache)`. Neither POSIX
nor the Rust regex engine has lookaround, which is why a fourth term and a
negated term have nowhere to go.

`ck` ranks by meaning and `ck-lex` by word frequency, so neither holds any
operator at all. `OR` and the
space between terms both flatten into words, and each identifier is split, so
`build_candidates` is embedded as `build candidates`.

A tool runs only where it can write the whole query. Where it cannot, the
search is skipped and says what it could not express, rather than searching for
something looser:

```sh
search-tool 'cache -test' notes
```

```
== [notes] ck /home/you/personal ==
skipped: cannot express negation
```

A skipped search runs nothing, so it is neither a match nor a failure and the
exit status does not change. `--json` reports it as a `search` record with an
empty `command` and the same reason in `skipped`.

`ast` is a second class search here. An ast-grep pattern is code holding
metavariables, a language of its own rather than a subset of this one, so
nothing lowers into it and it is handed the query as typed. Anything past bare
words and a path filter skips it, and `--kind` leaves it out by default.

## Case

Every search folds case, so `saturation` and `Saturation` return the same
lines. `-S`, `--case-sensitive` matches the query as it is written instead.

| Tool | Folded | Case-sensitive |
|---|---|---|
| `rg`, `ripgrep-files`, `hist` | `--ignore-case` | `--case-sensitive` |
| `fzf` | `-i` | `+i` |
| `ck`, `ck-lex` | `-i` | the ck default |
| `man` | `-i` | `-I` |
| `ast` | neither, an ast-grep pattern matches syntax nodes | |
| `rovo` | neither, Confluence matches its own way | |

The flag is passed both ways where a tool takes one, so a `RIPGREP_CONFIG_PATH`
file or an fzf default cannot turn folding back on under `--case-sensitive`.
`ast` and `rovo` return the same results either way, so a case-sensitive run
still has to read them.

## Precache

`ck` builds its index during the first semantic or lexical search of a
directory, which makes that search slow. `--precache` builds those indexes ahead of time and
searches nothing, so it takes locations where the search takes a query:

```sh
search-tool --precache                  # every location that uses ck or ck-lex
search-tool --precache source notes
search-tool --precache source --subdir 'proj-*'
```

`search-tool-precache` is the same thing as its own command, and adds
`--dry-run`, which lists the directories without indexing them:

```sh
search-tool-precache source
search-tool-precache --dry-run
```

Either way it reads the same `--config` and `--subdir` as the search, picks every directory an indexed tool searches, and runs `ck --index`
over each one. A directory named by several locations is indexed once. Exit
status is 2 where an index build failed.

## Semantic lines

`search-tool-semantic` ships with this package and searches on its own, apart
from the aggregate. No location can name it, because a location searches with
tools that lower the query language and this takes a query of its own. It embeds
every line with a model2vec static model and returns the lines closest to the
query by cosine similarity. Both the query and the lines are lower-cased first,
which is as close to case-insensitive as one fixed vector per token gets. The model is a lookup table rather than a network,
so it loads in under a second and needs no index.

It reads standard input where no path is given, so it sits in a pipe:

```sh
git log -p | search-tool-semantic "changes to the licence check"
search-tool-semantic "storing records" src --top-k 5
rg -n "def " src | search-tool-semantic "build the search plan" --threshold 0.4
```

| Option | Does |
|---|---|
| `-k`, `--top-k` | How many lines to return, 10 by default |
| `-t`, `--threshold` | Lowest cosine similarity to return, 0.0 by default |
| `-m`, `--model` | Model to load, `minishlab/potion-base-8M` by default |
| `-S`, `--case-sensitive` | Embed the query and the lines as written |
| `--skip` | Directory name to prune, repeatable |
| `--include` | Glob naming the files to read, repeatable, all of them by default |
| `--json` | One JSON record per line, with its score |

Text output is `source:line:text`, where `source` is `-` for standard input.
Lines that are blank, files that are not text, paths holding a dot component,
`.git` among them, paths under a `--skip` name and paths no `--include` glob
names are all skipped. Standard input is one stream rather than a tree, so
`--skip` and `--include` do not reach it.

```sh
search-tool-semantic "storing records" src --include '*.py' --skip __pycache__
```

The first run downloads the model from Hugging Face, around 30 MB, and caches
it under `$HF_HOME`. Runs after that need no network. Exit status is 2 where
the model cannot be loaded, 0 where anything ranked above the threshold, and 1
where nothing did.

## Output

Text output prepends a header to each search:

```
== [source] rg /home/you/src/proj-analyser ==
```

`--json` parses what every tool returned and writes one JSON record per line.
Every search is reported first, then the scored targets:

```json
{"type": "search", "location": "source", "tool": "rg", "kind": "regex",
 "directory": "/home/you/src", "command": [["rg", "--json", "..."]],
 "skipped": null, "exit_code": 0, "candidates": 2, "stderr": ""}
{"type": "target", "query": "saturation", "key": "/home/you/src/report.py",
 "kind": "file", "votes": 1.6, "reach": 2.6, "relevance": 0.444,
 "candidates": [
   {"key": "/home/you/src/report.py", "kind": "file", "line": 18,
    "end_line": 22, "text": "...", "votes": 1.6, "sources": [
      {"location": "source", "tool": "ck", "directory": "/home/you/src",
       "rank": 1, "score": 0.84},
      {"location": "source", "tool": "rg", "directory": "/home/you/src",
       "rank": 3, "score": null}]},
   {"key": "/home/you/src/report.py", "kind": "file", "line": 51,
    "end_line": 51, "text": "...", "votes": 1.0, "sources": [
      {"location": "source", "tool": "rg", "directory": "/home/you/src",
       "rank": 4, "score": null}]}]}
```

A target is one file, shell command, manual page or remote page. `key` is the
absolute path, the command text or the URL, and `kind` is `file`, `command`,
`manual` or `remote`. `votes`, `reach` and `relevance` are its score, described
under Ranking below.

`candidates` holds every span the searches reported against that key, so a
caller can show the score against the file and still jump to a line or offer
the chunk behind it. They come out strongest first, a span before a whole file,
then by line.

Hits that share a key merge where their line spans overlap, so the line `rg`
matched and the chunk `ck` returned around it become one candidate holding both
sources. Hits that name no span, from `ripgrep-files`, `fzf`, `hist` and `man`,
merge with each other and keep a candidate of their own. `text` is the longest
text any source reported. Each source keeps the `rank` it held within its own
search, and the `score` where the tool reports one. A candidate holds the
`votes` its own sources cast, which orders the spans inside a target and never
scores the target itself.

Colour codes are stripped from `text` and `stderr`. `command` is a pipeline,
one argument list per stage, and `exit_code` is the highest exit code in it.
The `candidates` count on a `search` record is the spans that search
contributed, not the targets it reached.

Exit status is 2 where a tool failed, 0 where anything was found, and 1 where
nothing was. In `--json` mode that means one target or more.

## Ranking

Targets come out scored, the highest first and then by key. The score divides
what the searches contributed by the searches that could have returned the
target:

```
relevance = votes / (reach + prior)
```

The unit scored is the key, not the span. Spans agree only where they overlap,
so two tools that both found a file would corroborate each other only where
their chunk boundaries happen to meet, and a tool that names whole files would
never corroborate anything. A key is the one identity every tool reports.

`votes` counts one search at a time, not one hit at a time. `rg` reports every
matching line of a file and a semantic search reports the few chunks it ranked,
so summing the hits would score a file by how loudly one tool matched it rather
than by how many tools agreed. Each search is taken at its best hit against
that key.

A hit says one where the tool reports no score, so `rg`, `rg-files`, `hist`,
`man` and `ast` say a match and nothing more. A tool that scores its hits, `ck`
and `ck-lex`, is spread from 0 to 1 across the range of scores that one search
returned, because two tools that both score do not share a scale.

`fzf` matches almost every path of a tree, so a hit of its own would carry the
whole vote a match carries. It is scored here instead of taken at one, at
`log10(10 - 9 * edits / len(term))`, where `edits` is the fewest edits from a
query term to the part of the path closest to it. Scaling by the length of the
term spends the whole curve on every term, since the furthest a term can sit
from a window of a path is its own length. A typo in a six-letter term is worth
0.93 of a vote, half the term rewritten is worth 0.74 and a term nothing of the
path matches is worth nothing. A path is taken at the term it scores best on.
The score is already written on the shared scale, so the run does not spread it
the way it spreads `ck`.

Ordering is never read as relevance, since ripgrep returns files in the order it
walked them and a rank taken from that carries nothing.

`reach` is the summed weight of the searches that could have returned the
target. A search reaches a target when it ran, when its tool finds that kind of
thing, and, for a file, when the path lies inside the directory searched. A
skipped search and a failed search reach nothing, so their silence counts
against nothing. A search that ran and found nothing does count.

Dividing by the reach rather than by every search of a run is what keeps one
kind of result comparable to another. One `man` search covers the manual pages
and five searches may cover a source tree, so a page `man` found is scored out
of one and a file one of five searches found is scored out of five. Summing the
agreement alone would rank the file above the page whatever either one holds.
Inside one location the reach is the same for every file, so the correction does
its work between locations, between kinds, and wherever a tool was skipped or
failed.

`prior` is the weight of a notional search that found nothing, and `--prior`
sets it. It stops a target found by the one search able to reach it from
outscoring a target three of four searches found. `--prior 0` scores the bare
agreement rate, where one search of one reaches the top.

## Weights

What one vote is worth is per tool, and `weights` in the config file sets it:

```yaml
weights:
  ck: 0.6
  ck-lex: 0.6
```

A weight counts into the reach as well as the vote. A tool held at 0.6 that
agrees adds 0.6 to both, so downweighting a tool cannot cap the score of a
location that uses it, and a tool at 0 is left out of the score entirely.
Agreement from a downweighted tool alone is worth less than agreement from a
full one: `ck` on its own scores 0.6 against a reach of 0.6, and `rg` on its own
scores 1 against a reach of 1.

`ck` and `ck-lex` ship at 0.6 because they read the one index, so the two of
them agreeing says less than two tools that looked for different things. The
weight is per tool rather than per pair, so it also discounts `ck` in a location
where `ck-lex` does not run. Raise either to 1 to have it counted in full.

`weights` is a reserved top-level name, so no location can be called it. A tool
left out keeps the weight it declares, which is 1 for everything but the two ck
searches.

Only `--json` ranks. Text output writes each search as it finishes, in the order
the searches ran.
