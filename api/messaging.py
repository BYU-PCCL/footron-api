import dataclasses
from typing import List, Optional, Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_until_first_complete

router = APIRouter(
    prefix="/messaging",
    tags=["messaging"],
)


@dataclasses.dataclass
class ClientConnection:
    socket: WebSocket
    id: Optional[str] = None
    # TODO: See if we end up needing the app ID to be stored here


class ConnectionManager:
    def __init__(self):
        # TODO: Consider using something other than "server"--this isn't a pure server client model
        self.servers: Dict[str, WebSocket] = {}
        self.clients: Dict[str, List[ClientConnection]] = {}

    def add_server(self, connection: WebSocket, app_id: str):
        await connection.accept()
        self.servers

    async def add_client(self, connection: ClientConnection, app_id: str):
        await connection.websocket.accept()
        self.clients[].append(connection)

    def remove_client(self, websocket: WebSocket, app_id: str):
        if app_id not in self.clients:
            self.clients.remove(websocket)

    # async def broadcast(self, message: str):
    #     for connection in self.clients:
    #         await connection.send_text(message)


manager = ConnectionManager()


@router.websocket("/in/<app_id>")
async def messaging_in(websocket: WebSocket, app_id: str):
    # Connection hasn't been accepted yet so it doesn't have an ID
    connection = ClientConnection(websocket)

    await manager.add_client(connection, app_id)
    try:
        while True:
            data = await websocket.receive_json()
    except WebSocketDisconnect:
        manager.remove_client(websocket)

