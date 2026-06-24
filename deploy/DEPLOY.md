# نشر elzant.com على VPS (Ubuntu + Gunicorn + Nginx + Certbot)

دليل تنفيذ من الصفر. شغّل الأوامر على السيرفر بمستخدم لديه `sudo`.
**القاعدة:** SQLite (WAL) · الخادم: Gunicorn خلف Nginx · TLS عبر Let's Encrypt.

> **متطلب مسبق حرج:** Django 6 يتطلب **Python ≥ 3.12**.
> - Ubuntu **24.04** يأتي بـ Python 3.12 افتراضياً ✅
> - Ubuntu **22.04** فيه 3.10 → ثبّت 3.12: `sudo add-apt-repository -y ppa:deadsnakes/ppa && sudo apt install -y python3.12 python3.12-venv`

> **DNS:** قبل خطوة SSL، اضبط سجلّي A لـ `elzant.com` و`www.elzant.com` نحو IP السيرفر، وتأكّد من انتشارهما (`dig +short elzant.com`).

---

## 1) حزم النظام
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.12 python3.12-venv git nginx ufw
# Node.js 20 LTS (لبناء CSS والأصول على السيرفر)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
# Certbot
sudo apt install -y certbot python3-certbot-nginx
```

## 2) مستخدم التطبيق والمجلدات
```bash
sudo adduser --disabled-password --gecos "" elzant
sudo mkdir -p /srv/elzant && sudo chown elzant:elzant /srv/elzant
sudo chmod 755 /srv/elzant            # ليقرأ Nginx الستاتيك
```

## 3) جلب الكود + البيئة الافتراضية + التبعيات
ادفع المستودع إلى Git ثم استنسخه (أو استخدم rsync من جهازك).
```bash
sudo -u elzant -H bash          # ادخل كمستخدم elzant
cd /srv/elzant
git clone <REPO_URL> .          # بديل: rsync من المحلي (انظر الملاحظة أسفله)
python3.12 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
npm ci
```
> **بديل rsync (إن لم يكن هناك Git remote):** من جهازك المحلي:
> ```bash
> rsync -av --exclude .venv --exclude node_modules --exclude '.git' \
>   --exclude 'db.sqlite3*' --exclude 'staticfiles' --exclude '.env' \
>   ./ elzant@SERVER_IP:/srv/elzant/
> ```

## 4) بناء الأصول وإعداد Django
```bash
# (داخل /srv/elzant ومع تفعيل .venv وكمستخدم elzant)
SITE_URL=https://elzant.com npm run assets:build   # og-image.png + qr.svg للنطاق
npm run css:build                                  # static/css/output.css

cp deploy/.env.production.example .env
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
nano .env        # الصق SECRET_KEY وتأكّد من القيم (DEBUG=False, ALLOWED_HOSTS, SITE_URL, RATELIMIT_ENABLE=True, SQLITE_PATH)

mkdir -p data                       # مكان قاعدة SQLite (SQLITE_PATH)
python manage.py migrate
python manage.py createsuperuser    # اختر كلمة مرور قوية — لن تُسجَّل في أي مكان
python manage.py collectstatic --noinput
exit                                # اخرج من مستخدم elzant
```

## 5) خدمة systemd (Gunicorn)
```bash
sudo cp /srv/elzant/deploy/elzant.service /etc/systemd/system/elzant.service
sudo systemctl daemon-reload
sudo systemctl enable --now elzant
sudo systemctl status elzant --no-pager
# فحص داخلي (يجب 200):
curl -s -o /dev/null -w "%{http_code}\n" -H "X-Forwarded-Proto: https" -H "Host: elzant.com" http://127.0.0.1:8001/
```

## 6) Nginx
```bash
sudo cp /srv/elzant/deploy/nginx-elzant.conf /etc/nginx/sites-available/elzant
sudo ln -sf /etc/nginx/sites-available/elzant /etc/nginx/sites-enabled/elzant
sudo rm -f /etc/nginx/sites-enabled/default
sudo mkdir -p /var/www/certbot
sudo nginx -t && sudo systemctl reload nginx
```

## 7) الجدار الناري
```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw --force enable
```

## 8) شهادة SSL (Let's Encrypt)
```bash
# تأكّد أن DNS يشير للسيرفر أولاً.
sudo certbot --nginx -d elzant.com -d www.elzant.com --redirect \
  -m YOUR_EMAIL@example.com --agree-tos --no-eff-email
sudo systemctl reload nginx
sudo certbot renew --dry-run        # اختبار التجديد التلقائي
```
يضيف certbot تلقائياً خادم 443 وإعادة توجيه HTTP→HTTPS. بعدها يرسل Nginx
`X-Forwarded-Proto: https` فيعمل التطبيق على HTTPS دون حلقات إعادة توجيه.

## 9) التحديثات اللاحقة (إعادة نشر)
```bash
sudo bash /srv/elzant/deploy/update.sh
```

---

## النسخ الاحتياطي (مهم — SQLite)
انسخ قاعدة البيانات دورياً (cron يومي مثلاً):
```bash
sqlite3 /srv/elzant/data/db.sqlite3 ".backup '/srv/elzant/data/backup-$(date +\%F).sqlite3'"
```

## استكشاف الأعطال
```bash
sudo journalctl -u elzant -n 100 --no-pager     # سجلّ Gunicorn/Django
sudo tail -n 100 /var/log/nginx/error.log
sudo systemctl restart elzant
```

---

## ✅ اختبارات ما بعد النشر (نفّذها على https://elzant.com)
- [ ] الصفحة الرئيسية تفتح على **https** (القفل أخضر، لا تحذير شهادة).
- [ ] `https://elzant.com` و`https://www.elzant.com` كلاهما يعمل، وHTTP يحوّل إلى HTTPS.
- [ ] الظرف الرقمي يظهر أول مرة ويُغلق ويُتذكَّر.
- [ ] العدّاد التنازلي يعمل بأرقام عربية.
- [ ] `/admin/` يفتح وتسجيل الدخول يعمل.
- [ ] إرسال تهنئة تجريبية → صفحة الشكر تظهر البطاقة.
- [ ] **تحميل البطاقة كصورة** يعمل وتظهر العربية + الخط الفاخر سليمين.
- [ ] مشاركة واتساب: على الموبايل تُشارك ملف الصورة (Web Share)؛ على غيره تنزيل + رابط نصّي.
- [ ] من الإدارة: اعتماد التهنئة → تظهر في الجدار · رفضها → تختفي.
- [ ] مشاركة `https://elzant.com` في واتساب تُظهر صورة OG والعنوان (جرّب على https://developers.facebook.com/tools/debug/).
- [ ] احذف التهنئة التجريبية من الإدارة بعد الاختبار.

## قائمة التحقق النهائية قبل مشاركة الرابط مع العائلة
- [ ] أدخلت بيانات القاعة/العنوان/الخريطة/الوقت/التاريخ الهجري من «إعدادات الزفاف».
- [ ] استبدلت صورة العروسين النائبة ([static/img/couple-placeholder.svg](../static/img/couple-placeholder.svg)).
- [ ] **ثبّتت صورة OG النهائية** ([static/img/og-image.svg](../static/img/og-image.svg) ← `npm run assets:build`) قبل أي مشاركة واسعة — واتساب يخزّنها بقوة.
- [ ] غيّرت كلمة مرور الإدارة لكلمة قوية، و`DEBUG=False`.
- [ ] فعّلت النسخ الاحتياطي الدوري لـ SQLite.
- [ ] (اختياري بعد ثبات HTTPS) فعّل HSTS: اضبط `SECURE_HSTS_SECONDS` في [settings.py](../elzant/settings.py).
