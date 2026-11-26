from refcheck.normalize import normalize, normalize_doi, title_similarity
from refcheck.parsing import parse_input, parse_plain, split_plain


def test_normalize_handles_turkish_and_latex():
    assert normalize("Keleş, Işık & Gülçin") == "keles isik gulcin"
    assert normalize(r"G{\"o}del's {T}heorem") == "godel s theorem"


def test_normalize_doi():
    assert normalize_doi("https://doi.org/10.1038/NATURE14539.") == "10.1038/nature14539"
    assert normalize_doi("doi: 10.1109/cvpr.2016.90") == "10.1109/cvpr.2016.90"


def test_title_similarity_rejects_keyword_reuse():
    real = "Deep Residual Learning for Image Recognition"
    assert title_similarity("Deep residual learning for image recognition", real) == 100
    # A plausible fabricated title sharing keywords must not count as a match
    # (at most "possible match", which asks the author to check).
    assert title_similarity("Deep Residual Learning for Medical Image Segmentation in MRI", real) < 90


def test_title_similarity_subtitle():
    # Citation adds a subtitle the real paper does not have -> capped below a strong match.
    s = title_similarity("Attention is all you need: transformers for sequence transduction", "Attention is all you need")
    assert 75 <= s < 90
    # Citation omits the real subtitle -> fine.
    assert title_similarity(
        "Mastering the game of Go with deep neural networks and tree search",
        "Mastering the game of Go with deep neural networks and tree search: a study",
    ) >= 90


def test_parse_bibtex():
    refs = parse_input(
        """
        @article{lecun2015,
          title={Deep {L}earning},
          author={LeCun, Yann and Bengio, Yoshua and Hinton, Geoffrey},
          journal={Nature}, volume={521}, pages={436--444}, year={2015},
          doi={10.1038/nature14539}
        }
        @book{knuth, title={The Art of Computer Programming}, author={Knuth, Donald}, year={1968}}
        """
    )
    assert len(refs) == 2
    r = refs[0]
    assert (r.key, r.title, r.year, r.venue, r.doi) == ("lecun2015", "Deep Learning", 2015, "Nature", "10.1038/nature14539")
    assert refs[1].entry_type == "book"


def test_parse_apa():
    r = parse_plain(
        "LeCun, Y., Bengio, Y., & Hinton, G. (2015). Deep learning. Nature, 521(7553), 436–444. "
        "https://doi.org/10.1038/nature14539"
    )
    assert r.year == 2015
    assert r.title == "Deep learning"
    assert r.authors_text.startswith("LeCun")
    assert r.doi == "10.1038/nature14539"


def test_parse_ieee():
    r = parse_plain(
        '[3] K. He, X. Zhang, S. Ren, and J. Sun, "Deep residual learning for image recognition," '
        "in Proc. IEEE CVPR, 2016, pp. 770–778."
    )
    assert r.title == "Deep residual learning for image recognition"
    assert "He" in r.authors_text
    assert r.year == 2016


def test_split_numbered_with_wrapping():
    text = (
        "[1] A. Author, \"First title here,\" Journal, 2020.\n"
        "[2] B. Author, \"Second title that is long\n"
        "and wraps,\" Conf, 2021.\n"
    )
    parts = split_plain(text)
    assert len(parts) == 2
    assert parts[1].startswith("B. Author") and "and wraps" in parts[1]


def test_split_one_per_line():
    assert len(split_plain("Ref one (2020). Title one.\nRef two (2021). Title two.")) == 2
