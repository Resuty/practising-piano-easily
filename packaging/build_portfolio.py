"""Build a data-free Windows distribution or export clean repository sources."""

import argparse
import hashlib
from importlib import metadata
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "exports" / "portfolio"
BUNDLE = OUTPUT / "practising-piano-easily"
ARCHIVE = OUTPUT / "practising-piano-easily-windows.zip"
SOURCE_OUTPUT = ROOT / "exports" / "github"
SOURCE_DIRECTORY = SOURCE_OUTPUT / "practising-piano-easily"
SOURCE_ARCHIVE = SOURCE_OUTPUT / "practising-piano-easily-source.zip"
RUNTIME = ("PySide6", "PySide6-Addons", "PySide6-Essentials", "shiboken6", "mido",
           "python-rtmidi", "numpy", "sounddevice", "cffi", "pycparser", "packaging", "setuptools")
SOURCE_TREES = {"practising_piano_easily": {".py", ".md"}, "tests": {".py"},
                "packaging": {".py", ".spec", ".md", ".txt", ".html"}}
SOURCE_ROOTS = ("README.md", "README.zh-CN.md", "requirements.txt", "requirements-build.txt", "pytest.ini", "start.bat", ".gitignore")
DESIGN_DOCS = ("ARCHITECTURE.md", "MUSIC_THEORY.md", "TRAINING_MODEL.md", "ROADMAP.md")


def source_files(root=ROOT):
    for name in SOURCE_ROOTS:
        yield root / name
    for tree, suffixes in SOURCE_TREES.items():
        for path in sorted((root / tree).rglob("*")):
            if path.is_file() and path.suffix in suffixes and "__pycache__" not in path.parts:
                yield path
    for name in DESIGN_DOCS:
        yield root / "docs" / name


def check_source_files(files):
    personal_path = re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s\"']+", re.IGNORECASE)
    credential = re.compile(r"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|AKIA[0-9A-Z]{16}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----)")
    forbidden = {"data", "exports", ".git", ".venv", "__pycache__", ".idea", ".vscode", ".codex", ".agents"}
    for path in files:
        if not path.resolve().is_relative_to(ROOT.resolve()):
            raise ValueError("Source file is outside the project")
        relative = path.relative_to(ROOT)
        if forbidden.intersection(relative.parts) or path.name.startswith(".env"):
            raise ValueError(f"Private source file: {relative}")
        if path.suffix.lower() not in {".py", ".md", ".spec", ".txt", ".html", ".bat", ".ini", ""}:
            raise ValueError(f"Unapproved source file: {relative}")
        if "licenses" not in relative.parts:
            content = path.read_text(encoding="utf-8")
            if personal_path.search(content) or credential.search(content):
                raise ValueError(f"Possible personal path or credential in: {relative}")


def export_source():
    files = list(source_files())
    check_source_files(files)
    SOURCE_OUTPUT.mkdir(parents=True, exist_ok=True)
    if SOURCE_DIRECTORY.exists() or SOURCE_ARCHIVE.exists():
        raise FileExistsError("Existing GitHub export is preserved; choose a fresh export destination")
    SOURCE_DIRECTORY.mkdir()
    for path in files:
        target = SOURCE_DIRECTORY / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    with zipfile.ZipFile(SOURCE_ARCHIVE, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, Path(SOURCE_DIRECTORY.name) / path.relative_to(ROOT))
    with zipfile.ZipFile(SOURCE_ARCHIVE) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("Source ZIP integrity check failed")
    print(json.dumps({"source_directory": str(SOURCE_DIRECTORY), "source_archive": str(SOURCE_ARCHIVE),
                      "files": len(files), "bytes": SOURCE_ARCHIVE.stat().st_size}, ensure_ascii=False))


def fresh_generated_directory(directory):
    if directory.name not in {"Source", "THIRD_PARTY"} or directory.resolve().parent != BUNDLE.resolve():
        raise ValueError("Only generated Source/THIRD_PARTY directories inside this bundle may be refreshed")
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir(parents=True)


def copy_sources():
    destination = BUNDLE / "Source"
    check_source_files(list(source_files()))
    fresh_generated_directory(destination)
    for path in source_files():
        target = destination / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def copy_licenses():
    directory = BUNDLE / "THIRD_PARTY"
    fresh_generated_directory(directory)
    shutil.copy2(ROOT / "packaging" / "THIRD_PARTY.md", directory / "README.md")
    shutil.copytree(ROOT / "packaging" / "licenses", directory / "license-texts", dirs_exist_ok=True)
    for name in RUNTIME + ("PyInstaller",):
        distribution = metadata.distribution(name)
        target = directory / name
        target.mkdir(exist_ok=True)
        (target / "METADATA.txt").write_text(distribution.read_text("METADATA") or "", encoding="utf-8")
        for item in distribution.files or ():
            lower = str(item).lower()
            if ("__pycache__" not in item.parts and item.suffix not in {".py", ".pyc", ".pyo"}
                    and any(term in lower for term in ("license", "copying", "copyright", "notice", "authors"))):
                source = Path(distribution.locate_file(item))
                if source.is_file():
                    # Wheel-relative paths are retained without allowing traversal.
                    relative = Path(*[part for part in item.parts if part not in {"..", "."}])
                    output = target / relative
                    output.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, output)
    python_license = next((path for path in (Path(sys.base_prefix) / "LICENSE.txt",
        Path(sys.base_prefix) / "LICENSE_PYTHON.txt", ROOT / "packaging" / "licenses" /
        f"Python-{platform.python_version()}-LICENSE.txt") if path.is_file()), None)
    if python_license is None:
        raise FileNotFoundError("Build interpreter's Python license is required")
    shutil.copy2(python_license, directory / "Python-LICENSE.txt")
    # Retain notices for the exact Conda stdlib DLL packages, when this runtime uses them.
    conda_meta = Path(sys.base_prefix) / "conda-meta"
    for prefix in ("libffi", "sqlite", "mpdecimal", "libmpdec", "openssl", "bzip2", "expat", "libexpat", "xz", "zlib", "libzlib"):
        for record in conda_meta.glob(prefix + "-*.json"):
            package_info = json.loads(record.read_text(encoding="utf-8"))
            package_name = f"{package_info['name']}-{package_info['version']}-{package_info['build']}"
            target = directory / package_name
            target.mkdir(exist_ok=True)
            (target / "PACKAGE.json").write_text(json.dumps(
                {key: package_info.get(key) for key in ("name", "version", "build", "license")}, indent=2), encoding="utf-8")
            notices = Path(sys.base_prefix) / "pkgs" / package_name / "info" / "licenses"
            if notices.is_dir():
                shutil.copytree(notices, target, dirs_exist_ok=True)


def package():
    if not (BUNDLE / "practising-piano-easily.exe").is_file():
        raise FileNotFoundError("Build the EXE before packaging")
    for locale in ("ja", "zh"):
        shutil.copy2(ROOT / "packaging" / f"README_{locale}.md", BUNDLE / f"README_{locale}.md")
    copy_sources()
    copy_licenses()
    versions = {name: metadata.version(name) for name in RUNTIME}
    (BUNDLE / "Source" / "requirements-runtime-lock.txt").write_text(
        "\n".join(f"{name}=={version}" for name, version in versions.items()) + "\n", encoding="utf-8")
    verification = ROOT / "packaging" / "VERIFICATION.md"
    if verification.is_file():
        shutil.copy2(verification, BUNDLE / "VERIFICATION.md")
    source_digest = hashlib.sha256()
    for path in source_files():
        source_digest.update(path.relative_to(ROOT).as_posix().encode("utf-8") + b"\0" + path.read_bytes())
    manifest = {"application": "practising piano easily", "release_date": "2026-10-21", "platform": "Windows x64",
                "python": platform.python_version(), "pyinstaller": metadata.version("PyInstaller"),
                "source_sha256": source_digest.hexdigest(),
                "languages": ["ja", "zh_CN", "en"], "default_language": "ja", "dependencies": versions,
                "excluded": ["personal data", "downloaded scores", "audio", "PDFs", "credentials", "git history"]}
    (BUNDLE / "BUILD_INFO.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    files = sorted(path for path in BUNDLE.rglob("*") if path.is_file() and path.name != "SHA256SUMS.txt")
    for path in files:
        relative = path.relative_to(BUNDLE)
        if any(part in {"data", "exports", ".git", ".venv", "__pycache__"} for part in relative.parts):
            raise ValueError(f"Private/unwanted directory in release: {relative}")
        if path.suffix.lower() in {".db", ".sqlite", ".sqlite3", ".mid", ".midi", ".pdf", ".mp3", ".wav"}:
            raise ValueError(f"Personal media or database in release: {relative}")
    checksums = "\n".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(BUNDLE).as_posix()}" for path in files)
    (BUNDLE / "SHA256SUMS.txt").write_text(checksums + "\n", encoding="utf-8")
    with zipfile.ZipFile(ARCHIVE, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(BUNDLE.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(OUTPUT))
    with zipfile.ZipFile(ARCHIVE) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("ZIP integrity check failed")
    digest = hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
    ARCHIVE.with_suffix(".zip.sha256").write_text(f"{digest}  {ARCHIVE.name}\n", encoding="ascii")
    print(json.dumps({"archive": str(ARCHIVE), "bytes": ARCHIVE.stat().st_size, "sha256": digest}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-only", action="store_true", help="Refresh documents and archive without rebuilding the EXE")
    parser.add_argument("--source-only", action="store_true", help="Export a clean source tree without Git history or runtime data")
    args = parser.parse_args()
    if args.source_only:
        if args.archive_only:
            parser.error("Choose either --source-only or --archive-only")
        export_source()
        return
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if not args.archive_only:
        if BUNDLE.exists():
            parser.error("Existing build folder is preserved. Use a new output directory or --archive-only for docs.")
        subprocess.run([sys.executable, "-m", "PyInstaller", "--distpath", str(OUTPUT), "--workpath",
                        str(ROOT / "exports" / "build-portfolio"), str(ROOT / "packaging" / "practising-piano-easily.spec")],
                       cwd=ROOT, check=True)
    package()


if __name__ == "__main__":
    main()
