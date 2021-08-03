import json
import logging
from typing import Dict

from pydantic import BaseModel, Field

from ..constants import BASE_DATA_PATH

logger = logging.getLogger(__name__)


class ExperienceColors(BaseModel):
    primary: str
    secondary_light: str
    secondary_dark: str


DEFAULT_COLORS = ExperienceColors(
    primary="#212121", secondary_light="#fafafa", secondary_dark="#252525"
)


class ExperienceColorsManager:
    _colors: Dict[str, ExperienceColors]

    def __init__(self):
        self.load()

    def load(self):
        try:
            with open(BASE_DATA_PATH / "colors.json") as colors_file:
                self._colors = {
                    id: ExperienceColors.parse_obj(colors)
                    for id, colors in json.load(colors_file).items()
                }
        except FileNotFoundError:
            logger.warning("Couldn't load colors.json, colors will not be available")
            self._colors = {}

    @property
    def colors(self):
        return self._colors
