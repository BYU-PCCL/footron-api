# TODO: Write some actual tests

import asyncio
import datetime
import json
import sys

import websockets

queue = asyncio.Queue()

APP_NAME = "test"
# Because client should immediately exit if denied access, False means "pending."
accepted = False
start_time: datetime.datetime

CONNECT_TIMEOUT = 10


async def handle_message(message):
    global accepted
    if message["type"] == "acc":
        if not message["accepted"]:
            reason = (
                message["reason"]
                if "reason" in message and message["reason"]
                else "no reason provided"
            )
            print(f"Disconnected: {reason}")
            return False

        accepted = True
        print(f"Connection to '{APP_NAME}' accepted")
        return True

    # TODO: Think very carefully about how this should work
    if message["type"] == "ahb":
        if message["up"] is False:
            if (datetime.datetime.now() - start_time).seconds < CONNECT_TIMEOUT:
                print("App sent back negative heartbeat, will keep waiting")
                return True

            if accepted:
                print("App disconnected")
            else:
                print(
                    f"Couldn't connect to app within {CONNECT_TIMEOUT}s timeout",
                    file=sys.stderr,
                )

            return False

        if message["up"] is True:
            if accepted:
                return True

            await queue.put({"type": "con"})
            return True

        print(
            f"message['up'] was invalid type '{type(message['up'])}'", file=sys.stderr
        )
        # 'up' was of an invalid type
        return False

    if message["type"] == "app":
        print(f"New application x: {message['body']['x']}")
        await queue.put({"type": "cap", "body": {"x": message["body"]["x"] * 2}})
        return True

    print(f"Message was unhandled type {message['type']}", file=sys.stderr)
    return False


async def consumer_handler(websocket):
    async for message in websocket:
        if not await handle_message(json.loads(message)):
            return


async def producer_handler(websocket):
    while True:
        message = await queue.get()
        await websocket.send(json.dumps(message))


async def handler():
    uri = f"ws://localhost:8000/messaging/in/{APP_NAME}"
    async with websockets.connect(uri) as websocket:
        consumer_task = asyncio.ensure_future(consumer_handler(websocket))
        producer_task = asyncio.ensure_future(producer_handler(websocket))
        done, pending = await asyncio.wait(
            [consumer_task, producer_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()


if __name__ == "__main__":
    start_time = datetime.datetime.now()
    asyncio.get_event_loop().run_until_complete(handler())
