from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from src.main import create_app
from tests.builders import CSV_CUSTOMERS, JSON_CUSTOMERS, csv_body, json_body, offline


@pytest.fixture
def client() -> Iterator[TestClient]:
    """The real application, started through its lifespan on the twelve test customers."""
    app = create_app(transport=offline(csv=csv_body(CSV_CUSTOMERS), json=json_body(JSON_CUSTOMERS)))
    with TestClient(app) as test_client:
        yield test_client
