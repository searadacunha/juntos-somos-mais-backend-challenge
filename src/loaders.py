"""Download the two partner files and parse them into raw records. No business rule lives here."""

import csv
import io
import json
from typing import Any

import httpx


class SourceError(RuntimeError):
    """A source could not be downloaded, or is not in the expected format."""


async def fetch(client: httpx.AsyncClient, url: str) -> str:
    """Return the body behind `url` as text.

    A signed URL carries its secret in the query string, and httpx puts the URL in
    its error messages. So the error raised here names the failure without the URL,
    and `from None` keeps the httpx error out of the traceback the server prints.
    """
    try:
        response = await client.get(url)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise SourceError(f"download failed with HTTP {exc.response.status_code}") from None
    except (httpx.HTTPError, httpx.InvalidURL) as exc:
        raise SourceError(f"download failed with {type(exc).__name__}") from None
    try:
        # "utf-8-sig" also reads plain UTF-8. The official CSV starts with a byte order
        # mark that would otherwise become part of the first column name.
        return response.content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SourceError("the body is not UTF-8 text") from exc


def parse_csv(text: str) -> list[dict[str, Any]]:
    """Parse the CSV export. A column named `name__first` becomes `{"name": {"first": ...}}`."""
    try:
        return [_nest(row) for row in csv.DictReader(io.StringIO(text))]
    except csv.Error as exc:
        raise SourceError(f"invalid CSV: {exc}") from exc


def _nest(row: dict[Any, Any]) -> dict[str, Any]:
    if None in row:
        # More cells than column names: the values cannot be trusted to be under the
        # right name. An empty record is returned so that validation rejects the row.
        return {}
    record: dict[str, Any] = {}
    for column, value in row.items():
        *parents, leaf = column.split("__")
        node = record
        for parent in parents:
            node = node.setdefault(parent, {})
        node[leaf] = value
    return record


def parse_json(text: str) -> list[Any]:
    """Parse the JSON export: an object whose "results" key holds the list of records."""
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SourceError(f"invalid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno})") from exc
    results = document.get("results") if isinstance(document, dict) else None
    if not isinstance(results, list):
        raise SourceError('invalid JSON: expected an object with a "results" list')
    return results
