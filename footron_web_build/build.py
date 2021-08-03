from __future__ import annotations

import dataclasses
import json
import logging
import shutil
import subprocess
import tempfile
import argparse
from datetime import datetime

import colorgram
from os import PathLike
from pathlib import Path
from typing import Union, List, Dict, Any, Optional

from color_utils import rgb, rgb_to_hex

# We need to update these if we ever change the web app's directory structure
_SOURCE_BUILD_PATH = Path("build")
_SOURCE_GENERATED_PATH = Path("src", "controls", "generated")
_SOURCE_GENERATED_INDEX_PATH = _SOURCE_GENERATED_PATH / "index.ts"
_SOURCE_STATIC_ICONS_PATH = Path("icons")
_SOURCE_STATIC_ICONS_THUMBS_PATH = _SOURCE_STATIC_ICONS_PATH / "thumbs"
_SOURCE_STATIC_ICONS_WIDE_PATH = _SOURCE_STATIC_ICONS_PATH / "wide"

_BUILD_STATIC_PATH = Path("static")

_EXPERIENCE_CONFIG_PATH = Path("config.json")
_EXPERIENCE_WIDE_PATH = Path("wide.jpg")
_EXPERIENCE_THUMB_PATH = Path("thumb.jpg")
_EXPERIENCE_CONTROLS_PATH = Path("controls")
_EXPERIENCE_CONTROLS_SOURCE_PATH = _EXPERIENCE_CONTROLS_PATH / "lib"
_EXPERIENCE_CONTROLS_STATIC_PATH = _EXPERIENCE_CONTROLS_PATH / "static"

_CONTROLS_INDEX_TEMPLATE = (
    "%s\n"
    "const controls: Map<string, () => JSX.Element> = new Map([\n"
    "  %s\n"
    "]);\n"
    "export default controls;\n"
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("footron web build")


class BuildError(Exception):
    pass


class Experience:
    path: Path
    config: Dict[str, Any]
    id: str
    colors: Optional[ComputedColors]

    @property
    def controls_source_path(self):
        return self.path / _EXPERIENCE_CONTROLS_SOURCE_PATH

    @property
    def controls_static_path(self):
        return self.path / _EXPERIENCE_CONTROLS_STATIC_PATH

    @property
    def wide_image_path(self):
        return self.path / _EXPERIENCE_WIDE_PATH

    @property
    def thumb_image_path(self):
        return self.path / _EXPERIENCE_THUMB_PATH

    def __init__(self, path: Union[str, PathLike]):
        self.path = Path(path).absolute()
        self._load_config()
        self._calculate_colors()

    def _calculate_colors(self):
        base_color = [
            l / 255
            for l in list(colorgram.extract(str(self.wide_image_path), 1)[0].hsl)
        ]
        secondary_dark = rgb_to_hex(
            *rgb(
                *(
                    (base_color[0] + 0.1) % 1,
                    max(base_color[1] - 0.15, 0),
                    base_color[2] + 0.1,
                )
            )
        )
        secondary_light = rgb_to_hex(
            *rgb(*((base_color[0] + 0.18) % 1, min(base_color[1] * 1.5, 0.9), 0.94))
        )
        base_color = rgb_to_hex(*rgb(*(base_color[0], min(base_color[1], 0.74), 0.35)))
        self.colors = ComputedColors(base_color, secondary_light, secondary_dark)

    def _load_config(self):
        with open(self.path / "config.json") as config_file:
            self.config = json.load(config_file)
        self.id = self.config["id"]


@dataclasses.dataclass
class ComputedColors:
    primary: str
    secondary_light: str
    secondary_dark: str


@dataclasses.dataclass
class BuildResult:
    output_path: Path
    experiences: List[Experience]


class WebBuilder:
    web_source_path: Path
    experiences: List[Experience]

    _output_path: Path

    def __init__(
        self,
        web_source_path: Union[str, PathLike],
        finished_build_path: Union[str, PathLike],
        experience_paths: List[Union[str, PathLike]],
    ):
        self.web_source_path = Path(web_source_path).absolute()
        self.finished_build_path = Path(finished_build_path).absolute()
        self.experiences = [*map(Experience, experience_paths)]
        self._output_path = Path(web_source_path).absolute()

    @property
    def _output_controls_source_path(self):
        return self._output_path / _SOURCE_GENERATED_PATH

    @property
    def _output_controls_source_index_path(self):
        return self._output_path / _SOURCE_GENERATED_INDEX_PATH

    @property
    def _output_build_path(self):
        return self._output_path / _SOURCE_BUILD_PATH

    @property
    def _output_static_path(self):
        return self._output_build_path / _BUILD_STATIC_PATH

    def _copy_source_to_output_dir(self):
        logger.info(f"Copying source to {self._output_path}...")
        shutil.copytree(
            self.web_source_path,
            self._output_path,
            symlinks=True,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(".git/", "build/", ".idea/"),
        )

    def _link_controls(self):
        logger.info("Linking controls and generating index.ts...")

        module_imports = []
        map_entries = []

        # We have test generated output--so we can do dev builds--that we need to delete
        shutil.rmtree(self._output_controls_source_path)
        self._output_controls_source_path.mkdir()

        for i, experience in enumerate(self.experiences):
            if experience.controls_source_path.exists():
                linked_source_path = self._output_controls_source_path / experience.id
                linked_source_path.symlink_to(experience.controls_source_path)

                module_imports.append(f'import Controls{i} from "./{experience.id}";')
                map_entries.append(f'["{experience.id}", Controls{i}]')

        index_content = _CONTROLS_INDEX_TEMPLATE % (
            "\n".join(module_imports),
            ",\n".join(map_entries),
        )
        with open(self._output_controls_source_index_path, "w") as index_file:
            index_file.write(index_content)

    def _yarn_build(self):
        logger.info("Running yarn build...")
        build_process = subprocess.run(["yarn", "build"], cwd=self._output_path)
        if build_process.returncode != 0:
            raise BuildError(
                f"Yarn exited with error status {build_process.returncode}"
            )

    def _add_static_assets(self):
        logger.info("Adding static assets to build output..")
        thumbs_path = self._output_static_path / _SOURCE_STATIC_ICONS_THUMBS_PATH
        wide_path = self._output_static_path / _SOURCE_STATIC_ICONS_WIDE_PATH
        experiences_static_path = self._output_static_path / "experiences"
        thumbs_path.mkdir(parents=True)
        wide_path.mkdir(parents=True)
        experiences_static_path.mkdir(parents=True)

        for experience in self.experiences:
            if experience.controls_static_path.exists():
                shutil.copytree(
                    experience.controls_static_path,
                    experiences_static_path / experience.id,
                )

            icon_filename = f"{experience.id}.jpg"

            if experience.thumb_image_path.exists():
                shutil.copyfile(
                    experience.thumb_image_path, thumbs_path / icon_filename
                )

            if experience.wide_image_path.exists():
                shutil.copyfile(experience.wide_image_path, wide_path / icon_filename)

    def _copy_build_to_finished_dir(self):
        logger.info(f"Copying successful build output to {self.finished_build_path}...")
        shutil.copytree(self._output_build_path, self.finished_build_path)

    def build(self):
        with tempfile.TemporaryDirectory() as self._output_path:
            start_time = datetime.now()
            # Check if finished build path already exists so we don't get through a
            # whole build and find it later:
            if self.finished_build_path.exists():
                raise FileExistsError(
                    f"Output build path {self.finished_build_path} already exists"
                )
            # Useful for debugging:
            # self._output_path = Path("/tmp/test-build")
            # self._output_path.mkdir(parents=True, exist_ok=True)
            self._copy_source_to_output_dir()
            self._link_controls()
            self._yarn_build()
            self._add_static_assets()
            self._copy_build_to_finished_dir()
            build_duration = datetime.now() - start_time
            seconds = f"{build_duration.seconds}s" if build_duration.seconds else None
            millis = (
                f"{build_duration.microseconds / 1000}ms"
                if build_duration.microseconds
                else None
            )
            time_units = " ".join(filter(bool, [seconds, millis]))
            logger.info(f"Build finished successfully in {time_units}")
            return BuildResult(self.finished_build_path, self.experiences)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build a Footron web app.")
    parser.add_argument("web_source_path", type=Path)
    parser.add_argument("output_path", type=Path)
    parser.add_argument("experience_paths", nargs="+", type=Path)
    parser.add_argument("--color-output-path", type=Path)

    args = parser.parse_args()
    # print(args.experience_paths)
    builder = WebBuilder(args.web_source_path, args.output_path, args.experience_paths)
    output = builder.build()

    color_output_path = args.color_output_path

    if color_output_path:
        with open(color_output_path, "w") as color_file:
            color_data = {}
            for experience in output.experiences:
                color_data[experience.id] = {
                    "primary": experience.colors.primary,
                    "secondary_light": experience.colors.secondary_light,
                    "secondary_dark": experience.colors.secondary_dark,
                }
            json.dump(color_data, color_file)
    else:
        print("Output colors:")
        for experience in output.experiences:
            print(f"- {experience.id}")
            print(f"  - primary: {experience.colors.primary}")
            print(f"  - secondary light: {experience.colors.secondary_light}")
            print(f"  - secondary dark: {experience.colors.secondary_dark}")
