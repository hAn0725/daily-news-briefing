import os

import pytest

from news_crawler.secure import protect, unprotect


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI only")
def test_dpapi_round_trip():
    secret = b"test-only-bigmodel-key"

    try:
        encrypted = protect(secret)
    except OSError:
        pytest.skip("DPAPI user profile is unavailable in this sandbox")

    assert encrypted != secret
    assert unprotect(encrypted) == secret
