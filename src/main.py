"""HTTP layer: the application factory, the startup load and the routes."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, FastAPI, Query, Request

from src.config import settings
from src.loaders import SourceError
from src.models import Health, UserQuery, UsersPage
from src.service import UserStore, load_users

logger = logging.getLogger(__name__)
router = APIRouter()


def get_store(request: Request) -> UserStore:
    return request.app.state.store


StoreDep = Annotated[UserStore, Depends(get_store)]


# One handler, two paths: the challenge README documents /users, and the official
# validate.sh calls /api/v1/users. Both must answer with the same contract.
@router.get("/users", tags=["users"], summary="List customers")
@router.get("/api/v1/users", tags=["users"], summary="List customers (path used by validate.sh)")
async def list_users(query: Annotated[UserQuery, Query()], store: StoreDep) -> UsersPage:
    """Customers in load order, optionally filtered by region and classification.

    `totalCount` is the number of customers matching the filters. A page past the
    end returns an empty `users` list. An invalid or unknown parameter returns 422.
    """
    return store.page(
        region=query.region,
        customer_type=query.type,
        page_number=query.page_number,
        page_size=query.page_size,
    )


@router.get("/health", tags=["ops"], summary="Liveness and load report")
async def health(store: StoreDep) -> Health:
    """Answers only once both sources are loaded: the server does not start otherwise."""
    return Health(status="ok", users=len(store.users), rejected_records=store.rejected)


def create_app(transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    """Build the application. `transport` lets the tests replace the network."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            app.state.store = await load_users(settings, transport)
        except SourceError as exc:
            # Raising here stops the server before it accepts a request, so a failed
            # or partial load can never be served as if it were the full data set.
            logger.critical("startup aborted: %s", exc)
            raise
        logger.info(
            "startup complete users=%d rejected=%d", len(app.state.store.users), app.state.store.rejected
        )
        yield

    app = FastAPI(
        title="Juntos Somos Mais customers API",
        description="Customers loaded from the two partner files, transformed and kept in memory.",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.include_router(router)
    return app


logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
# At INFO httpx logs every request with its full URL, query string included. The
# source URLs are configuration and may be signed, so they stay out of the logs.
logging.getLogger("httpx").setLevel(logging.WARNING)
app = create_app()
