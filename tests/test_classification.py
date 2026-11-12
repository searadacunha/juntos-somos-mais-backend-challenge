from itertools import combinations

import pytest

from src.classification import RULES, BoundingBox, classify
from src.models import CustomerType

SPECIAL_1, SPECIAL_2, NORMAL = (box for _, box in RULES)


def test_rules_hold_the_three_published_boxes_in_priority_order():
    assert [customer_type for customer_type, _ in RULES] == ["special", "special", "normal"]
    # Same numbers as the README, each axis sorted.
    assert (
        BoundingBox(min_lat=-46.361899, max_lat=-34.276938, min_lon=-15.411580, max_lon=-2.196998)
        == SPECIAL_1
    )
    assert (
        BoundingBox(min_lat=-52.997614, max_lat=-44.428305, min_lon=-23.966413, max_lon=-19.766959)
        == SPECIAL_2
    )
    assert (
        BoundingBox(min_lat=-54.777426, max_lat=-46.603598, min_lon=-34.016466, max_lon=-26.155681) == NORMAL
    )


def test_from_published_sorts_both_axes_whichever_corner_comes_first():
    expected = BoundingBox(min_lat=0, max_lat=10, min_lon=0, max_lon=5)
    assert BoundingBox.from_published(minlon=5, minlat=10, maxlon=0, maxlat=0) == expected
    assert BoundingBox.from_published(minlon=0, minlat=0, maxlon=5, maxlat=10) == expected


def test_the_readme_order_taken_literally_would_match_nobody():
    """Why the axes are sorted: the README names the larger longitude "min"."""
    as_written = BoundingBox(min_lat=-46.361899, max_lat=-34.276938, min_lon=-2.196998, max_lon=-15.411580)
    assert not as_written.contains(-40.0, -10.0)
    assert SPECIAL_1.contains(-40.0, -10.0)


@pytest.mark.parametrize(
    ("latitude", "longitude", "expected"),
    [
        pytest.param("-40.0", "-10.0", "special", id="inside-first-special-box"),
        pytest.param("-50.0", "-21.0", "special", id="inside-second-special-box"),
        pytest.param("-50.0", "-30.0", "normal", id="inside-normal-box"),
        pytest.param("-36.7158", "-9.1518", "special", id="real-customer-of-the-dataset-special"),
        pytest.param("-47.3360", "-31.9196", "normal", id="real-customer-of-the-dataset-normal"),
        pytest.param("-46.9519", "-57.4496", "laborious", id="readme-example"),
        pytest.param("10.0", "10.0", "laborious", id="far-from-every-box"),
        pytest.param("-40.0", "-30.0", "laborious", id="special-latitude-with-normal-longitude"),
        pytest.param("-10.0", "-40.0", "laborious", id="first-special-box-with-axes-swapped"),
        pytest.param(-40.0, -10, "special", id="numbers-instead-of-strings"),
        pytest.param(" -40.0 ", "\t-10.0\n", "special", id="surrounding-whitespace"),
    ],
)
def test_classify_points(latitude, longitude, expected):
    assert classify(latitude, longitude) == expected


@pytest.mark.parametrize(
    ("customer_type", "box"), RULES, ids=["first-special-box", "second-special-box", "normal-box"]
)
def test_the_edges_of_a_box_are_inside_and_the_next_point_is_outside(customer_type, box):
    step = 0.000001  # the precision of the published values
    latitude = (box.min_lat + box.max_lat) / 2
    longitude = (box.min_lon + box.max_lon) / 2
    for corner_lat in (box.min_lat, box.max_lat):
        for corner_lon in (box.min_lon, box.max_lon):
            assert classify(corner_lat, corner_lon) == customer_type
    assert classify(box.min_lat, longitude) == customer_type
    assert classify(box.max_lat, longitude) == customer_type
    assert classify(latitude, box.min_lon) == customer_type
    assert classify(latitude, box.max_lon) == customer_type

    assert classify(box.min_lat - step, longitude) == "laborious"
    assert classify(box.max_lat + step, longitude) == "laborious"
    assert classify(latitude, box.min_lon - step) == "laborious"
    assert classify(latitude, box.max_lon + step) == "laborious"


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [
        pytest.param(None, None, id="both-missing"),
        pytest.param("-40.0", None, id="longitude-missing"),
        pytest.param(None, "-10.0", id="latitude-missing"),
        pytest.param("", "", id="empty-strings"),
        pytest.param("south", "west", id="words"),
        pytest.param("-40,0", "-10,0", id="decimal-comma"),
        pytest.param("nan", "nan", id="not-a-number"),
        pytest.param("-inf", "-10.0", id="infinite"),
        pytest.param("-400.0", "-10.0", id="latitude-out-of-range"),
        pytest.param([-40.0], {"lon": -10.0}, id="wrong-types"),
        pytest.param(10**400, "-10.0", id="integer-too-large-for-a-float"),
    ],
)
def test_coordinates_that_are_missing_or_invalid_are_laborious(latitude, longitude):
    assert classify(latitude, longitude) == CustomerType.LABORIOUS


def test_the_published_boxes_do_not_overlap():
    """So on the real rules a customer can never be both special and normal."""
    for first, second in combinations((SPECIAL_1, SPECIAL_2, NORMAL), 2):
        apart_in_latitude = first.max_lat < second.min_lat or second.max_lat < first.min_lat
        apart_in_longitude = first.max_lon < second.min_lon or second.max_lon < first.min_lon
        assert apart_in_latitude or apart_in_longitude


def test_when_boxes_overlap_the_first_rule_wins():
    wide = BoundingBox(min_lat=0, max_lat=10, min_lon=0, max_lon=10)
    inner = BoundingBox(min_lat=4, max_lat=6, min_lon=4, max_lon=6)
    special_first = ((CustomerType.SPECIAL, inner), (CustomerType.NORMAL, wide))
    normal_first = ((CustomerType.NORMAL, wide), (CustomerType.SPECIAL, inner))

    assert classify(5, 5, special_first) == "special"
    assert classify(5, 5, normal_first) == "normal"
    assert classify(1, 1, special_first) == "normal"
    assert classify(11, 11, special_first) == "laborious"


def test_the_labels_are_applied_as_published_not_transposed():
    """Pins the reading chosen in docs/decisions.md, so that changing it is a visible act.

    With the published labels the first special box lies in the South Atlantic and the
    city of São Paulo (latitude -23.55, longitude -46.63) is laborious. If the README
    had the two axes transposed, São Paulo would be special instead.
    """
    assert classify(-23.55, -46.63) == "laborious"
    assert classify(-40.0, -10.0) == "special"
