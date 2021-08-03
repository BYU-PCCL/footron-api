import logging

import aiohttp

from ..constants import JsonDict, CONTROLLER_URL
from .colors import ExperienceColorsManager, DEFAULT_COLORS

_ENDPOINT_EXPERIENCES = "/experiences"
_ENDPOINT_COLLECTIONS = "/collections"
_ENDPOINT_CURRENT_EXPERIENCE = "/current"
_ENDPOINT_PLACARD = "/placard"

_EXPERIENCE_FIELD_LAST_UPDATE = "last_update"

logger = logging.getLogger(__name__)


class ControllerApi:
    def __init__(self, aiohttp_session=aiohttp.ClientSession()):
        self._aiohttp_session = aiohttp_session
        self._experiences = None
        self._collections = None
        self._current_experience = None
        self._last_update = None
        self._colors_manager = ExperienceColorsManager()

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

    def _add_experience_view_fields(self, experience: JsonDict) -> JsonDict:
        experience_id = experience["id"]

        try:
            colors = self._colors_manager.colors[experience_id]
        except KeyError:
            logging.warning(f"Couldn't find colors for experience '{experience_id}'")
            colors = DEFAULT_COLORS

        colors = {
            "primary": colors.primary,
            "secondaryLight": colors.secondary_light,
            "secondaryDark": colors.secondary_dark,
        }

        thumbnails = {
            "wide": f"/static/icons/wide/{experience_id}.jpg",
            "thumb": f"/static/icons/thumbs/{experience_id}.jpg",
        }

        return {**experience, "colors": colors, "thumbnails": thumbnails}

    async def experiences(self, use_cache=True) -> JsonDict:
        if self._experiences is None or not use_cache:
            self._experiences = {
                id: self._add_experience_view_fields(experience)
                for id, experience in (
                    await self._get_json_response(_ENDPOINT_EXPERIENCES)
                ).items()
            }

        return self._experiences

    async def collections(self, use_cache=True) -> JsonDict:
        if self._collections is None or not use_cache:
            self._collections = await self._get_json_response(_ENDPOINT_COLLECTIONS)

        return self._collections

    async def current_experience(self, use_cache=True) -> JsonDict:
        if (
            self._current_experience is None
            or _EXPERIENCE_FIELD_LAST_UPDATE not in self._current_experience
            or not use_cache
        ):
            self._current_experience = self._add_experience_view_fields(
                await self._get_json_response(_ENDPOINT_CURRENT_EXPERIENCE)
            )

            if (
                _EXPERIENCE_FIELD_LAST_UPDATE in self._current_experience
                and self._current_experience[_EXPERIENCE_FIELD_LAST_UPDATE]
                != self._last_update
            ):
                self._last_update = self._current_experience[
                    _EXPERIENCE_FIELD_LAST_UPDATE
                ]
                self._invalidate_cache()

        return self._current_experience

    async def set_current_experience(self, id: str) -> JsonDict:
        async with self._aiohttp_session.put(
            self._url_with_endpoint(_ENDPOINT_CURRENT_EXPERIENCE), json={"id": id}
        ) as response:
            return await response.json()

    async def patch_current_experience(self, updates: JsonDict) -> JsonDict:
        async with self._aiohttp_session.patch(
            self._url_with_endpoint(_ENDPOINT_CURRENT_EXPERIENCE), json=updates
        ) as response:
            return await response.json()

    async def placard(self) -> JsonDict:
        # No caching for placard, make @vinhowe explain himself
        return await self._get_json_response(_ENDPOINT_PLACARD)

    async def patch_placard(self, updates: JsonDict) -> JsonDict:
        async with self._aiohttp_session.patch(
            self._url_with_endpoint(_ENDPOINT_PLACARD), json=updates
        ) as response:
            return await response.json()
