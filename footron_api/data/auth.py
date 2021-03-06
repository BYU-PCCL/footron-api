import asyncio
import logging
import string
import secrets
import urllib.parse
import footron_protocol as protocol
from typing import List, Callable, Awaitable, Union, Optional

import aiohttp

from .controller import ControllerApi
from ..constants import AUTH_TIMEOUT_S

logger = logging.getLogger(__name__)

# Note that bytes != characters; see
# https://docs.python.org/3/library/secrets.html#secrets.token_urlsafe.
#
# @vinhowe: 6 bytes gives us 8 characters, which one might worry is susceptible to
# brute force attacks, but plugging in an example output from
# `secrets.token_urlsafe(6)` ("z8iCIY-i") to https://www.grc.com/haystack.htm gives us
# an online brute force time of around 213 millennia. Granted, if the attacker knows
# that the length of this code is fixed, it could take less time. I think we're safe
# because:
#
# - We'll set codes to expire in at most 20 minutes
# - At the least we'll use local DoS detection software like fail2ban, at most
#   Cloudflare or similar
#
# The reason we pick a shorter code to begin with is that it results in a smaller--and
# nicer looking--QR code.
_CODE_BYTES_COUNT = 6


# (str) -> None
AuthCallback = Callable[[str], Union[Awaitable[None], None]]


class AuthManager:
    _code: str
    _next_code: Optional[str]
    _last_lock: protocol.Lock
    _lock: protocol.Lock
    _listeners: List[AuthCallback]
    _auto_advance_task: Optional[asyncio.Task]

    def __init__(self, controller: ControllerApi, base_domain: str):
        self._code = self._generate_code()
        self._next_code = self._generate_code()
        self._controller = controller
        self._base_domain = base_domain
        self._last_lock = False
        self._lock = False
        self._listeners = []
        self._auto_advance_task = asyncio.get_event_loop().create_task(
            self._advance_after_timeout()
        )
        asyncio.get_event_loop().create_task(self._update_placard_url())
        asyncio.get_event_loop().create_task(self._update_placard_url_loop())

    def check(self, code: str):
        return self._check(code, self._code)

    def check_next(self, code: str):
        return self._check(code, self._next_code)

    @staticmethod
    def _check(a: Optional[str], b: Optional[str]):
        # TODO(vinhowe): Justify this confusing logic. Write a comment explaining it.
        if (a is None) != (b is None):
            return False
        # See
        # https://fastapi.tiangolo.com/advanced/security/http-basic-auth/#timing-attacks
        # for some background on the use of secrets.compare_digest() here
        return secrets.compare_digest(a, b)

    @property
    def code(self):
        return self._code

    @property
    def next_code(self):
        return self._next_code

    @property
    def lock(self):
        return self._lock

    @lock.setter
    def lock(self, lock: protocol.Lock):
        if lock == self._lock:
            return

        self._last_lock = self._lock
        self._lock = lock
        asyncio.get_event_loop().create_task(self._handle_lock_change())

    async def advance(self):
        if not self._lock:
            self._code = self.next_code
            self._next_code = self._generate_code()

            await self._notify_listeners()
            await self._update_placard_url()

        if self._auto_advance_task and not self._auto_advance_task.cancelled():
            self._auto_advance_task.cancel()

        if not self._lock:
            self._auto_advance_task = asyncio.get_event_loop().create_task(
                self._advance_after_timeout()
            )

    async def _advance_after_timeout(self):
        await asyncio.sleep(AUTH_TIMEOUT_S)
        logger.debug("Auth timeout expired, auto-cycling")
        await self.advance()

    async def _handle_lock_change(self):
        # Set these here so we (hopefully) don't have to deal with race conditions
        lock = self._lock
        last_lock = self._last_lock
        await self._controller.patch_current_experience({"lock": lock})
        # Apparently isinstance(x, int) is true if x is a bool, so we have to check for
        # that
        if isinstance(lock, int) and not isinstance(lock, bool):
            self._next_code = self.code
        elif lock is True:
            self._next_code = None
        else:
            self._next_code = self._generate_code()
            # If we had a closed lock, kick everyone off. Otherwise, we'll just do
            # normal pruning. Note that if people refresh, they'll be able to stick
            # around, which a problem that we should find an elegant way to address.
            if type(last_lock) == bool:
                self._code = self._generate_code()
        await self._notify_listeners()
        await self._update_placard_url()

    def add_listener(self, callback: AuthCallback):
        self._listeners.append(callback)

    def remove_listener(self, callback: AuthCallback):
        self._listeners.remove(callback)

    async def _notify_listeners(self):
        # TODO: Consider removing the string self.code argument from listeners
        #  because the only existing consumer so far (the messaging router) doesn't
        #  even use it

        # TODO also: see if we can pass in methods that aren't coroutines and await
        #  them without any problems
        await asyncio.gather(*[listener(self.code) for listener in self._listeners])

    async def _update_placard_url(self):
        new_url = None
        if self.next_code:
            new_url = self.create_url()
            logger.debug(f"New url is {new_url}")
        await self._controller.patch_placard_url(new_url)

    async def _update_placard_url_loop(self):
        """Check if QR code is empty and populate it with URL if so"""
        while True:
            try:
                placard_data = await self._controller.placard_url()
                if "url" not in placard_data or placard_data["url"] is None:
                    await self._update_placard_url()
            except aiohttp.ClientError:
                # TODO: Determine if it's worth showing errors here or if we can just
                #  fire and forget
                pass

            await asyncio.sleep(1)

    def create_url(self):
        return urllib.parse.urljoin(self._base_domain, f"/c/{self.next_code}")

    @staticmethod
    def _generate_code() -> str:
        return secrets.token_urlsafe(_CODE_BYTES_COUNT)
