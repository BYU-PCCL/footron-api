# TODO: Write some actual tests

import asyncio
import json

import websockets


async def test():
    uri = "ws://localhost:8000/messaging/out/test"
    async with websockets.connect(uri) as websocket:
        await websocket.send(json.dumps({"type": "cap", "client": "abcdefg", "body": {"a": "b"}}))
        print(await websocket.recv())


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(test())
