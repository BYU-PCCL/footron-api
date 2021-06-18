from fastapi import APIRouter

from ..data import controller_api

router = APIRouter(
    prefix="/api",
    tags=["api"],
)


@router.get("/experiences")
async def experiences():
    return await controller_api.experiences()


@router.get("/collections")
async def collections():
    return await controller_api.collections()


@router.get("/current")
async def current_experience():
    return await controller_api.current_experience()
