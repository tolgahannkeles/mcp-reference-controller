"""Decision logic on hand-made records (no network)."""

from dataclasses import replace

from refcheck.models import Reference, Status
from refcheck.parsing import parse_input, parse_plain
from refcheck.verify import assess, merge


def _fields(v):
    return {i.field: i for i in v.issues}


def test_correct_reference_is_verified(deep_learning):
    ref = parse_plain("LeCun, Y., Bengio, Y., & Hinton, G. (2015). Deep learning. Nature, 521(7553), 436–444.")
    v = assess(ref, [deep_learning])
    assert v.status == Status.VERIFIED
    # only a "DOI missing" note
    assert set(_fields(v)) == {"doi"}


def test_wrong_year_needs_correction(deep_learning):
    ref = parse_plain("LeCun, Y., Bengio, Y., & Hinton, G. (2012). Deep learning. Nature, 521, 436–444.")
    v = assess(ref, [deep_learning])
    assert v.status == Status.NEEDS_CORRECTION
    assert _fields(v)["year"].correct == "2015"
    assert v.bibtex and "doi = {10.1038/nature14539}" in v.bibtex


def test_year_off_by_one_is_only_a_warning(deep_learning):
    ref = parse_plain("LeCun, Y., Bengio, Y., & Hinton, G. (2014). Deep learning. Nature.")
    assert assess(ref, [deep_learning]).status == Status.VERIFIED


def test_real_title_with_fabricated_authors(deep_learning):
    ref = parse_plain("Smith, J., & Kaya, A. (2015). Deep learning. Nature, 521, 436–444.")
    v = assess(ref, [deep_learning])
    assert v.status == Status.NEEDS_CORRECTION
    assert "LeCun" in _fields(v)["authors"].correct


def test_extra_fabricated_coauthor_in_bibtex(deep_learning):
    ref = parse_input("@article{x, title={Deep learning}, author={LeCun, Yann and Yilmaz, Ahmet}, year={2015}}")[0]
    v = assess(ref, [deep_learning])
    assert v.status == Status.NEEDS_CORRECTION
    assert "Yilmaz" in _fields(v)["authors"].message


def test_doi_pointing_to_another_paper(deep_learning, resnet):
    ref = parse_plain(
        "He, K., Zhang, X., Ren, S., & Sun, J. (2016). Deep residual learning for image recognition. "
        "In CVPR (pp. 770–778). https://doi.org/10.1038/nature14539"
    )
    v = assess(ref, [deep_learning, resnet], doi_record=deep_learning, doi_is_registered=True)
    assert v.status == Status.NEEDS_CORRECTION
    doi = _fields(v)["doi"]
    assert "different work" in doi.message and doi.correct == "10.1109/cvpr.2016.90"


def test_nonexistent_doi(deep_learning):
    ref = parse_plain("LeCun, Y. (2015). Deep learning. Nature. https://doi.org/10.1038/nature99999999")
    v = assess(ref, [deep_learning], doi_record=None, doi_is_registered=False)
    assert v.status == Status.NEEDS_CORRECTION
    assert "does not exist" in _fields(v)["doi"].message


def test_fabricated_reference_not_found(resnet):
    ref = parse_plain(
        "Demir, A., & Clarke, B. (2021). Hierarchical residual attention networks for multimodal "
        "sentiment forecasting. Journal of Artificial Intelligence Research, 70, 112–140."
    )
    v = assess(ref, [resnet])
    assert v.status == Status.NOT_FOUND
    assert v.match is None


def test_fabricated_title_reusing_keywords_gets_suggestion(resnet):
    ref = parse_plain("He, K. (2016). Deep residual learning for robust image recognition under noise. CVPR.")
    v = assess(ref, [resnet])
    assert v.status in (Status.NOT_FOUND, Status.POSSIBLE_MATCH)
    assert v.status != Status.VERIFIED


def test_book_not_found_is_unverifiable():
    # Turkish-language book, a typical example of a source missing from the indexes.
    ref = parse_input("@book{k, title={Yapay Zeka ve Toplum Üzerine Denemeler}, author={Aydın, Mehmet}, year={2019}}")[0]
    assert assess(ref, []).status == Status.UNVERIFIABLE


def test_retracted_work_is_flagged(deep_learning):
    retracted = replace(deep_learning, is_retracted=True)
    ref = parse_plain("LeCun, Y., Bengio, Y., & Hinton, G. (2015). Deep learning. Nature.")
    v = assess(ref, [retracted])
    assert v.status == Status.NEEDS_CORRECTION
    assert "retraction" in _fields(v)


def test_raw_string_without_extractable_title(deep_learning):
    # No (year) and no quotes: title is located inside the raw string instead.
    ref = Reference(raw="LeCun Y, Bengio Y, Hinton G. Deep learning. Nature 2015;521:436-44.", year=2015)
    assert assess(ref, [deep_learning]).status == Status.VERIFIED


def test_duplicate_titles_pick_most_consistent_record(deep_learning):
    # Crossref holds late re-deposits of famous papers; they must not win over the original.
    redeposit = replace(deep_learning, doi="10.65215/xyz", year=2025, venue=None, volume=None, pages=None)
    namesake = replace(deep_learning, doi="10.1/other", authors=["Ann Other"], family_names=["Other"], year=2015)
    ref = parse_plain("LeCun, Y., Bengio, Y., & Hinton, G. (2015). Deep learning. Nature, 521, 436–444.")
    v = assess(ref, [redeposit, namesake, deep_learning])
    assert v.status == Status.VERIFIED
    assert v.match.doi == "10.1038/nature14539"


def test_prefers_version_matching_cited_venue(resnet):
    preprint = replace(resnet, doi="10.48550/arxiv.1512.03385", year=2015, venue="arXiv (Cornell University)",
                       pages=None, cited_by_count=200000)
    ref = parse_plain("He, K., Zhang, X., Ren, S., & Sun, J. (2014). Deep residual learning for image recognition. CVPR.")
    v = assess(ref, [preprint, resnet])
    assert v.match.doi == "10.1109/cvpr.2016.90"
    assert v.status == Status.NEEDS_CORRECTION  # 2014 -> 2016

    arxiv_ref = parse_plain("He, K. et al. (2015). Deep residual learning for image recognition. arXiv:1512.03385.")
    assert assess(arxiv_ref, [resnet, preprint]).match.doi == "10.48550/arxiv.1512.03385"


def test_similar_title_with_no_shared_authors_is_not_found(resnet):
    similar = replace(resnet, title="Deep Residual Learning for Image Recognition: A Case Study")
    ref = parse_plain("Brennan, M., & Okafor, C. (2020). Deep residual learning for image recognition in drones. CVPR.")
    v = assess(ref, [similar])
    assert v.status == Status.NOT_FOUND
    assert v.suggestions and v.suggestions[0] is similar


def test_merge_prefers_crossref_and_keeps_retraction(deep_learning):
    oa = replace(deep_learning, source="openalex", is_retracted=True, cited_by_count=50000)
    merged = merge([oa, deep_learning])
    assert len(merged) == 1
    m = merged[0]
    assert m.source == "crossref" and m.is_retracted and m.cited_by_count == 50000
    assert m.also_found_in == ["openalex"]
