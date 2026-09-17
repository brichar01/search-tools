# search-tool

One command that searches several places with several tools and labels every
result with the tool and directory it came from.

A YAML config file names each place, called a location, and the tools that
search it. Three locations are built in and need no config: the tldr
cheatsheets, the system manual pages, and Confluence.

## Install

The cheatsheets are a submodule, so clone with them:

```sh
git clone --recurse-submodules <url> search-tool
cd search-tool
uv sync
```

An existing checkout picks them up with
`git submodule update --init --depth 1`.

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
`$XDG_CONFIG_HOME/search-tool/config.yml`, in that order. Where no file is
found, only the built-in locations are searched.

A location whose name matches a built-in replaces it.

## Tools

| Tool | Kind | Runs |
|---|---|---|
| `rg`, `ripgrep` | regex | `rg` over the directory |
| `ripgrep-files` | files | `rg --files` over the directory, filtered by the query |
| `ck` | semantic | `ck --sem` over the directory |
| `ast`, `ast-grep` | ast | `ast-grep run --pattern` over the directory |
| `man` | regex | `man -K -w --regex`, which lists matching manual pages |
| `rovo`, `confluence` | remote | `twg rovo search --app confluence` |

`man` and `rovo` search no directory, so a location that uses only those needs
no `directory`.

`--json` runs each tool in its machine-readable mode instead: `rg --json`,
`ck --jsonl`, `ast-grep run --json=compact` and `twg rovo search --output json`.
`ripgrep-files` and `man` list paths either way. Some `twg` versions write the
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
