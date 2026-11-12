"""Business rule 1: classify a customer by the bounding box that contains its coordinates.

The boxes are compared with the labels exactly as published: values labelled "lon"
against the longitude, values labelled "lat" against the latitude. docs/decisions.md
explains why, and what the other reading of the README would give.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from src.models import CustomerType


@dataclass(frozen=True)
class BoundingBox:
    """A latitude/longitude rectangle. A point on an edge is inside."""

    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float

    @classmethod
    def from_published(cls, *, minlon: float, minlat: float, maxlon: float, maxlat: float) -> "BoundingBox":
        """Build a box from the four values as the challenge README lists them.

        In the README every "minlon" is greater than its "maxlon" (-2.196998 and
        -15.411580 for the first box). Taken literally, `minlon <= lon <= maxlon` is
        never true and all 2000 customers come out laborious. A rectangle is the same
        set of points whichever corner is named first, so each axis is sorted.
        """
        low_lat, high_lat = sorted((minlat, maxlat))
        low_lon, high_lon = sorted((minlon, maxlon))
        return cls(min_lat=low_lat, max_lat=high_lat, min_lon=low_lon, max_lon=high_lon)

    def contains(self, latitude: float, longitude: float) -> bool:
        return self.min_lat <= latitude <= self.max_lat and self.min_lon <= longitude <= self.max_lon


Rule = tuple[CustomerType, BoundingBox]

# The first matching rule wins, so SPECIAL has priority over NORMAL. The published
# boxes do not overlap (tests/test_classification.py checks it), so today the order
# changes nothing; it is stated here so that a future overlapping box has a defined answer.
RULES: tuple[Rule, ...] = (
    (
        CustomerType.SPECIAL,
        BoundingBox.from_published(minlon=-2.196998, minlat=-46.361899, maxlon=-15.411580, maxlat=-34.276938),
    ),
    (
        CustomerType.SPECIAL,
        BoundingBox.from_published(
            minlon=-19.766959, minlat=-52.997614, maxlon=-23.966413, maxlat=-44.428305
        ),
    ),
    (
        CustomerType.NORMAL,
        BoundingBox.from_published(
            minlon=-26.155681, minlat=-54.777426, maxlon=-34.016466, maxlat=-46.603598
        ),
    ),
)


def classify(latitude: Any, longitude: Any, rules: Sequence[Rule] = RULES) -> CustomerType:
    """Return the type of the first box containing the point, else LABORIOUS.

    The README defines laborious as "anyone not matching the above". Coordinates that
    are missing or are not numbers cannot be inside a box, so they are laborious too.
    """
    try:
        lat, lon = float(latitude), float(longitude)
    except (TypeError, ValueError, OverflowError):  # OverflowError: an integer too large for a float
        return CustomerType.LABORIOUS
    for customer_type, box in rules:
        if box.contains(lat, lon):
            return customer_type
    return CustomerType.LABORIOUS
