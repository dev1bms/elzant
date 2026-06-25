# نشر elzant.com (Gunicorn + WhiteNoise خلف proxy/نفق موثوق)

دليل تنفيذ من الصفر. **لا يعتمد على Nginx.** التطبيق يخدم الملفات الثابتة بنفسه
عبر **WhiteNoise**، وGunicorn يستمع محلياً، ويوضَع خلف **proxy/نفق موثوق** يتولّى
HTTPS (Cloudflare Tunnel أو Caddy). شغّل الأوامر بمستخدم لديه `sudo`.

> **متطلب مسبق:** Django 6 يتطلب **Python ≥ 3.12** (Ubuntu 24.04 يأتي به؛ على 22.04
> ثبّته عبر `ppa:deadsnakes`). · القاعدة: **SQLite (WAL)**.

> **التحكّم بالمعدّل (throttling):** لا يُفرض داخل التطبيق (دلو LocMem غير موثوق عبر
> عمّال Gunicorn وقد يحجب الضيوف ظلماً). دفاعات السبام في التطبيق: CSRF + honeypot +
> حدود الطول + **المراجعة اليدوية**. أي تحديد معدّل للإنتاج مسؤولية الحافة/الـproxy
> (مثل قواعد Cloudflare WAF / النفق).

---

## 1) حزم النظام
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.12 python3.12-venv git ufw
# Node.js 20 LTS (لبناء CSS والأصول على السيرفر)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

## 2) مستخدم التطبيق والمجلدات
```bash
sudo adduser --disabled-password --gecos "" elzant
sudo mkdir -p /srv/elzant && sudo chown elzant:elzant /srv/elzant
```

## 3) جلب الكود + البيئة + التبعيات
```bash
sudo -u elzant -H bash
cd /srv/elzant
git clone <REPO_URL> .
python3.12 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
npm ci
```

## 4) بناء الأصول وإعداد Django
```bash
SITE_URL=https://elzant.com npm run assets:build
npm run css:build
cp deploy/.env.production.example .env
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
nano .env        # الصق SECRET_KEY وتأكّد من القيم (DEBUG=False, ALLOWED_HOSTS, SITE_URL, SQLITE_PATH)
mkdir -p data
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput   # WhiteNoise سيخدم staticfiles/
exit
```

## 5) خدمة systemd (Gunicorn يستمع محلياً)
Gunicorn يستمع على `127.0.0.1:8001` (انظر [gunicorn.conf.py](gunicorn.conf.py))،
وWhiteNoise يخدم `/static/`. لا حاجة لخادم ويب أمامي لخدمة الملفات.
```bash
sudo cp /srv/elzant/deploy/elzant.service /etc/systemd/system/elzant.service
sudo systemctl daemon-reload
sudo systemctl enable --now elzant
sudo systemctl status elzant --no-pager
# فحص داخلي (يجب 200):
curl -s -o /dev/null -w "%{http_code}\n" -H "X-Forwarded-Proto: https" -H "Host: elzant.com" http://127.0.0.1:8001/
```

## 6) النشر العلني + HTTPS — اختر مساراً واحداً

التطبيق يثق بترويسة `X-Forwarded-Proto` من الطبقة الأمامية (لاكتشاف HTTPS)، ويستخدم
ترويسات IP للمراجعة. **لذلك يجب ألّا يُعرَّض Gunicorn مباشرةً للإنترنت** — ضع أمامه
نفقاً/proxy موثوقاً.

### (أ) Cloudflare Tunnel — موصى به (بلا منافذ مفتوحة، TLS مجاني)
يوفّر HTTPS تلقائياً، ويضبط `X-Forwarded-Proto` و`CF-Connecting-IP` (يستفيد منها
تخزين IP للمراجعة).
```bash
# ثبّت cloudflared ثم:
cloudflared tunnel login
cloudflared tunnel create elzant
# وجّه النفق إلى التطبيق المحلي:
#   ingress:
#     - hostname: elzant.com
#       service: http://127.0.0.1:8001
#     - hostname: www.elzant.com
#       service: http://127.0.0.1:8001
#     - service: http_status:404
cloudflared tunnel route dns elzant elzant.com
cloudflared tunnel route dns elzant www.elzant.com
sudo cloudflared service install     # يشغّله كخدمة
```
التحكّم بالمعدّل/الحماية: فعّل قواعد Cloudflare (WAF / Rate Limiting) على المسار
`/` (POST).
الجدار الناري: لا تفتح منافذ واردة (النفق صادر فقط):
```bash
sudo ufw allow OpenSSH && sudo ufw --force enable
```

### (ب) Caddy — reverse proxy بـ HTTPS تلقائي
```bash
sudo apt install -y caddy
# /etc/caddy/Caddyfile:
#   elzant.com, www.elzant.com {
#       encode gzip
#       reverse_proxy 127.0.0.1:8001
#   }
sudo systemctl reload caddy
sudo ufw allow OpenSSH && sudo ufw allow 80,443/tcp && sudo ufw --force enable
```
Caddy يضبط `X-Forwarded-Proto` و`X-Forwarded-For` تلقائياً.

### (ج) Nginx + Certbot — خيار اختياري/قديم
ملف مثال جاهز في [nginx-elzant.conf](nginx-elzant.conf) (يخدم `/static/` مباشرةً
ويمرّر الباقي لـ 127.0.0.1:8001) مع `certbot --nginx`. **غير مطلوب** لأن WhiteNoise
يخدم الملفات؛ استخدمه فقط إن كان لديك Nginx بالفعل.

## 7) التحديثات اللاحقة (إعادة نشر)
```bash
sudo bash /srv/elzant/deploy/update.sh
```

---

## النسخ الاحتياطي (مهم — SQLite)
```bash
sqlite3 /srv/elzant/data/db.sqlite3 ".backup '/srv/elzant/data/backup-$(date +\%F).sqlite3'"
```

## استكشاف الأعطال
```bash
sudo journalctl -u elzant -n 100 --no-pager
sudo systemctl restart elzant
# Cloudflare Tunnel:  sudo journalctl -u cloudflared -n 100 --no-pager
```

---

## ✅ اختبارات ما بعد النشر (على https://elzant.com)
- [ ] الصفحة الرئيسية على **https** (القفل سليم) · HTTP يحوّل إلى HTTPS · النطاقان يعملان.
- [ ] شاشة الافتتاح تظهر وتُغلق وتُتذكَّر · العدّاد يعمل (أرقام إنجليزية).
- [ ] `/admin/` وتسجيل الدخول.
- [ ] إرسال تهنئة → صفحة الشكر تظهر البطاقة.
- [ ] **تحميل البطاقة صورة** يعمل، الأيقونة تبقى بعد الضغط، والعربية + الخطوط سليمة.
- [ ] مشاركة واتساب (Web Share على الموبايل، أو تنزيل + رابط).
- [ ] اعتماد التهنئة من الإدارة → تظهر في الجدار · رفضها → تختفي · احذف التجريبية.
- [ ] مشاركة `https://elzant.com` في واتساب تُظهر صورة OG (افحص: developers.facebook.com/tools/debug).

## قائمة التحقق النهائية قبل المشاركة
- [ ] أدخلت بيانات القاعة/العنوان/الخريطة/الوقت/الهجري + **اسم والد العروس** من «إعدادات الزفاف».
- [ ] استبدلت صورة العروسين/الخلفية وصورة OG النهائية (ثبّتها قبل المشاركة الواسعة).
- [ ] كلمة مرور إدارة قوية · `DEBUG=False` · نسخ احتياطي دوري لـ SQLite.
- [ ] فعّلت قواعد throttling على الحافة (Cloudflare/Caddy) إن أردت.
- [ ] (بعد ثبات HTTPS) فعّل HSTS: اضبط `SECURE_HSTS_SECONDS` في [settings.py](../elzant/settings.py).
