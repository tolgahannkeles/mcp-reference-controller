"""Source parsing and the full Verifier flow with mocked HTTP."""

import httpx
import pytest
import respx

from refcheck.config import Settings
from refcheck.http import HttpClient
from refcheck.models import Status
from refcheck.parsing import parse_plain
from refcheck.sources import parse_crossref, parse_openalex
from refcheck.verify import Verifier

CROSSREF_DL = {
    "DOI": "10.1038/nature14539",
    "title": ["Deep learning"],
    "author": [
        {"given": "Yann", "family": "LeCun"},
        {"given": "Yoshua", "family": "Bengio"},
        {"given": "Geoffrey", "family": "Hinton"},
    ],
    "issued": {"date-parts": [[2015, 5, 27]]},
    "container-title": ["Nature"],
    "volume": "521",
    "issue": "7553",
    "page": "436-444",
    "type": "journal-article",
}

OPENALEX_DL = {
    "id": "https://openalex.org/W1",
    "doi": "https://doi.org/10.1038/nature14539",
    "display_name": "Deep learning",
    "authorships": [{"author": {"display_name": n}} for n in ("Yann LeCun", "Yoshua Bengio", "Geoffrey E. Hinton")],
    "publication_year": 2015,
    "primary_location": {"source": {"display_name": "Nature"}},
    "biblio": {"volume": "521", "issue": "7553", "first_page": "436", "last_page": "444"},
    "type": "article",
    "is_retracted": False,
    "cited_by_count": 70000,
}


def test_parse_crossref():
    r = parse_crossref({**CROSSREF_DL, "title": ["Deep <i>learning</i>"]})
    assert r.title == "Deep learning"
    assert r.family_names == ["LeCun", "Bengio", "Hinton"]
    assert r.year == 2015 and r.pages == "436-444"


def test_parse_openalex():
    r = parse_openalex(OPENALEX_DL)
    assert r.doi == "10.1038/nature14539"
    assert r.family_names[-1] == "Hinton"
    assert r.pages == "436-444" and r.venue == "Nature"


@pytest.fixture
def verifier():
    http = HttpClient(Settings(mailto=None, openalex_api_key=None, cache_path=None))
    return Verifier(http)


@respx.mock
async def test_verify_by_doi(verifier):
    respx.get(url__regex=r"https://api\.crossref\.org/works/10\.1038/nature14539.*").mock(
        return_value=httpx.Response(200, json={"message": CROSSREF_DL})
    )
    respx.get(url__regex=r"https://api\.openalex\.org/works/https://doi\.org/.*").mock(
        return_value=httpx.Response(200, json={**OPENALEX_DL, "is_retracted": True})
    )
    ref = parse_plain(
        "LeCun, Y., Bengio, Y., & Hinton, G. (2015). Deep learning. Nature, 521, 436–444. "
        "https://doi.org/10.1038/nature14539"
    )
    v = await verifier.verify(ref)
    # The OpenAlex retraction flag is merged into the Crossref record.
    assert v.status == Status.NEEDS_CORRECTION
    assert v.match.is_retracted and "openalex" in v.match.also_found_in


@respx.mock
async def test_fabricated_doi_and_title(verifier):
    respx.get(url__regex=r"https://api\.crossref\.org/works/10\.9999.*").mock(return_value=httpx.Response(404))
    respx.get(url__regex=r"https://api\.openalex\.org/works/https://doi\.org/.*").mock(return_value=httpx.Response(404))
    respx.get(url__regex=r"https://doi\.org/api/handles/.*").mock(return_value=httpx.Response(404))
    respx.get(url__regex=r"https://api\.crossref\.org/works\?.*").mock(
        return_value=httpx.Response(200, json={"message": {"items": [CROSSREF_DL]}})
    )
    respx.get(url__regex=r"https://api\.openalex\.org/works\?.*").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    ref = parse_plain(
        "Arslan, B., & Novak, P. (2022). Quantum-inspired deep learning for protein folding dynamics. "
        "Nature Machine Intelligence, 4, 211–225. https://doi.org/10.9999/fake.2022.001"
    )
    v = await verifier.verify(ref)
    assert v.status == Status.NOT_FOUND
    assert any(i.field == "doi" and "does not exist" in i.message for i in v.issues)


@respx.mock
async def test_sources_down_gives_error(verifier):
    respx.get(url__regex=r".*").mock(side_effect=httpx.ConnectError("offline"))
    v = await verifier.verify(parse_plain("Someone, A. (2020). Some title of a paper here. Journal."))
    assert v.status == Status.ERROR
