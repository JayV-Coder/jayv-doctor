from fastapi import FastAPI

from aid_api import __version__
from aid_api.agents import router as agents
from aid_api.alerts import router as alerts
from aid_api.audit import router as audit
from aid_api.connectors import router as connectors
from aid_api.core import errors, request_meta, telemetry
from aid_api.dashboard import router as dashboard
from aid_api.diagnoses import router as diagnoses
from aid_api.executions import router as executions
from aid_api.health import router as health
from aid_api.imports import router as imports
from aid_api.incidents import router as incidents
from aid_api.ingestion import agent_router
from aid_api.ingestion import router as ingestion
from aid_api.integrations import router as integrations
from aid_api.itsm import router as itsm
from aid_api.knowledge import router as knowledge
from aid_api.orgs import router as orgs
from aid_api.privacy import router as privacy
from aid_api.reports import router as reports
from aid_api.usage import router as usage
from aid_api.webhooks import router as webhooks


def create_app() -> FastAPI:
    app = FastAPI(
        title="Integration AI Doctor API",
        version=__version__,
        openapi_url="/api/v1/openapi.json",
    )
    errors.install(app)
    request_meta.install(app)
    app.include_router(health.router)
    app.include_router(orgs.router)
    app.include_router(integrations.router)
    app.include_router(imports.router)
    app.include_router(ingestion.tokens)
    app.include_router(ingestion.events)
    app.include_router(agent_router.agent)
    app.include_router(agents.router)
    app.include_router(alerts.router)
    app.include_router(webhooks.router)
    app.include_router(itsm.router)
    app.include_router(itsm.hooks)
    app.include_router(connectors.router)
    app.include_router(executions.router)
    app.include_router(incidents.router)
    app.include_router(dashboard.router)
    app.include_router(knowledge.router)
    app.include_router(diagnoses.router)
    app.include_router(audit.router)
    app.include_router(privacy.router)
    app.include_router(usage.router)
    app.include_router(reports.router)
    app.include_router(reports.shared)
    telemetry.configure(app)
    return app


app = create_app()
