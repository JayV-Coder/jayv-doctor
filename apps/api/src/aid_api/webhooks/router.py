"""Webhooks de saída (ticket #42): só Owner e Admin com MFA cadastram, veem as entregas e
reenviam. O segredo de assinatura aparece só na criação e na rotação."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, status

from aid_api.core.auth import Claims, require_manager
from aid_api.core.idempotency import Idempotent, IdempotentRoute
from aid_api.core.permissions import MANAGE_CONNECTORS
from aid_api.core.rate_limit import rate_limit
from aid_api.webhooks.repo import WebhookRepository, get_webhook_repository
from aid_api.webhooks.schemas import Delivery, Webhook, WebhookChange, WebhookIn, WebhookSecret

router = APIRouter(
    prefix="/api/v1",
    tags=["webhooks"],
    route_class=IdempotentRoute,
    dependencies=[Depends(rate_limit)],
)
Manager = Annotated[Claims, Depends(require_manager(*MANAGE_CONNECTORS))]
Repository = Annotated[WebhookRepository, Depends(get_webhook_repository)]


@router.get("/webhooks", response_model=list[Webhook])
async def list_webhooks(claims: Manager, repository: Repository) -> list[Webhook]:
    return await repository.all(claims)


@router.post("/webhooks", response_model=WebhookSecret, status_code=status.HTTP_201_CREATED)
async def create_webhook(
    new: WebhookIn, claims: Manager, repository: Repository, _: Idempotent
) -> WebhookSecret:
    return await repository.create(claims, new)


@router.patch("/webhooks/{target}", response_model=Webhook)
async def update_webhook(
    target: UUID, change: WebhookChange, claims: Manager, repository: Repository, _: Idempotent
) -> Webhook:
    return await repository.update(claims, str(target), change)


@router.post("/webhooks/{target}/rotate-secret", response_model=WebhookSecret)
async def rotate_secret(
    target: UUID, claims: Manager, repository: Repository, _: Idempotent
) -> WebhookSecret:
    return await repository.rotate(claims, str(target))


@router.delete("/webhooks/{target}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(
    target: UUID, claims: Manager, repository: Repository, _: Idempotent
) -> None:
    await repository.delete(claims, str(target))


@router.get("/webhooks/{target}/deliveries", response_model=list[Delivery])
async def list_deliveries(target: UUID, claims: Manager, repository: Repository) -> list[Delivery]:
    return await repository.deliveries(claims, str(target))


@router.post(
    "/webhook-deliveries/{target}/resend",
    response_model=dict[str, Any],
    status_code=status.HTTP_202_ACCEPTED,
)
async def resend(
    target: UUID, claims: Manager, repository: Repository, _: Idempotent
) -> dict[str, Any]:
    return await repository.resend(claims, str(target))
