# elzant.com — موقع زفاف محمود ورينان

موقع زفاف عربي (RTL) فاخر مبني على **Django 6 + SQLite + Tailwind CSS v4**.
القلب: ترك التهاني + توليد بطاقة تهنئة قابلة للمشاركة + جدار تهاني خاضع للمراجعة.

## المتطلبات
- Python 3.14 (بيئة `.venv` جاهزة) · Node.js + npm (لبناء Tailwind والأصول)

## التشغيل محلياً
```bash
# 1) تفعيل البيئة وتثبيت تبعيات بايثون
source .venv/bin/activate
pip install -r requirements.txt

# 2) تبعيات الواجهة + بناء CSS والأصول
npm install
npm run css:build          # ينتج static/css/output.css
npm run assets:build       # يولّد og-image.png من og-image.svg

# 3) قاعدة البيانات وحساب الإدارة
python manage.py migrate
python manage.py createsuperuser

# 4) التشغيل
python manage.py runserver
```
الموقع على http://127.0.0.1:8000 ولوحة الإدارة على http://127.0.0.1:8000/admin/

أثناء تطوير الواجهة: `npm run css:watch` لإعادة بناء CSS تلقائياً.

## الإعداد (.env)
انسخ `.env.example` إلى `.env` واملأ القيم. ولّد مفتاحاً:
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```
| المتغيّر | الغرض |
|---|---|
| `SECRET_KEY` | مفتاح Django السري (إلزامي) |
| `DEBUG` | `True` للتطوير، `False` للإنتاج |
| `ALLOWED_HOSTS` | مضيفو الإنتاج (مفصولون بفواصل) |
| `CSRF_TRUSTED_ORIGINS` | أصول CSRF الموثوقة (https) |
| `SITE_URL` | رابط الموقع المعتمد (لروابط Open Graph) |
| `RATELIMIT_ENABLE` | تفعيل حدّ معدّل إرسال التهاني (إنتاج) |

## إدارة المحتوى
- **تفاصيل المناسبة:** لوحة الإدارة ← «إعدادات الزفاف» (اسم القاعة، العنوان، رابط الخريطة، الموعد، التاريخ الهجري).
- **مراجعة التهاني:** لوحة الإدارة ← «التهاني» ← تحديد ← «اعتماد المحدد» / «رفض المحدد». لا تظهر أي تهنئة على الجدار قبل الاعتماد.

## النشر على VPS
دليل النشر الكامل (Ubuntu + Gunicorn + Nginx + Certbot + SQLite) في
**[deploy/DEPLOY.md](deploy/DEPLOY.md)**، وملفات الخدمة في مجلد [deploy/](deploy).
للتحديث بعد النشر: `sudo bash /srv/elzant/deploy/update.sh`.

تذكيرات سريعة:
- `DEBUG=False` · `ALLOWED_HOSTS=elzant.com,www.elzant.com` · `SITE_URL=https://elzant.com` · `RATELIMIT_ENABLE=True`.
- `npm run assets:build` ثم `npm run css:build` ثم `collectstatic` قبل التشغيل.
- ثبّت `og:image` قبل المشاركة الواسعة (واتساب يخزّنها بقوة).
- فعّل HSTS (`SECURE_HSTS_SECONDS`) بعد تأكيد HTTPS.
