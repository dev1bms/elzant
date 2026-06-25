#!/usr/bin/env bash
# Redeploy elzant.com after pulling new code. Run as root/sudo:
#   sudo bash /srv/elzant/deploy/update.sh
# Non-destructive: never touches .env, the SQLite database, or media.
set -euo pipefail

sudo -u elzant -H bash <<'EOF'
set -euo pipefail
APP=/srv/elzant
cd "$APP"

# Generated assets (output.css, static/img/og-image.*) are gitignored, so a
# previous build never dirties the tree. Refuse to clobber any *real* local
# edits — report them and stop instead.
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
