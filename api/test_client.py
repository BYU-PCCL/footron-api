# TODO: Write some actual tests

import asyncio
import json

import websockets


async def test():
    uri = "ws://localhost:8000/messaging/in/test"
    async with websockets.connect(uri) as websocket:
        await websocket.send(json.dumps({"type": 0}))
        print(await websocket.recv())


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(test())
