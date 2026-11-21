import argparse
import os
import shutil
import subprocess
import tempfile
import zipapp
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRS = ("app", "ingest", "desktop", "static", "bank")
SOURCE_FILES = ("run.py", "config.yaml", "sources.yaml", "requirements.txt")


def _copy_source(target):
    for name in SOURCE_DIRS:
        source = ROOT / name
        if source.is_dir():
            shutil.copytree(source, target / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for name in SOURCE_FILES:
        source = ROOT / name
        if source.is_file():
            shutil.copy2(source, target / name)
    site = ROOT / "site"
    if (site / "index.html").is_file():
        shutil.copytree(site, target / "site", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (target / "__main__.py").write_text(
        "from desktop.main import main\nraise SystemExit(main())\n",
        encoding="utf-8",
    )


def build_zipapp(output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as raw:
        staging = Path(raw)
        _copy_source(staging)
        zipapp.create_archive(staging, output)
    return output


def build_pyinstaller(output):
    executable = shutil.which("pyinstaller")
    if not executable:
        return None
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [executable, "--clean", "--noconfirm", "--distpath", str(target.parent),
         "--workpath", str(target.parent / "build"), "--specpath", str(ROOT / "desktop"),
         "desktop/EnglishDaily.spec"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "PyInstaller failed")
    built = target.parent / ("EnglishDaily.exe" if os.name == "nt" else "EnglishDaily")
    if built.is_file():
        shutil.move(str(built), str(target))
    return target if target.is_file() else None


def build(output, prefer_pyinstaller=False):
    if prefer_pyinstaller:
        built = build_pyinstaller(output)
        if built:
            return built
    return build_zipapp(output)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(prog="build-desktop")
    parser.add_argument("--out", default="dist/EnglishDaily.pyz")
    parser.add_argument("--pyinstaller", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    artifact = build(args.out, prefer_pyinstaller=args.pyinstaller)
    print(f"Desktop artifact written to {artifact}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
