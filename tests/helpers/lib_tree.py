"""Copy easydeploy-lib and product shell wrappers into isolated test trees."""

from __future__ import annotations

import shutil
import stat
from pathlib import Path

EASYDEPLOY_INIT = Path("lib") / "init.sh"

PRODUCT_LIB_SCRIPTS = (
    "scripts/lib.sh",
    "scripts/lib_matrix.sh",
    "scripts/deps_config.sh",
)


def easydeploy_lib_dir(repo_root: Path) -> Path:
    return repo_root / "easydeploy-lib"


def easydeploy_lib_available(repo_root: Path) -> bool:
    return (easydeploy_lib_dir(repo_root) / EASYDEPLOY_INIT).is_file()


def require_easydeploy_lib(repo_root: Path) -> Path:
    lib_dir = easydeploy_lib_dir(repo_root)
    if not (lib_dir / EASYDEPLOY_INIT).is_file():
        raise FileNotFoundError(
            "easydeploy-lib submodule is not checked out. "
            "Run: git submodule update --init --recursive"
        )
    return lib_dir


def copy_easydeploy_lib(repo_root: Path, dest_root: Path) -> None:
    src = require_easydeploy_lib(repo_root)
    dest = dest_root / "easydeploy-lib"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)


def copy_executable_script(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(src.read_text())
    dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def stage_product_lib_scripts(repo_root: Path, dest_root: Path) -> None:
    """easydeploy-lib submodule + thin Matrix lib wrappers."""
    copy_easydeploy_lib(repo_root, dest_root)
    for rel in PRODUCT_LIB_SCRIPTS:
        src = repo_root / rel
        dest = dest_root / rel
        copy_executable_script(src, dest)
