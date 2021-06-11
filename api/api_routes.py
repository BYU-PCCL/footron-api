from typing import Optional

import aiohttp
from fastapi import APIRouter

CONTROLLER_URL = "http://localhost:5000"

aiohttp_session: Optional[aiohttp.ClientSession] = None

router = APIRouter(
    prefix="/api",
    tags=["api"],
)


@router.on_event("startup")
async def startup():
    global aiohttp_session
    aiohttp_session = aiohttp.ClientSession()


@router.get("/experiences")
async def experiences():
    # TODO: Cache this instead of just forwarding a request every time
    async with aiohttp_session.get(f"{CONTROLLER_URL}/apps") as response:
        return await response.json()


@router.get("/collections")
async def collections():
    # TODO: Cache this instead of just forwarding a request every time
    async with aiohttp_session.get(f"{CONTROLLER_URL}/collections") as response:
        return await response.json()


@router.get("/current-experience")
async def current_experience():
    # TODO: Cache this instead of just forwarding a request every time
    async with aiohttp_session.get(f"{CONTROLLER_URL}/current-app") as response:
        return await response.json()


