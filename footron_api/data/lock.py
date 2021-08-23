from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import footron_protocol as protocol

if TYPE_CHECKING:
    from ..data import AuthManager, ControllerApi


class LockManager:
    _lock: protocol.Lock
    _auth_manager: AuthManager
    _controller: ControllerApi

    def __init__(self, auth_manager: AuthManager, controller: ControllerApi):
        self._lock = False
        self._auth_manager = auth_manager
        self._controller = controller

    @property
    def lock(self):
        return self._lock

    @lock.setter
    def lock(self, lock: protocol.Lock):
        if lock == self._lock:
            return

        self._lock = lock
        await self._controller.patch_current_experience({"lock": lock})
        # This allows new clients to join an existing client without
        asyncio.get_event_loop().create_task(self._auth_manager.lock(lock))
        # TODO: Interact with auth manager to allow
