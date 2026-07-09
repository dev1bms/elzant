#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# إعادة نشر elzant.com بعد وصول commits جديدة إلى origin/main.
#
# شغّله كـ«صاحب المشروع» (لا كـ root) — يستدعي sudo فقط لإعادة تشغيل الخدمة:
#     bash deploy/update.sh
#
# يكتشف تلقائياً:  مجلد المشروع (من موقع هذا الملف)  +  البيئة (venv/ أو .venv/).
# آمن وغير مدمّر:  يرفض العمل مع تعديلات غير مُلتزَمة، يأخذ نسخة احتياطية من قاعدة
# SQLite قبل الهجرة، ولا يعيد تشغيل الخدمة إلا بعد نجاح كل الخطوات.
#
# تجاوُز الافتراضيات عند اختلاف الإعداد (اختياري):
#     ELZANT_SERVICE=elzant.service  ELZANT_HEALTH_URL=http://127.0.0.1:8019/ \
#     ELZANT_SITE_URL=https://elzant.com  bash deploy/update.sh
# ---------------------------------------------------------------------------
set -euo pipefail

BRANCH="${ELZANT_BRANCH:-main}"
SERVICE="${ELZANT_SERVICE:-elzant.service}"
SITE_URL="${ELZANT_SITE_URL:-https://elzant.com}"
# Must match the Gunicorn bind in deploy/gunicorn.conf.py (127.0.0.1:8001).
HEALTH_URL="${ELZANT_HEALTH_URL:-http://127.0.0.1:8001/}"
KEEP_BACKUPS="${ELZANT_KEEP_BACKUPS:-10}"

# --- تحديد مجلد المشروع + البيئة من موقع السكربت ---
APP="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP"
if   [ -d "$APP/venv" ];  then VENV="$APP/venv"
elif [ -d "$APP/.venv" ]; then VENV="$APP/.venv"
else echo "✗ لم أجد البيئة الافتراضية (venv/ أو .venv/) في $APP" >&2; exit 1; fi
PY="$VENV/bin/python"; PIP="$VENV/bin/pip"

command -v git >/dev/null || { echo "✗ git غير موجود." >&2; exit 1; }
command -v npm >/dev/null || { echo "✗ npm غير موجود (لازم لبناء CSS)." >&2; exit 1; }

echo "▶ المشروع: $APP"
echo "▶ البيئة:  $VENV"

# --- 1) لا تدُس على تعديلات محلية ---
if [ -n "$(git status --porcelain)" ]; then
  echo "✗ توقّف: توجد تعديلات محلية غير مُلتزَمة — راجِعها أو التزِمها أولاً:" >&2
  git status --short >&2
  exit 1
fi

# --- 2) هل يوجد جديد للسحب؟ ---
git fetch --quiet origin "$BRANCH"
if git diff --quiet "HEAD..origin/$BRANCH"; then
  echo "✓ لا جديد على origin/$BRANCH — لا حاجة للتحديث."
  exit 0
fi
echo "▶ commits جديدة:"
git --no-pager log --oneline "HEAD..origin/$BRANCH" | sed 's/^/   /'

# --- 3) نسخة احتياطية من قاعدة SQLite قبل الهجرة ---
DB="$(grep -E '^SQLITE_PATH=' .env 2>/dev/null | head -1 | cut -d= -f2- || true)"
DB="${DB%\"}"; DB="${DB#\"}"
if [ -z "${DB:-}" ]; then
  for c in "$APP/db.sqlite3" "$APP/data/db.sqlite3"; do [ -f "$c" ] && DB="$c" && break; done
fi
if [ -n "${DB:-}" ] && [ -f "$DB" ]; then
  mkdir -p "$APP/backups"
  BK="$APP/backups/db-$(date +%F-%H%M%S).sqlite3"
  if command -v sqlite3 >/dev/null; then sqlite3 "$DB" ".backup '$BK'"; else cp "$DB" "$BK"; fi
  echo "✓ نسخة احتياطية: $BK"
  ls -1t "$APP/backups"/db-*.sqlite3 2>/dev/null | tail -n +"$((KEEP_BACKUPS+1))" | xargs -r rm -f
else
  echo "⚠ لم أجد ملف قاعدة SQLite — تخطّي النسخ الاحتياطي."
fi

# --- 4) السحب + التبعيات + الأصول + الهجرة + الستاتيك ---
git pull --ff-only origin "$BRANCH"
"$PIP" install -q -r requirements.txt
npm ci --silent
SITE_URL="$SITE_URL" npm run assets:build
npm run css:build
"$PY" manage.py migrate --noinput
"$PY" manage.py collectstatic --noinput
"$PY" manage.py check

# --- 5) إعادة التشغيل + فحص صحّة ---
sudo systemctl restart "$SERVICE"
sleep 2
CODE="$(curl -s -o /dev/null -w '%{http_code}' \
        -H 'X-Forwarded-Proto: https' -H "Host: ${SITE_URL#https://}" \
        "$HEALTH_URL" || echo 000)"
if [ "$CODE" = "200" ]; then
  echo "✓ تم النشر بنجاح — $SERVICE يعمل (HTTP $CODE)."
else
  echo "⚠ أُعيد التشغيل لكن الفحص الداخلي أعاد HTTP $CODE." >&2
  echo "  راجِع: sudo journalctl -u $SERVICE -n 50 --no-pager" >&2
  exit 1
fi
