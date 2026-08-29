#!/usr/bin/env bash
# Pre-submission checks. Run from the repo root:  ./scripts/preflight.sh
# Exits non-zero if anything that would get the build rejected is still wrong.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
FAIL=0
pass() { printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }
fail() { printf '  \033[31m✗\033[0m %s\n' "$1"; FAIL=1; }

API="$(python3 -c "import json;print(json.load(open('frontend/eas.json'))['build']['production']['env']['EXPO_PUBLIC_BACKEND_URL'])")"

echo "▸ Backend tests"
if (cd backend && /usr/bin/env python3 -c "import asyncpg" >/dev/null 2>&1 || [ -n "${PYTEST_PYTHON:-}" ]); then
  if (cd backend && "${PYTEST_PYTHON:-python3}" -m pytest -q -p no:warnings >/tmp/asets-pytest.log 2>&1); then
    pass "$(tail -1 /tmp/asets-pytest.log)"
  else
    fail "backend tests failed — see /tmp/asets-pytest.log"
  fi
else
  warn "backend test deps not installed (pip install -r backend/requirements.txt)"
fi

echo "▸ App config"
python3 - <<'PY'
import json, sys
c = json.load(open("frontend/app.json"))["expo"]
ok = True
def p(m): print(f"  \033[32m✓\033[0m {m}")
def f(m):
    global ok; ok = False; print(f"  \033[31m✗\033[0m {m}")
for plat, key in (("ios", "bundleIdentifier"), ("android", "package")):
    v = c[plat][key]
    (f if ("emergent" in v or "example" in v) else p)(f"{plat} id: {v}")
p(f"name: {c['name']} · slug: {c['slug']} · version: {c['version']}")
if c["ios"]["infoPlist"].get("ITSAppUsesNonExemptEncryption") is not False:
    f("ITSAppUsesNonExemptEncryption must be false (export compliance)")
else:
    p("export compliance declared")
sys.exit(0 if ok else 1)
PY
[ $? -ne 0 ] && FAIL=1

echo "▸ Store credentials in eas.json"
if grep -q "REPLACE_WITH" frontend/eas.json; then
  warn "eas.json still has REPLACE_WITH_* placeholders (needed only for 'eas submit -p ios')"
else
  pass "submit config filled in"
fi
[ -f frontend/credentials/play-service-account.json ] \
  && pass "Play service-account key present" \
  || warn "frontend/credentials/play-service-account.json missing (needed for 'eas submit -p android')"

echo "▸ Assets"
for f in icon.png adaptive-icon.png splash-image.png favicon.png; do
  p="frontend/assets/images/$f"
  if [ -f "$p" ]; then
    dim="$(sips -g pixelWidth -g pixelHeight "$p" 2>/dev/null | awk '/pixel/{printf "%s ", $2}')"
    pass "$f (${dim:-?})"
  else
    fail "$f missing"
  fi
done

echo "▸ Types"
if (cd frontend && [ -d node_modules ]); then
  if (cd frontend && ./node_modules/.bin/tsc --noEmit -p tsconfig.json >/dev/null 2>&1); then
    pass "tsc clean"
  else
    fail "tsc reported errors (run: cd frontend && npx tsc --noEmit)"
  fi
else
  warn "frontend/node_modules missing — run 'yarn install' in frontend/"
fi

echo "▸ Live API ($API)"
case "$API" in
  *REPLACE-WITH*) fail "EXPO_PUBLIC_BACKEND_URL in frontend/eas.json is still a placeholder — set it to the deployed Cloud Run URL" ;;
esac
health="$(curl -fsS --max-time 15 "$API/api/health" 2>/dev/null)"
if [ -n "$health" ]; then
  pass "health: $health"
  case "$health" in
    *'"receipt_ocr":"disabled"'*) warn "receipt scanning disabled (set ANTHROPIC_API_KEY) — the app degrades to manual entry" ;;
  esac
  case "$health" in
    *'"companies_house":false'*) warn "Companies House lookup not configured (optional)" ;;
  esac
  case "$health" in
    *'"hmrc":"disabled"'*) warn "HMRC filing not configured — the app hides the feature" ;;
    *'"hmrc":"sandbox"'*)  warn "HMRC is in SANDBOX mode — do not ship this to the stores as live filing" ;;
  esac
  case "$health" in
    *'"hmrc":"disabled"'*) : ;;
    *) if "${PYTEST_PYTHON:-python3}" "$ROOT/scripts/check_hmrc.py" >/tmp/asets-hmrc.log 2>&1; then
         pass "HMRC subscriptions and redirect URI verified"
       else
         warn "HMRC setup incomplete — run scripts/check_hmrc.py"
       fi ;;
  esac
  case "$health" in
    *'"database":"down"'*) fail "database is unreachable" ;;
  esac
else
  fail "no response from $API/api/health — deploy the backend first"
fi

for page in privacy terms delete-account support; do
  code="$(curl -o /dev/null -s -w '%{http_code}' --max-time 15 "$API/legal/$page")"
  [ "$code" = "200" ] && pass "legal/$page reachable" || fail "legal/$page returned $code (store listings need these URLs live)"
done

echo
if [ $FAIL -eq 0 ]; then
  printf '\033[32mPreflight passed.\033[0m Next: eas build --profile production --platform all\n'
else
  printf '\033[31mPreflight failed.\033[0m Fix the ✗ items above before submitting.\n'
fi
exit $FAIL
