"""Core logic: find the real record behind a reference and judge the citation.

`assess()` is a pure function (easy to unit test); `Verifier` does the I/O.
"""

from __future__ import annotations

import asyncio
import re

from rapidfuzz import fuzz

from .bibtex import to_bibtex
from .http import HttpClient
from .models import Issue, Record, Reference, Severity, Status, Verification
from .normalize import family_name_in, normalize, title_in_text, title_similarity
from .parsing import is_often_unindexed
from .sources import Crossref, OpenAlex, doi_registered

STRONG = 90.0  # title similarity needed to call it the same work
POSSIBLE = 75.0  # below STRONG but worth showing as a likely candidate
SUGGEST = 55.0  # minimum similarity to offer as "did you mean"


# ---------------------------------------------------------------- scoring

def title_score(ref: Reference, rec: Record) -> float:
    if ref.title:
        return title_similarity(ref.title, rec.title)
    return title_in_text(rec.title, ref.raw)


def cited_family_names(ref: Reference) -> list[str] | None:
    """Family names from a structured BibTeX author field ("A, B and C, D")."""
    if ref.entry_type is None or not ref.authors_text:
        return None
    names = []
    for part in re.split(r"\s+and\s+", ref.authors_text):
        part = part.strip()
        if not part or part.lower() in ("others", "et al.", "et al"):
            continue
        names.append(part.split(",")[0].strip() if "," in part else part.split()[-1])
    return names


def _author_haystack(ref: Reference) -> str:
    if ref.authors_text:
        return ref.authors_text
    return ref.raw.replace(ref.title, " ") if ref.title else ref.raw


def author_hits(ref: Reference, rec: Record) -> int:
    hay = _author_haystack(ref)
    return sum(family_name_in(f, hay) for f in rec.family_names[:5])


def _rank(ref: Reference, cands: list[Record]) -> list[tuple[float, Record]]:
    scored = [(title_score(ref, c), c) for c in cands]
    scored.sort(key=lambda sc: (sc[0], author_hits(ref, sc[1])), reverse=True)
    return scored


# ---------------------------------------------------------------- field checks

def _short_authors(names: list[str], n: int = 4) -> str:
    return ", ".join(names[:n]) + (" et al." if len(names) > n else "")


def check_fields(ref: Reference, rec: Record) -> list[Issue]:
    issues: list[Issue] = []

    if rec.is_retracted:
        issues.append(Issue("retraction", Severity.ERROR, "This work has been RETRACTED."))

    # Authors
    if rec.family_names:
        hay = _author_haystack(ref)
        first_ok = family_name_in(rec.family_names[0], hay)
        hits = author_hits(ref, rec)
        cited = cited_family_names(ref)
        unknown = [c for c in cited or [] if not any(normalize(c) == normalize(f) for f in rec.family_names)]
        correct = _short_authors(rec.authors)
        if hits == 0:
            issues.append(Issue(
                "authors", Severity.ERROR,
                "None of the record's authors appear in the citation (authors may be fabricated).",
                cited=ref.authors_text, correct=correct,
            ))
        elif unknown:
            issues.append(Issue(
                "authors", Severity.ERROR,
                f"Cited author(s) not on the actual paper: {', '.join(unknown)}.",
                cited=ref.authors_text, correct=correct,
            ))
        elif not first_ok:
            issues.append(Issue(
                "authors", Severity.WARNING,
                "First author differs from the record (author order may be wrong).",
                cited=ref.authors_text, correct=correct,
            ))

    # Year
    if ref.year and rec.year and ref.year != rec.year:
        diff = abs(ref.year - rec.year)
        issues.append(Issue(
            "year", Severity.WARNING if diff == 1 else Severity.ERROR,
            "Year is off by one (often preprint vs. published version)." if diff == 1 else "Year is wrong.",
            cited=str(ref.year), correct=str(rec.year),
        ))

    # DOI
    if ref.doi and rec.doi and ref.doi != rec.doi:
        issues.append(Issue("doi", Severity.ERROR, "DOI does not match this work.", cited=ref.doi, correct=rec.doi))
    elif not ref.doi and rec.doi:
        issues.append(Issue("doi", Severity.WARNING, "DOI is missing; consider adding it.", correct=rec.doi))

    # Venue (lenient: abbreviations are common)
    if ref.venue and rec.venue:
        a, b = normalize(ref.venue), normalize(rec.venue)
        if "arxiv" not in a + b and max(fuzz.token_set_ratio(a, b), fuzz.partial_ratio(a, b)) < 60 \
                and not _is_abbreviation(a, b):
            issues.append(Issue("venue", Severity.WARNING, "Venue differs from the record.", cited=ref.venue, correct=rec.venue))

    # Volume / pages
    if ref.volume and rec.volume and normalize(ref.volume) != normalize(rec.volume):
        issues.append(Issue("volume", Severity.WARNING, "Volume differs.", cited=ref.volume, correct=rec.volume))
    fp_ref, fp_rec = _first_page(ref.pages), _first_page(rec.pages)
    if fp_ref and fp_rec and fp_ref != fp_rec:
        issues.append(Issue("pages", Severity.WARNING, "Pages differ.", cited=ref.pages, correct=rec.pages))

    return issues


def _first_page(p: str | None) -> str | None:
    m = re.search(r"[A-Za-z]?\d+", p or "")
    return m.group(0).lower() if m else None


def _is_abbreviation(a: str, b: str) -> bool:
    """'ieee trans pattern anal mach intell' vs the full journal name."""
    short, long_ = sorted((a.split(), b.split()), key=len)
    it = iter(long_)
    return all(any(w.startswith(s) for w in it) for s in short)


# ---------------------------------------------------------------- decision

def venue_matches(ref: Reference, rec: Record) -> bool | None:
    """Does the cited venue agree with the record's? None when it cannot be told."""
    if not rec.venue:
        return None
    venue = normalize(rec.venue)
    text = normalize(ref.venue) if ref.venue else normalize(ref.raw)
    if not text:
        return None
    if "arxiv" in venue:
        return "arxiv" in text
    # Acronyms such as "(CVPR)" or "NeurIPS" are how venues are usually cited.
    acronyms = re.findall(r"\(([A-Za-z][A-Za-z&]{2,})\)", rec.venue)
    if any(f" {normalize(a)} " in f" {text} " for a in acronyms):
        return True
    core = re.sub(r"\b(19|20)\d{2}\b|\b\d+(st|nd|rd|th)\b", " ", venue).split()
    if not core:
        return None
    if ref.venue:
        return fuzz.token_set_ratio(" ".join(core), text) >= 60 or _is_abbreviation(text, " ".join(core))
    return fuzz.partial_ratio(" ".join(core), text) >= 85


def _consistency(ref: Reference, rec: Record) -> tuple:
    """Sort key: venue agrees, fewer errors, fewer warnings, more citations, closer year.

    Venue comes first so that a citation of the conference version is matched to
    that version rather than to its arXiv preprint (or vice versa).
    """
    issues = check_fields(ref, rec)
    errors = sum(i.severity == Severity.ERROR for i in issues)
    vm = venue_matches(ref, rec)
    return (
        {True: 0, None: 1, False: 2}[vm],
        errors,
        len(issues) - errors,
        -(rec.cited_by_count or 0),
        abs((ref.year or 0) - (rec.year or 0)) if ref.year and rec.year else 0,
    )


def _pick(ref: Reference, ranked: list[tuple[float, Record]]) -> tuple[float, Record | None]:
    # Several records can share a title (duplicates, re-deposits, other papers with the
    # same catchy title). Among strong title matches pick the one most consistent with
    # the citation.
    strong = [sc for sc in ranked if sc[0] >= STRONG]
    if strong:
        return min(strong, key=lambda sc: _consistency(ref, sc[1]))
    # A merely similar title with none of the cited authors is a different paper.
    possible = [sc for sc in ranked if sc[0] >= POSSIBLE and (author_hits(ref, sc[1]) or not sc[1].family_names)]
    if possible:
        return possible[0]
    return 0.0, None


def _with_doi_issues(issues: list[Issue], doi_issues: list[Issue], best: Record) -> list[Issue]:
    """DOI-lookup findings are more specific than check_fields' generic DOI mismatch."""
    if not doi_issues:
        return issues
    for i in doi_issues:
        i.correct = i.correct or best.doi
    return [i for i in issues if i.field != "doi"] + doi_issues


def assess(
    ref: Reference,
    candidates: list[Record],
    *,
    doi_record: Record | None = None,
    doi_is_registered: bool | None = None,
    searched: list[str] | None = None,
) -> Verification:
    searched = searched or []
    ranked = _rank(ref, candidates)
    doi_issues: list[Issue] = []

    if ref.doi and doi_record is None and doi_is_registered is False:
        doi_issues.append(Issue("doi", Severity.ERROR, "This DOI does not exist (not registered at doi.org).", cited=ref.doi))
    if doi_record is not None and title_score(ref, doi_record) < POSSIBLE:
        doi_issues.append(Issue(
            "doi", Severity.ERROR,
            f'The cited DOI belongs to a different work: "{doi_record.title}" ({doi_record.year}).',
            cited=ref.doi,
        ))

    best_score, best = _pick(ref, ranked)
    suggestions = [c for s, c in ranked if s >= SUGGEST and c is not best][:3]

    if best is not None and best_score >= STRONG:
        issues = _with_doi_issues(check_fields(ref, best), doi_issues, best)
        errors = [i for i in issues if i.severity == Severity.ERROR]
        if errors:
            status = Status.NEEDS_CORRECTION
            summary = "The work exists, but the citation has errors: " + "; ".join(i.field for i in errors) + "."
            bib = to_bibtex(best, key=ref.key)
        else:
            status = Status.VERIFIED
            summary = "Verified: a matching record was found." + (" (minor notes below)" if issues else "")
            bib = None
        return Verification(ref, status, summary, match=best, title_similarity=best_score,
                            issues=issues, searched=searched, bibtex=bib)

    if best is not None and best_score >= POSSIBLE:
        return Verification(
            ref, Status.POSSIBLE_MATCH,
            "A similar but not identical work was found. Check whether this is the intended paper; "
            "if not, the reference may be fabricated.",
            match=best, title_similarity=best_score,
            issues=_with_doi_issues(check_fields(ref, best), doi_issues, best),
            suggestions=suggestions, searched=searched,
        )

    if is_often_unindexed(ref) and not doi_issues:
        return Verification(
            ref, Status.UNVERIFIABLE,
            "Not found in scholarly indexes, but this type of source (book, thesis, report, web page) "
            "is often not indexed. Please verify it manually.",
            suggestions=suggestions, searched=searched, issues=doi_issues,
        )

    return Verification(
        ref, Status.NOT_FOUND,
        "No matching work was found in any source. This reference is likely fabricated; "
        "replace it with a real source." + (" See 'did_you_mean' for close candidates." if suggestions else ""),
        suggestions=suggestions, searched=searched, issues=doi_issues,
    )


# ---------------------------------------------------------------- I/O

class Verifier:
    def __init__(self, http: HttpClient):
        self.http = http
        self.crossref = Crossref(http)
        self.openalex = OpenAlex(http)

    async def verify(self, ref: Reference) -> Verification:
        searched: list[str] = []
        errors: list[str] = []
        doi_record: Record | None = None
        doi_reg: bool | None = None

        if ref.doi:
            for src in (self.crossref, self.openalex):
                try:
                    doi_record = await src.get_by_doi(ref.doi)
                    searched.append(f"{src.name} (DOI lookup)")
                except Exception as e:  # noqa: BLE001
                    errors.append(f"{src.name}: {e}")
                if doi_record:
                    break
            doi_reg = True if doi_record else await doi_registered(self.http, ref.doi)
            if doi_record is None:
                searched.append("doi.org registry")

        candidates: list[Record] = [doi_record] if doi_record else []
        if not (doi_record and title_score(ref, doi_record) >= STRONG):
            oa_query = ref.title or ref.raw
            results = await asyncio.gather(
                self.crossref.search(ref.raw),
                self.openalex.search(oa_query),
                return_exceptions=True,
            )
            for src, res in zip((self.crossref, self.openalex), results):
                if isinstance(res, BaseException):
                    errors.append(f"{src.name}: {res}")
                else:
                    searched.append(f"{src.name} (search)")
                    candidates.extend(res)
        elif doi_record.source == "crossref":
            # Strong DOI match from Crossref: ask OpenAlex only for the retraction flag.
            try:
                oa = await self.openalex.get_by_doi(ref.doi)
                if oa:
                    candidates.append(oa)
            except Exception:  # noqa: BLE001
                pass

        if not candidates and errors and not any("search" in s for s in searched):
            return Verification(ref, Status.ERROR, "Could not reach the bibliographic sources: " + "; ".join(errors),
                                searched=searched)

        v = assess(ref, merge(candidates), doi_record=doi_record, doi_is_registered=doi_reg, searched=searched)
        if errors:
            v.searched.append("errors: " + "; ".join(errors))
        return v


def merge(records: list[Record]) -> list[Record]:
    """Deduplicate records by DOI (or title+year), preferring Crossref metadata."""
    out: dict[str, Record] = {}
    for r in records:
        key = r.doi or f"{normalize(r.title)}|{r.year}"
        if key not in out:
            out[key] = r
            continue
        kept = out[key]
        if r.source == "crossref" and kept.source != "crossref":
            r.also_found_in = [kept.source, *kept.also_found_in]
            r.is_retracted |= kept.is_retracted
            r.cited_by_count = r.cited_by_count or kept.cited_by_count
            out[key] = r
        elif r.source != kept.source and r.source not in kept.also_found_in:
            kept.also_found_in.append(r.source)
            kept.is_retracted |= r.is_retracted
            kept.cited_by_count = kept.cited_by_count or r.cited_by_count
    return list(out.values())
