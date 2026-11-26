# refcheck: Reference Checker MCP Server

An MCP server that helps authors catch **fabricated (hallucinated) or mis-cited
references** before submission, especially when writing with AI assistance.
It looks each reference up in Crossref and OpenAlex, compares the cited details
field by field with the real record, and returns a corrected BibTeX entry.

## Tools

| Tool | What it does |
|---|---|
| `check_references` | Checks a whole reference list (BibTeX, or plain text in APA, IEEE, ...) |
| `verify_reference` | Checks a single reference |
| `search_literature` | Finds **real** papers for a topic or claim, with ready BibTeX |
| `get_bibtex` | Builds a correct BibTeX entry for a DOI |

### Result statuses

| Status | Meaning |
|---|---|
| `verified` | A real record matches and the cited details agree (minor notes possible) |
| `needs_correction` | The work exists but the citation has errors (year, authors, DOI, retracted...). A corrected BibTeX is included |
| `possible_match` | A similar work exists but the match is uncertain. The author should check |
| `not_found` | No source has it: **likely fabricated**. Close candidates, if any, are listed under `did_you_mean` |
| `unverifiable` | A source type often missing from indexes (book, thesis, report, web page). Check manually |
| `error` | The sources could not be reached |

Detected problems: fully fabricated works, real titles with fabricated authors,
non-existent DOIs, DOIs belonging to another paper, wrong year/volume/pages,
retracted papers, and fabricated subtitles added to real titles.

## Installation

```powershell
git clone <repo-url> refcheck
cd refcheck
python -m venv .venv
.\.venv\Scripts\pip install -e .
```

On macOS/Linux use `python3 -m venv .venv` and `.venv/bin/pip install -e .`.

## Connecting to an AI client

refcheck is a standard **stdio** MCP server, so it works with any MCP-capable
client. Every client needs the same two things:

- **command**: the server executable
  - Windows: `C:\path\to\refcheck\.venv\Scripts\refcheck-mcp.exe`
  - macOS/Linux: `/path/to/refcheck/.venv/bin/refcheck-mcp`
- **env** (optional): `REFCHECK_MAILTO=lab-contact@example.edu`

Only the config file location and format differ. In JSON on Windows, write
backslashes in paths as `\\`. After changing a config, restart the client (or
reload the window) and approve the server when asked.

Once connected, ask for example: *"Check this reference list: ..."* or
*"Find real sources for this paragraph."*

### Claude Code (CLI and VS Code / JetBrains extensions)

Per project, create `.mcp.json` in the root of the folder you write in:

```json
{
  "mcpServers": {
    "refcheck": {
      "command": "C:\\path\\to\\refcheck\\.venv\\Scripts\\refcheck-mcp.exe",
      "env": { "REFCHECK_MAILTO": "lab-contact@example.edu" }
    }
  }
}
```

Or for all projects:

```powershell
claude mcp add --scope user refcheck -e REFCHECK_MAILTO=lab-contact@example.edu -- C:\path\to\refcheck\.venv\Scripts\refcheck-mcp.exe
```

Run `/mcp` in a new session to confirm that `refcheck` is connected.

### Claude Desktop

Add the same `mcpServers` block to `claude_desktop_config.json`
(Windows: `%APPDATA%\Claude\`, macOS: `~/Library/Application Support/Claude/`).

### VS Code with GitHub Copilot (agent mode)

Create `.vscode/mcp.json` in the workspace (or run **MCP: Add Server** from the
command palette to add it to your user settings). Note the top-level key is
`servers` and the `type` field:

```json
{
  "servers": {
    "refcheck": {
      "type": "stdio",
      "command": "C:\\path\\to\\refcheck\\.venv\\Scripts\\refcheck-mcp.exe",
      "env": { "REFCHECK_MAILTO": "lab-contact@example.edu" }
    }
  }
}
```

Open Copilot Chat in **Agent** mode; the refcheck tools appear under the tools icon.

### Cursor

`.cursor/mcp.json` in the project, or `~/.cursor/mcp.json` for all projects.
Same `mcpServers` block as Claude Code above. Check **Settings → MCP** for a
green status.

### Windsurf

`~/.codeium/windsurf/mcp_config.json` (or **Settings → Cascade → MCP Servers →
View raw config**). Same `mcpServers` block.

### Cline (VS Code extension)

Open the **MCP Servers** panel in Cline → **Configure MCP Servers**, and add the
same `mcpServers` block to `cline_mcp_settings.json`.

### Continue (VS Code / JetBrains extension)

Create `.continue/mcpServers/refcheck.yaml` in the workspace:

```yaml
name: refcheck
version: 0.0.1
schema: v1
mcpServers:
  - name: refcheck
    command: C:\path\to\refcheck\.venv\Scripts\refcheck-mcp.exe
    env:
      REFCHECK_MAILTO: lab-contact@example.edu
```

MCP tools are available in Continue's **Agent** mode.

### Gemini CLI

Add the same `mcpServers` block to `~/.gemini/settings.json` (or
`.gemini/settings.json` in the project).

### OpenAI Codex CLI

Add to `~/.codex/config.toml`:

```toml
[mcp_servers.refcheck]
command = 'C:\path\to\refcheck\.venv\Scripts\refcheck-mcp.exe'
env = { REFCHECK_MAILTO = "lab-contact@example.edu" }
```

### Other clients

Any client that supports stdio MCP servers works: point it at the executable
above. Config locations change between client versions; if a path here is out
of date, check the client's MCP documentation.

### Troubleshooting

- **Server does not start:** run the executable directly in a terminal. It should
  wait silently for input (stop it with Ctrl+C). An error here means the
  installation is broken; rerun `pip install -e .`.
- **Tools do not appear:** make sure the client is in agent/tool mode and was
  restarted after the config change.
- **Timeouts or `error` results:** the machine needs internet access to
  `api.crossref.org`, `api.openalex.org` and `doi.org`.

## Configuration (environment variables)

| Variable | Description |
|---|---|
| `REFCHECK_MAILTO` | Contact e-mail sent to Crossref/OpenAlex. Puts requests in the "polite pool", which is faster and more reliable. **Recommended.** |
| `REFCHECK_OPENALEX_API_KEY` | (Optional) OpenAlex API key for heavy use |
| `REFCHECK_CACHE` | Cache file path (default `%LOCALAPPDATA%\refcheck\cache.sqlite3`); set to `off` to disable |

Responses are cached for 30 days, so re-checking the same reference does not hit the APIs.

## Development

```powershell
.\.venv\Scripts\pip install -e ".[dev]"
.\.venv\Scripts\python -m pytest              # offline tests
.\.venv\Scripts\python -m pytest -m live      # end-to-end tests against the real APIs
```

Code layout (`src/refcheck/`):

- `parsing.py`: parses BibTeX and plain-text reference lists
- `sources.py`: Crossref, OpenAlex and doi.org clients
- `verify.py`: matching and decision logic (`assess()` is a pure function, easy to test)
- `normalize.py`: text normalization (Turkish characters, LaTeX) and similarity measures
- `bibtex.py`: BibTeX generation from verified records
- `server.py`: MCP tools

## Limitations and roadmap

- Books, theses and local Turkish journals may be missing from the indexes
  (`unverifiable`). **DergiPark** and **TR Dizin** support is next.
- More sources per field: arXiv, DBLP, PubMed, Semantic Scholar.
- Extracting reference lists from PDF and Word drafts (GROBID).
- Author plausibility (do the authors exist and publish in this area?).
- Whether a cited work actually supports the claim it is cited for.
- Citation style checking (APA, IEEE, ...).
