import asyncio

from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse

import api_routes

app = FastAPI()

app.include_router(api_routes.router)


# TODO: Remove this
i = 0


async def print_a_ton_of_stuff():
    global i
    while True:
        print(i)
        i += 1
        await asyncio.sleep(5)


@app.on_event("startup")
async def startup():
    loop = asyncio.get_event_loop()
    # This is a prototype for the heartbeating polling we'll have to do
    # loop.create_task(print_a_ton_of_stuff())


@app.get("/", response_class=HTMLResponse)
async def root():
    return """<p>Welcome to the CSTV API!</p>"""


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        data = await websocket.receive_text()
        await websocket.send_text(f"Message text was: {data}")
