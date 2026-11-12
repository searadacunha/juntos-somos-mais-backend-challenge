import pytest
from pydantic import ValidationError

from src.config import Settings


def test_without_any_variable_the_official_sources_are_used():
    settings = Settings.model_validate({})
    assert (
        settings.csv_url == "https://storage.googleapis.com/juntossomosmais-code-challenge/input-backend.csv"
    )
    assert (
        settings.json_url
        == "https://storage.googleapis.com/juntossomosmais-code-challenge/input-backend.json"
    )
    assert (settings.http_timeout_seconds, settings.max_page_size, settings.log_level) == (10.0, 100, "INFO")


def test_environment_variables_arrive_as_text_and_are_converted():
    settings = Settings.model_validate(
        {
            "CSV_URL": "http://localhost:9000/customers.csv",
            "JSON_URL": "http://localhost:9000/customers.json",
            "HTTP_TIMEOUT_SECONDS": "2.5",
            "MAX_PAGE_SIZE": "50",
            "LOG_LEVEL": "DEBUG",
            "HOME": "/home/app",  # the rest of the environment is ignored
        }
    )
    assert settings.csv_url == "http://localhost:9000/customers.csv"
    assert (settings.http_timeout_seconds, settings.max_page_size, settings.log_level) == (2.5, 50, "DEBUG")


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("CSV_URL", "not a url"),
        ("CSV_URL", ""),
        ("JSON_URL", "ftp://files.example.test/customers.json"),
        ("HTTP_TIMEOUT_SECONDS", "0"),
        ("HTTP_TIMEOUT_SECONDS", "fast"),
        ("MAX_PAGE_SIZE", "0"),
        ("MAX_PAGE_SIZE", "many"),
        ("LOG_LEVEL", "verbose"),
    ],
)
def test_an_unusable_value_is_refused_and_the_error_names_the_variable(variable, value):
    with pytest.raises(ValidationError, match=variable):
        Settings.model_validate({variable: value})


def test_a_refused_url_is_not_echoed_in_the_error():
    with pytest.raises(ValidationError) as failure:
        Settings.model_validate({"CSV_URL": "ftp://files.example.test/customers.csv?signature=SECRET-TOKEN"})
    assert "CSV_URL" in str(failure.value)
    assert "SECRET-TOKEN" not in str(failure.value)
