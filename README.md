# search-tool

One command that searches several places with several tools and labels every
result with the tool and directory it came from.

A YAML config file names each place, called a location, and the tools that
search it. Three locations are built in and need no config: the tldr
cheatsheets, the system manual pages, and Confluence.

## Install

The cheatsheets are a submodule, so clone with them:

```sh
git clone --recurse-submodules git@github.com:brichar01/search-tools.git search-tool
cd search-tool
uv sync
```

An existing checkout picks them up with
`git submodule update --init --depth 1`.

To put `search-tool` and `search-tool-precache` on the path, install the
checkout as a tool. `uv` writes both scripts to `~/.local/bin`:

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
export SEARCH_TOOL_TLDR_DIR=~/.local/share/tldr/pages
```

That install carries the package alone, so the cheatsheets it searches have to
be cloned separately and named by `$SEARCH_TOOL_TLDR_DIR`. Without them every
tldr search fails with `No such file or directory`.

## Configure

Each top-level key is a location. `directory` is the root to search and accepts
`~` and environment variables. `tools` lists the tools that run there, in order.

```yaml
source:
  directory: $HOME/src
  tools: [ast, ripgrep, ripgrep-files]

notes:
  directory: $HOME/personal
  tools: [ck, rg]
```

The file is read from `--config`, from `$SEARCH_TOOL_CONFIG`, or from
`$HOME/.config/search-tool/config.yml`, in that order. Where no file is found,
only the built-in locations are searched.

A location whose name matches a built-in replaces it.

## Tools

| Tool | Kind | Runs |
|---|---|---|
| `rg`, `ripgrep` | regex | `rg` over the directory |
| `ripgrep-files` | files | `rg --files` over the directory, filtered by the query |
| `fzf`, `fuzzy` | files | `rg --files` over the directory, fuzzy-filtered by the query |
| `ck` | semantic | `ck --sem` over the directory |
| `m2v`, `model2vec` | semantic | `search-tool-semantic` over the directory |
| `ast`, `ast-grep` | ast | `ast-grep run --pattern` over the directory |
| `man` | regex | `man -K -w --regex`, which lists matching manual pages |
| `rovo`, `confluence` | remote | `twg rovo search --app confluence` |

`man` and `rovo` search no directory, so a location that uses only those needs
no `directory`.

`--json` runs each tool in its machine-readable mode instead: `rg --json`,
`ck --jsonl`, `search-tool-semantic --json`, `ast-grep run --json=compact` and
`twg rovo search --output json`.
`ripgrep-files`, `fzf` and `man` list paths either way. Some `twg` versions write the
search payload to a temporary file and print an envelope naming it, which the
parser follows.

## Search

```sh
search-tool "saturation" source notes        # two locations
search-tool "saturation"                     # every location, built-ins included
search-tool "saturation" source --subdir 'am100-*'
search-tool "saturation" --kind semantic --kind regex
search-tool "saturation" --json
```

The first positional is the query. The rest name the locations to search, and
naming none searches them all.

`--subdir` is a glob matched against each location directory, so `am100-*`
picks children and `*/tests` picks a level deeper. It only limits tools that
search a directory. A location with no matching subdirectory is not searched.

`--kind` is repeatable and limits the run to those kinds of search. Without it
every tool of every selected location runs.

## Precache

`ck` builds its index during the first semantic search of a directory, which
makes that search slow. `--precache` builds those indexes ahead of time and
searches nothing, so it takes locations where the search takes a query:

```sh
search-tool --precache                  # every location that uses ck
search-tool --precache source notes
search-tool --precache source --subdir 'am100-*'
```

`search-tool-precache` is the same thing as its own command, and adds
`--dry-run`, which lists the directories without indexing them:

```sh
search-tool-precache source
search-tool-precache --dry-run
```

Either way it reads the same `--config`, `--subdir` and `--tldr-dir` as the
search, picks every directory an indexed tool searches, and runs `ck --index`
over each one. `m2v` keeps no index, so it needs none of this. A directory named by several locations is indexed once. Exit
status is 2 where an index build failed.

## Semantic lines

`m2v` runs `search-tool-semantic`, which ships with this package. It embeds
every line with a model2vec static model and returns the lines closest to the
query by cosine similarity. The model is a lookup table rather than a network,
so it loads in under a second and needs no index.

It is also a command of its own, and reads standard input where no path is
given, which is what makes it the one semantic tool that can sit in a pipe:

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
| `--json` | One JSON record per line, with its score |

Text output is `source:line:text`, where `source` is `-` for standard input.
Lines that are blank, files that are not text, and paths holding a dot
component, `.git` among them, are all skipped.

The first run downloads the model from Hugging Face, around 30 MB, and caches
it under `$HF_HOME`. Runs after that need no network. Exit status is 2 where
the model cannot be loaded, 0 where anything ranked above the threshold, and 1
where nothing did.

## Output

Text output prepends a header to each search:

```
== [source] rg /home/benri/src/am100-analyser ==
```

`--json` parses what every tool returned and writes one JSON record per line.
Every search is reported first, then the merged candidates:

```json
{"type": "search", "location": "source", "tool": "rg", "kind": "regex",
 "directory": "/home/benri/src", "command": [["rg", "--json", "..."]],
 "exit_code": 0, "candidates": 2, "stderr": ""}
{"type": "candidate", "query": "saturation", "key": "/home/benri/src/probe.py",
 "kind": "file", "line": 18, "end_line": 22, "text": "...", "sources": [
   {"location": "source", "tool": "ck", "directory": "/home/benri/src",
    "rank": 1, "score": 0.84},
   {"location": "source", "tool": "rg", "directory": "/home/benri/src",
    "rank": 3, "score": null}]}
```

A candidate is one file span, manual page or remote page. `key` is the absolute
path or the URL, and `kind` is `file`, `manual` or `remote`.

Hits that share a key merge where their line spans overlap, so the line `rg`
matched and the chunk `ck` returned around it become one candidate holding both
sources. Hits that name no span, from `ripgrep-files` and `man`, merge with each
other and keep a candidate of their own. `text` is the longest text any source
reported. Each source keeps the `rank` it held within its own search, and the
`score` where the tool reports one.

Candidates come out ordered by key, then by line. Nothing ranks them against
each other yet. Colour codes are stripped from `text` and `stderr`.

`command` is a pipeline, one argument list per stage, and `exit_code` is the
highest exit code in it.

Exit status is 2 where a tool failed, 0 where anything was found, and 1 where
nothing was. In `--json` mode that means one candidate or more.
