from typing import Union, Optional

from fastapi import APIRouter
from pydantic import BaseModel, validator

from ..data import controller_api

router = APIRouter(
    prefix="/api",
    tags=["api"],
)


# TODO: Add authentication middleware + authentication state in data module

# TODO: Consider moving these models somewhere (possibly to use Pydantic for models more broadly)
class CurrentExperienceChange(BaseModel):
    id: str


class CurrentExperienceUpdate(BaseModel):
    end_time: Optional[int] = None
    lock: Optional[Union[bool, int]] = None
    # TODO: Add a validator that at least one of these values is not none:
    #  https://github.com/samuelcolvin/pydantic/issues/506#issuecomment-522255484 might be helpful


@router.get("/experiences")
async def experiences():
    return await controller_api.experiences()


@router.get("/collections")
async def collections():
    return await controller_api.collections()


@router.get("/current")
async def current_experience():
    return await controller_api.current_experience(use_cache=False)


@router.put("/current")
async def set_current_experience(change: CurrentExperienceChange):
    return await controller_api.set_current_experience(id=change.id)


@router.patch("/current")
async def update_current_experience(update: CurrentExperienceUpdate):
    return await controller_api.set_current_experience(**update.dict())
