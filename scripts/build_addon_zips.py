#!/usr/bin/env python3
"""Build installable Blender add-on zips for each add-on in this repository.

Blender's **Install…** button expects a zip whose top level contains the
add-on package folder. This script zips each add-on folder into ``dist/``:

    python scripts/build_addon_zips.py

producing ``dist/hve_tools.zip``, ``dist/motion_data_tools.zip``, and
``dist/point_cloud_tools.zip``.
"""

import os
import zipfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(REPO_ROOT, "dist")

ADDONS = (
    "hve_tools",
    "motion_data_tools",
    "point_cloud_tools",
)

EXCLUDED_DIRS = {"__pycache__"}
EXCLUDED_SUFFIXES = (".pyc", ".pyo")


def build_zip(addon):
    src_dir = os.path.join(REPO_ROOT, addon)
    zip_path = os.path.join(DIST, f"{addon}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(src_dir):
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
            for name in sorted(files):
                if name.endswith(EXCLUDED_SUFFIXES):
                    continue
                full = os.path.join(root, name)
                arcname = os.path.relpath(full, REPO_ROOT)
                zf.write(full, arcname)
    return zip_path


def main():
    os.makedirs(DIST, exist_ok=True)
    for addon in ADDONS:
        zip_path = build_zip(addon)
        print(f"Built {os.path.relpath(zip_path, REPO_ROOT)}")


if __name__ == "__main__":
    main()
