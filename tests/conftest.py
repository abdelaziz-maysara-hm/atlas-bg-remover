import os, sys
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
TESTIMGS = Path(os.environ.get("ATLAS_TEST_IMAGES", "/workspace/testimgs"))


@pytest.fixture(scope="session")
def remover():
    from atlas_bg.engine import Remover
    from atlas_bg.models import find_model
    if not find_model("u2netp"):
        pytest.skip("u2netp model not available")
    return Remover("u2netp", allow_download=False)


@pytest.fixture(scope="session")
def isnet():
    from atlas_bg.engine import Remover
    from atlas_bg.models import find_model
    if not find_model("isnet-general-use"):
        pytest.skip("isnet model not available")
    return Remover("isnet-general-use", allow_download=False)


def real(name):
    for sub in ("src", "edge"):
        p = TESTIMGS / sub / name
        if p.exists():
            return p
    pytest.skip(f"test image {name} not available")
