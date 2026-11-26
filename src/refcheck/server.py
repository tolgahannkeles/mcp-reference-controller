"""MCP server exposing the reference checker as tools."""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from typing import Any

from mcp.server.mcpserver import MCPServer

from .bibtex import to_bibtex
from .config import Settings
from .http import HttpClient
from .models import Status
from .normalize import normalize_doi
from .parsing import parse_input
from .verify import Verifier

MAX_REFERENCES = 300

INSTRUCTIONS = """\
Reference checker for academic writing. It looks references up in Crossref and
OpenAlex to catch fabricated (hallucinated) or mis-cited references.

- Before a manuscript or reference list is finalized, run `check_references` on it.
- Never invent a reference. When a claim needs a citation, use `search_literature`
  and cite only works it returns.
- For every reference with status not_found or needs_correction, tell the author
  clearly, show the corrected data or the 'did_you_mean' candidates, and do not
  silently keep the original.
- not_found means no index has the work: treat as likely fabricated, but say that
  the author should double-check. unverifiable means the source type (book, thesis,
  web page) is often unindexed and needs a manual check.
"""

mcp = MCPServer("refcheck", instructions=INSTRUCTIONS)

_verifier: Verifier | None = None


def _get_verifier() -> Verifier:
    global _verifier
    if _verifier is None:
        _verifier = Verifier(HttpClient(Settings()))
    return _verifier


@mcp.tool()
async def check_references(references: str) -> dict[str, Any]:
    """Check a whole reference list for fabricated or incorrect references.

    `references` may be BibTeX (one or more @entries) or a pasted reference list in
    any common style (APA, IEEE, ...), one reference per line, numbered ([1], 1.),
    or separated by blank lines.

    Returns a summary count per status and, for each reference: status
    (verified / needs_correction / possible_match / not_found / unverifiable / error),
    the matched real record, field-level issues with corrections, 'did_you_mean'
    candidates, and corrected BibTeX where useful.
    """
    refs = parse_input(references)
    if not refs:
        return {"error": "No references found in the input."}
    truncated = len(refs) > MAX_REFERENCES
    refs = refs[:MAX_REFERENCES]

    verifier = _get_verifier()
    sem = asyncio.Semaphore(4)

    async def one(i: int, r):
        async with sem:
            d = (await verifier.verify(r)).to_dict()
        d["index"] = i + 1
        if r.key:
            d["key"] = r.key
        return d

    results = await asyncio.gather(*(one(i, r) for i, r in enumerate(refs)))
    counts = Counter(r["status"] for r in results)
    out: dict[str, Any] = {
        "total": len(results),
        "summary": {s.value: counts.get(s.value, 0) for s in Status if counts.get(s.value)},
        "results": results,
    }
    if truncated:
        out["note"] = f"Only the first {MAX_REFERENCES} references were checked."
    return out


@mcp.tool()
async def verify_reference(reference: str) -> dict[str, Any]:
    """Check a single reference (a formatted citation string or one BibTeX entry).

    Use this while writing, e.g. right before inserting a citation. See
    `check_references` for the meaning of the returned fields.
    """
    refs = parse_input(reference)
    if not refs:
        return {"error": "Could not read a reference from the input."}
    return (await _get_verifier().verify(refs[0])).to_dict()


@mcp.tool()
async def search_literature(
    query: str, limit: int = 5, year_from: int | None = None, year_to: int | None = None
) -> list[dict[str, Any]]:
    """Find REAL papers for a topic or claim (OpenAlex), each with ready BibTeX.

    Use this instead of writing references from memory. `query` can be keywords or
    the sentence that needs a citation. Results include citation counts to help pick
    well-established sources.
    """
    limit = max(1, min(limit, 20))
    recs = await _get_verifier().openalex.search(query, rows=limit, year_from=year_from, year_to=year_to)
    return [{**r.to_dict(), "bibtex": to_bibtex(r)} for r in recs]


@mcp.tool()
async def get_bibtex(doi: str) -> str:
    """Return a correct BibTeX entry for a DOI, built from Crossref (or OpenAlex) metadata."""
    norm = normalize_doi(doi)
    if not norm:
        return "Invalid DOI."
    v = _get_verifier()
    rec = await v.crossref.get_by_doi(norm) or await v.openalex.get_by_doi(norm)
    if rec is None:
        return f"No metadata found for DOI {norm}. It may not exist."
    return to_bibtex(rec)


def main() -> None:
    logging.getLogger("httpx").setLevel(logging.WARNING)
    mcp.run("stdio")


if __name__ == "__main__":
    main()
