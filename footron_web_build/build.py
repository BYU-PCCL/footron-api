from __future__ import annotations

import dataclasses
import json
import logging
import shutil
import subprocess
import tempfile
import argparse
from datetime import datetime
from functools import partial

import colorgram
from os import PathLike
from pathlib import Path
from typing import Union, List, Dict, Any, Optional

from .color_utils import rgb, rgb_to_hex

# We need to update these if we ever change the web app's directory structure
_SOURCE_BUILD_PATH = Path("build")
_SOURCE_PUBLIC_PATH = Path("public")
_SOURCE_GENERATED_PATH = Path("src", "controls", "generated")
_SOURCE_GENERATED_INDEX_PATH = _SOURCE_GENERATED_PATH / "index.ts"
_SOURCE_STATIC_ICONS_PATH = Path("icons")
_SOURCE_STATIC_ICONS_THUMBS_PATH = _SOURCE_STATIC_ICONS_PATH / "thumbs"
_SOURCE_STATIC_ICONS_WIDE_PATH = _SOURCE_STATIC_ICONS_PATH / "wide"

_BUILD_STATIC_PATH = Path("static")

# TODO: Change this to something more specific to Footron because we use it to
#  identify which paths contain experiences
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
    type: str
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

    def __init__(self, path: Union[str, PathLike], generate_colors=True):
        self.path = Path(path).absolute()
        self._load_config()
        if (
            generate_colors
            and self.wide_image_path.exists()
            and self.thumb_image_path.exists()
        ):
            self._calculate_colors()

    def _calculate_colors(self):
        logger.info(f"Generating colors for {self.id}")
        base_color = [
            l / 255
            for l in list(colorgram.extract(str(self.wide_image_path), 1)[0].hsl)
        ]
        base_color = (base_color[0], min(base_color[1], 0.74), 0.35)
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
        with open(self.path / _EXPERIENCE_CONFIG_PATH) as config_file:
            self.config = json.load(config_file)
        self.id = self.config["id"]
        self.type = self.config["type"]


@dataclasses.dataclass
class ComputedColors:
    primary: str
    secondary_light: str
    secondary_dark: str


@dataclasses.dataclass
class BuildResult:
    output_path: Path
    experiences: List[Experience]


class BuildPath:
    _temp_dir: Optional[tempfile.TemporaryDirectory]
    _output_dir: Path
    _debug: bool

    def __init__(self, output_dir: Path, debug=False):
        self._temp_dir = None
        self._output_dir = output_dir
        self._debug = debug

    def __enter__(self):
        if self._debug:
            return self._output_dir

        self._temp_dir = tempfile.TemporaryDirectory()
        return self._temp_dir.__enter__()

    def __exit__(self, *args, **kwargs):
        if self._debug:
            return

        return self._temp_dir.__exit__(*args, **kwargs)


class WebBuilder:
    web_source_path: Path
    finished_build_path: Path
    experiences: List[Experience]

    _output_path: Path
    _debug: bool

    def __init__(
        self,
        web_source_path: Union[str, PathLike],
        finished_build_path: Union[str, PathLike],
        experience_paths: List[Union[str, PathLike]],
        generate_colors=False,
        debug=False,
    ):
        self.web_source_path = Path(web_source_path).absolute()
        self.finished_build_path = Path(finished_build_path).absolute()
        experience_paths = list(
            filter(lambda p: (p / _EXPERIENCE_CONFIG_PATH).exists(), experience_paths)
        )
        self.experiences = [
            *map(partial(Experience, generate_colors=generate_colors), experience_paths)
        ]
        self._output_path = Path(web_source_path).absolute()
        self._debug = debug

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
        if self._debug:
            base_path = self._output_path / _SOURCE_PUBLIC_PATH
        else:
            base_path = self._output_build_path
        return base_path / _BUILD_STATIC_PATH

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

        module_imports = ['import VideoScrubber from "../VideoScrubber";']
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
            elif (
                experience.type == "video"
                and "scrubbing" in experience.config
                and experience.config["scrubbing"] is True
            ):
                map_entries.append(f'["{experience.id}", VideoScrubber]')

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
        build_type_name = "build" if not self._debug else "debug copy"
        logger.info(f"Adding static assets to {build_type_name} output..")
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
        with BuildPath(self.finished_build_path, self._debug) as self._output_path:
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
            if not self._debug:
                self._yarn_build()
            self._add_static_assets()
            if not self._debug:
                self._copy_build_to_finished_dir()
            build_duration = datetime.now() - start_time
            seconds = f"{build_duration.seconds}s" if build_duration.seconds else None
            millis = (
                f"{build_duration.microseconds / 1000}ms"
                if build_duration.microseconds
                else None
            )
            time_units = " ".join(filter(bool, [seconds, millis]))
            build_type_name = "Build" if not self._debug else "Debug copy"
            logger.info(f"{build_type_name} finished successfully in {time_units}")
            return BuildResult(self.finished_build_path, self.experiences)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build a Footron web app.")
    parser.add_argument("web_source_path", type=Path)
    parser.add_argument("output_path", type=Path)
    parser.add_argument("experience_paths", nargs="+", type=Path)
    parser.add_argument("--color-output-path", type=Path)
    parser.add_argument("--debug", action="store_true")

    args = parser.parse_args()
    color_output_path = args.color_output_path
    builder = WebBuilder(
        args.web_source_path,
        args.output_path,
        args.experience_paths,
        generate_colors=bool(color_output_path),
        debug=args.debug,
    )
    output = builder.build()

    if color_output_path:
        with open(color_output_path, "w") as color_file:
            color_data = {}
            for experience in output.experiences:
                if not hasattr(experience, "colors"):
                    continue

                color_data[experience.id] = {
                    "primary": experience.colors.primary,
                    "secondary_light": experience.colors.secondary_light,
                    "secondary_dark": experience.colors.secondary_dark,
                }
            json.dump(color_data, color_file)
