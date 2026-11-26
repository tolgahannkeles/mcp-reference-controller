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

### Claude Code (CLI or VS Code extension)

Per project: create `.mcp.json` in the root of the folder you write in
(adjust the path to your installation):

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

For all projects:

```powershell
claude mcp add --scope user refcheck -e REFCHECK_MAILTO=lab-contact@example.edu -- C:\path\to\refcheck\.venv\Scripts\refcheck-mcp.exe
```

Start a new session and run `/mcp` to confirm `refcheck` is connected.

### Claude Desktop

Add the same `mcpServers` block to `%APPDATA%\Claude\claude_desktop_config.json`.

Then ask, for example: *"Check this reference list: ..."* or
*"Find real sources for this paragraph."*

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
