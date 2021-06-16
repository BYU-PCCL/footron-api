import dataclasses
from enum import Enum
from typing import Type, Optional, Any, Dict, TypedDict, Union

from ..constants import JsonDict
from .errors import *

PROTOCOL_VERSION = 1


class MessageType(Enum):
    #: Client connection status update
    APP_HEARTBEAT = 0
    #: App connection status update
    CLIENT_HEARTBEAT = 1
    #: Client connection request
    CONNECT = 2
    #: App response to client connection request
    ACCESS = 3
    #: All application-defined messages in either direction, including requests
    APPLICATION = 4
    #: Request to change app runtime settings, handled by router
    DISPLAY_SETTINGS = 5
    #: Lifecycle updates (pause, resume)
    LIFECYCLE = 6


FIELD_MSG_TYPE = "type"


@dataclasses.dataclass
class BaseMessage:
    type: str
    version: int

    @classmethod
    def create(cls, **kwargs):
        return cls(**kwargs, version=PROTOCOL_VERSION)


@dataclasses.dataclass
class ClientBoundMixin:
    client: str


@dataclasses.dataclass
class HeartbeatMessage(BaseMessage):
    up: bool
    type = MessageType.APP_HEARTBEAT


@dataclasses.dataclass
class ClientHeartbeatMessage(HeartbeatMessage, ClientBoundMixin):
    type = MessageType.CLIENT_HEARTBEAT


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
    req: Optional[str]
    body: Any
    type = MessageType.APPLICATION


@dataclasses.dataclass
class ClientBoundApplicationMessage(ApplicationMessage, ClientBoundMixin):
    type = MessageType.APPLICATION


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
    MessageType.APP_HEARTBEAT: HeartbeatMessage,
    MessageType.CLIENT_HEARTBEAT: ClientHeartbeatMessage,
    MessageType.CONNECT: ConnectMessage,
    MessageType.ACCESS: AccessMessage,
    MessageType.APPLICATION: ApplicationMessage,
    MessageType.DISPLAY_SETTINGS: DisplaySettingsMessage,
    MessageType.LIFECYCLE: LifecycleMessage,
}


def serialize(data: BaseMessage) -> JsonDict:
    # TODO: If we end up needing to profile this code, we might want to use .__dict__() here instead:
    #  https://stackoverflow.com/questions/52229521/why-is-dataclasses-asdictobj-10x-slower-than-obj-dict
    return dataclasses.asdict(data)


def deserialize(data: JsonDict) -> BaseMessage:
    if FIELD_MSG_TYPE not in data:
        raise InvalidMessageSchema(f"Message doesn't contain required field '{FIELD_MSG_TYPE}'")

    msg_type = data[FIELD_MSG_TYPE]
    if msg_type not in message_type_map:
        raise UnknownMessageType(f"Message specified unrecognized type '{msg_type}'")

    return message_type_map[msg_type].__new__(**data)
