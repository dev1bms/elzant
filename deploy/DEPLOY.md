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

## 7) الوسائط (صور التهاني المرفوعة) — مهم

صور الضيوف تُحفظ في `MEDIA_ROOT` خارج Git وخارج `staticfiles/`. WhiteNoise يخدم
الملفات الثابتة فقط ولا يخدم وسائط المستخدمين، فيجب تأمين خدمة `/media/` صراحةً
وإلا ظهرت صور مكسورة وتعذّر على الإدارة مراجعتها وفشل تصدير البطاقة (يحتاج الصورة
من نفس الأصل).

```bash
# مجلد دائم منسوخ احتياطياً (مملوك لمستخدم التطبيق):
sudo install -d -o elzant -g elzant /srv/elzant/media
```
في `/srv/elzant/.env`:
```
MEDIA_ROOT=/srv/elzant/media
# SERVE_MEDIA=True  ← الافتراضي؛ Django يخدم /media/ تلقائياً فتعمل الصور مباشرةً
```

**افتراضياً `SERVE_MEDIA=True`** فيخدم Django المسار `/media/` بنفسه — تعمل الصور
على أي مسار نشر دون إعداد إضافي (مقبول لموقع منخفض الحركة ومُخزَّن على Cloudflare).
الحجم الأقصى للرفع 10MB؛ نفق Cloudflare يسمح به افتراضياً. لكفاءة أعلى يمكن أن يخدم
الوسيط `/media/` بدل Django (واضبط حينها `SERVE_MEDIA=False`):
- **Caddy:**
  ```
  elzant.com, www.elzant.com {
      encode gzip
      handle_path /media/* { root * /srv/elzant/media; file_server }
      reverse_proxy 127.0.0.1:8001
  }
  ```
- **Nginx:** ملف المثال [nginx-elzant.conf](nginx-elzant.conf) يحوي
  `location /media/` و`client_max_body_size 12m` (يتجاوز حدّ الـ10MB).

النسخ الاحتياطي: انسخ `/srv/elzant/media/` مع قاعدة البيانات (انظر الأسفل).

## 8) التحديثات اللاحقة (إعادة نشر)
شغّل السكربت **كصاحب المشروع** (لا كـ root) — يستدعي `sudo` فقط لإعادة تشغيل الخدمة:
```bash
bash deploy/update.sh
```
يكتشف مجلد المشروع والبيئة (`venv/` أو `.venv/`) تلقائياً، يرفض العمل مع تعديلات غير مُلتزَمة، يأخذ **نسخة احتياطية من قاعدة SQLite قبل الهجرة** (في `backups/`)، ثم يبني الأصول ويهاجر ويجمع الستاتيك ويعيد تشغيل الخدمة مع فحص صحّة. عند اختلاف الإعداد غيّر: `ELZANT_SERVICE` · `ELZANT_HEALTH_URL` · `ELZANT_SITE_URL`.

---

## النسخ الاحتياطي (مهم — SQLite + الوسائط)
```bash
sqlite3 /srv/elzant/data/db.sqlite3 ".backup '/srv/elzant/data/backup-$(date +\%F).sqlite3'"
# الصور المرفوعة:
tar czf /srv/elzant/data/media-$(date +\%F).tar.gz -C /srv/elzant media
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

---

## دعوات واتساب (عبر Twilio) + اللوحة العائلية

طبقة الدعوات تُرسِل عبر **Twilio** (Content Templates + status callbacks موقّعة). تبدأ في **الوضع الآمن** (`enabled=False`) فلا يُرسَل شيء فعلياً حتى تُفعّلها.

> **دليل بصري كامل خطوة بخطوة** (من إنشاء حساب Twilio حتى الإرسال): `docs/whatsapp-setup-guide.html`.

**1) كل الإعدادات والاعتماد من الأدمن** (لا حاجة لأي `.env`): افتح `/admin/ → إعدادات واتساب` وأدخِل **Account SID** و**Auth Token** (مقنّع، superuser فقط)، ورقم واتساب المُرسِل (مثل `+14155238886` للـSandbox) أو **Messaging Service SID**، و**Content SID** (`HX…`)، ورمز الدولة (مصر=`20`). ⚠️ الـ Auth Token يُخزَّن في قاعدة البيانات — احمِ ملف SQLite ونسخه الاحتياطية.

**2) قالب المحتوى (Content Template) في Twilio:** أنشئه في Content Template Builder بمتغيّرين — `{{1}}` = اسم المدعو، `{{2}}` = رابط الدعوة — واعتمِده لواتساب، وانسخ الـ Content SID. يمرّر النظام `{"1": الاسم, "2": /i/<token>/}` تلقائياً.

**3) Status Callback — تلقائي:** يُرفِق النظام مع كل رسالة العنوان `https://elzant.com/webhooks/twilio/`؛ يتحقّق من توقيع `X-Twilio-Signature` بالـ Auth Token ويرفض غير الموقّع بـ 403. تأكّد فقط أن `SITE_URL=https://elzant.com` بالضبط وأن الموقع خلف HTTPS.

**4) اختبار قبل التفعيل:** (للـSandbox: أرسل `join <code>` من رقمك أولاً) أضف «رقم اختبار الإرسال» ثم زر **«إرسال رسالة اختبار»** (الوضع الآمن يُحاكي فقط). بعد اعتماد القالب فعّل الإرسال الحيّ وأرسل لرقمك، وتابِع انتقال الحالة إلى «سُلّمت/قُرئت/فُتح».

**5) حسابات المُرسِلين (اللوحة `/panel/`):** لكل فرد من العائلة أنشئ مستخدم Django ثم **«مُرسِل (عائلة)»** (`InviterProfile`) بالاسم الظاهر والجهة. فعّل **«يرى كل المدعوين»** لمن يحتاج. من لا يملك `InviterProfile` (ولا superuser) لا يدخل اللوحة.

> التكلفة: رسوم Twilio لكل رسالة + رسوم واتساب حسب فئة القالب ودولة المُستقبِل (Utility أرخص). أرسل لمدعوّين معروفين فقط وراقب جودة الرقم لتفادي الحظر.
