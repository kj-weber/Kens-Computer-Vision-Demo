"""
core.py -- zero-configuration environment bootstrap.

This is the part of the demo that lets a recruiter, a hiring manager, or a
curious stranger run ``python main.py`` on a stock Windows or macOS machine
and see a live camera pipeline with no manual setup:

1. Runs under whatever Python the visitor already has (3.9 or newer).
2. Creates a private virtual environment *inside this folder* (``.venv_ken``).
3. Installs the pinned dependencies from ``requirements.txt`` into it, but only
   when the requirements file has changed since the last successful install,
   so repeat launches are instant and work offline.
4. Re-launches ``main.py`` under that interpreter.

Nothing outside this folder is touched: no global ``pip install``, no system
Python upgrade, no shell profile edits. Delete ``.venv_ken`` to uninstall.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
VENV_DIR = PROJECT_DIR / ".venv_ken"
REQUIREMENTS = PROJECT_DIR / "requirements.txt"
STAMP = VENV_DIR / "requirements.sha256"
BOOTSTRAP_FLAG = "KENS_DEMO_BOOTSTRAPPED"
MIN_PYTHON = (3, 9)
PIP_TIMEOUT_S = 20   # fail fast when offline instead of hanging for minutes


def log(msg: str) -> None:
    """
    Prints a bootstrap message with the [SETUP] tag, so setup chatter is distinguishable from demo output.
    :param msg: str : The message to print.
    :return: Nothing.
    """
    print(f"[SETUP] {msg}", flush=True)


def venv_python() -> Path:
    """
    Locates the interpreter inside the private virtual environment, which lives in a different sub-folder per OS.
    :return: Path : The venv python executable (may not exist yet).
    """
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def running_inside_venv() -> bool:
    """
    Checks the flag the bootstrap sets when it re-launches main.py, so the child does not bootstrap again.
    :return: bool : True when this interpreter was launched by the bootstrap and already lives in the venv.
    """
    return os.environ.get(BOOTSTRAP_FLAG) == "1"


def requirements_hash() -> str:
    """
    Hashes requirements.txt so a change to the pins triggers exactly one reinstall.
    :return: str : sha256 hex digest of requirements.txt.
    """
    return hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()


def read_stamp() -> str | None:
    """
    Reads the hash stamped into the venv by the last successful install.
    :return: str/None : The stamped hash, or None if dependencies were never installed.
    """
    try:
        return STAMP.read_text().strip()
    except OSError:
        return None


def create_venv() -> None:
    """
    Creates the private virtual environment using the visitor's own python, and exits with a readable message if
    that is impossible.
    :return: Nothing.
    """
    log(f"Creating a private virtual environment at {VENV_DIR.name}/ ...")
    result = subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)])
    if result.returncode != 0 or not venv_python().exists():
        sys.exit(
            "[SETUP] ERROR: could not create a virtual environment. "
            "On Debian/Ubuntu install 'python3-venv'; on Windows/macOS reinstall "
            "Python from python.org and make sure 'python -m venv' works."
        )


def install_requirements(py: Path) -> bool:
    """
    Installs the pinned dependencies into the private environment, failing fast when offline, and stamps the
    requirements hash on success.
    :param py: Path : The venv interpreter.
    :return: bool : True on success, False if pip failed (most likely no internet).
    """
    log("Installing pinned dependencies into the private environment (first run only) ...")
    cmd = [
        str(py), "-m", "pip", "install",
        "--disable-pip-version-check",
        "--timeout", str(PIP_TIMEOUT_S),
        "--retries", "1",
        "-r", str(REQUIREMENTS),
    ]
    result = subprocess.run(cmd)
    if result.returncode == 0:
        STAMP.write_text(requirements_hash())
        return True
    return False


def ensure_environment(argv: list[str]) -> None:
    """
    The zero-configuration entry point. Returns normally only when already running inside the project venv;
    otherwise creates the venv, installs dependencies if the pins changed, re-launches main.py inside it, and exits
    with the child's return code.
    :param argv: list : Command line arguments to forward to the re-launched demo.
    :return: Nothing, or never returns (sys.exit) when bootstrapping.
    """
    if running_inside_venv():
        return

    if sys.version_info < MIN_PYTHON:
        sys.exit(f"[SETUP] ERROR: Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ is required, "
                 f"you are running {sys.version.split()[0]}.")

    log(f"Kenneth's Computer Vision Demo -- bootstrapping on {sys.platform} "
        f"with Python {sys.version.split()[0]}")

    py = venv_python()
    if not py.exists():
        create_venv()

    if requirements_hash() != read_stamp():
        if not install_requirements(py):
            if read_stamp() is None:
                sys.exit(
                    "[SETUP] ERROR: dependency install failed. Connect to the internet "
                    "once so the demo can download OpenCV and NumPy, then re-run."
                )
            log("WARNING: dependency update failed (offline?). Running with the "
                "previously installed versions.")
    else:
        log("Dependencies already installed, skipping download.")

    env = dict(os.environ)
    env[BOOTSTRAP_FLAG] = "1"
    env.setdefault("OPENCV_LOG_LEVEL", "ERROR")   # silence camera-probe chatter
    log("Launching the demo inside the private environment ...")
    try:
        code = subprocess.call([str(py), str(PROJECT_DIR / "main.py"), *argv], env=env)
    except KeyboardInterrupt:
        code = 130
    sys.exit(code)
