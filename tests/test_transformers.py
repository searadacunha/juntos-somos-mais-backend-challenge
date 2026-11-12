import pytest
from pydantic import ValidationError

from src.models import Gender, Region
from src.transformers import normalize_gender, region_for_state, to_e164, to_user
from tests.builders import MISSING, README_OUTPUT, raw_record

# The 27 state names exactly as they are spelled in the official files.
STATES_OF_THE_DATASET = {
    "acre": "norte",
    "amapá": "norte",
    "amazonas": "norte",
    "pará": "norte",
    "rondônia": "norte",
    "roraima": "norte",
    "tocantins": "norte",
    "alagoas": "nordeste",
    "bahia": "nordeste",
    "ceará": "nordeste",
    "maranhão": "nordeste",
    "paraíba": "nordeste",
    "pernambuco": "nordeste",
    "piauí": "nordeste",
    "rio grande do norte": "nordeste",
    "sergipe": "nordeste",
    "distrito federal": "centro-oeste",
    "goiás": "centro-oeste",
    "mato grosso": "centro-oeste",
    "mato grosso do sul": "centro-oeste",
    "espírito santo": "sudeste",
    "minas gerais": "sudeste",
    "rio de janeiro": "sudeste",
    "são paulo": "sudeste",
    "paraná": "sul",
    "rio grande do sul": "sul",
    "santa catarina": "sul",
}


# --- phones -----------------------------------------------------------------

CONVERTIBLE_PHONES = [
    pytest.param("(86) 8370-9831", "+558683709831", id="example-of-the-challenge-readme"),
    pytest.param("(11) 91234-5678", "+5511912345678", id="mobile-with-nine-digits"),
    pytest.param("86 8370 9831", "+558683709831", id="spaces"),
    pytest.param("86.8370.9831", "+558683709831", id="dots"),
    pytest.param("86-8370-9831", "+558683709831", id="hyphens"),
    pytest.param("8683709831", "+558683709831", id="digits-only"),
    pytest.param("  (86) 8370-9831\t", "+558683709831", id="surrounding-whitespace"),
    pytest.param("+55 86 8370-9831", "+558683709831", id="already-international"),
    pytest.param("+558683709831", "+558683709831", id="already-e164"),
    pytest.param("55 86 8370-9831", "+558683709831", id="calling-code-without-plus"),
    pytest.param("5511912345678", "+5511912345678", id="calling-code-without-plus-mobile"),
    pytest.param("(55) 3222-1234", "+555532221234", id="area-code-55-is-not-the-calling-code"),
    pytest.param("(01) 5415-5648", "+550154155648", id="dataset-area-code-starting-with-zero"),
    pytest.param("+1 305 555 0100", "+13055550100", id="foreign-number-keeps-its-calling-code"),
    pytest.param("+43 1234", "+431234", id="foreign-six-digits-the-shortest-accepted"),
    pytest.param("+123 456 789 012 345", "+123456789012345", id="foreign-fifteen-digits-the-e164-maximum"),
]


@pytest.mark.parametrize(("phone", "expected"), CONVERTIBLE_PHONES)
def test_to_e164_converts_complete_numbers_digit_for_digit(phone, expected):
    assert to_e164(phone) == expected


@pytest.mark.parametrize(("phone", "expected"), CONVERTIBLE_PHONES)
def test_to_e164_leaves_its_own_output_unchanged(phone, expected):
    assert to_e164(expected) == expected


@pytest.mark.parametrize(
    "phone",
    [
        pytest.param("8370-9831", id="no-area-code"),
        pytest.param("(86) 8370-983", id="one-digit-short"),
        pytest.param("(86) 8370-98311 2", id="too-many-digits"),
        pytest.param("+55 86 8370-983", id="international-but-one-digit-short"),
        pytest.param("5508683709831", id="calling-code-then-trunk-zero"),
        pytest.param("086 8370 9831", id="eleven-digits-starting-with-zero-is-ambiguous"),
        pytest.param("(86) 8370-9831 ramal 2", id="extension-written-in-letters"),
        pytest.param("86 8370 9831 / 86 8370 9832", id="two-numbers-in-one-cell"),
        pytest.param("not a phone", id="letters"),
        pytest.param("", id="empty"),
        pytest.param("   ", id="blank"),
        pytest.param("+", id="plus-alone"),
        pytest.param("++55 86 8370-9831", id="two-plus-signs"),
        pytest.param("+0 86 8370 9831", id="calling-code-starting-with-zero"),
        pytest.param("+1 23", id="foreign-and-too-short"),
        pytest.param("+43 123", id="foreign-five-digits"),
        pytest.param("+1234567890123456", id="more-than-fifteen-digits"),
        pytest.param("٨٦٨٣٧٠٩٨٣١", id="digits-of-another-script"),
        pytest.param(None, id="missing"),
        pytest.param(8683709831, id="number-instead-of-text"),
    ],
)
def test_to_e164_produces_nothing_rather_than_a_guess(phone):
    assert to_e164(phone) is None


# --- regions ----------------------------------------------------------------


def test_the_dataset_spells_27_states():
    assert len(STATES_OF_THE_DATASET) == 27


@pytest.mark.parametrize(("state", "region"), STATES_OF_THE_DATASET.items())
def test_every_state_of_the_dataset_has_its_region(state, region):
    assert region_for_state(state) == region


@pytest.mark.parametrize(
    ("region", "count"),
    [("norte", 7), ("nordeste", 9), ("centro-oeste", 4), ("sudeste", 4), ("sul", 3)],
)
def test_each_region_has_the_right_number_of_states(region, count):
    assert sum(1 for state in STATES_OF_THE_DATASET if region_for_state(state) == region) == count


@pytest.mark.parametrize(
    ("state", "region"),
    [
        pytest.param("São Paulo", Region.SUDESTE, id="capitalised"),
        pytest.param("SAO PAULO", Region.SUDESTE, id="upper-case-without-accent"),
        pytest.param("  sao   paulo ", Region.SUDESTE, id="extra-spaces"),
        pytest.param("sao-paulo", Region.SUDESTE, id="hyphen"),
        pytest.param("são paulo", Region.SUDESTE, id="accent-as-a-combining-character"),
        pytest.param("Espirito Santo", Region.SUDESTE, id="accent-left-out"),
        pytest.param("Pará", Region.NORTE, id="para-is-not-parana"),
        pytest.param("Paraná", Region.SUL, id="parana-is-not-para"),
        pytest.param("Paraíba", Region.NORDESTE, id="paraiba-is-not-parana"),
        pytest.param("Mato Grosso", Region.CENTRO_OESTE, id="mato-grosso"),
        pytest.param("Mato Grosso do Sul", Region.CENTRO_OESTE, id="mato-grosso-do-sul-is-not-sul"),
        pytest.param("Rio Grande do Norte", Region.NORDESTE, id="rio-grande-do-norte-is-not-norte"),
    ],
)
def test_region_lookup_ignores_case_accents_and_spacing(state, region):
    assert region_for_state(state) == region


@pytest.mark.parametrize("state", ["", "atlantis", "SP", "texas", None, 35], ids=repr)
def test_an_unknown_state_has_no_region(state):
    assert region_for_state(state) is None


# --- gender -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("gender", "expected"),
    [
        ("male", Gender.M),
        ("female", Gender.F),
        ("MALE", Gender.M),
        (" Female ", Gender.F),
        ("m", Gender.M),
        ("F", Gender.F),
    ],
)
def test_gender_is_mapped_to_one_letter(gender, expected):
    assert normalize_gender(gender) == expected


@pytest.mark.parametrize("gender", ["", "other", "x", "malefemale", None, 1], ids=repr)
def test_an_unexpected_gender_is_unknown_not_guessed(gender):
    assert normalize_gender(gender) is None


# --- one whole record ---------------------------------------------------------


def as_json(record):
    return to_user(record).model_dump(mode="json")


def test_the_readme_example_comes_out_exactly_as_the_contract_shows():
    produced = as_json(raw_record())
    assert produced == README_OUTPUT
    assert list(produced) == list(README_OUTPUT)  # same field order as the contract
    assert list(produced["location"]) == list(README_OUTPUT["location"])


def test_ages_are_removed_and_dates_move_to_birthday_and_registered():
    produced = as_json(raw_record(dob__age=39, registered__age=13))
    assert "dob" not in produced
    assert "age" not in str(produced)
    assert produced["birthday"] == "1979-01-22T03:35:31Z"
    assert produced["registered"] == "2005-07-01T13:52:48Z"


def test_a_csv_row_gives_the_same_user_as_the_json_record():
    """CSV cells are all text: the postcode and the ages arrive as strings."""
    from_csv = raw_record(location__postcode="37260", dob__age="39", registered__age="13")
    assert as_json(from_csv) == README_OUTPUT


def test_the_state_name_is_kept_as_received_while_the_region_is_found():
    produced = as_json(raw_record(location__state="SÃO PAULO"))
    assert produced["location"]["state"] == "SÃO PAULO"
    assert produced["location"]["region"] == "sudeste"


def test_surrounding_spaces_are_removed_from_text_fields():
    produced = as_json(raw_record(location__street="8558 rua belo horizonte ", name__first=" ione"))
    assert produced["location"]["street"] == "8558 rua belo horizonte"
    assert produced["name"]["first"] == "ione"


def test_business_fallbacks_keep_the_customer():
    produced = as_json(
        raw_record(
            gender="unknown",
            location__state="atlantis",
            phone="8370-9831",
            cell=None,
            location__coordinates__latitude="not a number",
        )
    )
    assert produced["gender"] is None
    assert produced["location"]["region"] is None
    assert produced["telephoneNumbers"] == []
    assert produced["mobileNumbers"] == []
    assert produced["type"] == "laborious"
    assert produced["location"]["coordinates"]["latitude"] == "not a number"


def test_coordinates_sent_as_numbers_are_classified_and_served_as_text():
    produced = as_json(
        raw_record(location__coordinates__latitude=-40.0, location__coordinates__longitude=-10)
    )
    assert produced["type"] == "special"
    assert produced["location"]["coordinates"] == {"latitude": "-40.0", "longitude": "-10"}


def test_a_coordinate_too_large_for_a_float_is_laborious_not_a_crash():
    produced = as_json(raw_record(location__coordinates__latitude=10**400))
    assert produced["type"] == "laborious"


def test_a_date_with_another_offset_is_converted_to_utc():
    produced = as_json(raw_record(dob__date="1979-01-22T05:35:31+02:00"))
    assert produced["birthday"] == "1979-01-22T03:35:31Z"


def test_fractions_of_a_second_are_dropped_to_match_the_contract():
    produced = as_json(raw_record(dob__date="1979-01-22T03:35:31.987Z"))
    assert produced["birthday"] == "1979-01-22T03:35:31Z"


@pytest.mark.parametrize(
    ("override", "field"),
    [
        pytest.param({"name": MISSING}, "name", id="name-missing"),
        pytest.param({"name__last": None}, "name.last", id="last-name-null"),
        pytest.param({"email": "   "}, "email", id="email-blank"),
        pytest.param({"location": "somewhere"}, "location.street", id="location-is-not-an-object"),
        pytest.param({"location__postcode": "01310-100"}, "location.postcode", id="postcode-not-a-number"),
        pytest.param({"location__coordinates": MISSING}, "location.coordinates", id="coordinates-missing"),
        pytest.param(
            {"location__coordinates__latitude": None}, "location.coordinates.latitude", id="latitude-null"
        ),
        pytest.param(
            {"location__coordinates__longitude": " "}, "location.coordinates.longitude", id="longitude-blank"
        ),
        pytest.param({"picture__thumbnail": MISSING}, "picture.thumbnail", id="thumbnail-missing"),
        pytest.param({"dob": MISSING}, "birthday", id="date-of-birth-missing"),
        pytest.param({"dob__date": "22/01/1979"}, "birthday", id="date-in-another-format"),
        pytest.param({"dob__date": "1979-01-22T03:35:31"}, "birthday", id="date-without-utc-offset"),
        pytest.param({"registered__date": "1120225968"}, "registered", id="date-as-unix-timestamp-text"),
        pytest.param({"registered__date": 1120225968}, "registered", id="date-as-unix-timestamp-number"),
        pytest.param({"dob__date": "0001-01-01T00:00:00+05:00"}, "birthday", id="date-before-year-1-in-utc"),
        pytest.param(
            {"registered__date": "9999-12-31T23:00:00-05:00"}, "registered", id="date-after-year-9999-in-utc"
        ),
    ],
)
def test_a_record_that_cannot_fill_the_contract_is_refused(override, field):
    with pytest.raises(ValidationError) as failure:
        to_user(raw_record(**override))
    assert field in {".".join(map(str, error["loc"])) for error in failure.value.errors()}


@pytest.mark.parametrize("record", [None, "ione", 42, ["gender", "male"]], ids=repr)
def test_a_record_that_is_not_an_object_is_refused(record):
    with pytest.raises(ValueError, match="not an object"):
        to_user(record)
