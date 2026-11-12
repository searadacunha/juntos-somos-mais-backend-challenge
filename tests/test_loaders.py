import asyncio
import json
import re
import traceback

import httpx
import pytest

from src.loaders import SourceError, fetch, parse_csv, parse_json
from tests.builders import CSV_COLUMNS, csv_body, json_body, raw_record

URL = "https://files.example.test/customers.csv?signature=SECRET-TOKEN"


def fetch_from(reply, url: str = URL) -> str:
    """Run fetch() against a transport that gives `reply` (a response, or an exception to raise)."""

    def handler(request: httpx.Request) -> httpx.Response:
        if isinstance(reply, Exception):
            raise reply
        return reply

    async def run() -> str:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch(client, url)

    return asyncio.run(run())


# --- download -----------------------------------------------------------------


def test_fetch_returns_the_body_as_text():
    assert fetch_from(httpx.Response(200, content="região,são paulo".encode())) == "região,são paulo"


def test_fetch_drops_the_byte_order_mark_of_the_official_csv():
    assert fetch_from(httpx.Response(200, content=b"\xef\xbb\xbf" + b'"gender"')) == '"gender"'


@pytest.mark.parametrize(
    ("reply", "reason"),
    [
        pytest.param(httpx.Response(404), "HTTP 404", id="not-found"),
        pytest.param(httpx.Response(500), "HTTP 500", id="server-error"),
        pytest.param(httpx.Response(503), "HTTP 503", id="unavailable"),
        pytest.param(httpx.ConnectTimeout("too slow"), "ConnectTimeout", id="connect-timeout"),
        pytest.param(httpx.ReadTimeout("too slow"), "ReadTimeout", id="read-timeout"),
        pytest.param(httpx.ConnectError("refused"), "ConnectError", id="connection-refused"),
        pytest.param(httpx.RemoteProtocolError("cut"), "RemoteProtocolError", id="connection-cut"),
    ],
)
def test_fetch_turns_every_network_failure_into_a_source_error(reply, reason):
    with pytest.raises(SourceError, match=reason) as failure:
        fetch_from(reply)
    # Neither the message nor the traceback a server would print shows the signed URL.
    assert "SECRET-TOKEN" not in "".join(traceback.format_exception(failure.value))


def test_fetch_follows_no_redirect_by_itself_and_reports_it():
    """Redirects are enabled on the client built by the service, not here: a bare 302 is a failure."""
    with pytest.raises(SourceError, match="HTTP 302"):
        fetch_from(httpx.Response(302, headers={"location": "https://elsewhere.example.test/"}))


def test_fetch_refuses_a_body_that_is_not_utf8():
    with pytest.raises(SourceError, match="not UTF-8"):
        fetch_from(httpx.Response(200, content="são paulo".encode("latin-1")))


def test_fetch_reports_a_url_that_httpx_refuses_to_build():
    """httpx.InvalidURL is not an httpx.HTTPError, so it needs its own handling."""
    with pytest.raises(SourceError, match="InvalidURL"):
        fetch_from(httpx.Response(200), url="https://files.example.test/" + "a" * 70_000)


# --- CSV ----------------------------------------------------------------------


def decoded_csv(records) -> str:
    return csv_body(records).decode("utf-8-sig")


def test_parse_csv_rebuilds_the_nested_record():
    [parsed] = parse_csv(decoded_csv([raw_record()]))
    expected = raw_record(location__postcode="37260", dob__age="39", registered__age="13")
    assert parsed == expected  # same shape as the JSON source, every cell as text


def test_parse_csv_keeps_commas_quotes_and_accents_inside_cells():
    record = raw_record(location__street='12 rua "das flores", bloco 3', location__city="são josé")
    [parsed] = parse_csv(decoded_csv([record]))
    assert parsed["location"]["street"] == '12 rua "das flores", bloco 3'
    assert parsed["location"]["city"] == "são josé"


def test_parse_csv_keeps_the_rows_in_file_order():
    records = [raw_record(email=f"{letter}@example.com") for letter in "cab"]
    assert [row["email"] for row in parse_csv(decoded_csv(records))] == [
        "c@example.com",
        "a@example.com",
        "b@example.com",
    ]


HEADER = ",".join(CSV_COLUMNS) + "\r\n"


def test_parse_csv_with_only_a_header_has_no_record():
    assert parse_csv(decoded_csv([])) == []


@pytest.mark.parametrize(
    ("header", "missing"),
    [
        pytest.param("", ", ".join(CSV_COLUMNS), id="empty-file"),
        pytest.param(HEADER.replace(",cell,", ","), "cell", id="one-column-missing"),
        pytest.param(HEADER.replace("gender,", "sex,"), "gender", id="one-column-renamed"),
        pytest.param("id,label\r\n1,one\r\n", ", ".join(CSV_COLUMNS), id="another-file"),
    ],
)
def test_parse_csv_refuses_a_header_without_every_expected_column(header, missing):
    with pytest.raises(SourceError, match=re.escape(f"invalid CSV: missing columns {missing}")):
        parse_csv(header)


def test_parse_csv_ignores_columns_it_does_not_know():
    """Even one that collides with a nested name, such as `name` next to `name__first`."""
    plain = decoded_csv([raw_record()])
    header, row = plain.splitlines()
    assert parse_csv(f"{header},name,source\r\n{row},ione,partner\r\n") == parse_csv(plain)


def test_parse_csv_marks_the_cells_of_a_short_row_as_missing():
    [parsed] = parse_csv(HEADER + "male,mr\r\n")
    assert (parsed["gender"], parsed["name"]["title"]) == ("male", "mr")
    assert parsed["name"]["first"] is None
    assert parsed["picture"]["thumbnail"] is None


def test_parse_csv_empties_a_row_with_more_cells_than_columns():
    """Its values may sit under the wrong names, so nothing of it is kept."""
    assert parse_csv(HEADER + ",".join(["x"] * (len(CSV_COLUMNS) + 1)) + "\r\n") == [{}]


def test_parse_csv_reports_text_that_is_not_csv():
    with pytest.raises(SourceError, match="invalid CSV: field larger than field limit"):
        parse_csv(HEADER + '"male,a@example.com\r\n' + "x" * 200_000)


# --- JSON ---------------------------------------------------------------------


def test_parse_json_returns_the_results_list():
    records = [raw_record(), raw_record(email="other@example.com")]
    assert parse_json(json_body(records).decode()) == records


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("", id="empty-body"),
        pytest.param('{"results": [', id="truncated"),
        pytest.param("<html>Service unavailable</html>", id="html-error-page"),
        # json.loads raises a plain ValueError here, not a JSONDecodeError.
        pytest.param('{"results": [' + "1" * 5000 + "]}", id="integer-over-the-digit-limit"),
    ],
)
def test_parse_json_reports_text_that_is_not_json(text):
    with pytest.raises(SourceError, match="invalid JSON"):
        parse_json(text)


@pytest.mark.parametrize(
    "document",
    [
        pytest.param([raw_record()], id="bare-list"),
        pytest.param({"data": []}, id="no-results-key"),
        pytest.param({"results": {"0": raw_record()}}, id="results-is-an-object"),
        pytest.param({"results": None}, id="results-is-null"),
        pytest.param("results", id="a-string"),
    ],
)
def test_parse_json_requires_an_object_with_a_results_list(document):
    with pytest.raises(SourceError, match='"results" list'):
        parse_json(json.dumps(document))
