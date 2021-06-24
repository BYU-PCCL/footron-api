import secrets
from typing import Union, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

from ..data import controller_api, auth_manager

# @vinhowe: we could just not set a username, but I figure it gives us an extra layer of security against dumb
# scripts that try default credentials for a lot of services. Because the code is sufficiently random and we might be
# behind a firewall anyway, this is a super hypothetical concern. We should feel comfortable removing the username
# check if it becomes inconvenient for us.
_USERNAME = "cstv"

router = APIRouter(
    prefix="/api",
    tags=["api"],
)

_security = HTTPBasic()


# TODO: Consider moving these models somewhere (possibly to use Pydantic for models more broadly)
class CurrentExperienceChange(BaseModel):
    id: str


class CurrentExperienceUpdate(BaseModel):
    end_time: Optional[int] = None
    lock: Optional[Union[bool, int]] = None
    # TODO: Add a validator that at least one of these values is not none:
    #  https://github.com/samuelcolvin/pydantic/issues/506#issuecomment-522255484 might be helpful


async def validate_auth_code(credentials: HTTPBasicCredentials = Depends(_security)):
    """
    Based on the example at https://fastapi.tiangolo.com/advanced/security/http-basic-auth/#check-the-username

    :param credentials:
    :raises HTTPException: if credentials are incorrect:
    """

    # See https://fastapi.tiangolo.com/advanced/security/http-basic-auth/#timing-attacks for some background on the
    # use of secrets.compare_digest() here
    correct_username = secrets.compare_digest(credentials.username, _USERNAME)
    matches_code = secrets.compare_digest(credentials.password, auth_manager.code)
    matches_next_code = secrets.compare_digest(credentials.password, auth_manager.next_code)
    if not (correct_username and (matches_code or matches_next_code)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or code",
            headers={"WWW-Authenticate": "Basic"},
        )

    if matches_next_code:
        await auth_manager.advance()

    # TODO: Decide whether it actually makes sense to return this in any case
    return auth_manager.code


@router.get("/experiences")
async def experiences(_: str = Depends(validate_auth_code)):
    return await controller_api.experiences()


@router.get("/collections")
async def collections(_: str = Depends(validate_auth_code)):
    return await controller_api.collections()


@router.get("/current")
async def current_experience(_: str = Depends(validate_auth_code)):
    return await controller_api.current_experience(use_cache=False)


@router.put("/current")
async def set_current_experience(
    change: CurrentExperienceChange, _: str = Depends(validate_auth_code)
):
    return await controller_api.set_current_experience(id=change.id)


@router.patch("/current")
async def update_current_experience(
    update: CurrentExperienceUpdate, _: str = Depends(validate_auth_code)
):
    return await controller_api.set_current_experience(**update.dict())
