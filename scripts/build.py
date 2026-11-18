from __future__ import annotations

import compileall
import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGINS = ROOT / "plugins"
DIST = ROOT / "dist"
DIST.mkdir(exist_ok=True)

for package in sorted(path for path in PLUGINS.iterdir() if path.is_dir()):
    manifest = json.loads((package / "puzzary-plugin.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == "puzzary.plugin.v1"
    assert manifest["api_version"] == "1"
    assert manifest["slug"] == package.name
    assert (package / manifest["entrypoint"]).is_file()
    if manifest.get("templates"):
        assert (package / manifest["templates"]).is_dir()
    if manifest.get("static"):
        assert (package / manifest["static"]).is_dir()
    assert compileall.compile_file(str(package / manifest["entrypoint"]), quiet=1)

    base = DIST / f"puzzary-{manifest['slug']}-{manifest['version']}"
    archive = Path(shutil.make_archive(str(base), "zip", package.parent, package.name))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(".zip.sha256").write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    print(f"Built {archive.name} ({digest})")

