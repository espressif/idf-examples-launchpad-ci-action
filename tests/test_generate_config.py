import json
import os

import pytest

import generate_config as gc

try:
    import tomllib
except ImportError:  # Python < 3.11
    tomllib = None

URL = 'https://owner.github.io/repo/'


def record(app_dir, target, config_name='', idf_version='latest', status='build success', merged=True):
    name = os.path.basename(app_dir)
    merged_bin = '-'.join(p for p in (name, config_name, target, idf_version) if p) + '.bin'
    return {
        'build_system': 'launchpad_cmake',
        'app_dir': app_dir,
        'target': target,
        'config_name': config_name,
        'build_status': status,
        'merged_bin': merged_bin if merged and status == 'build success' else None,
        'launchpad_app_name': name if merged else None,
        'launchpad_idf_version': idf_version if merged else None,
    }


def render(records, fmt=gc.DEFAULT_APP_NAME_FORMAT):
    return gc.render_config_toml(gc.collect_entries(records, fmt), URL)


@pytest.mark.parametrize(
    'fmt, config, expected',
    [
        ('@n-@c-@v', 'box', 'blink-box-release-v5_5'),
        ('@n-@c-@v', '', 'blink-release-v5_5'),
        ('@n-@c (IDF @v)', 'box', 'blink-box (IDF release-v5_5)'),
        ('@n-@c (IDF @v)', '', 'blink (IDF release-v5_5)'),
        ('@f-@v', '', 'examples_blink-release-v5_5'),
    ],
)
def test_format_app_name(fmt, config, expected):
    assert gc.format_app_name(fmt, 'blink', config, 'release-v5_5', 'examples/blink') == expected


def test_format_app_name_does_not_expand_placeholders_in_values():
    assert gc.format_app_name('@n-@c-@v', 'demo@v', 'x@n', 'latest', 'examples/demo@v') == 'demo@v-x@n-latest'


@pytest.mark.parametrize('name', sorted(gc.RESERVED_NAMES))
def test_reserved_app_name_is_an_error(name):
    with pytest.raises(gc.ConfigError, match='reserved key'):
        gc.collect_entries([record(f'examples/{name}', 'esp32')], '@n')


def test_legacy_layout():
    content = render(
        [
            record('examples/hello', 'esp32c3'),
            record('examples/blink', 'esp32s3', 'box'),
            record('examples/hello', 'esp32'),
        ]
    )
    assert content == (
        'esp_toml_version = 1.0\n'
        'firmware_images_url = "https://owner.github.io/repo/"\n'
        'supported_apps = ["blink-box-latest", "hello-latest"]\n'
        '\n'
        '[blink-box-latest]\n'
        'chipsets = ["esp32s3"]\n'
        'image.esp32s3 = "blink-box-esp32s3-latest.bin"\n'
        'android_app_url = ""\n'
        'ios_app_url = ""\n'
        '\n'
        '[hello-latest]\n'
        'chipsets = ["esp32", "esp32c3"]\n'
        'image.esp32 = "hello-esp32-latest.bin"\n'
        'image.esp32c3 = "hello-esp32c3-latest.bin"\n'
        'android_app_url = ""\n'
        'ios_app_url = ""\n'
    )


@pytest.mark.skipif(tomllib is None, reason='tomllib requires Python 3.11+')
def test_output_is_valid_toml_with_nested_images():
    content = render(
        [record('examples/blink', 'esp32', 'box'), record('examples/blink', 'esp32s3', 'box')],
        '@n (@c, IDF @v)',
    )
    data = tomllib.loads(content)
    assert data['supported_apps'] == ['blink (box, IDF latest)']
    app = data['blink (box, IDF latest)']
    assert app['chipsets'] == ['esp32', 'esp32s3']
    assert app['image'] == {'esp32': 'blink-box-esp32-latest.bin', 'esp32s3': 'blink-box-esp32s3-latest.bin'}


def test_default_and_config_builds_of_one_app_are_kept():
    entries = gc.collect_entries(
        [record('examples/blink', 'esp32'), record('examples/blink', 'esp32', 'box'), record('examples/blink', 'esp32s3', 'box')]
    )
    assert entries == {
        'blink-latest': {'esp32': 'blink-esp32-latest.bin'},
        'blink-box-latest': {'esp32': 'blink-box-esp32-latest.bin', 'esp32s3': 'blink-box-esp32s3-latest.bin'},
    }


def test_non_adjacent_records_are_grouped():
    entries = gc.collect_entries(
        [record('examples/a', 'esp32'), record('examples/b', 'esp32'), record('examples/a', 'esp32c3')]
    )
    assert entries == {
        'a-latest': {'esp32': 'a-esp32-latest.bin', 'esp32c3': 'a-esp32c3-latest.bin'},
        'b-latest': {'esp32': 'b-esp32-latest.bin'},
    }


def test_multiple_idf_versions():
    entries = gc.collect_entries(
        [record('examples/a', 'esp32', idf_version='release-v5_5'), record('examples/a', 'esp32', idf_version='latest')]
    )
    assert list(entries) == ['a-latest', 'a-release-v5_5']


def test_unsuccessful_and_unmerged_builds_are_ignored():
    entries = gc.collect_entries(
        [
            record('examples/a', 'esp32'),
            record('examples/a', 'esp32c3', status='build failed'),
            record('examples/a', 'esp32s3', status='skipped'),
            record('examples/b', 'esp32', merged=False),
        ]
    )
    assert entries == {'a-latest': {'esp32': 'a-esp32-latest.bin'}}


def test_no_apps_is_an_error():
    with pytest.raises(gc.ConfigError, match='No successfully built apps'):
        gc.collect_entries([record('examples/a', 'esp32', status='build failed')])
    with pytest.raises(gc.ConfigError, match='No successfully built apps'):
        gc.collect_entries([])


@pytest.mark.parametrize('targets', [('esp32', 'esp32'), ('esp32', 'esp32c3')])
@pytest.mark.parametrize('fmt', ['@n-@c-@v', '@f-@v'])
def test_same_directory_name_is_an_error(targets, fmt):
    records = [record('examples/a/blink', targets[0]), record('examples/b/blink', targets[1])]
    with pytest.raises(gc.ConfigError, match='same directory name "blink"'):
        gc.collect_entries(records, fmt)


def test_format_without_app_name_is_an_error_for_several_apps():
    with pytest.raises(gc.ConfigError, match='includes @n'):
        gc.collect_entries([record('examples/a', 'esp32'), record('examples/b', 'esp32')], '@v')


def test_format_without_config_placeholder_is_an_error_for_variants():
    with pytest.raises(gc.ConfigError, match='more than one binary for target esp32'):
        gc.collect_entries([record('examples/a', 'esp32'), record('examples/a', 'esp32', 'box')], '@n-@v')


def test_main_merges_parallel_files(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('GITHUB_REPOSITORY', 'Owner/repo')
    binaries = tmp_path / 'binaries'
    binaries.mkdir()
    jobs = [
        [record('examples/a', 'esp32'), record('examples/b', 'esp32')],
        [record('examples/a', 'esp32c3'), record('examples/c', 'esp32', 'box')],
    ]
    for i, records in enumerate(jobs, 1):
        (binaries / f'app_info_latest_{i}.json').write_text(''.join(json.dumps(r) + '\n' for r in records))
        for r in records:
            (binaries / r['merged_bin']).write_text('bin')

    assert gc.main(['--binaries-dir', str(binaries), '--remove-app-info']) == 0

    content = (binaries / 'config.toml').read_text()
    assert 'firmware_images_url = "https://Owner.github.io/repo/"' in content
    assert 'supported_apps = ["a-latest", "b-latest", "c-box-latest"]' in content
    assert 'chipsets = ["esp32", "esp32c3"]' in content
    assert not list(binaries.glob('app_info_*.json'))
    assert 'Generated' in capsys.readouterr().out


def test_main_fails_on_missing_binary(tmp_path, capsys):
    binaries = tmp_path / 'binaries'
    binaries.mkdir()
    (binaries / 'app_info_latest_1.json').write_text(json.dumps(record('examples/a', 'esp32')) + '\n')

    assert gc.main(['--binaries-dir', str(binaries), '--firmware-images-url', URL]) == 1
    assert 'Merged binary "a-esp32-latest.bin" not found' in capsys.readouterr().err
    assert not (binaries / 'config.toml').exists()


def test_main_fails_without_app_info(tmp_path, capsys):
    assert gc.main(['--binaries-dir', str(tmp_path), '--firmware-images-url', URL]) == 1
    assert 'No app info files found' in capsys.readouterr().err


def test_main_custom_url_gets_trailing_slash(tmp_path):
    (tmp_path / 'app_info_latest_1.json').write_text(json.dumps(record('examples/a', 'esp32')) + '\n')
    (tmp_path / 'a-esp32-latest.bin').write_text('bin')

    assert gc.main(['--binaries-dir', str(tmp_path), '--firmware-images-url', 'https://example.com/fw']) == 0
    assert 'firmware_images_url = "https://example.com/fw/"' in (tmp_path / 'config.toml').read_text()
