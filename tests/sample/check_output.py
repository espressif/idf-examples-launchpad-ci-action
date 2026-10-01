#!/usr/bin/env python3
"""Checks the output of the action for the sample project. Used by .github/workflows/test.yml."""

import argparse
import os
import sys
import tomllib

APP = 'hello_launchpad'
TARGETS = ['esp32', 'esp32c3']


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binaries-dir', default='binaries')
    parser.add_argument('--idf-version', required=True)
    args = parser.parse_args()

    version = args.idf_version.replace('.', '_')
    with open(os.path.join(args.binaries_dir, 'config.toml'), 'rb') as fr:
        config = tomllib.load(fr)

    errors = []
    expected_apps = [f'{APP}-{version}', f'{APP}-variant-{version}']
    if config.get('supported_apps') != expected_apps:
        errors.append(f'supported_apps is {config.get("supported_apps")}, expected {expected_apps}')

    repository = os.environ.get('GITHUB_REPOSITORY', '')
    if repository:
        owner, repo = repository.split('/', 1)
        expected_url = f'https://{owner}.github.io/{repo}/'
        if config.get('firmware_images_url') != expected_url:
            errors.append(f'firmware_images_url is {config.get("firmware_images_url")}, expected {expected_url}')

    for app, config_name in zip(expected_apps, ['', 'variant']):
        entry = config.get(app, {})
        if entry.get('chipsets') != TARGETS:
            errors.append(f'{app}: chipsets is {entry.get("chipsets")}, expected {TARGETS}')
        for target in TARGETS:
            expected_bin = '-'.join(p for p in (APP, config_name, target, version) if p) + '.bin'
            image = entry.get('image', {}).get(target)
            if image != expected_bin:
                errors.append(f'{app}: image.{target} is {image}, expected {expected_bin}')
                continue
            path = os.path.join(args.binaries_dir, image)
            if not os.path.isfile(path) or os.path.getsize(path) == 0:
                errors.append(f'{app}: {path} is missing or empty')

    leftovers = [f for f in os.listdir(args.binaries_dir) if f.startswith('app_info_')]
    if leftovers:
        errors.append(f'app info files were not removed: {leftovers}')

    if errors:
        print('\n'.join(f'::error::{e}' for e in errors))
        return 1

    print(f'Output in {args.binaries_dir} is valid:')
    for f in sorted(os.listdir(args.binaries_dir)):
        print(f'  {f}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
