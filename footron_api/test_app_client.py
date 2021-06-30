# TODO: Write some actual tests

import asyncio
import json
import random
import time

import websockets

clients = set()
queue = asyncio.Queue()

APP_NAME = "test"


async def state_push():
    # This is basically what the app messaging library's default API does
    while True:
        loop_start = time.time()
        message = {"type": "app", "body": {"x": random.random()}}
        for client in clients:
            await queue.put({**message, "client": client})
        await asyncio.sleep(0.1 - (time.time() - loop_start))


async def handle_message(message):
    if message["type"] == "con":
        print(f"Connection request from client '{message['client']}'")
        clients.add(message["client"])
        return await queue.put(
            {"type": "acc", "accepted": True, "client": message["client"]}
        )

    if message["type"] == "chb":
        if message["up"] is False:
            print(f"Client(s) disconnected: '{message['clients']}'")
            for client in message["clients"]:
                if client not in clients:
                    continue

                clients.remove(client)
            return

        print(f"Client(s) connections up: {message['clients']}")

    if message["type"] == "cap":
        if "body" not in message or "x" not in message["body"]:
            print("Got invalid client message")
            return

        print(f"New x from client: {message['body']['x']}")


async def consumer_handler(websocket):
    async for message in websocket:
        await handle_message(json.loads(message))


async def producer_handler(websocket):
    while True:
        message = await queue.get()
        await websocket.send(json.dumps(message))


async def handler():
    uri = f"ws://localhost:8000/messaging/out/{APP_NAME}"
    async with websockets.connect(uri) as websocket:
        state_push_task = asyncio.ensure_future(state_push())
        # noinspection PyTypeChecker
        consumer_task = asyncio.ensure_future(consumer_handler(websocket))
        producer_task = asyncio.ensure_future(producer_handler(websocket))
        done, pending = await asyncio.wait(
            [consumer_task, producer_task, state_push_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(handler())
