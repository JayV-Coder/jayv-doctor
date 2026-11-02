from fastapi import FastAPI

from aid_api import __version__
from aid_api.core import errors, telemetry
from aid_api.health import router as health
from aid_api.imports import router as imports
from aid_api.integrations import router as integrations
from aid_api.orgs import router as orgs


def create_app() -> FastAPI:
    app = FastAPI(
        title="Integration AI Doctor API",
        version=__version__,
        openapi_url="/api/v1/openapi.json",
    )
    errors.install(app)
    app.include_router(health.router)
    app.include_router(orgs.router)
    app.include_router(integrations.router)
    app.include_router(imports.router)
    telemetry.configure(app)
    return app


app = create_app()
