"""Turn user input (BibTeX or a pasted reference list) into Reference objects."""

from __future__ import annotations

import re

import bibtexparser

from .models import Reference
from .normalize import find_doi, normalize_doi, strip_latex

_BIBTEX_START = re.compile(r"^\s*@\w+\s*\{", re.MULTILINE)
_MARKER = re.compile(r"^\s*(\[\d{1,4}\]|\d{1,4}\.(?=\s)|\d{1,4}\)(?=\s))\s*")
_PAREN_YEAR = re.compile(r"\((\d{4})[a-z]?(?:,[^)]*)?\)")
_ANY_YEAR = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
_QUOTED = re.compile(r"[\"“”']{1,2}(.{10,}?)[,.]?[\"“”']{1,2}")

_UNINDEXED_TYPES = {
    "book", "inbook", "incollection", "phdthesis", "mastersthesis", "thesis",
    "techreport", "report", "misc", "online", "manual", "unpublished", "booklet",
}


def looks_like_bibtex(text: str) -> bool:
    return bool(_BIBTEX_START.search(text))


def parse_input(text: str) -> list[Reference]:
    text = text.strip()
    if not text:
        return []
    if looks_like_bibtex(text):
        return parse_bibtex(text)
    return [parse_plain(chunk) for chunk in split_plain(text)]


# ---------------------------------------------------------------- BibTeX

def parse_bibtex(text: str) -> list[Reference]:
    library = bibtexparser.parse_string(text)
    refs = []
    for entry in library.entries:
        f = {k.lower(): strip_latex(str(v.value)).strip() for k, v in entry.fields_dict.items()}
        year = _first_year(f.get("year") or f.get("date") or "")
        venue = f.get("journal") or f.get("journaltitle") or f.get("booktitle") or f.get("publisher")
        title = " ".join(f["title"].split()) if f.get("title") else None
        authors = " ".join(f["author"].split()) if f.get("author") else None
        raw = ". ".join(
            p for p in [authors, f"({year})" if year else None, title, venue] if p
        )
        refs.append(
            Reference(
                raw=raw or entry.key,
                title=title,
                authors_text=authors,
                year=year,
                venue=venue,
                doi=normalize_doi(f.get("doi")) or (find_doi(f["url"]) if f.get("url") else None),
                volume=f.get("volume"),
                pages=f.get("pages"),
                entry_type=entry.entry_type.lower(),
                key=entry.key,
            )
        )
    return refs


# ---------------------------------------------------------------- plain text

def split_plain(text: str) -> list[str]:
    """Split a pasted reference list into individual references."""
    lines = text.splitlines()

    # 1) Blank-line separated blocks.
    blocks = [b for b in re.split(r"\n\s*\n", text) if b.strip()]
    if len(blocks) > 1:
        return [_clean(b) for b in blocks]

    # 2) Numbered markers ([1], 1., 1)) with wrapped continuation lines.
    if sum(1 for ln in lines if _MARKER.match(ln)) >= 2:
        refs: list[str] = []
        for ln in lines:
            if not ln.strip():
                continue
            if _MARKER.match(ln) or not refs:
                refs.append(ln)
            else:
                refs[-1] += " " + ln
        return [_clean(r) for r in refs]

    # 3) One reference per line.
    return [_clean(ln) for ln in lines if ln.strip()]


def _clean(chunk: str) -> str:
    chunk = " ".join(chunk.split())
    return _MARKER.sub("", chunk, count=1).strip()


def parse_plain(raw: str) -> Reference:
    """Best-effort field extraction from a formatted citation (APA, IEEE, ...).

    Fields left as None are fine: verification falls back to searching with the
    whole string.
    """
    ref = Reference(raw=raw, doi=find_doi(raw))

    m = _PAREN_YEAR.search(raw)
    if m:  # APA / Harvard: Authors (Year). Title. Venue...
        ref.year = int(m.group(1))
        ref.authors_text = raw[: m.start()].strip(" ,.") or None
        rest = raw[m.end():].lstrip(" .")
        title = re.split(r"(?<=[a-z0-9)\]])[.?!]\s", rest, maxsplit=1)[0]
        ref.title = _clean_title(title)
    else:
        ref.year = _first_year(raw)

    q = _QUOTED.search(raw)
    if q and (ref.title is None or not m):  # IEEE: Authors, "Title," Venue, year.
        ref.title = _clean_title(q.group(1))
        ref.authors_text = raw[: q.start()].strip(" ,.") or ref.authors_text

    if ref.title and len(ref.title.split()) < 2:
        ref.title = None
    return ref


def _clean_title(t: str) -> str:
    return t.strip().strip("\"“”'").rstrip(",.").strip()


def _first_year(s: str) -> int | None:
    m = _ANY_YEAR.search(s)
    return int(m.group(1)) if m else None


def is_often_unindexed(ref: Reference) -> bool:
    raw = ref.raw.lower()
    if "arxiv" in raw or ref.doi:  # preprints and DOI'd works are indexed
        return False
    if ref.entry_type in _UNINDEXED_TYPES:
        return True
    return bool(_UNINDEXED_MARKERS.search(raw))


# Words that mark theses and web sources in citations, in several languages,
# since reference lists are often written in the manuscript's language.
_UNINDEXED_WORDS = [
    # thesis / dissertation
    # ("these", German for thesis, is left out: it is a common English word.)
    "thesis", "dissertation", "thèse", "doktorarbeit", "masterarbeit",
    "tesis", "tese", "tesi", "tez", "tezi", "proefschrift", "avhandling", "rozprawa",
    "väitöskirja", "диссертация", "диссертации", "praca doktorska",
    # retrieved / accessed (web sources)
    "retrieved from", "accessed", "abgerufen", "zugegriffen", "consulté", "consultado",
    "accedido", "acesso em", "consultato", "erişim", "geraadpleegd", "dostęp",
]
# CJK words have no spaces around them, so they are matched without word boundaries.
_UNINDEXED_CJK = ["学位论文", "博士论文", "硕士论文", "博士論文", "修士論文", "학위논문"]
_UNINDEXED_MARKERS = re.compile(
    r"(?<!\w)(?:" + "|".join(re.escape(w) for w in _UNINDEXED_WORDS) + r")(?!\w)"
    r"|" + "|".join(_UNINDEXED_CJK) +
    r"|https?://(?!(?:dx\.)?doi\.org)"
)
