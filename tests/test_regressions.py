"""Regressions found by the audit of 2026-11-15: each test fails on a one-line mutant or on 2a1677e."""

import asyncio
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.config import settings
from src.loaders import SourceError, parse_json
from src.main import create_app
from src.service import load_users
from src.transformers import to_e164, to_user
from tests.builders import CSV_CUSTOMERS, JSON_CUSTOMERS, csv_body, json_body, offline, raw_record

ROOT = Path(__file__).resolve().parents[1]


# The suite let these mutants through: each test pins the behaviour one of them breaks.


def test_a_source_whose_records_are_all_rejected_fails_the_load():
    with pytest.raises(SourceError, match="json source: no usable record out of 3"):
        asyncio.run(
            load_users(
                settings, offline(csv=csv_body(CSV_CUSTOMERS), json=json_body([raw_record(email=None)] * 3))
            )
        )


def test_a_plus_after_leading_spaces_keeps_its_calling_code():
    assert to_e164(" +1 305 555 0100") == "+13055550100"


def test_an_eleven_digit_mobile_in_area_code_55_is_kept():
    assert to_e164("(55) 99123-4567") == "+5555991234567"


def test_a_date_with_surrounding_spaces_is_read():
    assert to_user(raw_record(dob__date=" 1979-01-22T03:35:31Z ")).model_dump(mode="json")["birthday"] == (
        "1979-01-22T03:35:31Z"
    )


def test_the_region_comes_from_the_state_even_if_the_source_sends_one():
    assert to_user(raw_record(location__state="bahia", location__region="sul")).location.region == "nordeste"


def test_rejections_of_both_sources_are_added():
    store = asyncio.run(
        load_users(
            settings,
            offline(
                csv=csv_body([*CSV_CUSTOMERS, raw_record(email=None)]),
                json=json_body([*JSON_CUSTOMERS, raw_record(email=None)]),
            ),
        )
    )
    assert store.rejected == 2


def test_null_fields_keep_their_key_on_the_wire_and_load_order_is_not_email_order():
    unknown = raw_record(email="zz-first@example.com", gender="unknown", location__state="atlantis")
    app = create_app(
        transport=offline(csv=csv_body([unknown, *CSV_CUSTOMERS]), json=json_body(JSON_CUSTOMERS))
    )
    with TestClient(app) as client:
        first = client.get("/users?pageSize=1").json()["users"][0]
    assert first["email"] == "zz-first@example.com"
    assert first["gender"] is None
    assert first["location"]["region"] is None


# Inputs that escaped the record-level contract of docs/decisions.md section 5.


def test_deeply_nested_json_is_a_source_error():
    with pytest.raises(SourceError, match="invalid JSON"):
        parse_json('{"results": ' + "[" * 10**6 + "]" * 10**6 + "}")


def _with_first(field: str, literal: str) -> bytes:
    """The JSON export with the first value of `field` replaced by a raw literal."""
    text = json_body(JSON_CUSTOMERS).decode()
    found = re.search(rf'"{field}": \d+', text)
    return (text[: found.start()] + f'"{field}": {literal}' + text[found.end() :]).encode()


def test_an_oversized_integer_in_a_dropped_field_does_not_refuse_the_source():
    store = asyncio.run(
        load_users(settings, offline(csv=csv_body(CSV_CUSTOMERS), json=_with_first("age", "9" * 5000)))
    )
    assert (len(store.users), store.rejected) == (len(CSV_CUSTOMERS) + len(JSON_CUSTOMERS), 0)


def test_an_oversized_integer_postcode_rejects_only_its_record():
    store = asyncio.run(
        load_users(settings, offline(csv=csv_body(CSV_CUSTOMERS), json=_with_first("postcode", "9" * 5000)))
    )
    assert (len(store.users), store.rejected) == (len(CSV_CUSTOMERS) + len(JSON_CUSTOMERS) - 1, 1)


def test_a_boolean_postcode_is_rejected():
    with pytest.raises(ValidationError) as failure:
        to_user(raw_record(location__postcode=True))
    assert "location.postcode" in {".".join(map(str, error["loc"])) for error in failure.value.errors()}


def test_the_default_page_size_never_exceeds_max_page_size():
    script = "from src.models import UserQuery; print(UserQuery.model_validate({}).page_size)"
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env={**os.environ, "MAX_PAGE_SIZE": "5"},
        capture_output=True,
        text=True,
        check=True,
    )
    assert int(result.stdout) == 5
