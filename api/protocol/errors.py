class ProtocolError(Exception):
    """Base for all protocol errors"""
    pass


class AccessError(ProtocolError):
    """A unauthorized client attempted to send an authenticated message"""
    pass


class UnknownMessageType(ProtocolError):
    """A client or app sent a readable message with an unregistered type"""
    pass


class InvalidMessageSchema(ProtocolError):
    """A client or app sent a message with an incorrect schema"""
    pass


class UnhandledMessageType(ProtocolError):
    """A client or app sent a valid message type that couldn't be handled"""
    pass
