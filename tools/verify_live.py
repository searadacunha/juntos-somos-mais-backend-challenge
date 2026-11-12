"""Check a running instance of the API against a second implementation of the rules.

Standard library only, and nothing is imported from src/. The bounding boxes are read
again from the challenge README (at the commit this solution answers), the regions
come from a separate list of the 27 states, and every expected customer is rebuilt
from the two official files. Then every page of both routes is compared with it.

It expects the official data, whose phone numbers all have 10 digits.

Usage: python tools/verify_live.py [base URL, default http://localhost:8080]
"""

import csv
import io
import json
import re
import sys
import urllib.error
import urllib.request

README = (
    "https://raw.githubusercontent.com/juntossomosmais/backend-challenge/"
    "e3965fb7f1998fba8d92d8f08ce37759dda3d5ae/README.md"
)
CSV_URL = "https://storage.googleapis.com/juntossomosmais-code-challenge/input-backend.csv"
JSON_URL = "https://storage.googleapis.com/juntossomosmais-code-challenge/input-backend.json"

REGIONS = {
    "norte": ["acre", "amapá", "amazonas", "pará", "rondônia", "roraima", "tocantins"],
    "nordeste": [
        "alagoas",
        "bahia",
        "ceará",
        "maranhão",
        "paraíba",
        "pernambuco",
        "piauí",
        "rio grande do norte",
        "sergipe",
    ],
    "centro-oeste": ["distrito federal", "goiás", "mato grosso", "mato grosso do sul"],
    "sudeste": ["espírito santo", "minas gerais", "rio de janeiro", "são paulo"],
    "sul": ["paraná", "rio grande do sul", "santa catarina"],
}
REGION_OF = {state: region for region, states in REGIONS.items() for state in states}
TYPES = ("special", "normal", "laborious")


def download(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=30) as response:
        return response.read()


def published_boxes() -> list[tuple[str, float, float, float, float]]:
    row = re.compile(
        r"\|\s*\*\*(SPECIAL|NORMAL)\*\*\s*\|\s*minlon:\s*(-?[\d.]+),\s*minlat:\s*(-?[\d.]+),"
        r"\s*maxlon:\s*(-?[\d.]+),\s*maxlat:\s*(-?[\d.]+)"
    )
    boxes = [
        (label.lower(), *map(float, values)) for label, *values in row.findall(download(README).decode())
    ]
    assert len(boxes) == 3, f"expected 3 boxes in the README, found {boxes}"
    return boxes


def expected_type(boxes, latitude: str, longitude: str) -> str:
    lat, lon = float(latitude), float(longitude)
    for label, minlon, minlat, maxlon, maxlat in boxes:
        lat_ok = min(minlat, maxlat) <= lat <= max(minlat, maxlat)
        lon_ok = min(minlon, maxlon) <= lon <= max(minlon, maxlon)
        if lat_ok and lon_ok:
            return label
    return "laborious"


def from_csv_row(row: dict) -> dict:
    return {
        "gender": row["gender"],
        "name": {"title": row["name__title"], "first": row["name__first"], "last": row["name__last"]},
        "location": {
            "street": row["location__street"],
            "city": row["location__city"],
            "state": row["location__state"],
            "postcode": row["location__postcode"],
            "coordinates": {
                "latitude": row["location__coordinates__latitude"],
                "longitude": row["location__coordinates__longitude"],
            },
            "timezone": {
                "offset": row["location__timezone__offset"],
                "description": row["location__timezone__description"],
            },
        },
        "email": row["email"],
        "dob": {"date": row["dob__date"]},
        "registered": {"date": row["registered__date"]},
        "phone": row["phone"],
        "cell": row["cell"],
        "picture": {
            "large": row["picture__large"],
            "medium": row["picture__medium"],
            "thumbnail": row["picture__thumbnail"],
        },
    }


def expected_user(boxes, raw: dict) -> dict:
    location = raw["location"]

    def e164(number: str) -> list[str]:
        digits = re.sub(r"\D", "", number)
        assert len(digits) == 10, f"unexpected phone shape in the official data: {number!r}"
        return ["+55" + digits]

    return {
        "type": expected_type(
            boxes, location["coordinates"]["latitude"], location["coordinates"]["longitude"]
        ),
        "gender": {"male": "M", "female": "F"}[raw["gender"]],
        "name": {part: raw["name"][part].strip() for part in ("title", "first", "last")},
        "location": {
            "region": REGION_OF[location["state"]],
            "street": location["street"].strip(),
            "city": location["city"].strip(),
            "state": location["state"],
            "postcode": int(location["postcode"]),
            "coordinates": dict(location["coordinates"]),
            "timezone": dict(location["timezone"]),
        },
        "email": raw["email"],
        "birthday": raw["dob"]["date"],
        "registered": raw["registered"]["date"],
        "telephoneNumbers": e164(raw["phone"]),
        "mobileNumbers": e164(raw["cell"]),
        "picture": dict(raw["picture"]),
        "nationality": "BR",
    }


def main(base: str) -> int:
    boxes = published_boxes()
    rows = list(csv.DictReader(io.StringIO(download(CSV_URL).decode("utf-8-sig"))))
    records = json.loads(download(JSON_URL))["results"]
    expected = [expected_user(boxes, from_csv_row(row)) for row in rows] + [
        expected_user(boxes, record) for record in records
    ]
    print(f"expected customers rebuilt: {len(expected)} ({len(rows)} CSV rows + {len(records)} JSON records)")

    failures = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        print(f"{'ok  ' if ok else 'FAIL'}  {label}{f': {detail}' if detail else ''}")
        if not ok:
            failures.append(label)

    def get(path: str):
        try:
            with urllib.request.urlopen(base + path, timeout=15) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, json.load(error)

    def walk(route: str, page_size: int, filters: str = "") -> tuple[list, set]:
        users, totals, page = [], set(), 1
        while True:
            status, body = get(f"{route}?pageNumber={page}&pageSize={page_size}{filters}")
            assert status == 200, (route, page, status, body)
            assert list(body) == ["pageNumber", "pageSize", "totalCount", "users"], list(body)
            assert (body["pageNumber"], body["pageSize"]) == (page, page_size)
            totals.add(body["totalCount"])
            if not body["users"]:
                return users, totals
            users += body["users"]
            page += 1

    readme_route, readme_totals = walk("/users", 100)
    validator_route, validator_totals = walk("/api/v1/users", 100)
    check("totalCount without filter is 2000 on /users", readme_totals == {2000}, str(readme_totals))
    check(
        "totalCount without filter is 2000 on /api/v1/users",
        validator_totals == {2000},
        str(validator_totals),
    )
    check("both routes return the same customers", readme_route == validator_route)
    # strict=False: a difference in length is reported by the check below, not raised.
    pairs = list(zip(expected, readme_route, strict=False))
    mismatches = [index for index, (want, got) in enumerate(pairs) if want != got]
    check(
        "every customer equals its recomputation, in load order",
        len(readme_route) == len(expected) and not mismatches,
        f"{len(readme_route)} served, {len(mismatches)} different"
        + (f", first at {mismatches[0]}" if mismatches else ""),
    )
    check("field order follows the contract", all(list(w) == list(g) for w, g in pairs))

    small_pages, _ = walk("/users", 7)
    check("pages of 7 give the same sequence as pages of 100", small_pages == readme_route)

    for customer_type in TYPES:
        users, totals = walk("/api/v1/users", 100, f"&type={customer_type}")
        want = [user for user in expected if user["type"] == customer_type]
        check(f"type={customer_type}", users == want and totals == {len(want)}, f"{len(want)} customers")
    for region in REGIONS:
        users, totals = walk("/users", 100, f"&region={region}")
        want = [user for user in expected if user["location"]["region"] == region]
        check(f"region={region}", users == want and totals == {len(want)}, f"{len(want)} customers")
    wrong = []
    for region in REGIONS:
        for customer_type in TYPES:
            users, totals = walk("/users", 50, f"&region={region}&type={customer_type}")
            want = [u for u in expected if u["location"]["region"] == region and u["type"] == customer_type]
            if users != want or totals != {len(want)}:
                wrong.append(f"{region}&{customer_type}")
    check("the 15 region and type combinations", not wrong, ", ".join(wrong))

    status, body = get("/users?pageNumber=21&pageSize=100")
    check(
        "a page after the last is empty", status == 200 and body["users"] == [] and body["totalCount"] == 2000
    )
    refused = [
        f"{route}?{query}"
        for route in ("/users", "/api/v1/users")
        for query in (
            "pageNumber=0",
            "pageSize=0",
            "pageSize=101",
            "pageNumber=abc",
            "region=south",
            "page=2",
        )
        if get(f"{route}?{query}")[0] != 422
    ]
    check("invalid or unknown parameters give 422", not refused, ", ".join(refused))
    status, body = get("/health")
    check(
        "health",
        status == 200 and body == {"status": "ok", "users": 2000, "rejectedRecords": 0},
        json.dumps(body),
    )

    print("all checks passed" if not failures else f"{len(failures)} check(s) failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"))
