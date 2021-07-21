# See https://www.python.org/dev/peps/pep-0563/
from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket
from footron_router import MessagingRouter

from ..data import auth_manager

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


@router.on_event("startup")
async def on_startup():
    asyncio.get_event_loop().create_task(_messaging_router.run_heartbeating())


# Until https://github.com/tiangolo/fastapi/pull/2640 is merged in, the prefix
# specified in our APIRouter won't apply to websocket routes, so we have to manually
# set them
@router.websocket("/messaging/in/{auth_code}")
async def messaging_in(websocket: WebSocket, auth_code: str):
    await _messaging_router.client_connection(websocket, auth_code)


@router.websocket("/messaging/out/{app_id}")
async def messaging_out(websocket: WebSocket, app_id: str):
    await _messaging_router.app_connection(websocket, app_id)
