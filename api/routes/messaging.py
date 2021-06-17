# See https://www.python.org/dev/peps/pep-0563/
from __future__ import annotations

import asyncio
import dataclasses
import logging
import uuid
from typing import Dict, Union, TypedDict

from fastapi import APIRouter, WebSocket
from fastapi.concurrency import run_until_first_complete

from .. import protocol
from ..constants import JsonDict
from ..data import controller_api

router = APIRouter(
    prefix="/messaging",
    tags=["messaging"],
)

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


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
    queue: asyncio.Queue[Union[protocol.BaseMessage, _AppBoundMessageInfo]] = asyncio.Queue()

    async def send_message_from_client(self, client_id: str, message: protocol.BaseMessage):
        return self.queue.put(_AppBoundMessageInfo(client_id, message))

    async def send_heartbeat(self, client_id: str, up: bool):
        return self.socket.send_json(
            protocol.ClientHeartbeatMessage.create(up=up, client=client_id)
        )

    async def receive_handler(self):
        async for message in self.socket.iter_json():
            await self._handle_receive_message(protocol.deserialize(message))

    async def send_handler(self):
        """Handle messages in queue: app -> client"""
        while True:
            item = await self.queue.get()

            message = None
            if isinstance(item, _AppBoundMessageInfo):
                message = protocol.serialize(item.message)
                # App needs to know source of client messages
                message["client"] = item.client
            if isinstance(item, protocol.BaseMessage):
                message = protocol.serialize(item)

            if message is None:
                raise TypeError("Message wasn't _AppBoundMessageInfo or BaseMessage")

            await self.socket.send_json(message)

    async def _handle_receive_message(self, message: protocol.BaseMessage):
        if hasattr(message, "client"):
            if not self.manager.app_has_client(self.id, message.client):
                await self.send_heartbeat(message.client, False)
                return

            return self._send_to_client(message)

        if isinstance(message, protocol.DisplaySettingsMessage):
            return controller_api.update_display_settings(message.settings)

        raise protocol.UnhandledMessageType(f"Unhandled message type '{message.type}' from app '{self.id}'")

    async def _send_to_client(
        self, message: Union[protocol.BaseMessage, protocol.ClientBoundMixin]
    ):
        # TODO: The type hint for 'message' feels incorrect as it appears to represent either an instance of a
        #  BaseMessage or a ClientBoundMixin, but not a combination of both
        if not hasattr(message, "client"):
            raise ValueError(
                f"App {self.id} attempted to send message to client without specifying client ID"
            )

        return self.manager.clients[self.id][message.client].send_message(message)


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

    async def send_message(self, message: protocol.BaseMessage):
        return self.queue.put(message)

    async def send_heartbeat(self, up: bool):
        return self.socket.send_json(protocol.HeartbeatMessage.create(up=up))

    async def receive_handler(self):
        """Handle messages from socket: client -> app"""
        async for message in self.socket.iter_json():
            self._handle_receive_message(message)

    async def send_handler(self):
        """Handle messages in queue: app -> client"""
        while True:
            self._handle_send_message(await self.queue.get())

    def _handle_receive_message(self, data: JsonDict):
        if not self.manager.app_connected(self.app_id):
            await self.send_heartbeat(False)
            return

        message = protocol.deserialize(data)

        try:
            self._check_message_auth(message)
        except protocol.AccessError as error:
            logging.error(error)
            return

        await self.manager.apps[self.app_id].send_message_from_client(self.id, message)

    def _handle_send_message(self, message: protocol.BaseMessage):
        self._pre_send(message)
        serialized_message = protocol.serialize(message)
        # Client doesn't need to know its ID because it doesn't have to self-identify
        del serialized_message["client"]
        await self.socket.send_json(serialized_message)
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
        await connection.socket.accept()
        self.apps[connection.id] = connection

    async def remove_app(self, connection: _AppConnection):
        await connection.socket.accept()
        self.apps[connection.id] = connection

    async def add_client(self, connection: _ClientConnection):
        await connection.socket.accept()

        if connection.app_id not in self.clients:
            self.clients[connection.app_id] = {}

        self.clients[connection.app_id][connection.id] = connection

    async def remove_client(self, connection: _ClientConnection):
        await connection.socket.close()
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


_manager = _ConnectionManager()


@router.websocket("/in/<app_id>")
async def messaging_in(websocket: WebSocket, app_id: str):
    connection = _ClientConnection(websocket, app_id, str(uuid.uuid4()), _manager)

    await _manager.add_client(connection)
    await run_until_first_complete(
        (connection.receive_handler, {}),
        (connection.send_handler, {}),
    )
    await _manager.remove_client(connection)


@router.websocket("/out/<app_id>")
async def messaging_in(websocket: WebSocket, app_id: str):
    connection = _AppConnection(websocket, app_id, _manager)

    await _manager.add_app(connection)
    await run_until_first_complete(
        (connection.receive_handler, {}),
        (connection.send_handler, {}),
    )
    await _manager.remove_app(connection)
