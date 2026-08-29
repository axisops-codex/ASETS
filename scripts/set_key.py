#!/usr/bin/env python3
"""Set a value in backend/.env without opening an editor.

    python3 scripts/set_key.py COMPANIES_HOUSE_API_KEY
    python3 scripts/set_key.py ANTHROPIC_API_KEY

Prompts for the value without echoing it, so it never reaches your shell
history or your screen. Everything else in the file is left exactly as it
was — only the one line changes.

Editing .env by hand is fine too, but an editor that has had the file
open while a script rewrote it will refuse to save over the newer copy;
this avoids that entirely.

Add --deploy to push the value to Secret Manager and redeploy.
"""
import argparse
import getpass
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / "backend" / ".env"

# Which of these belong in Secret Manager, and what the API calls them.
DEPLOYABLE = {
    "ANTHROPIC_API_KEY", "COMPANIES_HOUSE_API_KEY",
    "HMRC_CLIENT_ID", "HMRC_CLIENT_SECRET", "JWT_SECRET", "TOKEN_ENCRYPTION_KEY",
}


def gcp_project() -> str | None:
    env_out = ROOT / "deploy" / "gcp.env"
    if not env_out.exists():
        return None
    for line in env_out.read_text().splitlines():
        if line.startswith("PROJECT_ID="):
            return line.split("=", 1)[1].strip()
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name", help="the variable to set, e.g. ANTHROPIC_API_KEY")
    ap.add_argument("--deploy", action="store_true",
                    help="also store it in Secret Manager and redeploy Cloud Run")
    args = ap.parse_args()

    name = args.name.strip().upper()
    if not re.fullmatch(r"[A-Z0-9_]+", name):
        print("That is not a variable name.", file=sys.stderr)
        return 2
    if not ENV.exists():
        print(f"{ENV} does not exist — run scripts/gen_secrets.py first", file=sys.stderr)
        return 2

    value = getpass.getpass(f"{name} (not echoed): ").strip()
    if not value:
        print("Nothing entered; the file was not touched.", file=sys.stderr)
        return 1

    text = ENV.read_text()
    line = f"{name}={value}"
    if re.search(rf"^{name}=", text, flags=re.M):
        text = re.sub(rf"^{name}=.*$", line, text, flags=re.M)
        what = "updated"
    else:
        text = text.rstrip("\n") + "\n" + line + "\n"
        what = "added"
    ENV.write_text(text)
    os.chmod(ENV, 0o600)
    print(f"✓ {what} {name} in backend/.env ({len(value)} characters)")
    print("  If your editor has the file open, close and reopen it — its copy is now stale.")

    if not args.deploy:
        print(f"\nTo put it live:  python3 scripts/set_key.py {name} --deploy")
        return 0

    project = gcp_project()
    if not project:
        print("No deploy/gcp.env — cannot reach Secret Manager.", file=sys.stderr)
        return 1
    if name not in DEPLOYABLE:
        print(f"{name} is not one of the deployed secrets; stopping after the file edit.")
        return 0

    exists = subprocess.run(["gcloud", "secrets", "describe", name, f"--project={project}"],
                            capture_output=True).returncode == 0
    if not exists:
        subprocess.run(["gcloud", "secrets", "create", name, "--replication-policy=automatic",
                        f"--project={project}"], check=True, capture_output=True)
    subprocess.run(["gcloud", "secrets", "versions", "add", name, "--data-file=-",
                    f"--project={project}"], input=value.encode(), check=True, capture_output=True)
    print(f"✓ stored in Secret Manager ({project})")

    print("\nRedeploying…")
    subprocess.run([str(ROOT / "scripts" / "deploy_cloudrun.sh")], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
