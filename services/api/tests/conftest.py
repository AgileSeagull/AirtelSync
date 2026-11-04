import os

import pytest

os.environ.setdefault("UDYAM_ADVISOR_MODE", "scripted")  # tests never call the real API unless they opt in

from app import store  # noqa: E402

store.use_memory()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    return TestClient(app)
