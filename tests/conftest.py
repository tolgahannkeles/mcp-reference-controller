import pytest

from refcheck.models import Record


@pytest.fixture
def deep_learning() -> Record:
    return Record(
        source="crossref",
        title="Deep learning",
        authors=["Yann LeCun", "Yoshua Bengio", "Geoffrey Hinton"],
        family_names=["LeCun", "Bengio", "Hinton"],
        year=2015,
        venue="Nature",
        doi="10.1038/nature14539",
        volume="521",
        issue="7553",
        pages="436-444",
        type="journal-article",
    )


@pytest.fixture
def resnet() -> Record:
    return Record(
        source="crossref",
        title="Deep Residual Learning for Image Recognition",
        authors=["Kaiming He", "Xiangyu Zhang", "Shaoqing Ren", "Jian Sun"],
        family_names=["He", "Zhang", "Ren", "Sun"],
        year=2016,
        venue="2016 IEEE Conference on Computer Vision and Pattern Recognition (CVPR)",
        doi="10.1109/cvpr.2016.90",
        pages="770-778",
        type="proceedings-article",
    )
