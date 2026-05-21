"""Wire your FastAPI app into pytest-fastprom via the `fastapi_app` fixture."""

import pytest

from .app import create_app


@pytest.fixture
def fastapi_app():
    # Fresh app per test → fresh instrumentator binding, no cross-test leak.
    return create_app()
