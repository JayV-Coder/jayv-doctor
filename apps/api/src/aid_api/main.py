from fastapi import FastAPI

from aid_api import __version__, me, members, orgs
from aid_api.errors import ApiError, problem_handler


def create_app() -> FastAPI:
    app = FastAPI(
        title="Integration AI Doctor API",
        version=__version__,
        openapi_url="/api/v1/openapi.json",
    )
    app.add_exception_handler(ApiError, problem_handler)
    app.include_router(me.router)
    app.include_router(orgs.router)
    app.include_router(members.router)
    return app


app = create_app()
