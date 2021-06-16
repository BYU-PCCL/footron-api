import aiohttp

from ..constants import JsonDict
from .. import protocol

CONTROLLER_URL = "http://localhost:5000"


class ControllerApi:
    def __init__(self, aiohttp_session=aiohttp.ClientSession()):
        self._aiohttp_session = aiohttp_session
        self._experiences = None
        self._collections = None
        self._current_experience = None

    @staticmethod
    def _url_with_endpoint(endpoint) -> str:
        return f"{CONTROLLER_URL}{endpoint}"

    async def _get_json_response(self, endpoint) -> JsonDict:
        async with self._aiohttp_session.get(
            self._url_with_endpoint(endpoint)
        ) as response:
            return await response.json()

    async def experiences(self, use_cache=True) -> JsonDict:
        if self._experiences is None or not use_cache:
            self._experiences = await self._get_json_response("/experiences")

        return self._experiences

    async def collections(self, use_cache=True) -> JsonDict:
        if self._collections is None or not use_cache:
            self._collections = await self._get_json_response("/collections")

        return self._collections

    async def current_experience(self, use_cache=True) -> JsonDict:
        if self._current_experience is None or not use_cache:
            self._current_experience = await self._get_json_response("/current")

        return self._current_experience

    async def update_display_settings(self, settings: protocol.DisplaySettings) -> bool:
        async with self._aiohttp_session.put(
            self._url_with_endpoint("/current"), json=settings
        ) as response:
            return response.ok

