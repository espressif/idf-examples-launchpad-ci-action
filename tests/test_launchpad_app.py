import json
import os
import subprocess
import sys
import textwrap
from importlib.metadata import PackageNotFoundError

import pytest
from conftest import LAUNCHPAD_DIR
from idf_build_apps.constants import BuildStatus

import generate_config
import launchpad_app
from launchpad_app import LaunchpadApp

CMAKELISTS = 'cmake_minimum_required(VERSION 3.16)\ninclude($ENV{IDF_PATH}/tools/cmake/project.cmake)\nproject(app)\n'


def create_app(root, rel_path, files=()):
    app_dir = root / rel_path
    app_dir.mkdir(parents=True)
    (app_dir / 'CMakeLists.txt').write_text(CMAKELISTS)
    for f in files:
        (app_dir / f).write_text('')
    return app_dir


def read_calls(log):
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


@pytest.fixture
def built_app(tmp_path, monkeypatch, fake_esptool):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('LAUNCHPAD_OUTPUT_DIR', 'out')
    monkeypatch.setenv('LAUNCHPAD_IDF_VERSION', 'release-v5.5')
    monkeypatch.setattr(launchpad_app, 'package_version', lambda _: '4.8.1')
    create_app(tmp_path, 'examples/blink')

    app = LaunchpadApp('examples/blink', 'esp32', build_dir='build_@t_@w', config_name='box')
    os.makedirs(app.build_path)
    (tmp_path / app.build_path / 'flash_args').write_text('0x1000 bootloader/bootloader.bin\n')
    app.build_status = BuildStatus.SUCCESS
    return app


@pytest.mark.parametrize(
    'version, expected',
    [('4.8.1', 'merge_bin'), ('5.0.0', 'merge-bin'), ('5.3.0.dev2', 'merge-bin'), ('dev', 'merge_bin')],
)
def test_esptool_merge_command(monkeypatch, version, expected):
    monkeypatch.setattr(launchpad_app, 'package_version', lambda _: version)
    assert launchpad_app.esptool_merge_command() == expected


def test_esptool_merge_command_without_esptool(monkeypatch):
    def _raise(_):
        raise PackageNotFoundError('esptool')

    monkeypatch.setattr(launchpad_app, 'package_version', _raise)
    assert launchpad_app.esptool_merge_command() == 'merge_bin'


def test_merged_bin_name():
    assert launchpad_app.merged_bin_name('blink', 'box', 'esp32', 'latest') == 'blink-box-esp32-latest.bin'
    assert launchpad_app.merged_bin_name('blink', '', 'esp32', 'latest') == 'blink-esp32-latest.bin'
    assert launchpad_app.merged_bin_name('blink', None, 'esp32', 'latest') == 'blink-esp32-latest.bin'


def test_idf_version_label(monkeypatch):
    monkeypatch.setenv('LAUNCHPAD_IDF_VERSION', 'release-v5.5')
    assert launchpad_app.get_idf_version_label() == 'release-v5_5'
    monkeypatch.delenv('LAUNCHPAD_IDF_VERSION')
    assert launchpad_app.get_idf_version_label() == 'v5_5_1'


def test_post_build_merges_binaries(built_app, tmp_path, fake_esptool):
    built_app._post_build()

    assert built_app.build_status == BuildStatus.SUCCESS
    assert built_app.merged_bin == 'blink-box-esp32-release-v5_5.bin'
    output = tmp_path / 'out' / 'blink-box-esp32-release-v5_5.bin'
    assert output.read_text() == 'merged'
    assert read_calls(fake_esptool) == [
        {
            'args': ['--chip', 'esp32', 'merge_bin', '-o', str(output), '@flash_args'],
            'cwd': os.path.realpath(tmp_path / built_app.build_path),
        }
    ]

    info = json.loads(built_app.to_json())
    assert info['build_system'] == 'launchpad_cmake'
    assert info['merged_bin'] == 'blink-box-esp32-release-v5_5.bin'
    assert info['launchpad_app_name'] == 'blink'
    assert info['launchpad_idf_version'] == 'release-v5_5'


def test_post_build_fails_when_esptool_fails(built_app, monkeypatch, fake_esptool):
    monkeypatch.setenv('FAKE_ESPTOOL_FAIL', '1')
    built_app._post_build()

    assert built_app.build_status == BuildStatus.FAILED
    assert 'fake failure' in built_app.build_comment
    assert built_app.merged_bin is None


def test_post_build_fails_without_flash_args(built_app, tmp_path, fake_esptool):
    os.remove(tmp_path / built_app.build_path / 'flash_args')
    built_app._post_build()

    assert built_app.build_status == BuildStatus.FAILED
    assert '"flash_args" not found' in built_app.build_comment
    assert read_calls(fake_esptool) == []


def test_post_build_skips_unsuccessful_builds(built_app, fake_esptool):
    built_app.build_status = BuildStatus.FAILED
    built_app._post_build()

    assert built_app.merged_bin is None
    assert read_calls(fake_esptool) == []


FAKE_BUILD_MODULE = textwrap.dedent(
    """
    import os
    import typing as t

    from idf_build_apps.constants import BuildStatus
    from launchpad_app import LaunchpadApp


    class FakeBuildApp(LaunchpadApp):
        build_system: t.Literal['fake_launchpad_cmake'] = 'fake_launchpad_cmake'

        def _build(self, **kwargs):
            open(self.build_log_path, 'w').close()
            with open(os.path.join(self.build_path, 'flash_args'), 'w') as fw:
                fw.write('0x1000 bootloader/bootloader.bin\\n')
            self.build_status = BuildStatus.SUCCESS
    """
)


def test_idf_build_apps_loads_hook_and_generates_config(tmp_path, monkeypatch, fake_esptool):
    """Runs the real idf-build-apps CLI the same way action.yml does, only idf.py and esptool are faked."""
    create_app(tmp_path, 'examples/blink', ['sdkconfig.ci', 'sdkconfig.ci.box'])
    create_app(tmp_path, 'examples/hello')
    (tmp_path / '.idf_build_apps.toml').write_text(
        'paths = ["examples"]\n'
        'target = "all"\n'
        'recursive = true\n'
        'config_rules = ["sdkconfig.ci=", "sdkconfig.ci.*="]\n'
    )
    hook_dir = tmp_path / 'hook'
    hook_dir.mkdir()
    (hook_dir / 'fake_build_app.py').write_text(FAKE_BUILD_MODULE)
    (tmp_path / 'binaries').mkdir()  # action.yml creates the output directory before building

    env = dict(os.environ, LAUNCHPAD_OUTPUT_DIR='binaries', LAUNCHPAD_IDF_VERSION='latest')
    proc = subprocess.run(
        [
            sys.executable,
            '-m',
            'idf_build_apps',
            'build',
            '--config-file',
            '.idf_build_apps.toml',
            '--collect-app-info',
            'binaries/app_info_latest_@p.json',
            '--build-system',
            'fake_build_app:FakeBuildApp',
            '--extra-pythonpaths',
            LAUNCHPAD_DIR,
            str(hook_dir),
            '--parallel-count',
            '1',
            '--parallel-index',
            '1',
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr

    binaries = tmp_path / 'binaries'
    assert sorted(p.name for p in binaries.glob('*.bin')) == sorted(
        [f'blink-{t}-latest.bin' for t in ('esp32', 'esp32c3', 'esp32s3')]
        + [f'blink-box-{t}-latest.bin' for t in ('esp32', 'esp32c3', 'esp32s3')]
        + [f'hello-{t}-latest.bin' for t in ('esp32', 'esp32c3', 'esp32s3')]
    )
    assert len(read_calls(fake_esptool)) == 9

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('GITHUB_REPOSITORY', 'owner/repo')
    assert generate_config.main(['--binaries-dir', 'binaries', '--remove-app-info']) == 0

    content = (binaries / 'config.toml').read_text()
    assert 'supported_apps = ["blink-latest", "blink-box-latest", "hello-latest"]' in content
    assert content.count('chipsets = ["esp32", "esp32c3", "esp32s3"]') == 3
    assert not list(binaries.glob('app_info_*.json'))
