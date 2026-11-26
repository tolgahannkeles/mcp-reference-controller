from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Status(str, Enum):
    VERIFIED = "verified"
    """A real record matches the reference and the cited details agree."""

    NEEDS_CORRECTION = "needs_correction"
    """The work exists, but some cited details (year, authors, DOI...) are wrong."""

    POSSIBLE_MATCH = "possible_match"
    """A similar record exists but the match is not strong enough to be sure."""

    NOT_FOUND = "not_found"
    """No matching record in any source. Likely fabricated (hallucinated)."""

    UNVERIFIABLE = "unverifiable"
    """Not found, but the type (book, thesis, report, web page...) is often missing
    from scholarly indexes, so absence is not strong evidence."""

    ERROR = "error"
    """The sources could not be reached; nothing can be concluded."""


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


@dataclass
class Reference:
    """A reference as the author wrote it."""

    raw: str
    title: str | None = None
    authors_text: str | None = None
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    volume: str | None = None
    pages: str | None = None
    entry_type: str | None = None  # bibtex type when known (article, book, ...)
    key: str | None = None  # bibtex key when known


@dataclass
class Record:
    """A bibliographic record returned by an index (Crossref, OpenAlex...)."""

    source: str
    title: str
    authors: list[str] = field(default_factory=list)  # "Given Family" display names
    family_names: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    type: str | None = None
    url: str | None = None
    is_retracted: bool = False
    cited_by_count: int | None = None
    also_found_in: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = {
            "title": self.title,
            "authors": self.authors,
            "year": self.year,
            "venue": self.venue,
            "volume": self.volume,
            "issue": self.issue,
            "pages": self.pages,
            "doi": self.doi,
            "type": self.type,
            "url": self.url or (f"https://doi.org/{self.doi}" if self.doi else None),
            "found_in": [self.source, *self.also_found_in],
            "is_retracted": self.is_retracted,
        }
        if self.cited_by_count is not None:
            d["cited_by_count"] = self.cited_by_count
        return d


@dataclass
class Issue:
    field: str
    severity: Severity
    message: str
    cited: str | None = None
    correct: str | None = None

    def to_dict(self) -> dict:
        d = {"field": self.field, "severity": self.severity.value, "message": self.message}
        if self.cited is not None:
            d["cited"] = self.cited
        if self.correct is not None:
            d["correct"] = self.correct
        return d


@dataclass
class Verification:
    reference: Reference
    status: Status
    summary: str
    match: Record | None = None
    title_similarity: float | None = None
    issues: list[Issue] = field(default_factory=list)
    suggestions: list[Record] = field(default_factory=list)
    searched: list[str] = field(default_factory=list)
    bibtex: str | None = None

    def to_dict(self) -> dict:
        d: dict = {
            "reference": self.reference.raw,
            "status": self.status.value,
            "summary": self.summary,
        }
        if self.match is not None:
            d["matched_record"] = self.match.to_dict()
            d["title_similarity"] = round(self.title_similarity or 0, 1)
        if self.issues:
            d["issues"] = [i.to_dict() for i in self.issues]
        if self.suggestions:
            d["did_you_mean"] = [s.to_dict() for s in self.suggestions]
        if self.bibtex:
            d["corrected_bibtex"] = self.bibtex
        d["searched"] = self.searched
        return d
