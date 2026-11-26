"""End-to-end checks against the real APIs. Run with: pytest -m live"""

import pytest

from refcheck.config import Settings
from refcheck.http import HttpClient
from refcheck.models import Status
from refcheck.parsing import parse_input
from refcheck.verify import Verifier

pytestmark = pytest.mark.live

CASES = [
    # Real, correct
    ("LeCun, Y., Bengio, Y., & Hinton, G. (2015). Deep learning. Nature, 521(7553), 436–444.",
     {Status.VERIFIED}),
    ('K. He, X. Zhang, S. Ren, and J. Sun, "Deep residual learning for image recognition," '
     "in Proc. IEEE CVPR, 2016, pp. 770–778.",
     {Status.VERIFIED}),
    ("Vaswani, A., Shazeer, N., Parmar, N., Uszkoreit, J., Jones, L., Gomez, A. N., Kaiser, L., & "
     "Polosukhin, I. (2017). Attention is all you need. Advances in Neural Information Processing Systems, 30.",
     {Status.VERIFIED}),
    # Real paper, wrong year
    ("LeCun, Y., Bengio, Y., & Hinton, G. (2011). Deep learning. Nature, 521(7553), 436–444.",
     {Status.NEEDS_CORRECTION}),
    # Real paper, DOI of another paper
    ("He, K., Zhang, X., Ren, S., & Sun, J. (2016). Deep residual learning for image recognition. "
     "CVPR, 770–778. https://doi.org/10.1038/nature14539",
     {Status.NEEDS_CORRECTION}),
    # Fabricated (LLM-style)
    ("Hoffmann, L., & Taner, E. (2021). Graph-augmented contrastive transformers for early sepsis "
     "prediction in pediatric intensive care. Journal of Biomedical Informatics, 118, 103781.",
     {Status.NOT_FOUND, Status.POSSIBLE_MATCH}),
    ("Brennan, M., Okafor, C., & Lindqvist, J. (2020). Federated meta-reinforcement learning for "
     "adaptive traffic signal control in heterogeneous urban networks. IEEE Transactions on "
     "Intelligent Transportation Systems, 21(9), 3871–3884. https://doi.org/10.1109/TITS.2020.2987654",
     {Status.NOT_FOUND, Status.NEEDS_CORRECTION}),
]


@pytest.fixture
def verifier():
    return Verifier(HttpClient(Settings()))


@pytest.mark.parametrize("raw,expected", CASES)
async def test_live(verifier, raw, expected):
    v = await verifier.verify(parse_input(raw)[0])
    assert v.status in expected, v.to_dict()
