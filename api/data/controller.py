import aiohttp

from ..constants import JsonDict

CONTROLLER_URL = "http://localhost:5000"

_ENDPOINT_EXPERIENCES = "/experiences"
_ENDPOINT_COLLECTIONS = "/collections"
_ENDPOINT_CURRENT_EXPERIENCE = "/current"


class ControllerApi:
    def __init__(self, aiohttp_session=aiohttp.ClientSession()):
        self._aiohttp_session = aiohttp_session
        self._experiences = None
        self._collections = None
        self._current_experience = None
        self._last_update = None

    @staticmethod
    def _url_with_endpoint(endpoint) -> str:
        return f"{CONTROLLER_URL}{endpoint}"

    def _invalidate_cache(self):
        self._experiences = None
        self._collections = None
        self._current_experience = None

    async def _get_json_response(self, endpoint) -> JsonDict:
        async with self._aiohttp_session.get(
            self._url_with_endpoint(endpoint)
        ) as response:
            return await response.json()

    async def experiences(self, use_cache=True) -> JsonDict:
        if self._experiences is None or not use_cache:
            self._experiences = await self._get_json_response(_ENDPOINT_EXPERIENCES)

        return self._experiences

    async def collections(self, use_cache=True) -> JsonDict:
        if self._collections is None or not use_cache:
            self._collections = await self._get_json_response(_ENDPOINT_COLLECTIONS)

        return self._collections

    async def current_experience(self, use_cache=True) -> JsonDict:
        if self._current_experience is None or not use_cache:
            self._current_experience = await self._get_json_response(
                _ENDPOINT_CURRENT_EXPERIENCE
            )

            if self._current_experience["last_update"] != self._last_update:
                self._last_update = self._current_experience["last_update"]
                self._invalidate_cache()

        return self._current_experience

    async def set_current_experience(self, id: str) -> bool:
        async with self._aiohttp_session.put(
            self._url_with_endpoint(_ENDPOINT_CURRENT_EXPERIENCE), json={"id": id}
        ) as response:
            return await response.json()

    async def patch_current_experience(self, updates: JsonDict) -> bool:
        async with self._aiohttp_session.patch(
            self._url_with_endpoint(_ENDPOINT_CURRENT_EXPERIENCE), json=updates
        ) as response:
            return await response.json()
