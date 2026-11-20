from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGINS = ROOT / "plugins"
DIST = ROOT / "dist"
LICENSE_FILES = (ROOT / "LICENSE", ROOT / "NOTICE")
FIXED_ZIP_TIME = (2026, 1, 1, 0, 0, 0)


def add_file(bundle: zipfile.ZipFile, archive_name: str, data: bytes) -> None:
    entry = zipfile.ZipInfo(archive_name, FIXED_ZIP_TIME)
    entry.compress_type = zipfile.ZIP_DEFLATED
    entry.external_attr = 0o100644 << 16
    bundle.writestr(entry, data)


def build_archive(package: Path, archive: Path) -> None:
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for source in sorted(path for path in package.rglob("*") if path.is_file()):
            if source.suffix in {".pyc", ".pyo"} or "__pycache__" in source.parts:
                continue
            archive_name = f"{package.name}/{source.relative_to(package).as_posix()}"
            add_file(bundle, archive_name, source.read_bytes())
        for source in LICENSE_FILES:
            add_file(bundle, f"{package.name}/{source.name}", source.read_bytes())


def main() -> None:
    shutil.rmtree(DIST, ignore_errors=True)
    DIST.mkdir()
    checksums: list[str] = []

    for package in sorted(path for path in PLUGINS.iterdir() if path.is_dir()):
        manifest_path = package / "puzzary-plugin.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["schema"] == "puzzary.plugin.v1"
        assert manifest["api_version"] == "1"
        assert manifest["slug"] == package.name
        assert manifest["license"] == "Apache-2.0"
        entrypoint = package / manifest["entrypoint"]
        assert entrypoint.is_file()
        compile(entrypoint.read_text(encoding="utf-8"), str(entrypoint), "exec")
        if manifest.get("templates"):
            assert (package / manifest["templates"]).is_dir()
        if manifest.get("static"):
            assert (package / manifest["static"]).is_dir()

        archive = DIST / f"puzzary-{manifest['slug']}-{manifest['version']}.zip"
        build_archive(package, archive)
        with zipfile.ZipFile(archive) as bundle:
            names = set(bundle.namelist())
            assert f"{package.name}/LICENSE" in names
            assert f"{package.name}/NOTICE" in names
            assert f"{package.name}/puzzary-plugin.json" in names
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        checksum = f"{digest}  {archive.name}"
        archive.with_suffix(".zip.sha256").write_text(f"{checksum}\n", encoding="utf-8")
        checksums.append(checksum)
        print(f"Built {archive.name} ({digest})")

    (DIST / "SHA256SUMS").write_text("\n".join(checksums) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
