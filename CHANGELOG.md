# Unreleased

# Release v2.0.0

## Breaking changes

- Bumped idf-build-apps to 3.x, which requires Python 3.10+ (ESP-IDF v5.2 or newer Docker images). Use v1 for older ESP-IDF versions.
- `install.sh --enable-ci` is no longer run, which avoids Python dependency conflicts with ESP-IDF ([#11](https://github.com/espressif/idf-examples-launchpad-ci-action/issues/11))
- `IDF_EXTRA_ACTIONS_PATH` is no longer set to `$GITHUB_WORKSPACE/examples`, and `IDF_VERSION` is no longer exported to the following steps
- `--build-dir` is no longer forced, so the `build_dir` from the idf-build-apps configuration file is used
- Removed `generateFiles.py`

## Features

- Binaries are merged right after each build by a custom idf-build-apps build system (`launchpad/launchpad_app.py`)
- New `generate-config` action that generates `config.toml` from the results of several build jobs (parallel builds, several IDF versions)
- New inputs `output_dir`, `generate_config`, `app_name_format` ([#3](https://github.com/espressif/idf-examples-launchpad-ci-action/issues/3)), `firmware_images_url`, and `idf_build_apps_version`
- New output `output_dir`

## Fixes

- Apps with both builds without a config and config variants no longer lose builds in `config.toml`
- Config variants built for several targets list all targets in `config.toml`
- Apps whose builds are not listed next to each other are no longer duplicated in `config.toml`
- The action fails with a clear error when the configuration file is missing or no app was built ([#7](https://github.com/espressif/idf-examples-launchpad-ci-action/issues/7))
- The action fails when merging binaries fails, or when two apps would get the same name
- Action inputs are passed through environment variables instead of being inserted into the scripts

## Other

- Documented config variants, which replace the term "kit" ([#4](https://github.com/espressif/idf-examples-launchpad-ci-action/issues/4))
- Added unit tests and a self-test workflow

# Release v1.0.4 (17.3.2026)

- Bumped idf-build-apps version

# Release v1.0.3 (22.7.2025)

- Fixed a regex for the extraction of config name

# Release v1.0.2 (20.5.2025)

- Added an option to specify path to the idf-build-apps configuration file
- Fixed a bug where the examples were not being built to indepentent directories for multiple targets
- Updated idf-build-apps version to 2.10.1

# Release v1.0.1 (22.1.2024)

- Fixed a bug where the kit regex was not checked properly
- Fix version of idf-build-apps

# Release v1.0 (31.07.2023)

- Initial release
