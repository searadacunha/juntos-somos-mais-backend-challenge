import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.config import Settings

ROOT = Path(__file__).resolve().parents[1]


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


def test_the_environment_reaches_the_running_code():
    """In a fresh process: the settings read os.environ, and the page limit and log level are used."""
    script = textwrap.dedent(
        """
        import logging

        from pydantic import ValidationError

        import src.main
        from src.config import settings
        from src.models import UserQuery

        print(settings.json_url, settings.http_timeout_seconds, logging.getLogger().level)
        UserQuery.model_validate({"pageSize": 5})
        try:
            UserQuery.model_validate({"pageSize": 6})
        except ValidationError:
            print("pageSize=6 refused")
        """
    )
    environment = {
        **os.environ,
        "JSON_URL": "http://localhost:9000/customers.json",
        "HTTP_TIMEOUT_SECONDS": "2.5",
        "MAX_PAGE_SIZE": "5",
        "LOG_LEVEL": "DEBUG",
    }
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=ROOT, env=environment, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["http://localhost:9000/customers.json 2.5 10", "pageSize=6 refused"]


def test_a_refused_url_is_not_echoed_in_the_error():
    with pytest.raises(ValidationError) as failure:
        Settings.model_validate({"CSV_URL": "ftp://files.example.test/customers.csv?signature=SECRET-TOKEN"})
    assert "CSV_URL" in str(failure.value)
    assert "SECRET-TOKEN" not in str(failure.value)
