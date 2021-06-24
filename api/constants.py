import os
from typing import Dict, Any, Union

_BASE_URL_ENV = "CSTV_BASE_URL"

BASE_URL = (
    os.environ[_BASE_URL_ENV]
    if _BASE_URL_ENV in os.environ
    else "http://localhost:5000"
)

# TODO: If we end up having a lot of global types, move them into types.py
JsonDict = Dict[str, Union[Any, Any]]
