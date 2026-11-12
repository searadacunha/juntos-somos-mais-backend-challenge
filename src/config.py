"""Runtime configuration, read once from environment variables."""

import os
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

HTTP_URL = r"^https?://\S+$"


class Settings(BaseModel):
    """Every setting has a default, so the service runs with no configuration at all.

    A value that cannot be used (a negative timeout, an unknown log level) fails
    here, at import time, with a message that names the environment variable.
    """

    # A refused value is not echoed in the error: a source URL may carry a secret.
    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    csv_url: str = Field(
        "https://storage.googleapis.com/juntossomosmais-code-challenge/input-backend.csv",
        validation_alias="CSV_URL",
        pattern=HTTP_URL,
    )
    json_url: str = Field(
        "https://storage.googleapis.com/juntossomosmais-code-challenge/input-backend.json",
        validation_alias="JSON_URL",
        pattern=HTTP_URL,
    )
    # httpx applies this to each phase (connect, read, write, pool), not to the whole download.
    http_timeout_seconds: float = Field(10.0, validation_alias="HTTP_TIMEOUT_SECONDS", gt=0)
    max_page_size: int = Field(100, validation_alias="MAX_PAGE_SIZE", ge=1)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        "INFO", validation_alias="LOG_LEVEL"
    )


settings = Settings.model_validate(dict(os.environ))
