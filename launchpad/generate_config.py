#!/usr/bin/env python3
"""
Generate the ESP Launchpad config.toml from the app info files written by idf-build-apps
(`--collect-app-info`) when building with the LaunchpadApp build system.

Only the Python standard library is used, so this script can run outside of the ESP-IDF environment,
e.g. in a deploy job that merges the results of several parallel build jobs.
"""

import argparse
import glob
import json
import os
import re
import sys
import typing as t

SUCCESS_STATUS = 'build success'
DEFAULT_APP_NAME_FORMAT = '@n-@c-@v'
APP_INFO_FILE_PATTERN = 'app_info_*.json'
BARE_KEY_RE = re.compile(r'^[A-Za-z0-9_-]+$')
# top-level keys of config.toml, apps must not use these names
RESERVED_NAMES = {'esp_toml_version', 'firmware_images_url', 'supported_apps'}


class ConfigError(Exception):
    pass


def format_app_name(fmt: str, name: str, config_name: str, idf_version: str, app_dir: str) -> str:
    """
    Expand the placeholders in `fmt`:
        @n app name, @c config name, @v IDF version, @f app path with "/" replaced by "_".

    Like the @w placeholder of idf-build-apps, an empty @c is removed together with
    the character before it, e.g. "@n-@c-@v" becomes "@n-@v".
    """
    if not config_name and '@c' in fmt:
        pos = fmt.find('@c')
        fmt = fmt[: max(0, pos - 1)] + fmt[pos + 2 :]

    values = {'@n': name, '@c': config_name, '@v': idf_version, '@f': app_dir.replace('/', '_')}
    # one pass, so an "@" inside a value is not expanded again
    return re.sub('@[ncvf]', lambda m: values[m.group()], fmt)


def find_app_info_files(patterns: t.Sequence[str]) -> t.List[str]:
    files: t.List[str] = []
    for pattern in patterns:
        for f in sorted(glob.glob(pattern)):
            if os.path.isfile(f) and f not in files:
                files.append(f)
    if not files:
        raise ConfigError(f'No app info files found matching: {", ".join(patterns)}')
    return files


def load_records(files: t.Sequence[str]) -> t.List[t.Dict[str, t.Any]]:
    records = []
    for f in files:
        with open(f) as fr:
            for lineno, line in enumerate(fr, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as e:
                    raise ConfigError(f'{f}:{lineno}: invalid JSON: {e}') from e
    return records


def collect_entries(
    records: t.Sequence[t.Dict[str, t.Any]],
    app_name_format: str = DEFAULT_APP_NAME_FORMAT,
    binaries_dir: t.Optional[str] = None,
) -> t.Dict[str, t.Dict[str, str]]:
    """Return {launchpad app name: {target: merged binary file name}}, in a deterministic order."""
    apps = [r for r in records if r.get('build_status') == SUCCESS_STATUS and r.get('merged_bin')]
    if not apps:
        raise ConfigError(
            'No successfully built apps with merged binaries were found. '
            'Check that the idf-build-apps configuration file finds your apps and that they build for at least one target.'
        )

    def _key(r: t.Dict[str, t.Any]) -> t.Tuple[str, ...]:
        return (
            os.path.normpath(r['app_dir']),
            r['target'],
            r.get('config_name') or '',
            r.get('launchpad_idf_version') or '',
        )

    entries: t.Dict[str, t.Dict[str, str]] = {}
    entry_owner: t.Dict[str, str] = {}
    name_owner: t.Dict[str, str] = {}

    for r in sorted(apps, key=_key):
        app_dir, target, config_name, idf_version = _key(r)
        merged_bin = r['merged_bin']
        name = r.get('launchpad_app_name') or os.path.basename(app_dir)

        # the binary file names only contain the app name, so it must be unique
        owner = name_owner.setdefault(name, app_dir)
        if owner != app_dir:
            raise ConfigError(
                f'Apps "{owner}" and "{app_dir}" have the same directory name "{name}". '
                'Apps must have unique directory names, because the binaries are named after them.'
            )

        if binaries_dir is not None and not os.path.isfile(os.path.join(binaries_dir, merged_bin)):
            raise ConfigError(f'Merged binary "{merged_bin}" not found in "{binaries_dir}"')

        entry_name = format_app_name(app_name_format, name, config_name, idf_version, app_dir)
        if not entry_name:
            raise ConfigError(f'app_name_format "{app_name_format}" produced an empty name for "{app_dir}"')
        if entry_name in RESERVED_NAMES:
            raise ConfigError(
                f'App name "{entry_name}" of "{app_dir}" is a reserved key in config.toml. '
                'Use an app_name_format that includes @v.'
            )

        owner = entry_owner.setdefault(entry_name, app_dir)
        if owner != app_dir:
            raise ConfigError(
                f'Apps "{owner}" and "{app_dir}" are both named "{entry_name}". '
                'Use an app_name_format that includes @n.'
            )

        images = entries.setdefault(entry_name, {})
        if images.get(target, merged_bin) != merged_bin:
            raise ConfigError(
                f'App "{entry_name}" has more than one binary for target {target} '
                f'("{images[target]}" and "{merged_bin}"). Include @c and @v in app_name_format.'
            )
        images[target] = merged_bin

    return entries


def _toml_string(value: str) -> str:
    # JSON basic strings without ASCII escaping are valid TOML basic strings
    return json.dumps(value, ensure_ascii=False)


def _toml_key(key: str) -> str:
    return key if BARE_KEY_RE.match(key) else _toml_string(key)


def render_config_toml(entries: t.Dict[str, t.Dict[str, str]], firmware_images_url: str) -> str:
    lines = [
        'esp_toml_version = 1.0',
        f'firmware_images_url = {_toml_string(firmware_images_url)}',
        f'supported_apps = [{", ".join(_toml_string(name) for name in entries)}]',
    ]
    for name, images in entries.items():
        lines.append('')
        lines.append(f'[{_toml_key(name)}]')
        lines.append(f'chipsets = [{", ".join(_toml_string(target) for target in images)}]')
        for target, merged_bin in images.items():
            lines.append(f'image.{_toml_key(target)} = {_toml_string(merged_bin)}')
        lines.append('android_app_url = ""')
        lines.append('ios_app_url = ""')
    return '\n'.join(lines) + '\n'


def default_firmware_images_url() -> str:
    repository = os.environ.get('GITHUB_REPOSITORY', '')
    if '/' not in repository:
        raise ConfigError('GITHUB_REPOSITORY is not set, please pass --firmware-images-url')
    owner, repo = repository.split('/', 1)
    return f'https://{owner}.github.io/{repo}/'


def main(argv: t.Optional[t.Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        '--binaries-dir',
        default='binaries',
        help='Directory with the merged binaries. config.toml is written here. (default: %(default)s)',
    )
    parser.add_argument(
        '--app-info',
        nargs='+',
        help=f'App info files or glob patterns (default: <binaries-dir>/{APP_INFO_FILE_PATTERN})',
    )
    parser.add_argument(
        '--firmware-images-url',
        help='URL the binaries are served from (default: https://<owner>.github.io/<repo>/)',
    )
    parser.add_argument(
        '--app-name-format',
        default=DEFAULT_APP_NAME_FORMAT,
        help='Format of the app names in config.toml. Placeholders: @n app name, @c config name, '
        '@v IDF version, @f app path. (default: %(default)s)',
    )
    parser.add_argument(
        '--remove-app-info',
        action='store_true',
        help='Remove the app info files after config.toml was generated',
    )
    args = parser.parse_args(argv)

    try:
        files = find_app_info_files(args.app_info or [os.path.join(args.binaries_dir, APP_INFO_FILE_PATTERN)])
        entries = collect_entries(load_records(files), args.app_name_format or DEFAULT_APP_NAME_FORMAT, args.binaries_dir)
        url = args.firmware_images_url or default_firmware_images_url()
        if not url.endswith('/'):
            url += '/'
        content = render_config_toml(entries, url)
    except ConfigError as e:
        prefix = '::error::' if os.environ.get('GITHUB_ACTIONS') == 'true' else 'error: '
        print(f'{prefix}{e}', file=sys.stderr)
        return 1

    os.makedirs(args.binaries_dir, exist_ok=True)
    output = os.path.join(args.binaries_dir, 'config.toml')
    with open(output, 'w') as fw:
        fw.write(content)

    if args.remove_app_info:
        for f in files:
            os.remove(f)

    print(f'Generated {output} with {len(entries)} app(s):')
    for name, images in entries.items():
        print(f'  {name}: {", ".join(images)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
