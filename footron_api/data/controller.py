import logging
from typing import Optional

import aiohttp

from ..constants import JsonDict, CONTROLLER_URL

_ENDPOINT_EXPERIENCES = "/experiences"
_ENDPOINT_COLLECTIONS = "/collections"
_ENDPOINT_FOLDERS = "/folders"
_ENDPOINT_CURRENT_EXPERIENCE = "/current"
_ENDPOINT_PLACARD_EXPERIENCE = "/placard/experience"
_ENDPOINT_PLACARD_URL = "/placard/url"

_EXPERIENCE_FIELD_LAST_UPDATE = "last_update"

logger = logging.getLogger(__name__)


class ControllerApi:
    def __init__(self, aiohttp_session=aiohttp.ClientSession()):
        self._aiohttp_session = aiohttp_session
        self._experiences = None
        self._collections = None
        self._folders = None
        self._current_experience = None
        self._placard_experience = None
        self._last_update = None

    @staticmethod
    def _url_with_endpoint(endpoint) -> str:
        return f"{CONTROLLER_URL}{endpoint}"

    def _invalidate_cache(self):
        self._experiences = None
        self._collections = None
        self._folders = None
        self._current_experience = None
        self._placard_experience = None

    def reset(self):
        self._invalidate_cache()

    async def _get_json_response(self, endpoint) -> JsonDict:
        async with self._aiohttp_session.get(
            self._url_with_endpoint(endpoint)
        ) as response:
            return await response.json()

    async def _put_json(self, endpoint, data: JsonDict) -> JsonDict:
        async with self._aiohttp_session.put(
            self._url_with_endpoint(endpoint), json=data
        ) as response:
            return await response.json()

    async def _patch_json(self, endpoint, data: JsonDict) -> JsonDict:
        async with self._aiohttp_session.patch(
            self._url_with_endpoint(endpoint), json=data
        ) as response:
            return await response.json()

    def _experience_view_fields(self, experience_id: str) -> JsonDict:
        thumbnails = {
            "wide": f"/static/icons/wide/{experience_id}.jpg",
            "thumb": f"/static/icons/thumbs/{experience_id}.jpg",
        }

        return {"thumbnails": thumbnails}

    async def experiences(self, use_cache=True) -> JsonDict:
        if self._experiences is None or not use_cache:
            self._experiences = {
                id: {**experience, **self._experience_view_fields(id)}
                for id, experience in (
                    await self._get_json_response(_ENDPOINT_EXPERIENCES)
                ).items()
                if "unlisted" not in experience or not experience["unlisted"]
            }

        return self._experiences

    async def collections(self, use_cache=True) -> JsonDict:
        if self._collections is None or not use_cache:
            self._collections = await self._get_json_response(_ENDPOINT_COLLECTIONS)

        return self._collections

    async def folders(self, use_cache=True) -> JsonDict:
        experiences = await self.experiences(use_cache=use_cache)

        if self._folders is None or not use_cache:
            self._folders = {
                id: {
                    **folder,
                    **self._experience_view_fields(folder["featured"]),
                    **{
                        "colors": experiences.get(folder["featured"], {}).get(
                            "colors", {}
                        )
                    },
                }
                for id, folder in (
                    await self._get_json_response(_ENDPOINT_FOLDERS)
                ).items()
            }

        return self._folders

    async def current_experience(self, use_cache=True) -> JsonDict:
        if (
            self._current_experience is None
            or _EXPERIENCE_FIELD_LAST_UPDATE not in self._current_experience
            or not use_cache
        ):
            new_experience = await self._get_json_response(_ENDPOINT_CURRENT_EXPERIENCE)
            if not new_experience:
                return {}
            self._current_experience = {
                **new_experience,
                **self._experience_view_fields(new_experience["id"]),
            }

            if (
                _EXPERIENCE_FIELD_LAST_UPDATE in self._current_experience
                and self._current_experience[_EXPERIENCE_FIELD_LAST_UPDATE]
                != self._last_update
            ):
                self._last_update = self._current_experience[
                    _EXPERIENCE_FIELD_LAST_UPDATE
                ]
                self.reset()

        return self._current_experience

    async def set_current_experience(self, id: str) -> JsonDict:
        return await self._put_json(_ENDPOINT_CURRENT_EXPERIENCE, {"id": id})

    async def patch_current_experience(self, updates: JsonDict) -> JsonDict:
        return await self._patch_json(_ENDPOINT_CURRENT_EXPERIENCE, updates)

    async def placard_experience(self) -> JsonDict:
        return await self._get_json_response(_ENDPOINT_PLACARD_EXPERIENCE)

    async def patch_placard_experience(self, updates: JsonDict) -> JsonDict:
        return await self._patch_json(_ENDPOINT_PLACARD_EXPERIENCE, updates)

    async def placard_url(self) -> JsonDict:
        # No caching for placard, make @vinhowe explain himself
        return await self._get_json_response(_ENDPOINT_PLACARD_URL)

    async def patch_placard_url(self, url: Optional[str]) -> JsonDict:
        return await self._patch_json(_ENDPOINT_PLACARD_URL, {"url": url})
