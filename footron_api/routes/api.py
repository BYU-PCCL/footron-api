from typing import Union, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.security import APIKeyCookie, APIKeyHeader
from pydantic import BaseModel

from ..data import controller_api, auth_manager

# @vinhowe: we could just not set a username, but I figure it gives us an extra layer
# of security against dumb scripts that try default credentials for a lot of
# services. Because the code is sufficiently random and we might be behind a firewall
# anyway, this is a super hypothetical concern. We should feel comfortable removing
# the username check if it becomes inconvenient for us.
_USERNAME = "cstv"

router = APIRouter(
    prefix="/api",
    tags=["api"],
)

_API_KEY_NAME = "X-AUTH-CODE"

_api_key_header = APIKeyHeader(name=_API_KEY_NAME, auto_error=False)
_api_key_cookie = APIKeyCookie(name=_API_KEY_NAME, auto_error=False)


# TODO: Consider moving these models somewhere (possibly to use Pydantic for models
#  more broadly)
class CurrentExperienceChange(BaseModel):
    id: str


class CurrentExperienceUpdate(BaseModel):
    end_time: Optional[int] = None
    lock: Optional[Union[bool, int]] = None
    # TODO: Add a validator that at least one of these values is not none:
    #  https://github.com/samuelcolvin/pydantic/issues/506#issuecomment-522255484
    #  might be helpful


async def validate_auth_code(
    header_key: str = Depends(_api_key_header),
    cookie_key: str = Depends(_api_key_cookie),
):
    """
    Based on the example at
    https://fastapi.tiangolo.com/advanced/security/http-basic-auth/#check-the-username

    :param cookie_key:
    :param header_key:
    :raises HTTPException: if credentials are incorrect:
    """

    # Precedence: header > cookie

    if header_key is not None:
        client_code = header_key
    elif cookie_key is not None:
        client_code = cookie_key
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not authenticated"
        )

    matches_code = auth_manager.check(client_code)
    matches_next_code = auth_manager.check_next(client_code)
    if not (matches_code or matches_next_code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid auth code",
        )

    if matches_next_code:
        await auth_manager.advance()

    # TODO: Decide whether it actually makes sense to return this in any case
    return auth_manager.code


@router.get("/", response_class=HTMLResponse)
async def _root():
    return """<p>Welcome to the Footron API!</p>"""


@router.get("/experiences", dependencies=[Depends(validate_auth_code)])
async def experiences():
    return await controller_api.experiences()


@router.get("/collections", dependencies=[Depends(validate_auth_code)])
async def collections():
    return await controller_api.collections()


@router.get("/current", dependencies=[Depends(validate_auth_code)])
async def current_experience():
    return await controller_api.current_experience(use_cache=False)


@router.put("/current", dependencies=[Depends(validate_auth_code)])
async def set_current_experience(change: CurrentExperienceChange):
    if auth_manager.lock is True:
        raise HTTPException(
            status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
            detail="Setting current experience is forbidden during closed lock",
        )

    experience = await controller_api.current_experience()
    # This handles the specific case that an "open" lock of n is held
    if experience and change.id != experience["id"]:
        # TODO: I know this is hacky, but it's the most straightforward way to remove
        #  locks that will handle non-messaging apps right now. Feel free to come up
        #  with something better.
        auth_manager.lock = False

    return await controller_api.set_current_experience(id=change.id)


@router.patch("/current", dependencies=[Depends(validate_auth_code)])
async def update_current_experience(update: CurrentExperienceUpdate):
    return await controller_api.set_current_experience(**update.dict())
