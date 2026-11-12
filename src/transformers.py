"""Business rule 2: field transformations, and the mapping of one raw record to the contract."""

import re
import unicodedata
from collections.abc import Mapping
from typing import Any

from src.classification import classify
from src.models import Gender, Region, User

BRAZIL_CALLING_CODE = "55"

_GENDERS = {"male": Gender.M, "m": Gender.M, "female": Gender.F, "f": Gender.F}

_STATES_BY_REGION = {
    Region.NORTE: ("acre", "amapa", "amazonas", "para", "rondonia", "roraima", "tocantins"),
    Region.NORDESTE: (
        "alagoas",
        "bahia",
        "ceara",
        "maranhao",
        "paraiba",
        "pernambuco",
        "piaui",
        "rio grande do norte",
        "sergipe",
    ),
    Region.CENTRO_OESTE: ("distrito federal", "goias", "mato grosso", "mato grosso do sul"),
    Region.SUDESTE: ("espirito santo", "minas gerais", "rio de janeiro", "sao paulo"),
    Region.SUL: ("parana", "rio grande do sul", "santa catarina"),
}
_REGION_BY_STATE = {state: region for region, states in _STATES_BY_REGION.items() for state in states}

# Digits and the usual separators, with at most one leading "+". Letters (an extension,
# a note typed in the cell) make the value something other than a plain phone number.
_PHONE = re.compile(r"\+?[0-9\s().-]+")


def region_for_state(state: Any) -> Region | None:
    """Return the region of a Brazilian state name, or None when the name is not known.

    The comparison ignores case, accents, punctuation and repeated spaces, so
    "São Paulo", "sao  paulo" and "SAO-PAULO" are the same state. The name itself is
    never rewritten: the caller keeps the value it received.
    """
    if not isinstance(state, str):
        return None
    unaccented = "".join(
        char for char in unicodedata.normalize("NFKD", state) if not unicodedata.combining(char)
    )
    return _REGION_BY_STATE.get(" ".join(re.findall(r"[a-z0-9]+", unaccented.casefold())))


def normalize_gender(gender: Any) -> Gender | None:
    """male -> M, female -> F. Anything else is unknown and stays None rather than guessed."""
    return _GENDERS.get(gender.strip().casefold()) if isinstance(gender, str) else None


def to_e164(phone: Any) -> str | None:
    """Convert a phone number to E.164, or return None when it cannot be done safely.

    This changes the format and nothing else: no digit is added, dropped or
    reinterpreted, and the result is not checked against the real numbering plan
    (docs/decisions.md gives the measurements behind that choice).

    - 10 or 11 digits are a Brazilian national number (area code + subscriber): "+55" is added.
    - A number that already carries 55, written "+55 ..." or "55 ...", is kept as it is.
    - A number written with "+" and another calling code is kept as it is.
    - Any other digit count is incomplete or overlong: no number is produced.
    - 11 digits starting with 0 can be a trunk prefix plus 10 digits, or an area code
      plus 9 digits. The two readings give different numbers, so none is produced.
    """
    if not isinstance(phone, str) or not _PHONE.fullmatch(phone.strip()):
        return None
    digits = re.sub(r"[^0-9]", "", phone)
    written_with_plus = phone.strip().startswith("+")
    if written_with_plus and not digits.startswith(BRAZIL_CALLING_CODE):
        return f"+{digits}" if 8 <= len(digits) <= 15 and digits[0] != "0" else None
    if written_with_plus or (len(digits) in (12, 13) and digits.startswith(BRAZIL_CALLING_CODE)):
        digits = digits[len(BRAZIL_CALLING_CODE) :]
    is_complete = len(digits) == 10 or (len(digits) == 11 and digits[0] != "0")
    return f"+{BRAZIL_CALLING_CODE}{digits}" if is_complete else None


def _section(record: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = record.get(key)
    return value if isinstance(value, Mapping) else {}


def _e164_list(phone: Any) -> list[str]:
    number = to_e164(phone)
    return [number] if number else []


def to_user(record: Any) -> User:
    """Apply every business rule to one raw record.

    Raises ValueError (pydantic's ValidationError is one) when the record cannot
    satisfy the output contract. `dob.age` and `registered.age` are dropped simply
    because only the dates are read.
    """
    if not isinstance(record, Mapping):
        raise ValueError("the record is not an object")
    location = _section(record, "location")
    coordinates = _section(location, "coordinates")
    return User.model_validate(
        {
            "type": classify(coordinates.get("latitude"), coordinates.get("longitude")),
            "gender": normalize_gender(record.get("gender")),
            "name": record.get("name"),
            "location": {**location, "region": region_for_state(location.get("state"))},
            "email": record.get("email"),
            "birthday": _section(record, "dob").get("date"),
            "registered": _section(record, "registered").get("date"),
            "telephone_numbers": _e164_list(record.get("phone")),
            "mobile_numbers": _e164_list(record.get("cell")),
            "picture": record.get("picture"),
            "nationality": "BR",
        }
    )
