#!/usr/bin/env bash
# Redeploy elzant.com after pulling new code. Run as root/sudo:
#   sudo bash /srv/elzant/deploy/update.sh
# Non-destructive: never touches .env, the SQLite database, or media.
set -euo pipefail

sudo -u elzant -H bash <<'EOF'
set -euo pipefail
APP=/srv/elzant
cd "$APP"

# Assets that `npm run assets:build` regenerates each deploy. Reset them to the
# committed version first so a previous build's bytes don't leave the tree dirty
# and break `git pull --ff-only`. This only discards generated, tracked images.
GENERATED="static/img/og-image.png static/img/qr.svg"
git checkout -- $GENERATED 2>/dev/null || true

# Refuse to clobber any *other* local edits — report them and stop instead.
if [ -n "$(git status --porcelain)" ]; then
  echo "Aborting: working tree has local changes beyond generated assets:" >&2
  git status --short >&2
  exit 1
fi

git pull --ff-only
"$APP/.venv/bin/pip" install -q -r requirements.txt
npm ci --silent
SITE_URL=https://elzant.com npm run assets:build
npm run css:build
"$APP/.venv/bin/python" manage.py migrate --noinput
"$APP/.venv/bin/python" manage.py collectstatic --noinput
EOF

systemctl restart elzant
echo "✓ elzant.com redeployed"
