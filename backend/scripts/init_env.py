#!/usr/bin/env python3
"""Create ``backend/.env`` from ``.env.example`` with fresh local secrets.

Standard library only (works on Linux, macOS and Windows). It fills the three
local secrets (database owner password, app database password, encryption KEK)
with random values and, if given, your OpenRouter key::

    python3 scripts/init_env.py                       # then paste your key into .env
    python3 scripts/init_env.py --openrouter-key sk-or-...
    OPENROUTER_API_KEY=sk-or-... python3 scripts/init_env.py

It refuses to overwrite an existing ``.env`` unless ``--force`` is given (the
database volume keeps the passwords of the first start; see README,
Troubleshooting).
"""

from __future__ import annotations

import argparse
import base64
import os
import secrets
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def render(template: str, openrouter_key: str | None) -> str:
    owner_pw = "own-" + secrets.token_urlsafe(18)
    app_pw = "app" + secrets.token_hex(16)
    kek = base64.b64encode(os.urandom(32)).decode("ascii")
    out = []
    for line in template.splitlines():
        if line.startswith("POSTGRES_PASSWORD="):
            line = f"POSTGRES_PASSWORD={owner_pw}"
        elif line.startswith("DATABASE_URL="):
            line = line.replace("CHANGE_ME_app_password", app_pw)
        elif line.startswith("ENCRYPTION_KEK="):
            line = f"ENCRYPTION_KEK={kek}"
        elif line.startswith("OPENROUTER_API_KEY=") and openrouter_key:
            line = f"OPENROUTER_API_KEY={openrouter_key}"
        out.append(line)
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--openrouter-key", default=os.environ.get("OPENROUTER_API_KEY"))
    parser.add_argument("--force", action="store_true", help="overwrite an existing .env")
    args = parser.parse_args(argv)
    target = BACKEND / ".env"
    if target.exists() and not args.force:
        print(f"{target} already exists; use --force to regenerate it "
              "(then also run `docker compose down -v`).")
        return 1
    template = (BACKEND / ".env.example").read_text(encoding="utf-8")
    target.write_text(render(template, args.openrouter_key), encoding="utf-8")
    print(f"wrote {target}")
    if args.openrouter_key:
        print("OpenRouter key set.")
    else:
        print("Next: paste your OpenRouter key into OPENROUTER_API_KEY in backend/.env")
    return 0


if __name__ == "__main__":
    sys.exit(main())
