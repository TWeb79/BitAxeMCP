import os
import pytest
from dotenv import load_dotenv

load_dotenv()

@pytest.fixture
def bitaxe_host():
    host = os.environ.get("BITAXE_HOST")
    if not host:
        pytest.skip("BITAXE_HOST not set — no live device configured for tests")
    return host
