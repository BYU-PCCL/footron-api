import logging
import os
from pathlib import Path
from typing import Dict, Any, Union

from xdg import xdg_data_home

# TODO: Is there actually a good reason to use env variables here instead of CLI
#  arguments?

_BASE_URL_ENV = "FT_BASE_URL"
_CONTROLLER_URL_ENV = "FT_CONTROLLER_URL"
_LOG_LEVEL_ENV = "FT_LOG_LEVEL"

# The user-facing URL--where the static website is hosted
BASE_URL = (
    os.environ[_BASE_URL_ENV]
    if _BASE_URL_ENV in os.environ
    else "http://localhost:3000"
)

# The base URL for the Controller API
CONTROLLER_URL = (
    os.environ[_CONTROLLER_URL_ENV]
    if _BASE_URL_ENV in os.environ
    else "http://localhost:8000"
)

BASE_DATA_PATH = (
    Path(os.environ["FT_API_DATA_PATH"])
    if "FT_API_DATA_PATH" in os.environ
    else Path(xdg_data_home(), "footron-api")
)

# 15 minutes (should be, 30s for testing)
AUTH_TIMEOUT_S = 30

def _log_level(arg):
    level = getattr(logging, arg.upper(), None)
    if level is None:
        raise ValueError(f"Invalid log level '{arg}'")
    return level


LOG_LEVEL = (
    _log_level(os.environ[_LOG_LEVEL_ENV])
    if _LOG_LEVEL_ENV in os.environ
    else logging.INFO
)

# TODO: If we end up having a lot of global types, move them into types.py
JsonDict = Dict[str, Union[Any, Any]]
