"""Render a verified Record as a BibTeX entry."""

from __future__ import annotations

from .models import Record
from .normalize import normalize

_TYPE_MAP = {
    "journal-article": "article",
    "article": "article",
    "proceedings-article": "inproceedings",
    "book": "book",
    "monograph": "book",
    "edited-book": "book",
    "book-chapter": "incollection",
    "dissertation": "phdthesis",
    "report": "techreport",
}
_VENUE_FIELD = {"article": "journal", "inproceedings": "booktitle", "incollection": "booktitle"}
_STOP = {"a", "an", "the", "on", "of", "in", "for", "and", "to", "with", "towards", "toward"}


def _esc(s: str) -> str:
    return s.replace("&", r"\&").replace("%", r"\%").replace("$", r"\$").replace("#", r"\#")


def _bib_author(display: str, family: str | None) -> str:
    if family and display.endswith(family):
        given = display[: -len(family)].strip()
        return f"{family}, {given}" if given else family
    return display


def make_key(rec: Record) -> str:
    fam = normalize(rec.family_names[0]).replace(" ", "") if rec.family_names else "anon"
    word = next((w for w in normalize(rec.title).split() if w not in _STOP), "work")
    return f"{fam}{rec.year or ''}{word}"


def to_bibtex(rec: Record, key: str | None = None) -> str:
    etype = _TYPE_MAP.get(rec.type or "", "misc")
    fields: list[tuple[str, str]] = [("title", rec.title)]
    if rec.authors:
        fams = rec.family_names + [None] * (len(rec.authors) - len(rec.family_names))
        fields.append(("author", " and ".join(_bib_author(a, f) for a, f in zip(rec.authors, fams))))
    if rec.venue:
        fields.append((_VENUE_FIELD.get(etype, "howpublished" if etype == "misc" else "publisher"), rec.venue))
    for name, value in (
        ("year", rec.year),
        ("volume", rec.volume),
        ("number", rec.issue),
        ("pages", rec.pages.replace("-", "--") if rec.pages and "--" not in rec.pages else rec.pages),
        ("doi", rec.doi),
    ):
        if value:
            fields.append((name, str(value)))
    if not rec.doi and rec.url:
        fields.append(("url", rec.url))

    body = ",\n".join(f"  {k} = {{{_esc(v) if k not in ('doi', 'url') else v}}}" for k, v in fields)
    return f"@{etype}{{{key or make_key(rec)},\n{body}\n}}"
