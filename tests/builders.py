"""Builders shared by the tests: raw records, the two file formats and an offline transport.

Nothing here touches the network. The official files are never read by the tests.
"""

import csv
import io
import json
from typing import Any

import httpx

from src.config import settings

MISSING = object()  # pass as a value to raw_record() to remove a field

# Column names of the official CSV, in file order.
CSV_COLUMNS = (
    "gender",
    "name__title",
    "name__first",
    "name__last",
    "location__street",
    "location__city",
    "location__state",
    "location__postcode",
    "location__coordinates__latitude",
    "location__coordinates__longitude",
    "location__timezone__offset",
    "location__timezone__description",
    "email",
    "dob__date",
    "dob__age",
    "registered__date",
    "registered__age",
    "phone",
    "cell",
    "picture__large",
    "picture__medium",
    "picture__thumbnail",
)

# The "Output Contract" example of the challenge README, copied as is.
README_OUTPUT = {
    "type": "laborious",
    "gender": "M",
    "name": {"title": "mr", "first": "quirilo", "last": "nascimento"},
    "location": {
        "region": "sul",
        "street": "680 rua treze",
        "city": "varginha",
        "state": "paraná",
        "postcode": 37260,
        "coordinates": {"latitude": "-46.9519", "longitude": "-57.4496"},
        "timezone": {"offset": "+8:00", "description": "Beijing, Perth, Singapore, Hong Kong"},
    },
    "email": "quirilo.nascimento@example.com",
    "birthday": "1979-01-22T03:35:31Z",
    "registered": "2005-07-01T13:52:48Z",
    "telephoneNumbers": ["+556629637520"],
    "mobileNumbers": ["+553270684089"],
    "picture": {
        "large": "https://randomuser.me/api/portraits/men/83.jpg",
        "medium": "https://randomuser.me/api/portraits/med/men/83.jpg",
        "thumbnail": "https://randomuser.me/api/portraits/thumb/men/83.jpg",
    },
    "nationality": "BR",
}


def raw_record(**overrides: Any) -> dict[str, Any]:
    """A valid record in the nested shape of the JSON source.

    Without overrides it is the input that must produce README_OUTPUT. Overrides use
    the CSV column spelling, for example `raw_record(location__state="acre")`.
    """
    record: dict[str, Any] = {
        "gender": "male",
        "name": {"title": "mr", "first": "quirilo", "last": "nascimento"},
        "location": {
            "street": "680 rua treze",
            "city": "varginha",
            "state": "paraná",
            "postcode": 37260,
            "coordinates": {"latitude": "-46.9519", "longitude": "-57.4496"},
            "timezone": {"offset": "+8:00", "description": "Beijing, Perth, Singapore, Hong Kong"},
        },
        "email": "quirilo.nascimento@example.com",
        "dob": {"date": "1979-01-22T03:35:31Z", "age": 39},
        "registered": {"date": "2005-07-01T13:52:48Z", "age": 13},
        "phone": "(66) 2963-7520",
        "cell": "(32) 7068-4089",
        "picture": {
            "large": "https://randomuser.me/api/portraits/men/83.jpg",
            "medium": "https://randomuser.me/api/portraits/med/men/83.jpg",
            "thumbnail": "https://randomuser.me/api/portraits/thumb/men/83.jpg",
        },
    }
    for path, value in overrides.items():
        *parents, leaf = path.split("__")
        node = record
        for parent in parents:
            node = node[parent]
        if value is MISSING:
            del node[leaf]
        else:
            node[leaf] = value
    return record


# Points chosen well inside each published box, and one far from all of them.
IN_FIRST_SPECIAL_BOX = ("-40.0", "-10.0")
IN_SECOND_SPECIAL_BOX = ("-50.0", "-21.0")
IN_NORMAL_BOX = ("-50.0", "-30.0")
OUTSIDE_EVERY_BOX = ("10.0", "10.0")


def customer(number: int, state: str, point: tuple[str, str]) -> dict[str, Any]:
    """A record identified by its number, so that tests can assert on order."""
    return raw_record(
        email=f"customer{number:02d}@example.com",
        location__state=state,
        location__coordinates__latitude=point[0],
        location__coordinates__longitude=point[1],
    )


def email(number: int) -> str:
    return f"customer{number:02d}@example.com"


# Twelve customers: seven in the CSV, five in the JSON.
#   special: 1, 2, 8      normal: 3, 9      laborious: 4, 5, 6, 7, 10, 11, 12
#   sul: 3, 6, 8, 10, 12  sudeste: 1, 7, 9  nordeste: 2  norte: 4, 11  centro-oeste: 5
CSV_CUSTOMERS = [
    customer(1, "são paulo", IN_FIRST_SPECIAL_BOX),
    customer(2, "bahia", IN_SECOND_SPECIAL_BOX),
    customer(3, "paraná", IN_NORMAL_BOX),
    customer(4, "amazonas", OUTSIDE_EVERY_BOX),
    customer(5, "goiás", OUTSIDE_EVERY_BOX),
    customer(6, "paraná", OUTSIDE_EVERY_BOX),
    customer(7, "são paulo", OUTSIDE_EVERY_BOX),
]
JSON_CUSTOMERS = [
    customer(8, "paraná", IN_FIRST_SPECIAL_BOX),
    customer(9, "são paulo", IN_NORMAL_BOX),
    customer(10, "rio grande do sul", OUTSIDE_EVERY_BOX),
    customer(11, "acre", OUTSIDE_EVERY_BOX),
    customer(12, "paraná", OUTSIDE_EVERY_BOX),
]


def _flatten(record: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in record.items():
        if isinstance(value, dict):
            flat.update(_flatten(value, f"{prefix}{key}__"))
        else:
            flat[f"{prefix}{key}"] = value
    return flat


def csv_body(records: list[dict[str, Any]]) -> bytes:
    """The records as the official CSV is served: byte order mark, quoted cells, CRLF lines."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(_flatten(record) for record in records)
    return b"\xef\xbb\xbf" + buffer.getvalue().encode("utf-8")


def json_body(records: list[Any]) -> bytes:
    return json.dumps({"results": records}, ensure_ascii=False).encode("utf-8")


Reply = bytes | httpx.Response | Exception


def offline(csv: Reply, json: Reply) -> httpx.MockTransport:
    """A transport that answers the two configured URLs and nothing else.

    A reply can be a body (served with 200), a ready response, or an exception to raise.
    """
    replies = {settings.csv_url: csv, settings.json_url: json}

    def handler(request: httpx.Request) -> httpx.Response:
        reply = replies.get(str(request.url), httpx.Response(404))
        if isinstance(reply, Exception):
            raise reply
        return reply if isinstance(reply, httpx.Response) else httpx.Response(200, content=reply)

    return httpx.MockTransport(handler)
