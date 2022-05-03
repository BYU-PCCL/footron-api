# See https://www.python.org/dev/peps/pep-0563/
from __future__ import annotations

import asyncio
from datetime import datetime

import footron_protocol as protocol
from fastapi import APIRouter, WebSocket
from footron_router import MessagingRouter

from ..data import auth_manager, controller_api


router = APIRouter(
    prefix="/messaging",
    tags=["messaging"],
)

# TODO: Use FastAPI's dependency injection for auth_manager of declaring a global
#  variable to make this code easier to write tests for. See:
#  - https://fastapi.tiangolo.com/tutorial/dependencies/
#  - https://fastapi.tiangolo.com/tutorial/dependencies/classes-as-dependencies/
#  - https://fastapi.tiangolo.com/advanced/advanced-dependencies/
_messaging_router = MessagingRouter(auth_manager)


def on_display_settings(settings: protocol.DisplaySettings):
    if settings.lock is not None:
        auth_manager.lock = settings.lock

    if settings.end_time is not None:
        asyncio.get_event_loop().create_task(
            controller_api.patch_current_experience({"end_time": settings.end_time})
        )


def on_interaction(at: datetime):
    asyncio.get_event_loop().create_task(
        controller_api.patch_current_experience(
            {"last_interaction": int(at.timestamp() * 1000)}
        )
    )


@router.on_event("startup")
async def on_startup():
    _messaging_router.add_display_settings_listener(on_display_settings)
    _messaging_router.add_interaction_listener(on_interaction)
    asyncio.get_event_loop().create_task(_messaging_router.run_heartbeating())


# Until https://github.com/tiangolo/fastapi/pull/2640 is merged in, the prefix
# specified in our APIRouter won't apply to websocket routes, so we have to manually
# set them
@router.websocket("/in/{auth_code}")
async def messaging_in(websocket: WebSocket, auth_code: str):
    await _messaging_router.client_connection(websocket, auth_code)


@router.websocket("/out/{app_id}")
async def messaging_out(websocket: WebSocket, app_id: str):
    await _messaging_router.app_connection(websocket, app_id)
