import asyncio
import string
import secrets
import urllib.parse
from typing import List, Callable

from .controller import ControllerApi


# Note that bytes != characters; see https://docs.python.org/3/library/secrets.html#secrets.token_urlsafe.
#
# @vinhowe: 6 bytes gives us 8 characters, which one might worry is susceptible to brute force attacks, but plugging
# in an example output from `secrets.token_urlsafe(6)` ("z8iCIY-i") to https://www.grc.com/haystack.htm gives us an
# online brute force time of around 213 millennia. Granted, if the attacker knows that the length of this code is
# fixed, it could take less time. I think we're safe because:
#
# - We'll set codes to expire in at most 20 minutes
# - At the least we'll use local DoS detection software like fail2ban, at most Cloudflare or similar
#
# The reason we pick a shorter code to begin with is that it results in a smaller--and nicer looking--QR code.
_CODE_BYTES_COUNT = 6

_ALPHANUMERIC_CHARS = string.ascii_letters + string.digits

# (str) -> None
_ListenerCallable = Callable[[str], None]


class AuthManager:
    code: str
    next_code: str
    _listeners: List[_ListenerCallable]

    def __init__(self, controller: ControllerApi, base_domain: str):
        self.code = self._generate_code()
        self.next_code = self._generate_code()
        self._controller = controller
        self._base_domain = base_domain
        self._listeners = []
        asyncio.get_event_loop().create_task(self._update_placard_url())

    async def advance(self):
        self.code = self.next_code
        self.next_code = self._generate_code()
        self._notify_listeners()
        await self._update_placard_url()

    def add_listener(self, callback: _ListenerCallable):
        self._listeners.append(callback)

    def remove_listener(self, callback: _ListenerCallable):
        self._listeners.remove(callback)

    def _notify_listeners(self):
        [listener(self.code) for listener in self._listeners]

    async def _update_placard_url(self):
        await self._controller.patch_placard({"url": self._create_url()})

    def _create_url(self):
        return urllib.parse.urljoin(self._base_domain, f"/c/{self.next_code}")

    @staticmethod
    def _generate_code() -> str:
        return secrets.token_urlsafe(_CODE_BYTES_COUNT)
