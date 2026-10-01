import os
import sys
import tempfile
import textwrap

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAUNCHPAD_DIR = os.path.join(REPO_ROOT, 'launchpad')


def _create_fake_idf() -> str:
    """Minimal ESP-IDF tree, enough for idf_build_apps to be imported without a real ESP-IDF."""
    idf_path = tempfile.mkdtemp(prefix='fake_idf_')
    os.makedirs(os.path.join(idf_path, 'tools', 'cmake'))
    os.makedirs(os.path.join(idf_path, 'tools', 'idf_py_actions'))
    with open(os.path.join(idf_path, 'tools', 'cmake', 'version.cmake'), 'w') as fw:
        fw.write('set(IDF_VERSION_MAJOR 5)\nset(IDF_VERSION_MINOR 5)\nset(IDF_VERSION_PATCH 1)\n')
    with open(os.path.join(idf_path, 'tools', 'idf_py_actions', 'constants.py'), 'w') as fw:
        fw.write("SUPPORTED_TARGETS = ['esp32', 'esp32c3', 'esp32s3']\nPREVIEW_TARGETS = []\n")
    return idf_path


if not os.environ.get('IDF_PATH'):
    os.environ['IDF_PATH'] = _create_fake_idf()

sys.path.insert(0, LAUNCHPAD_DIR)


@pytest.fixture
def fake_esptool(tmp_path, monkeypatch):
    """A fake `esptool` package on PYTHONPATH that records its argv and writes the output file."""
    pkg = tmp_path / 'fake_esptool' / 'esptool'
    pkg.mkdir(parents=True)
    (pkg / '__init__.py').write_text('')
    (pkg / '__main__.py').write_text(
        textwrap.dedent(
            """
            import json, os, sys
            args = sys.argv[1:]
            with open(os.environ['FAKE_ESPTOOL_LOG'], 'a') as fw:
                fw.write(json.dumps({'args': args, 'cwd': os.getcwd()}) + '\\n')
            if os.environ.get('FAKE_ESPTOOL_FAIL'):
                print('A fatal error occurred: fake failure', file=sys.stderr)
                sys.exit(2)
            with open(args[args.index('-o') + 1], 'w') as fw:
                fw.write('merged')
            """
        )
    )
    log = tmp_path / 'esptool_calls.jsonl'
    monkeypatch.setenv('FAKE_ESPTOOL_LOG', str(log))
    monkeypatch.setenv('PYTHONPATH', os.pathsep.join([str(pkg.parent), os.environ.get('PYTHONPATH', '')]))
    return log
