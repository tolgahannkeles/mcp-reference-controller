"""Clients for scholarly indexes. Each returns normalized Record objects."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from .http import HttpClient, NotFound
from .models import Record
from .normalize import normalize_doi

_TAG = re.compile(r"<[^>]+>")


def _clean(s: str | None) -> str | None:
    if not s:
        return None
    return " ".join(_TAG.sub("", s).split()) or None


# ---------------------------------------------------------------- Crossref

class Crossref:
    name = "crossref"
    base = "https://api.crossref.org"
    _select = "DOI,title,subtitle,author,issued,container-title,volume,issue,page,type,URL"

    def __init__(self, http: HttpClient):
        self.http = http

    def _params(self, extra: dict | None = None) -> dict:
        p = dict(extra or {})
        if self.http.settings.mailto:
            p["mailto"] = self.http.settings.mailto
        return p

    async def get_by_doi(self, doi: str) -> Record | None:
        try:
            body = await self.http.get_json(f"{self.base}/works/{quote(doi, safe='/')}", self._params())
        except NotFound:
            return None
        return parse_crossref(body["message"])

    async def search(self, query: str, rows: int = 5) -> list[Record]:
        body = await self.http.get_json(
            f"{self.base}/works",
            self._params({"query.bibliographic": query[:500], "rows": rows, "select": self._select}),
        )
        return [r for r in (parse_crossref(i) for i in body["message"]["items"]) if r]


def parse_crossref(m: dict[str, Any]) -> Record | None:
    title = _clean((m.get("title") or [None])[0])
    if not title:
        return None
    subtitle = _clean((m.get("subtitle") or [None])[0])
    if subtitle and subtitle.lower() not in title.lower():
        title = f"{title}: {subtitle}"
    authors, families = [], []
    for a in m.get("author") or []:
        family = a.get("family") or a.get("name")
        if not family:
            continue
        families.append(family)
        authors.append(" ".join(p for p in (a.get("given"), family) if p))
    parts = (m.get("issued") or {}).get("date-parts") or [[None]]
    year = parts[0][0] if parts and parts[0] else None
    return Record(
        source="crossref",
        title=title,
        authors=authors,
        family_names=families,
        year=year,
        venue=_clean((m.get("container-title") or [None])[0]),
        doi=normalize_doi(m.get("DOI")),
        volume=m.get("volume"),
        issue=m.get("issue"),
        pages=m.get("page"),
        type=m.get("type"),
        url=m.get("URL"),
    )


# ---------------------------------------------------------------- OpenAlex

class OpenAlex:
    name = "openalex"
    base = "https://api.openalex.org"
    _select = (
        "id,doi,display_name,authorships,publication_year,primary_location,"
        "biblio,type,is_retracted,cited_by_count"
    )

    def __init__(self, http: HttpClient):
        self.http = http

    def _params(self, extra: dict | None = None) -> dict:
        p = dict(extra or {})
        s = self.http.settings
        if s.mailto:
            p["mailto"] = s.mailto
        if s.openalex_api_key:
            p["api_key"] = s.openalex_api_key
        return p

    async def get_by_doi(self, doi: str) -> Record | None:
        try:
            body = await self.http.get_json(
                f"{self.base}/works/https://doi.org/{quote(doi, safe='/')}", self._params()
            )
        except NotFound:
            return None
        return parse_openalex(body)

    async def search(
        self, query: str, rows: int = 5, year_from: int | None = None, year_to: int | None = None
    ) -> list[Record]:
        params = {"search": query[:500], "per-page": rows, "select": self._select}
        filters = []
        if year_from:
            filters.append(f"from_publication_date:{year_from}-01-01")
        if year_to:
            filters.append(f"to_publication_date:{year_to}-12-31")
        if filters:
            params["filter"] = ",".join(filters)
        body = await self.http.get_json(f"{self.base}/works", self._params(params))
        return [r for r in (parse_openalex(i) for i in body.get("results", [])) if r]


def parse_openalex(w: dict[str, Any]) -> Record | None:
    title = _clean(w.get("display_name") or w.get("title"))
    if not title:
        return None
    authors, families = [], []
    for a in w.get("authorships") or []:
        name = (a.get("author") or {}).get("display_name") or a.get("raw_author_name")
        if not name:
            continue
        authors.append(name)
        families.append(name.split()[-1])
    biblio = w.get("biblio") or {}
    first, last = biblio.get("first_page"), biblio.get("last_page")
    pages = f"{first}-{last}" if first and last and first != last else first
    source = ((w.get("primary_location") or {}).get("source") or {})
    return Record(
        source="openalex",
        title=title,
        authors=authors,
        family_names=families,
        year=w.get("publication_year"),
        venue=source.get("display_name"),
        doi=normalize_doi(w.get("doi")),
        volume=biblio.get("volume"),
        issue=biblio.get("issue"),
        pages=pages,
        type=w.get("type"),
        url=w.get("id"),
        is_retracted=bool(w.get("is_retracted")),
        cited_by_count=w.get("cited_by_count"),
    )


# ---------------------------------------------------------------- DOI registry

async def doi_registered(http: HttpClient, doi: str) -> bool | None:
    """True/False if doi.org knows the DOI (any registration agency); None on error."""
    try:
        body = await http.get_json(f"https://doi.org/api/handles/{quote(doi, safe='/')}")
    except NotFound:
        return False
    except Exception:
        return None
    return body.get("responseCode") == 1
