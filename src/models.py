"""The API contract: what a customer looks like on the way out, and the query string on the way in.

The output models follow the "Output Contract" of the challenge README field for field.
A record that cannot fill a required field is rejected at load time (see service.py)
instead of being served in a different shape.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field
from pydantic.alias_generators import to_camel

from src.config import settings

DEFAULT_PAGE_SIZE = 10


class CustomerType(StrEnum):
    SPECIAL = "special"
    NORMAL = "normal"
    LABORIOUS = "laborious"


class Region(StrEnum):
    NORTE = "norte"
    NORDESTE = "nordeste"
    CENTRO_OESTE = "centro-oeste"
    SUDESTE = "sudeste"
    SUL = "sul"


class Gender(StrEnum):
    M = "M"
    F = "F"


def _parse_utc(value: object) -> datetime:
    """Accept only an ISO 8601 date-time that carries its UTC offset, and convert it to UTC.

    Pydantic alone would also read a bare number as a Unix timestamp, which would
    turn a shifted CSV column into a plausible looking date. Fractions of a second
    are dropped: the contract has second resolution.
    """
    if not isinstance(value, str):
        raise ValueError("expected an ISO 8601 date-time string")
    parsed = datetime.fromisoformat(value.strip())
    if parsed.tzinfo is None:
        raise ValueError("the date-time has no UTC offset")
    try:
        return parsed.astimezone(UTC).replace(microsecond=0)
    except OverflowError:
        # "0001-01-01T00:00:00+05:00" is valid ISO 8601 but falls before year 1 in UTC.
        raise ValueError("the date-time is out of range once converted to UTC") from None


# Serialised by pydantic as "1979-01-22T03:35:31Z", the format shown in the contract.
UtcDatetime = Annotated[datetime, BeforeValidator(_parse_utc)]


class Contract(BaseModel):
    """Shared rules: camelCase on the wire, surrounding spaces removed, no blank string."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        validate_by_name=True,
        serialize_by_alias=True,
        str_strip_whitespace=True,
        str_min_length=1,
    )


class Name(Contract):
    title: str
    first: str
    last: str


class Coordinates(Contract):
    # The contract shows coordinates as strings; a source that sends numbers is still accepted.
    model_config = ConfigDict(coerce_numbers_to_str=True)

    latitude: str
    longitude: str


class Timezone(Contract):
    offset: str
    description: str


class Location(Contract):
    region: Region | None  # None when the state is not a known Brazilian state
    street: str
    city: str
    state: str
    postcode: int
    coordinates: Coordinates
    timezone: Timezone


class Picture(Contract):
    large: str
    medium: str
    thumbnail: str


class User(Contract):
    type: CustomerType
    gender: Gender | None  # None when the source value is neither male nor female
    name: Name
    location: Location
    email: str
    birthday: UtcDatetime
    registered: UtcDatetime
    telephone_numbers: list[str]
    mobile_numbers: list[str]
    picture: Picture
    nationality: Literal["BR"]


class UsersPage(Contract):
    page_number: int
    page_size: int
    total_count: int  # number of customers matching the filters, not the size of this page
    users: list[User]


class Health(Contract):
    status: Literal["ok"]
    users: int
    rejected_records: int


class UserQuery(BaseModel):
    """Query string of GET /users. An unknown parameter is an error, not something to ignore:
    `?pagesize=50` silently answering with the default page would hide the typo."""

    model_config = ConfigDict(extra="forbid")

    region: Region | None = Field(None, description="Keep only the customers of this region.")
    type: CustomerType | None = Field(None, description="Keep only the customers of this classification.")
    page_number: int = Field(1, alias="pageNumber", ge=1, description="Page to return. The first page is 1.")
    page_size: int = Field(
        DEFAULT_PAGE_SIZE,
        alias="pageSize",
        ge=1,
        le=settings.max_page_size,
        description="Number of customers per page.",
    )
