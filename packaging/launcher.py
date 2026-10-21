"""Absolute package entry point for PyInstaller (no relative __main__ imports)."""

from practising_piano_easily.app import main


if __name__ == "__main__":
    raise SystemExit(main())
