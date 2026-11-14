"""A duplicate CSV header must not silently overwrite a customer field."""

import pytest

from src.loaders import CSV_COLUMNS, SourceError, parse_csv


def test_duplicate_required_csv_header_is_rejected():
    header = ",".join((*CSV_COLUMNS, "email"))
    row = ",".join(["value"] * (len(CSV_COLUMNS) + 1))
    with pytest.raises(SourceError, match="duplicate column names"):
        parse_csv(header + "\n" + row + "\n")


def test_duplicate_unknown_csv_header_is_rejected():
    header = ",".join((*CSV_COLUMNS, "unexpected", "unexpected"))
    row = ",".join(["value"] * (len(CSV_COLUMNS) + 2))
    with pytest.raises(SourceError, match="duplicate column names"):
        parse_csv(header + "\n" + row + "\n")
