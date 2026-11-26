"""Text normalization and fuzzy comparison helpers."""

from __future__ import annotations

import re
import unicodedata

from rapidfuzz import fuzz

_LATEX_ACCENT = re.compile(r"\\[`'^\"~=.uvHtcdbkr]\s*")
_LATEX_CMD = re.compile(r"\\[a-zA-Z]+\s*")
_NON_ALNUM = re.compile(r"[^0-9a-z]+")
_DOI = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>{}]+)", re.IGNORECASE)

# Letters that NFKD does not decompose to ASCII.
_SPECIAL = str.maketrans(
    {"ı": "i", "İ": "I", "ø": "o", "Ø": "O", "ł": "l", "Ł": "L", "ß": "ss", "æ": "ae", "œ": "oe", "đ": "d"}
)


def strip_latex(text: str) -> str:
    text = _LATEX_ACCENT.sub("", text)
    text = _LATEX_CMD.sub("", text)
    return text.replace("{", "").replace("}", "").replace("~", " ")


def normalize(text: str | None) -> str:
    """Lowercase ASCII words separated by single spaces."""
    if not text:
        return ""
    text = strip_latex(text).translate(_SPECIAL)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return _NON_ALNUM.sub(" ", text.lower()).strip()


def normalize_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    doi = doi.strip()
    doi = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE)
    doi = re.sub(r"^doi:\s*", "", doi, flags=re.IGNORECASE)
    doi = doi.rstrip(".,;)]")
    return doi.lower() or None


def find_doi(text: str) -> str | None:
    m = _DOI.search(text)
    return normalize_doi(m.group(1)) if m else None


def _main_title(title: str) -> str | None:
    """'Main title: subtitle' -> 'main title' (only if the main part is substantial)."""
    for sep in (":", " - ", "?"):
        if sep in title:
            main = normalize(title.split(sep)[0])
            return main if len(main.split()) >= 4 else None
    return None


def _sim(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return max(fuzz.ratio(a, b), fuzz.token_sort_ratio(a, b))


# Score cap when only the cited *main* title matches, i.e. the citation adds a
# subtitle the real work does not have (a common hallucination pattern).
EXTRA_SUBTITLE_CAP = 85.0


def title_similarity(cited: str, record_title: str) -> float:
    """0-100 similarity between a cited title and a record title.

    Uses strict ratios (not token_set) because fabricated titles typically reuse
    real keywords; a subset match must not count as a match.
    """
    c, r = normalize(cited), normalize(record_title)
    best = _sim(c, r)
    # Citing a work without its subtitle is normal.
    if (r_main := _main_title(record_title)) is not None:
        best = max(best, _sim(c, r_main))
    # Citing it with a subtitle it does not have is suspicious: cap the score.
    if (c_main := _main_title(cited)) is not None:
        best = max(best, min(_sim(c_main, r), EXTRA_SUBTITLE_CAP))
    return best


def title_in_text(record_title: str, raw: str) -> float:
    """0-100: how well the record title appears inside a raw citation string."""
    t = normalize(record_title)
    r = normalize(raw)
    if len(t) < 12 or not r:
        return 0.0
    return fuzz.partial_ratio(t, r)


def family_name_in(family: str, text: str) -> bool:
    """Whether an author family name occurs as a word sequence in text."""
    f = normalize(family)
    if not f:
        return False
    return f" {f} " in f" {normalize(text)} "
