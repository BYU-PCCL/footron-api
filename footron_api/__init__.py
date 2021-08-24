import logging

from .app import app
from .constants import LOG_LEVEL

logging.basicConfig(level=LOG_LEVEL)
