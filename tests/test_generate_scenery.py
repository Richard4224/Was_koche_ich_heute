"""Tests for tools/generate_scenery.py: the script runs, and its SVGs are the ones in the repository.

The script writes into the project it lies in, so it runs here on a copy of itself in an empty folder.
"""

import filecmp
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ElementTree

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCENERY = [
    "static/scenery/firs-far.svg",
    "static/scenery/firs-mid.svg",
    "static/scenery/fir-edge.svg",
    "static/scenery/grass.svg",
    "templates/scenery/hut.svg",
    "templates/scenery/horizon.svg",
]


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    """Run the script on a copy of itself and return the folder it wrote to."""
    folder = tmp_path_factory.mktemp("scenery")
    for directory in ("tools", "static/scenery", "templates/scenery"):
        (folder / directory).mkdir(parents=True)
    shutil.copy(os.path.join(ROOT, "tools", "generate_scenery.py"), folder / "tools")
    subprocess.run([sys.executable, str(folder / "tools" / "generate_scenery.py")], check=True, capture_output=True)
    return folder


@pytest.mark.parametrize("path", SCENERY)
def test_scenery_in_the_repository_is_what_the_script_makes(generated, path):
    """Same seeds, same trees: if this fails, the SVG was edited by hand or the script wasn't run after a change."""
    assert filecmp.cmp(generated / path, os.path.join(ROOT, path), shallow=False)


@pytest.mark.parametrize("path", SCENERY)
def test_scenery_is_well_formed_svg(generated, path):
    root = ElementTree.parse(generated / path).getroot()
    assert root.tag == "{http://www.w3.org/2000/svg}svg" or root.tag == "svg"
    assert len(root) > 0


@pytest.mark.parametrize("path, width", [
    ("static/scenery/firs-far.svg", "4125"),
    ("static/scenery/firs-mid.svg", "3300"),
    ("static/scenery/fir-edge.svg", "600"),
])
def test_fir_rows_have_their_tile_width(generated, path, width):
    assert ElementTree.parse(generated / path).getroot().get("width") == width
