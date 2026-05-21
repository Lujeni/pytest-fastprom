import asyncio

import pytest
from fastapi import FastAPI

# pytest_plugins no longer needed — plugin auto-loads via pytest11 entry-point.
# Keep only if you need the plugin without `pip install -e .`:
# pytest_plugins = ["pytest_fastprom"]


@pytest.fixture
def fastapi_app():
    """Example FastAPI app — override in your project's conftest.py."""
    app = FastAPI()

    @app.get("/")
    async def read_main():
        return {"msg": "Hello World"}

    @app.get("/items/{item_id}")
    async def read_item(item_id: int):
        return {"item_id": item_id}

    @app.get("/slow")
    async def slow_endpoint():
        """Simulates a slow handler — sleeps 300ms."""
        await asyncio.sleep(0.3)
        return {"msg": "slow but sure"}

    return app
