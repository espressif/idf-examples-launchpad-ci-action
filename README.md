# idf-examples-launchpad-ci-action
This Github Action builds merged binaries of ESP examples and if you use example worklow, uploads them to the Github pages for ESP Launchpad.

# Usage

## Step 1: Setup Github Pages in your repository
You will have to setup Github Pages in your repository. Switch the Github pages to the branch you are running the workflow on. You can do this in the settings of your repository.

## Step 2: Configuration file
It is important to have `.idf_build_apps.toml` configuration file in the root directory of your repository. This file is used to configure the build process. 
For further information, please refer to the [documentation](https://docs.espressif.com/projects/idf-build-apps/en/latest/config_file.html).

Example configuration file:
```toml
paths = "examples" # Paths to search for buildable projects ["examples", "components"]
target = "all" # esp32, esp32s2, esp32c3, esp32s3, all...
recursive = true # Search for buildable projects recursively on the paths

# Configuration file for the build process 
config = "sdkconfig.defaults"
```
**Do not overwrite** `collect-app-info` **and** `build-dir` **options!** They are used by the `idf-build-apps` to collect information about the build and to find the build directory. 

## Inputs

### `idf_version`
The version of the ESP-IDF to use for building the binaries.
**Default:** `"latest"`

### `parallel_count`
The number of parallel builds.
**Default:** `1`

### `parallel_index`
The index of the parallel build.
**Default:** `1`

## Step 3: Create a workflow with ESP-IDF docker container. 
### Example usage

Basic workflow:

```yaml
jobs:

  build:
    strategy:
      matrix:
        idf_ver: ["latest"]
    runs-on: ubuntu-latest
    container: espressif/idf:${{ matrix.idf_ver }}
    steps:
      - name: Checkout repo
        uses: actions/checkout@v3
        with:
          submodules: 'recursive'

      - name: Action for Building and Uploading Binaries
        uses: espressif/idf-examples-launchpad-ci-action@v1.0.1
        with:
          idf_version: ${{ matrix.idf_ver }}

      - name: Upload Artifact
        uses: actions/upload-artifact@v3
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
        uses: actions/download-artifact@v3
        with:
          name: built_files
          path: binaries/

      - name: Upload built files to gh pages
        uses: actions/upload-pages-artifact@v2
        with:
          path: binaries/

      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v2
```

Workflow with parallel builds:

```yaml
jobs:
  build-and-upload-binaries:
    strategy:
      matrix:
        include:
          - idf_ver: "latest"
            parallel_count: 2
            parallel_index: 1
          - idf_ver: "release-v4.4"
            parallel_count: 2
            parallel_index: 2
    runs-on: ubuntu-latest
    container: espressif/idf:${{ matrix.idf_ver }}
    steps:
      - name: Checkout repo
        uses: actions/checkout@v3
        with:
          submodules: 'recursive'

      - name: Action for Building and Uploading Binaries
        uses: espressif/idf-examples-launchpad-ci-action@v1.0.1
        with:
          idf_version: ${{ matrix.idf_ver }}
          parallel_count: ${{ matrix.parallel_count }}
          parallel_index: ${{ matrix.parallel_index }}

      - name: Upload Artifact
        uses: actions/upload-artifact@v3
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
        uses: actions/download-artifact@v3
        with:
          name: built_files
          path: binaries/

      - name: Upload built files to gh pages
        uses: actions/upload-pages-artifact@v2
        with:
          path: binaries/

      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v2
```

#### Note:
- The output folder of merged binaries and config.toml is `./binaries`
- It's not mandatory to upload binaries to the Github Pages, although it is recommended, as the ESP-Launchpad is running under `github.io` domain and it would have problem with CORS, so if you want to use other way of storing your binaries and config.toml you will have to provide CORS headers for the ESP-Launchpad from your storage of choice.

## Step 4: Flash your binaries with ESP-Launchpad
Flashing your binaries using the ESP-Launchpad can be achieved by including a `flashConfigURL` query in the URL. The format for the URL is as follows: `https://espressif.github.io/esp-launchpad/?flashConfigURL=https://{owner}.github.io/{repository_name}/config.toml`.
