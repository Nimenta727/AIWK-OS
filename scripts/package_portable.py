"""Build a deterministic, source-only portable release; never copy credentials.

Use: python scripts/package_portable.py --output /path/to/AIWS-Prototype.zip
"""
import argparse
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOP_FILES = ("README.md", "AGENTS.md", "LICENSE", "app.py", ".gitignore")
FOLDERS = ("aiws", "web", "scripts", "docs", "tests")
IGNORE_DIRS = {"__pycache__", ".git", ".venv", "venv", "dist", "build"}
IGNORE_EXT = {".pyc", ".pyo", ".sqlite3", ".db", ".zip", ".exe"}


def package(output: Path, root: Path = ROOT) -> list[str]:
    root = root.resolve()
    output = output.resolve()
    files = [root / name for name in TOP_FILES if (root / name).is_file()]
    for folder in FOLDERS:
        location = root / folder
        if location.is_dir():
            files.extend(p for p in location.rglob("*") if p.is_file())
    selected = []
    for path in files:
        rel = path.relative_to(root)
        if (path.is_symlink() or any(part in IGNORE_DIRS or part.startswith(".") and part not in (".gitignore",)
                                 for part in rel.parts)
                or path.suffix.lower() in IGNORE_EXT or path.resolve() == output):
            continue
        selected.append((rel.as_posix(), path))
    if not selected or not (root / "app.py").exists():
        raise ValueError("Not an AIWS source folder")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, path in sorted(selected):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())
    return [name for name, _ in sorted(selected)]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT.parent / "AIWS-Prototype.zip")
    args = parser.parse_args()
    paths = package(args.output)
    print(f"Packaged {len(paths)} files: {args.output.resolve()}")
