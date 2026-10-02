"""
Custom idf-build-apps App class that merges the binaries of every successfully built app
into a single image that can be flashed with ESP Launchpad.

Load it with:
    idf-build-apps build --build-system launchpad_app:LaunchpadApp --extra-pythonpaths <dir of this file>

Environment variables:
    LAUNCHPAD_OUTPUT_DIR   directory for the merged binaries (default: "binaries")
    LAUNCHPAD_IDF_VERSION  IDF version label used in the file names (default: detected IDF version)
"""

import logging
import os
import subprocess
import sys
import typing as t
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version

from idf_build_apps import CMakeApp
from idf_build_apps.constants import IDF_VERSION_MAJOR
from idf_build_apps.constants import IDF_VERSION_MINOR
from idf_build_apps.constants import IDF_VERSION_PATCH
from idf_build_apps.constants import BuildStatus

# child of the idf_build_apps logger, so the messages use the handlers set up by idf-build-apps
LOGGER = logging.getLogger('idf_build_apps.launchpad')

OUTPUT_DIR_ENV = 'LAUNCHPAD_OUTPUT_DIR'
IDF_VERSION_ENV = 'LAUNCHPAD_IDF_VERSION'
DEFAULT_OUTPUT_DIR = 'binaries'


class MergeError(Exception):
    pass


def normalize_idf_version(idf_version: str) -> str:
    return idf_version.replace('.', '_')


def get_idf_version_label() -> str:
    label = os.environ.get(IDF_VERSION_ENV)
    if not label:
        label = f'v{IDF_VERSION_MAJOR}.{IDF_VERSION_MINOR}.{IDF_VERSION_PATCH}'
    return normalize_idf_version(label)


def merged_bin_name(app_name: str, config_name: t.Optional[str], target: str, idf_version: str) -> str:
    parts = [app_name, config_name, target, idf_version]
    return '-'.join(p for p in parts if p) + '.bin'


def esptool_merge_command() -> str:
    # esptool v5 renamed the sub-commands to use dashes, older versions only know `merge_bin`
    try:
        major = int(package_version('esptool').split('.')[0])
    except (PackageNotFoundError, ValueError):
        major = 0
    return 'merge-bin' if major >= 5 else 'merge_bin'


class LaunchpadApp(CMakeApp):
    build_system: t.Literal['launchpad_cmake'] = 'launchpad_cmake'  # type: ignore

    # Serialized into the --collect-app-info file and consumed by generate_config.py
    merged_bin: t.Optional[str] = None
    launchpad_app_name: t.Optional[str] = None
    launchpad_idf_version: t.Optional[str] = None

    def _post_build(self) -> None:
        # super() may still turn a successful build into a failed one (check_warnings)
        super()._post_build()

        if self.build_status != BuildStatus.SUCCESS:
            return

        try:
            self._merge_binaries()
        except MergeError as e:
            LOGGER.error('%s', e)
            self.build_status = BuildStatus.FAILED
            self.build_comment = str(e)

    def _merge_binaries(self) -> None:
        if not os.path.isfile(os.path.join(self.build_path, 'flash_args')):
            raise MergeError(f'Cannot merge binaries: "flash_args" not found in {self.build_path}')

        idf_version = get_idf_version_label()
        file_name = merged_bin_name(self.name, self.config_name, self.target, idf_version)
        output_dir = os.path.abspath(os.environ.get(OUTPUT_DIR_ENV) or DEFAULT_OUTPUT_DIR)
        output_path = os.path.join(output_dir, file_name)
        os.makedirs(output_dir, exist_ok=True)

        cmd = [
            sys.executable,
            '-m',
            'esptool',
            '--chip',
            self.target,
            esptool_merge_command(),
            '-o',
            output_path,
            '@flash_args',
        ]
        LOGGER.info('Merging binaries: %s', ' '.join(cmd))
        proc = subprocess.run(cmd, cwd=self.build_path, capture_output=True, text=True)
        if proc.returncode != 0:
            output = '\n'.join(s for s in (proc.stdout.strip(), proc.stderr.strip()) if s)
            raise MergeError(f'Merging binaries into {file_name} failed (exit code {proc.returncode}):\n{output}')

        LOGGER.info('Merged binaries into %s', output_path)
        self.merged_bin = file_name
        self.launchpad_app_name = self.name
        self.launchpad_idf_version = idf_version
