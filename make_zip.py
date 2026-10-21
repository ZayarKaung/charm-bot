"""Build a shareable zip of Charm Bot without secrets: python make_zip.py

Only files committed to Git are included, so .env (API keys, bot token),
charm_bot.db (chat data) and __pycache__ are never packed. The zip is
written to dist/charm-bot-<date>.zip.
"""

import subprocess
import sys
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# Anything matching these must never end up in the zip.
FORBIDDEN = (".env", ".db", ".db.bak", ".db-journal", ".pyc")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def main() -> int:
    if git("status", "--porcelain").strip():
        print("⚠️  You have uncommitted changes; they will NOT be in the zip.")
        print("   Commit first if you want them included.\n")

    output = ROOT / "dist" / f"charm-bot-{date.today().isoformat()}.zip"
    output.parent.mkdir(exist_ok=True)
    git("archive", "--format=zip", "--prefix=charm-bot/", "-o", str(output), "HEAD")

    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
    leaked = [name for name in names if name.endswith(FORBIDDEN)]
    if leaked:
        output.unlink()
        print("❌ Refusing to create zip; private files found:", ", ".join(leaked))
        return 1

    print(f"✅ Created {output.relative_to(ROOT)} ({len(names)} entries, {output.stat().st_size // 1024} KB)")
    print("   Excluded: .env, databases, __pycache__ and anything not committed.")
    print("   After unzipping: copy .env.example to .env and fill in your own keys.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
