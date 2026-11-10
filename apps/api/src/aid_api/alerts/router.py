"""Alertas (ticket #41, Tela 20). Todo Papel vê Regras e canais; Owner e Admin com MFA criam,
alteram e removem; cada Usuário cuida do push dos próprios aparelhos e do próprio silêncio."""

import os
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from aid_api.alerts.repo import AlertRepository, get_alert_repository
from aid_api.alerts.schemas import (
    AlertRule,
    AlertRuleChange,
    AlertRuleIn,
    Channel,
    ChannelIn,
    Preferences,
    PushKey,
    PushSubscription,
    PushSubscriptionIn,
)
from aid_api.core.auth import Claims, require_manager, require_role
from aid_api.core.idempotency import Idempotent, IdempotentRoute
from aid_api.core.permissions import MANAGE_CONNECTORS, VIEW
from aid_api.core.rate_limit import rate_limit

router = APIRouter(
    prefix="/api/v1",
    tags=["alerts"],
    route_class=IdempotentRoute,
    dependencies=[Depends(rate_limit)],
)
Viewer = Annotated[Claims, Depends(require_role(*VIEW))]
Manager = Annotated[Claims, Depends(require_manager(*MANAGE_CONNECTORS))]
Repository = Annotated[AlertRepository, Depends(get_alert_repository)]


@router.get("/alert-rules", response_model=list[AlertRule])
async def list_rules(claims: Viewer, repository: Repository) -> list[AlertRule]:
    return await repository.rules(claims)


@router.post("/alert-rules", response_model=AlertRule, status_code=status.HTTP_201_CREATED)
async def create_rule(
    new: AlertRuleIn, claims: Manager, repository: Repository, _: Idempotent
) -> AlertRule:
    return await repository.create_rule(claims, new)


@router.patch("/alert-rules/{target}", response_model=AlertRule)
async def update_rule(
    target: UUID, change: AlertRuleChange, claims: Manager, repository: Repository, _: Idempotent
) -> AlertRule:
    return await repository.update_rule(claims, str(target), change)


@router.delete("/alert-rules/{target}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(target: UUID, claims: Manager, repository: Repository, _: Idempotent) -> None:
    await repository.delete_rule(claims, str(target))


@router.get("/notification-channels", response_model=list[Channel])
async def list_channels(claims: Viewer, repository: Repository) -> list[Channel]:
    return await repository.channels(claims)


@router.post("/notification-channels", response_model=Channel, status_code=status.HTTP_201_CREATED)
async def create_channel(
    new: ChannelIn, claims: Manager, repository: Repository, _: Idempotent
) -> Channel:
    return await repository.create_channel(claims, new)


@router.delete("/notification-channels/{target}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(
    target: UUID, claims: Manager, repository: Repository, _: Idempotent
) -> None:
    await repository.delete_channel(claims, str(target))


@router.get("/push/key", response_model=PushKey)
async def push_key(claims: Viewer) -> PushKey:
    """Chave pública VAPID para o navegador assinar o push (`AID_VAPID_PUBLIC_KEY`)."""
    return PushKey(public_key=os.environ.get("AID_VAPID_PUBLIC_KEY") or None)


@router.get("/push-subscriptions", response_model=list[PushSubscription])
async def list_subscriptions(claims: Viewer, repository: Repository) -> list[PushSubscription]:
    return await repository.subscriptions(claims)


@router.post(
    "/push-subscriptions", response_model=PushSubscription, status_code=status.HTTP_201_CREATED
)
async def subscribe(
    new: PushSubscriptionIn, claims: Viewer, repository: Repository, _: Idempotent
) -> PushSubscription:
    return await repository.subscribe(claims, new)


@router.delete("/push-subscriptions/{target}", status_code=status.HTTP_204_NO_CONTENT)
async def unsubscribe(target: UUID, claims: Viewer, repository: Repository, _: Idempotent) -> None:
    await repository.unsubscribe(claims, str(target))


@router.get("/alert-preferences", response_model=Preferences)
async def preferences(claims: Viewer, repository: Repository) -> Preferences:
    return await repository.preferences(claims)


@router.put("/alert-preferences", response_model=Preferences)
async def save_preferences(
    change: Preferences, claims: Viewer, repository: Repository, _: Idempotent
) -> Preferences:
    return await repository.save_preferences(claims, change)
