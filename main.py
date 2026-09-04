"""
main.py -- the only file a visitor needs to run.

    python main.py                  # auto-detects a webcam, falls back to a synthetic scene
    python main.py --source synthetic
    python main.py --help

The first call bootstraps a private virtual environment (see core.py), then
hands off to the OS-independent pipeline in steady_core.py.
"""
import sys


def main(argv):
    """
    Bootstraps the private environment, then hands off to the OS independent pipeline.
    :param argv: list : Command line arguments, see steady_core.parse_args.
    :return: int : Process exit code.
    """
    from core import ensure_environment
    ensure_environment(argv)          # returns only once we are inside the venv

    from steady_core import parse_args, run_demo
    run_demo(parse_args(argv))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
