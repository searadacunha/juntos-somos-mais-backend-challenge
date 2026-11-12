import logging
import re

import httpx
import pytest
from fastapi.testclient import TestClient

from src.loaders import SourceError
from src.main import create_app
from tests.builders import (
    CSV_CUSTOMERS,
    JSON_CUSTOMERS,
    README_OUTPUT,
    csv_body,
    email,
    json_body,
    offline,
    raw_record,
)

GOOD_CSV = csv_body(CSV_CUSTOMERS)
GOOD_JSON = json_body(JSON_CUSTOMERS)
BOTH_PATHS = ["/users", "/api/v1/users"]


def emails(response) -> list[str]:
    return [user["email"] for user in response.json()["users"]]


def customers(*numbers: int) -> list[str]:
    return [email(number) for number in numbers]


# --- contract -----------------------------------------------------------------


@pytest.mark.parametrize("path", BOTH_PATHS)
def test_without_parameters_the_first_ten_customers_are_returned(client, path):
    response = client.get(path)
    body = response.json()

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert list(body) == ["pageNumber", "pageSize", "totalCount", "users"]
    assert (body["pageNumber"], body["pageSize"], body["totalCount"]) == (1, 10, 12)
    assert emails(response) == customers(*range(1, 11))


@pytest.mark.parametrize(
    "query",
    [
        "",
        "?pageNumber=1&pageSize=10",
        "?pageNumber=2&pageSize=5",
        "?region=sul",
        "?type=special",
        "?region=sul&type=laborious&pageSize=2&pageNumber=2",
        "?pageNumber=99",
        "?pageSize=0",
        "?region=nowhere",
    ],
)
def test_both_paths_give_the_same_answer(client, query):
    readme_path = client.get("/users" + query)
    validator_path = client.get("/api/v1/users" + query)
    assert readme_path.status_code == validator_path.status_code
    assert readme_path.json() == validator_path.json()


def test_the_readme_example_is_served_exactly_as_the_contract_shows():
    """End to end: the same customer read from the CSV and from the JSON, through HTTP."""
    app = create_app(transport=offline(csv=csv_body([raw_record()]), json=json_body([raw_record()])))
    with TestClient(app) as client:
        body = client.get("/users").json()

    assert body == {"pageNumber": 1, "pageSize": 10, "totalCount": 2, "users": [README_OUTPUT, README_OUTPUT]}
    assert list(body["users"][0]) == list(README_OUTPUT)


def test_the_request_of_the_official_validator_finds_what_it_greps(client):
    """validate.sh requests this URL and greps the body for the four field names."""
    response = client.get("/api/v1/users?pageNumber=1&pageSize=10")
    assert response.status_code == 200
    for field in ('"pageNumber"', '"pageSize"', '"totalCount"', '"users"'):
        assert field in response.text


# --- filters and pagination -----------------------------------------------------


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("type=special", [1, 2, 8]),
        ("type=normal", [3, 9]),
        ("type=laborious", [4, 5, 6, 7, 10, 11, 12]),
        ("region=sul", [3, 6, 8, 10, 12]),
        ("region=sudeste", [1, 7, 9]),
        ("region=nordeste", [2]),
        ("region=norte", [4, 11]),
        ("region=centro-oeste", [5]),
        ("region=sul&type=laborious", [6, 10, 12]),
        ("type=special&region=sul", [8]),
        ("region=norte&type=special", []),
    ],
)
def test_filters_select_customers_and_set_the_total(client, query, expected):
    response = client.get(f"/users?{query}&pageSize=100")
    assert response.status_code == 200
    assert emails(response) == customers(*expected)
    assert response.json()["totalCount"] == len(expected)


@pytest.mark.parametrize(
    ("query", "expected", "total"),
    [
        pytest.param("pageSize=5&pageNumber=1", [1, 2, 3, 4, 5], 12, id="first-page"),
        pytest.param("pageSize=5&pageNumber=3", [11, 12], 12, id="last-page-is-shorter"),
        pytest.param("pageSize=5&pageNumber=4", [], 12, id="page-after-the-last-is-empty"),
        pytest.param("region=sul&pageSize=2&pageNumber=2", [8, 10], 5, id="second-page-of-a-filter"),
        pytest.param("region=sul&pageSize=2&pageNumber=4", [], 5, id="filter-page-after-the-last"),
        pytest.param("pageSize=100", list(range(1, 13)), 12, id="largest-page-allowed"),
    ],
)
def test_pagination(client, query, expected, total):
    response = client.get(f"/users?{query}")
    assert response.status_code == 200
    assert emails(response) == customers(*expected)
    assert response.json()["totalCount"] == total


def test_the_response_echoes_the_requested_page_not_the_number_of_items(client):
    body = client.get("/users?pageNumber=3&pageSize=5").json()
    assert (body["pageNumber"], body["pageSize"], len(body["users"])) == (3, 5, 2)


def test_two_identical_requests_get_identical_answers(client):
    assert (
        client.get("/users?pageNumber=2&pageSize=3").json()
        == client.get("/users?pageNumber=2&pageSize=3").json()
    )


# --- invalid requests -------------------------------------------------------------


@pytest.mark.parametrize(
    ("query", "parameter", "error"),
    [
        ("pageNumber=0", "pageNumber", "greater_than_equal"),
        ("pageNumber=-1", "pageNumber", "greater_than_equal"),
        ("pageNumber=abc", "pageNumber", "int_parsing"),
        ("pageNumber=1.5", "pageNumber", "int_parsing"),
        ("pageNumber=", "pageNumber", "int_parsing"),
        ("pageSize=0", "pageSize", "greater_than_equal"),
        ("pageSize=101", "pageSize", "less_than_equal"),
        ("pageSize=1000000", "pageSize", "less_than_equal"),
        ("pageSize=ten", "pageSize", "int_parsing"),
        ("region=south", "region", "enum"),
        ("region=Sul", "region", "enum"),
        ("region=", "region", "enum"),
        ("type=vip", "type", "enum"),
        ("type=SPECIAL", "type", "enum"),
        ("page=2", "page", "extra_forbidden"),
        ("pagesize=5", "pagesize", "extra_forbidden"),
        ("pageNumber=1&sort=name", "sort", "extra_forbidden"),
    ],
)
@pytest.mark.parametrize("path", BOTH_PATHS)
def test_an_invalid_or_unknown_parameter_is_a_422_that_names_it(client, path, query, parameter, error):
    response = client.get(f"{path}?{query}")
    assert response.status_code == 422
    assert [(detail["loc"], detail["type"]) for detail in response.json()["detail"]] == [
        (["query", parameter], error)
    ]


def test_other_paths_and_methods_are_refused(client):
    assert client.get("/customers").status_code == 404
    assert client.get("/api/v2/users").status_code == 404
    assert client.post("/users").status_code == 405
    assert client.delete("/api/v1/users").status_code == 405


# --- operations -----------------------------------------------------------------


def test_health_reports_what_was_loaded(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "users": 12, "rejectedRecords": 0}


def test_health_shows_rejected_records_and_they_are_never_served():
    broken = raw_record(email="broken@example.com", location__postcode="01310-100")
    app = create_app(transport=offline(csv=GOOD_CSV, json=json_body([*JSON_CUSTOMERS, broken])))
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok", "users": 12, "rejectedRecords": 1}
        listing = client.get("/users?pageSize=100")

    assert listing.json()["totalCount"] == 12
    assert "broken@example.com" not in emails(listing)


def test_the_api_documents_itself(client):
    schema = client.get("/openapi.json").json()
    assert set(schema["paths"]) == {"/users", "/api/v1/users", "/health"}
    for path in BOTH_PATHS:
        parameters = {parameter["name"] for parameter in schema["paths"][path]["get"]["parameters"]}
        assert parameters == {"region", "type", "pageNumber", "pageSize"}
    assert client.get("/docs").status_code == 200


# --- startup ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("csv", "json", "message"),
    [
        pytest.param(
            httpx.Response(503), GOOD_JSON, "csv source: download failed with HTTP 503", id="csv-unavailable"
        ),
        pytest.param(
            GOOD_CSV,
            httpx.ConnectTimeout("too slow"),
            "json source: download failed with ConnectTimeout",
            id="json-times-out",
        ),
        pytest.param(GOOD_CSV, b"<html>503</html>", "json source: invalid JSON", id="json-is-an-error-page"),
        pytest.param(
            GOOD_CSV, json_body([]), "json source: no usable record out of 0", id="one-source-is-empty"
        ),
        pytest.param(
            csv_body([]), json_body([]), "csv source: no usable record out of 0", id="no-data-at-all"
        ),
    ],
)
def test_the_application_does_not_start_without_both_sources(caplog, csv, json, message):
    """No partial data: when one source fails, the other one is not served alone."""
    app = create_app(transport=offline(csv=csv, json=json))
    with (
        caplog.at_level(logging.CRITICAL, logger="src.main"),
        pytest.raises(SourceError, match=re.escape(message)),
        TestClient(app),
    ):
        pytest.fail("the application started")

    [logged] = caplog.messages
    assert logged.startswith(f"startup aborted: {message}")
