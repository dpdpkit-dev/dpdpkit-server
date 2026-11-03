import dpdpkit.consent  # from dpdpkit-core, which owns the dpdpkit package
from dpdpkit import server


def test_version() -> None:
    assert server.__version__ == "0.1.0a3"


def test_installs_alongside_dpdpkit_core() -> None:
    assert dpdpkit.consent.__name__ == "dpdpkit.consent"
