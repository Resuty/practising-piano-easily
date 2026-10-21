from pathlib import Path
import runpy
import zipfile
import pytest


def test_portfolio_source_allowlist_excludes_private_materials():
    root = Path(__file__).resolve().parents[1]
    module = runpy.run_path(str(root / "packaging" / "build_portfolio.py"))
    files = list(module["source_files"]())
    module["check_source_files"](files)
    assert files and all(path.is_file() for path in files)
    relative = [path.relative_to(root) for path in files]
    assert Path("practising_piano_easily/content/chord_tutorial_ja.md") in relative
    assert Path("packaging/launcher.py") in relative
    assert Path("tests/test_japanese.py") in relative
    for path in relative:
        assert not set(path.parts) & {"data", "exports", ".git", ".venv", "__pycache__"}
        assert path.suffix.lower() not in {".db", ".mid", ".midi", ".pdf", ".mp3", ".wav"}


def test_generated_directory_refresh_is_scoped_to_the_bundle(tmp_path):
    root = Path(__file__).resolve().parents[1]
    module = runpy.run_path(str(root / "packaging" / "build_portfolio.py"))
    refresh = module["fresh_generated_directory"]
    refresh.__globals__["BUNDLE"] = tmp_path / "build"
    target = tmp_path / "build" / "Source"
    target.mkdir(parents=True)
    (target / "stale.pyc").touch()
    refresh(target)
    assert target.is_dir() and not list(target.iterdir())
    outside = tmp_path / "Source"
    outside.mkdir()
    (outside / "keep.txt").touch()
    with pytest.raises(ValueError):
        refresh(outside)
    assert (outside / "keep.txt").exists()


@pytest.mark.parametrize("content", [
    "C:" + "/Users/" + "example/private.txt",
    "gh" + "p_" + "x" * 36,
    "-----BEGIN " + "PRIVATE KEY-----",
])
def test_public_source_rejects_personal_paths_and_credentials(tmp_path, content):
    module = runpy.run_path(str(Path(__file__).resolve().parents[1] / "packaging/build_portfolio.py"))
    check = module["check_source_files"]
    check.__globals__["ROOT"] = tmp_path
    candidate = tmp_path / "README.md"
    candidate.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match="Possible personal path or credential"):
        check([candidate])


@pytest.mark.parametrize("relative", ["data/private.txt", ".git/config", ".env", "song.mid"])
def test_public_source_rejects_private_files(tmp_path, relative):
    module = runpy.run_path(str(Path(__file__).resolve().parents[1] / "packaging/build_portfolio.py"))
    check = module["check_source_files"]
    check.__globals__["ROOT"] = tmp_path
    candidate = tmp_path / relative
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text("private", encoding="utf-8")
    with pytest.raises(ValueError):
        check([candidate])


def test_source_export_copies_only_approved_files_and_preserves_existing_export(tmp_path):
    module = runpy.run_path(str(Path(__file__).resolve().parents[1] / "packaging/build_portfolio.py"))
    export = module["export_source"]
    source = tmp_path / "project"
    source.mkdir()
    approved = source / "README.md"
    approved.write_text("public source", encoding="utf-8")
    (source / "private.db").write_bytes(b"local data")
    output = tmp_path / "output"
    directory = output / "practising-piano-easily"
    archive = output / "source.zip"
    export.__globals__.update(ROOT=source, SOURCE_OUTPUT=output, SOURCE_DIRECTORY=directory,
                              SOURCE_ARCHIVE=archive, source_files=lambda: iter([approved]))
    export()
    assert (directory / "README.md").read_text(encoding="utf-8") == "public source"
    assert not (directory / "private.db").exists()
    with zipfile.ZipFile(archive) as zipped:
        assert zipped.namelist() == ["practising-piano-easily/README.md"]
    (directory / "keep.txt").write_text("user edit", encoding="utf-8")
    with pytest.raises(FileExistsError):
        export()
    assert (directory / "keep.txt").read_text(encoding="utf-8") == "user edit"
