#!/usr/bin/env bash
# Redeploy elzant.com after pulling new code. Run as root/sudo:
#   sudo bash /srv/elzant/deploy/update.sh
set -euo pipefail

APP=/srv/elzant

sudo -u elzant -H bash -c "
  set -euo pipefail
  cd '$APP'
  git pull --ff-only
  '$APP/.venv/bin/pip' install -q -r requirements.txt
  npm ci --silent
  SITE_URL=https://elzant.com npm run assets:build
  npm run css:build
  '$APP/.venv/bin/python' manage.py migrate --noinput
  '$APP/.venv/bin/python' manage.py collectstatic --noinput
"

systemctl restart elzant
echo "✓ elzant.com redeployed"
