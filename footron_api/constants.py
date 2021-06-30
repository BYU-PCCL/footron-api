import os
from typing import Dict, Any, Union

_BASE_URL_ENV = "FT_BASE_URL"
_CONTROLLER_URL_ENV = "FT_CONTROLLER_URL"

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

# TODO: If we end up having a lot of global types, move them into types.py
JsonDict = Dict[str, Union[Any, Any]]
