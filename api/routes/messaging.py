# See https://www.python.org/dev/peps/pep-0563/
from __future__ import annotations

import asyncio
import dataclasses
import logging
import uuid
from typing import Dict, Union, List

from fastapi import APIRouter, WebSocket
from fastapi.concurrency import run_until_first_complete
from starlette.websockets import WebSocketState

from .. import protocol
from ..constants import JsonDict
from ..data import controller_api
from ..util import asyncio_interval

router = APIRouter(
    prefix="/messaging",
    tags=["messaging"],
)

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


# TODO: Move this somewhere
async def _checked_send(message: JsonDict, socket: WebSocket) -> bool:
    if socket.application_state == WebSocketState.DISCONNECTED:
        return False

    try:
        await socket.send_json(message)
    except RuntimeError as e:
        logger.error(f"Error during socket send: {e}")
        return False
    return True


@dataclasses.dataclass()
class _AppBoundMessageInfo:
    client: str
    message: protocol.BaseMessage


# TODO: Consider if AppConnection and ClientConnection are similar enough that they can share logic
@dataclasses.dataclass
class _AppConnection:
    socket: WebSocket
    id: str
    # TODO: I don't love how we're passing in an instance of the containing class here, is this clean?
    manager: _ConnectionManager
    queue: asyncio.Queue[
        Union[protocol.BaseMessage, _AppBoundMessageInfo]
    ] = asyncio.Queue()
    closed = False

    async def send_message_from_client(
        self, client_id: str, message: protocol.BaseMessage
    ):
        return await self.queue.put(_AppBoundMessageInfo(client_id, message))

    async def connect(self):
        return await self.socket.accept()

    async def close(self) -> bool:
        if self.closed:
            return False
        await self.socket.close()
        self.closed = True
        return True

    async def send_heartbeat(self, clients: Union[str, List[str]], up: bool):
        # Note that an "up" heartbeat containing a list of clients is expected to be comprehensive, and any clients
        # not listed should be removed. Likewise, a "down" heartbeat containing a list of clients should be interpreted
        # as a list of clients to remove.

        if isinstance(clients, str):
            clients = [clients]

        logger.info(f"Sending heartbeat to app: {self.id}")
        return await _checked_send(
            protocol.serialize(
                protocol.ClientHeartbeatMessage.create(up=up, clients=clients)
            ),
            self.socket,
        )

    async def receive_handler(self):
        async for message in self.socket.iter_json():
            await self._handle_receive_message(protocol.deserialize(message))

    async def send_handler(self):
        """Handle messages in queue: app -> client"""
        while True:
            await self._handle_send_message(await self.queue.get())

    async def _handle_receive_message(self, message: protocol.BaseMessage):
        if hasattr(message, "client"):
            if not self.manager.app_has_client(self.id, message.client):
                await self.send_heartbeat(message.client, False)
                return

            return await self._send_to_client(message)

        if isinstance(message, protocol.DisplaySettingsMessage):
            return await controller_api.update_display_settings(message.settings)

        raise protocol.UnhandledMessageType(
            f"Unhandled message type '{message.type}' from app '{self.id}'"
        )

    async def _handle_send_message(
        self, item: Union[protocol.BaseMessage, _AppBoundMessageInfo]
    ):
        message = None
        if isinstance(item, _AppBoundMessageInfo):
            message = protocol.serialize(item.message)
            # App needs to know source of client messages
            message["client"] = item.client
        if isinstance(item, protocol.BaseMessage):
            message = protocol.serialize(item)

        if message is None:
            raise TypeError("Message wasn't _AppBoundMessageInfo or BaseMessage")

        return await _checked_send(message, self.socket)

    async def _send_to_client(
        self, message: Union[protocol.BaseMessage, protocol.ClientBoundMixin]
    ):
        # TODO: The type hint for 'message' feels incorrect as it appears to represent either an instance of a
        #  BaseMessage or a ClientBoundMixin, but not a combination of both
        if not hasattr(message, "client"):
            raise ValueError(
                f"App '{self.id}' attempted to send message to client without specifying client ID"
            )

        return await self.manager.clients[self.id][message.client].send_message(message)


@dataclasses.dataclass
class _ClientConnection:
    socket: WebSocket
    app_id: str
    id: str
    # TODO: I don't love how we're passing in an instance of the containing class here, is this clean?
    manager: _ConnectionManager
    # Until this is true, all messages other than connection requests will be blocked
    accepted: bool = False
    queue: asyncio.Queue[protocol.BaseMessage] = asyncio.Queue()
    closed = False

    async def send_message(self, message: protocol.BaseMessage):
        return self.queue.put(message)

    async def send_heartbeat(self, up: bool) -> bool:
        await _checked_send(
            protocol.serialize(protocol.HeartbeatMessage.create(up=up)), self.socket
        )

    async def connect(self):
        return await self.socket.accept()

    async def close(self) -> bool:
        if self.closed:
            return False
        await self.socket.close()
        self.closed = True
        return True

    async def receive_handler(self):
        """Handle messages from socket: client -> app"""
        async for message in self.socket.iter_json():
            await self._handle_receive_message(message)

    async def send_handler(self):
        """Handle messages in queue: app -> client"""
        while True:
            await self._handle_send_message(await self.queue.get())

    async def _handle_receive_message(self, data: JsonDict):
        if not self.manager.app_connected(self.app_id):
            return await self.send_heartbeat(False)

        message = protocol.deserialize(data)

        try:
            self._check_message_auth(message)
        except protocol.AccessError as error:
            logging.error(error)
            return

        return await self.manager.apps[self.app_id].send_message_from_client(
            self.id, message
        )

    async def _handle_send_message(self, message: protocol.BaseMessage):
        self._pre_send(message)
        serialized_message = protocol.serialize(message)
        # Client doesn't need to know its ID because it doesn't have to self-identify
        del serialized_message["client"]
        await _checked_send(serialized_message, self.socket)
        if not self._post_send(message):
            # Cancel connection
            return

    def _check_message_auth(self, message: protocol.BaseMessage):
        if not self.accepted and not isinstance(message, protocol.ConnectMessage):
            # Return statement here will abort connection
            raise protocol.AccessError(
                f"Unauthorized client {self.id} attempted to send an authenticated message"
            )

    def _pre_send(self, message: protocol.BaseMessage):
        if isinstance(message, protocol.AccessMessage):
            self.accepted = message.accepted

    @staticmethod
    def _post_send(message: protocol.BaseMessage):
        if isinstance(message, protocol.AccessMessage) and not message.accepted:
            return False

        return True


class _ConnectionManager:
    def __init__(self):
        self.apps: Dict[str, _AppConnection] = {}
        # Important to note here that clients can be added for a specific app regardless of whether that app exists in
        #  self.apps. This is so that self.apps can represent only active connections to apps. Handling clients with no
        #  associated client is a different concern.
        self.clients: Dict[str, Dict[str, _ClientConnection]] = {}

    async def add_app(self, connection: _AppConnection):
        await connection.connect()
        self.apps[connection.id] = connection

    async def remove_app(self, connection: _AppConnection):
        await connection.close()
        self.apps[connection.id] = connection

    async def add_client(self, connection: _ClientConnection):
        await connection.connect()

        if connection.app_id not in self.clients:
            self.clients[connection.app_id] = {}

        self.clients[connection.app_id][connection.id] = connection

    async def remove_client(self, connection: _ClientConnection):
        await connection.close()
        if (
            connection.app_id not in self.clients
            or connection.id not in self.clients[connection.app_id]
        ):
            # TODO: Do we want to throw an error here instead?
            return

        del self.clients[connection.app_id][connection.id]

        if len(self.clients[connection.app_id]) == 0:
            del self.clients[connection.app_id]

    def app_connected(self, app_id: str) -> bool:
        return app_id in self.apps

    def app_has_client(self, app_id: str, client_id: str) -> bool:
        # See note on self.clients in __init__
        return app_id in self.clients and client_id in self.clients[app_id]

    async def send_heartbeats(self):
        """Send heartbeats to all connected clients and apps"""
        tasks = []
        for app in self.apps.values():
            client_ids = []
            if app.id in self.clients:
                client_ids = [c.id for c in self.clients[app.id].values()]

            tasks.append(app.send_heartbeat(client_ids, True))

        for app_id, clients in self.clients.items():
            app_up = self.app_connected(app_id)
            for client in clients.values():
                tasks.append(client.send_heartbeat(app_up))

        await asyncio.gather(*tasks)


_manager = _ConnectionManager()


@router.on_event("startup")
async def on_startup():
    asyncio.get_event_loop().create_task(
        asyncio_interval(_manager.send_heartbeats, 0.5)
    )


# Until https://github.com/tiangolo/fastapi/pull/2640 is merged in, the prefix specified in our APIRouter won't apply to
#  websocket routes, so we have to manually set them
@router.websocket("/messaging/in/{app_id}")
async def messaging_in(websocket: WebSocket, app_id: str):
    connection = _ClientConnection(websocket, app_id, str(uuid.uuid4()), _manager)

    await _manager.add_client(connection)
    await run_until_first_complete(
        (connection.receive_handler, {}),
        (connection.send_handler, {}),
    )
    await _manager.remove_client(connection)


@router.websocket("/messaging/out/{app_id}")
async def messaging_in(websocket: WebSocket, app_id: str):
    connection = _AppConnection(websocket, app_id, _manager)

    await _manager.add_app(connection)
    await run_until_first_complete(
        (connection.receive_handler, {}),
        (connection.send_handler, {}),
    )
    await _manager.remove_app(connection)
