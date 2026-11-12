import asyncio
import logging
import re

import httpx
import pytest

from src.config import settings
from src.loaders import SourceError
from src.service import MAX_REJECTION_DETAILS, UserStore, load_users
from src.transformers import to_user
from tests.builders import (
    CSV_CUSTOMERS,
    JSON_CUSTOMERS,
    csv_body,
    email,
    json_body,
    offline,
    raw_record,
)

GOOD_CSV = csv_body(CSV_CUSTOMERS)
GOOD_JSON = json_body(JSON_CUSTOMERS)


def load(csv, json) -> UserStore:
    return asyncio.run(load_users(settings, offline(csv=csv, json=json)))


def emails(users) -> list[str]:
    return [user.email for user in users]


def customers(*numbers: int) -> list[str]:
    return [email(number) for number in numbers]


# --- loading ------------------------------------------------------------------


def test_both_sources_are_merged_csv_first_then_json_each_in_file_order():
    store = load(GOOD_CSV, GOOD_JSON)
    assert emails(store.users) == customers(*range(1, 13))
    assert store.rejected == 0


def test_a_customer_present_in_both_files_is_kept_twice():
    """The two official files hold the same 1000 customers and the validator expects 2000:
    merging means concatenating, not de-duplicating."""
    store = load(csv_body([raw_record()]), json_body([raw_record()]))
    assert len(store.users) == 2
    assert store.users[0] == store.users[1]


@pytest.mark.parametrize(
    ("csv", "json", "message"),
    [
        pytest.param(
            httpx.Response(503), GOOD_JSON, "csv source: download failed with HTTP 503", id="csv-503"
        ),
        pytest.param(
            GOOD_CSV, httpx.Response(404), "json source: download failed with HTTP 404", id="json-404"
        ),
        pytest.param(
            httpx.ConnectTimeout("too slow"),
            GOOD_JSON,
            "csv source: download failed with ConnectTimeout",
            id="csv-timeout",
        ),
        pytest.param(
            GOOD_CSV,
            httpx.ConnectError("refused"),
            "json source: download failed with ConnectError",
            id="json-connection-refused",
        ),
        pytest.param(GOOD_CSV, b"<html>503</html>", "json source: invalid JSON", id="json-is-an-error-page"),
        pytest.param(
            GOOD_CSV,
            b"[]",
            'json source: invalid JSON: expected an object with a "results" list',
            id="json-wrong-shape",
        ),
        pytest.param(
            csv_body([]), GOOD_JSON, "csv source: no usable record out of 0", id="csv-has-only-its-header"
        ),
        pytest.param(
            GOOD_CSV, json_body([]), "json source: no usable record out of 0", id="json-has-no-record"
        ),
        pytest.param(
            b"id,label\r\n1,one\r\n2,two\r\n",
            GOOD_JSON,
            "csv source: invalid CSV: missing columns gender, name__title",
            id="csv-has-other-columns",
        ),
    ],
)
def test_one_unusable_source_fails_the_whole_load(csv, json, message):
    with pytest.raises(SourceError, match=re.escape(message)):
        load(csv, json)


def test_a_broken_record_is_rejected_and_counted_and_the_others_are_kept(caplog):
    broken = raw_record(
        email="secret.person@example.com", location__postcode="01310-100", dob__date="yesterday"
    )
    with caplog.at_level(logging.WARNING, logger="src.service"):
        store = load(GOOD_CSV, json_body([JSON_CUSTOMERS[0], broken, JSON_CUSTOMERS[1]]))

    assert emails(store.users) == customers(1, 2, 3, 4, 5, 6, 7, 8, 9)
    assert store.rejected == 1
    assert caplog.messages == [
        "source=json record=2 rejected: location.postcode (int_parsing), birthday (value_error)"
    ]


def test_logs_name_the_field_at_fault_but_never_a_value(caplog):
    broken = raw_record(
        email="secret.person@example.com", phone="(11) 91234-5678", location__postcode="SECRET"
    )
    with caplog.at_level(logging.DEBUG):
        load(GOOD_CSV, json_body([JSON_CUSTOMERS[0], broken, None]))

    assert "record=2 rejected: location.postcode (int_parsing)" in caplog.text
    assert "record=3 rejected: the record is not an object" in caplog.text
    for personal_value in ("secret.person", "91234", "SECRET", "customer01", "example.com"):
        assert personal_value not in caplog.text


def test_rejections_are_all_counted_but_only_the_first_ones_are_detailed(caplog):
    broken = [raw_record(email=None)] * (MAX_REJECTION_DETAILS + 5)
    with caplog.at_level(logging.WARNING, logger="src.service"):
        store = load(csv_body(CSV_CUSTOMERS), json_body([*broken, JSON_CUSTOMERS[0]]))

    assert store.rejected == MAX_REJECTION_DETAILS + 5
    assert len(caplog.messages) == MAX_REJECTION_DETAILS


def test_a_redirected_source_is_followed():
    moved_to = "https://mirror.example.test/customers.csv"

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == settings.csv_url:
            return httpx.Response(302, headers={"location": moved_to})
        return httpx.Response(200, content=GOOD_CSV if url == moved_to else GOOD_JSON)

    store = asyncio.run(load_users(settings, httpx.MockTransport(handler)))
    assert len(store.users) == 12


def test_the_configured_timeout_is_applied_to_every_download():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.extensions["timeout"])
        return httpx.Response(200, content=GOOD_CSV if str(request.url) == settings.csv_url else GOOD_JSON)

    impatient = settings.model_copy(update={"http_timeout_seconds": 2.5})
    asyncio.run(load_users(impatient, httpx.MockTransport(handler)))
    assert seen == [{"connect": 2.5, "read": 2.5, "write": 2.5, "pool": 2.5}] * 2


# --- querying -----------------------------------------------------------------


@pytest.fixture
def store() -> UserStore:
    return UserStore(users=tuple(to_user(record) for record in CSV_CUSTOMERS + JSON_CUSTOMERS))


@pytest.mark.parametrize(
    ("page_number", "page_size", "expected"),
    [
        pytest.param(1, 5, [1, 2, 3, 4, 5], id="first-page"),
        pytest.param(2, 5, [6, 7, 8, 9, 10], id="second-page"),
        pytest.param(3, 5, [11, 12], id="last-page-is-shorter"),
        pytest.param(4, 5, [], id="page-after-the-last-is-empty"),
        pytest.param(1, 12, list(range(1, 13)), id="one-page-holds-everything"),
        pytest.param(1, 100, list(range(1, 13)), id="page-larger-than-the-data"),
        pytest.param(12, 1, [12], id="one-customer-per-page"),
        pytest.param(10**12, 100, [], id="absurdly-high-page"),
    ],
)
def test_pages_are_numbered_from_one_and_cut_in_load_order(store, page_number, page_size, expected):
    page = store.page(page_number=page_number, page_size=page_size)
    assert emails(page.users) == customers(*expected)
    assert (page.page_number, page.page_size, page.total_count) == (page_number, page_size, 12)


@pytest.mark.parametrize("page_size", [1, 2, 5, 7, 12, 100])
def test_walking_the_pages_gives_every_customer_once_in_the_same_order(store, page_size):
    walked = []
    for page_number in range(1, 14):
        walked += emails(store.page(page_number=page_number, page_size=page_size).users)
    assert walked == customers(*range(1, 13))


@pytest.mark.parametrize(
    ("region", "customer_type", "expected"),
    [
        pytest.param(None, None, list(range(1, 13)), id="no-filter"),
        pytest.param(None, "special", [1, 2, 8], id="special"),
        pytest.param(None, "normal", [3, 9], id="normal"),
        pytest.param(None, "laborious", [4, 5, 6, 7, 10, 11, 12], id="laborious"),
        pytest.param("sul", None, [3, 6, 8, 10, 12], id="sul"),
        pytest.param("sudeste", None, [1, 7, 9], id="sudeste"),
        pytest.param("nordeste", None, [2], id="nordeste"),
        pytest.param("norte", None, [4, 11], id="norte"),
        pytest.param("centro-oeste", None, [5], id="centro-oeste"),
        pytest.param("sul", "laborious", [6, 10, 12], id="sul-and-laborious"),
        pytest.param("sul", "special", [8], id="sul-and-special"),
        pytest.param("sudeste", "normal", [9], id="sudeste-and-normal"),
        pytest.param("norte", "special", [], id="combination-matching-nobody"),
    ],
)
def test_filters_narrow_the_result_and_the_total(store, region, customer_type, expected):
    page = store.page(region=region, customer_type=customer_type, page_size=100)
    assert emails(page.users) == customers(*expected)
    assert page.total_count == len(expected)


def test_the_total_counts_the_matches_not_the_page(store):
    page = store.page(region="sul", page_number=2, page_size=2)
    assert emails(page.users) == customers(8, 10)
    assert page.total_count == 5
    assert page.page_size == 2


def test_a_customer_without_region_is_listed_but_matches_no_region_filter():
    stateless = to_user(raw_record(location__state="atlantis"))
    store = UserStore(users=(stateless,))
    assert store.page().total_count == 1
    assert [store.page(region=region).total_count for region in ("norte", "sul")] == [0, 0]
