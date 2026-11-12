"""Load both sources once, keep the result in memory, and answer queries from it."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import ValidationError

from src.config import Settings
from src.loaders import SourceError, fetch, parse_csv, parse_json
from src.models import CustomerType, Region, User, UsersPage
from src.transformers import to_user

logger = logging.getLogger(__name__)

# A broken export can reject every row. The count is always logged; the detail only for the first ones.
MAX_REJECTION_DETAILS = 10


@dataclass(frozen=True)
class UserStore:
    """The customers, in a fixed order: CSV rows first, then JSON records, each in file order.

    That order never changes while the process runs, which is what keeps pagination stable.
    """

    users: tuple[User, ...]
    rejected: int = 0

    def page(
        self,
        *,
        region: Region | None = None,
        customer_type: CustomerType | None = None,
        page_number: int = 1,
        page_size: int = 10,
    ) -> UsersPage:
        """Filter, then paginate. A page past the end is empty, not an error."""
        # A full scan per request: about 0.2 ms for 2000 customers, so no index is kept.
        matches = [
            user
            for user in self.users
            if (region is None or user.location.region == region)
            and (customer_type is None or user.type == customer_type)
        ]
        start = (page_number - 1) * page_size
        return UsersPage(
            page_number=page_number,
            page_size=page_size,
            total_count=len(matches),
            users=matches[start : start + page_size],
        )


async def load_users(settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> UserStore:
    """Download, parse and transform both sources.

    Raises SourceError as soon as one source is unusable: the caller gets either the
    whole data set or nothing. `transport` lets the tests replace the network.
    """
    sources: tuple[tuple[str, str, Callable[[str], list[Any]]], ...] = (
        ("csv", settings.csv_url, parse_csv),
        ("json", settings.json_url, parse_json),
    )
    users: list[User] = []
    rejected = 0
    async with httpx.AsyncClient(
        timeout=settings.http_timeout_seconds, follow_redirects=True, transport=transport
    ) as client:
        for name, url, parse in sources:
            try:
                records = parse(await fetch(client, url))
                accepted, refused = _transform(name, records)
                if not accepted:
                    raise SourceError(f"no usable record out of {len(records)}")
            except SourceError as exc:
                raise SourceError(f"{name} source: {exc}") from exc
            logger.info(
                "source=%s records=%d accepted=%d rejected=%d", name, len(records), len(accepted), refused
            )
            users += accepted
            rejected += refused
    return UserStore(users=tuple(users), rejected=rejected)


def _transform(source: str, records: list[Any]) -> tuple[list[User], int]:
    """Turn raw records into users. A record that breaks the contract is counted, never served."""
    users: list[User] = []
    rejected = 0
    for position, record in enumerate(records, start=1):
        try:
            users.append(to_user(record))
        except ValueError as exc:
            rejected += 1
            if rejected <= MAX_REJECTION_DETAILS:
                logger.warning("source=%s record=%d rejected: %s", source, position, _reasons(exc))
    return users, rejected


def _reasons(exc: ValueError) -> str:
    """Name the fields at fault and the kind of error, never the values: logs hold no personal data."""
    if isinstance(exc, ValidationError):
        errors = exc.errors()
        return ", ".join(f"{'.'.join(map(str, error['loc']))} ({error['type']})" for error in errors)
    return str(exc)
