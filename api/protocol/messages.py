from __future__ import annotations

import dataclasses
import enum
from enum import Enum
from typing import Type, Optional, Any, Dict, TypedDict, Union

from ..constants import JsonDict
from .errors import *

PROTOCOL_VERSION = 1


# TODO: Should we consider splitting up messages (and their types) by direction?
@enum.unique
class MessageType(Enum):
    #: Client connection status update
    HEARTBEAT_APP = "ahb"
    #: App connection status update
    HEARTBEAT_CLIENT = "chb"
    #: Client connection request
    CONNECT = "con"
    #: App response to client connection request
    ACCESS = "acc"
    #: Application-defined messages, including requests, from the client
    APPLICATION_CLIENT = "cap"
    #: Application-defined messages, including requests, from the app
    APPLICATION_APP = "app"
    #: Request to change app runtime settings, handled by router
    DISPLAY_SETTINGS = "dse"
    #: Lifecycle updates (pause, resume)
    LIFECYCLE = "lcy"


FIELD_MSG_TYPE = "type"


@dataclasses.dataclass
class BaseMessage:
    version: int
    type: MessageType

    @classmethod
    def create(cls, **kwargs) -> BaseMessage:
        # Force using class defined type
        if "type" in kwargs:
            del kwargs["type"]
        # noinspection PyArgumentList
        return cls(type=cls.type, version=PROTOCOL_VERSION, **kwargs)


@dataclasses.dataclass
class ClientBoundMixin:
    client: str


@dataclasses.dataclass
class HeartbeatMessage(BaseMessage):
    up: bool
    type = MessageType.HEARTBEAT_APP


@dataclasses.dataclass
class ClientHeartbeatMessage(HeartbeatMessage, ClientBoundMixin):
    type = MessageType.HEARTBEAT_CLIENT


@dataclasses.dataclass
class ConnectMessage(BaseMessage):
    type = MessageType.CONNECT


@dataclasses.dataclass
class AccessMessage(BaseMessage, ClientBoundMixin):
    accepted: bool
    reason: Optional[str]
    type = MessageType.ACCESS


@dataclasses.dataclass
class ApplicationMessage(BaseMessage):
    #: Request ID
    body: Any
    req: Optional[str] = None
    type = MessageType.APPLICATION_CLIENT


@dataclasses.dataclass
class ClientBoundApplicationMessage(ApplicationMessage, ClientBoundMixin):
    type = MessageType.APPLICATION_APP


class DisplaySettings(TypedDict):
    end_time: int
    # Lock states:
    # - false: no lock
    # - true: closed lock, not evaluating new connections
    # - n (int in [1, infinity)): after k = n active connections, controller will not accept new connections until k < n
    lock: Union[bool, int]


@dataclasses.dataclass
class DisplaySettingsMessage(BaseMessage):
    settings: DisplaySettings
    type = MessageType.DISPLAY_SETTINGS


@dataclasses.dataclass
class LifecycleMessage(BaseMessage):
    paused: bool
    type = MessageType.LIFECYCLE


message_type_map: Dict[MessageType, Type[BaseMessage]] = {
    MessageType.HEARTBEAT_APP: HeartbeatMessage,
    MessageType.HEARTBEAT_CLIENT: ClientHeartbeatMessage,
    MessageType.CONNECT: ConnectMessage,
    MessageType.ACCESS: AccessMessage,
    MessageType.APPLICATION_CLIENT: ApplicationMessage,
    MessageType.APPLICATION_APP: ClientBoundApplicationMessage,
    MessageType.DISPLAY_SETTINGS: DisplaySettingsMessage,
    MessageType.LIFECYCLE: LifecycleMessage,
}


def serialize(data: BaseMessage) -> JsonDict:
    # TODO: If we end up needing to profile this code, we might want to use .__dict__() here instead:
    #  https://stackoverflow.com/questions/52229521/why-is-dataclasses-asdictobj-10x-slower-than-obj-dict

    # This is a very hacky way (likely with better alternatives) to just get the 'type' field as its primitive type
    return {**dataclasses.asdict(data), "type": data.type.value}


def deserialize(data: JsonDict) -> BaseMessage:
    if FIELD_MSG_TYPE not in data:
        raise InvalidMessageSchema(
            f"Message doesn't contain required field '{FIELD_MSG_TYPE}'"
        )

    data[FIELD_MSG_TYPE] = MessageType(data[FIELD_MSG_TYPE])

    msg_type = data[FIELD_MSG_TYPE]
    if msg_type not in message_type_map:
        raise UnknownMessageType(f"Message specified unrecognized type '{msg_type}'")

    return message_type_map[msg_type].create(**data)
