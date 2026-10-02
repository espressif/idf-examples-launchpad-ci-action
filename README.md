# idf-examples-launchpad-ci-action

This GitHub Action builds ESP-IDF examples, merges the binaries of every build into a single flashable image, and generates the `config.toml` for [ESP Launchpad](https://espressif.github.io/esp-launchpad/). Together with the example workflows below, the result is published on GitHub Pages so anyone can flash your examples from the browser.

## How it works

1. [idf-build-apps](https://docs.espressif.com/projects/idf-build-apps) finds and builds the apps described by your configuration file.
2. Right after each successful build, a custom idf-build-apps build system (`launchpad/launchpad_app.py`) merges the binaries with `esptool merge_bin` into `binaries/<app>[-<config>]-<target>-<idf_version>.bin`.
3. `launchpad/generate_config.py` writes `binaries/config.toml` listing all merged binaries.

## Requirements

- An `espressif/idf` Docker image of **ESP-IDF v5.2 or newer**. idf-build-apps 3.x needs Python 3.10+.
- For older ESP-IDF versions, use `espressif/idf-examples-launchpad-ci-action@v1`.

# Usage

## Step 1: Set up GitHub Pages

In your repository go to **Settings → Pages** and set **Source** to **GitHub Actions**.

## Step 2: Configuration file

Create a `.idf_build_apps.toml` configuration file. By default it is expected in the root of the repository; use the `config_file` input for a different location. See the [idf-build-apps documentation](https://docs.espressif.com/projects/idf-build-apps/en/latest/references/config_file.html) for all options.

```toml
paths = ["examples"]   # Paths to search for buildable projects
target = "all"         # esp32, esp32s3, ... or all
recursive = true       # Search for buildable projects recursively

# Optional: build variants of the apps, see "Config variants" below
config_rules = ["sdkconfig.ci.*="]
```

The action sets the `collect_app_info` and `build_system` options itself. Any values for them in your configuration file are overridden. You can set `build_dir` to any value.

### Config variants

With `config_rules` (deprecated name: `config`), every matching sdkconfig file creates a separate build. For example, `config_rules = ["sdkconfig.ci.*="]` builds an app containing `sdkconfig.ci.box` and `sdkconfig.ci.lcd` twice, as the configs `box` and `lcd`.

Each config becomes a separate app in ESP Launchpad:

| Build                        | Launchpad app            | Binary                             |
|------------------------------|--------------------------|------------------------------------|
| `blink`, no config, esp32    | `blink-latest`           | `blink-esp32-latest.bin`           |
| `blink`, no config, esp32c3  | `blink-latest`           | `blink-esp32c3-latest.bin`         |
| `blink`, config `box`, esp32s3 | `blink-box-latest`     | `blink-box-esp32s3-latest.bin`     |

The targets of an app show up as the selectable chipsets in ESP Launchpad. Use `app_name_format` to change the app names.

## Inputs

| Input                    | Default                    | Description |
|--------------------------|----------------------------|-------------|
| `idf_version`            | `"latest"`                 | IDF version label used in app and binary names, usually the tag of the `espressif/idf` image. Dots are replaced by underscores. |
| `config_file`            | `"./.idf_build_apps.toml"` | Path to the idf-build-apps configuration file. |
| `parallel_count`         | `1`                        | Number of parallel build jobs. |
| `parallel_index`         | `1`                        | Index of this parallel build job (1-based). |
| `output_dir`             | `"binaries"`               | Directory for the merged binaries and `config.toml`. |
| `generate_config`        | `true`                     | Generate `config.toml`. Set to `false` when you build in several jobs and merge the results with the `generate-config` action. |
| `app_name_format`        | `"@n-@c-@v"`               | Format of the app names in `config.toml`. Placeholders: `@n` app name, `@c` config name, `@v` IDF version, `@f` app path with `/` replaced by `_`. When an app has no config, `@c` is removed together with the character before it (like `@w` in idf-build-apps), so `"@n-@c (IDF @v)"` gives `blink-box (IDF latest)` or `blink (IDF latest)`. |
| `firmware_images_url`    | `https://<owner>.github.io/<repo>/` | URL the binaries are served from. |
| `idf_build_apps_version` | `">=3.0,<4"`               | Version (e.g. `3.0.2`) or version specifier of idf-build-apps to install. |

## Outputs

| Output       | Description |
|--------------|-------------|
| `output_dir` | Directory with the merged binaries and `config.toml`. |

## Step 3: Create a workflow

### Basic workflow

```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    container: espressif/idf:release-v5.5
    steps:
      - name: Checkout repo
        uses: actions/checkout@v6
        with:
          submodules: 'recursive'

      - name: Build examples and generate config.toml
        uses: espressif/idf-examples-launchpad-ci-action@v2
        with:
          idf_version: release-v5.5

      - name: Upload Artifact
        uses: actions/upload-artifact@v7
        with:
          name: built_files
          path: binaries/

  deploy:
    needs: build

    permissions:
      pages: write
      id-token: write

    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}

    runs-on: ubuntu-latest
    steps:
      - name: Download built files
        uses: actions/download-artifact@v8
        with:
          name: built_files
          path: binaries/

      - name: Upload built files to GitHub Pages
        uses: actions/upload-pages-artifact@v4
        with:
          path: binaries/

      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
```

### Workflow with several jobs (parallel builds, several IDF versions)

When the builds are split across several jobs, each job only sees its own binaries. In that case:

1. Set `generate_config: false` in the build jobs.
2. Upload each job's output under a unique artifact name.
3. Run the `generate-config` action once in the deploy job, after downloading all artifacts into one directory.

```yaml
jobs:
  build:
    strategy:
      matrix:
        idf_ver: ["release-v5.5", "latest"]
        parallel_index: [1, 2]
    runs-on: ubuntu-latest
    container: espressif/idf:${{ matrix.idf_ver }}
    steps:
      - name: Checkout repo
        uses: actions/checkout@v6
        with:
          submodules: 'recursive'

      - name: Build examples
        uses: espressif/idf-examples-launchpad-ci-action@v2
        with:
          idf_version: ${{ matrix.idf_ver }}
          parallel_count: 2
          parallel_index: ${{ matrix.parallel_index }}
          generate_config: false

      - name: Upload Artifact
        uses: actions/upload-artifact@v7
        with:
          name: binaries-${{ matrix.idf_ver }}-${{ matrix.parallel_index }}
          path: binaries/

  deploy:
    needs: build

    permissions:
      pages: write
      id-token: write

    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}

    runs-on: ubuntu-latest
    steps:
      - name: Download built files
        uses: actions/download-artifact@v8
        with:
          pattern: binaries-*
          path: binaries/
          merge-multiple: true

      - name: Generate config.toml
        uses: espressif/idf-examples-launchpad-ci-action/generate-config@v2

      - name: Upload built files to GitHub Pages
        uses: actions/upload-pages-artifact@v4
        with:
          path: binaries/

      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
```

The `generate-config` action only needs `python3`. It accepts the inputs `binaries_dir` (default `binaries`), `app_name_format`, and `firmware_images_url`, which work like the inputs of the main action.

#### Notes

- The merged binaries and `config.toml` are written to `./binaries` (see `output_dir`).
- The build fails when an app fails to build, when its binaries cannot be merged, or when no app was built at all.
- Uploading the binaries to GitHub Pages is not mandatory, but it is recommended. ESP Launchpad runs on the `github.io` domain, so other storage has to serve the binaries and `config.toml` with CORS headers that allow ESP Launchpad.

## Step 4: Flash your binaries with ESP Launchpad

Open ESP Launchpad with the `flashConfigURL` query parameter pointing to your `config.toml`:

`https://espressif.github.io/esp-launchpad/?flashConfigURL=https://{owner}.github.io/{repository_name}/config.toml`

# Migrating from v1

- **ESP-IDF v5.2 or newer is required** (Python 3.10+ for idf-build-apps 3.x). Keep using `@v1` for older ESP-IDF versions.
- **idf-build-apps 3.x** is installed. Deprecated configuration names such as `config`, `manifest_file`, and `ignore_warning_file` still work.
- `install.sh --enable-ci` is no longer run. Install any extra Python packages your build needs in a step before the action.
- `IDF_EXTRA_ACTIONS_PATH` is no longer set to `$GITHUB_WORKSPACE/examples`. If you need it, set it in the `env` of the action step.
- The `IDF_VERSION` environment variable is no longer exported to the following steps.
- `--build-dir` is no longer forced to `build_@t_@w`, so the `build_dir` from your configuration file is used.
- The app and binary names are unchanged. `config.toml` is now complete:
  - Apps that have both builds without a config and config variants keep all of them.
  - A config variant built for several targets lists all of its targets.
- When building in several jobs, use the `generate-config` action as shown above.
