# REVIEW.md — مراجعة معمارية لـ elzant.com (قبل طبقة الدعوات)

> المرحلة 1 من `GOAL.md`. الغرض: فهم موثّق للمشروع قبل أي تعديل، وتحديد ما هو **مبني مسبقاً وقابل لإعادة الاستخدام** ونقاط المخاطرة — قبل بناء طبقة دعوات واتساب واللوحة العائلية.

## 1) خريطة معمارية موجزة

- تطبيق Django واحد: **`core`** داخل مشروع `elzant`. Django 6.0.6 · Python 3.14 · SQLite (WAL) · Tailwind v4 (بلا `tailwind.config.js`).
- **الواجهة العامة أربعة مسارات فقط** (`core/urls.py`): `home` (`/`)، `thank_you` (`/tahnia/shukran/`)، `invitation` (`/i/<token>/`)، `privacy` (`/privacy/`). كل شيء آخر هو **الأدمن**، وهو سطح إدارة المحتوى بالكامل.
- **الإعدادات** (`elzant/settings.py`): تُقرأ من `.env` عبر `django-environ`؛ `SECRET_KEY` من `os.environ` مباشرة (لأن `$` يُفسَّر كمرجع متغيّر). أمان يتشدّد آلياً عند `DEBUG=False` (SSL redirect، كوكيز آمنة، `SECURE_PROXY_SSL_HEADER`). HSTS=0 حتى تأكيد HTTPS.
- **WhiteNoise** يخدم الستاتيك (تخزين مضغوط/مُجزّأ في الإنتاج). **`/media/`** له مسار مستقل في `elzant/urls.py` (خدمة بالمسار بلا مصادقة — مهم أمنياً للتهاني).
- **النشر:** Gunicorn خلف Cloudflare Tunnel (بروكسي موثوق). المسار العام الآمن هذا **مناسب لاستقبال webhook من Meta**. ملفات النشر جاهزة: `deploy/DEPLOY.md`، `gunicorn.conf.py`، `elzant.service`، `nginx-elzant.conf`، `.env.production.example`.
- **TZ = Africa/Cairo، USE_TZ=True** — العدّاد وموعد الزفاف يعتمدان توقيت القاهرة (خزّن datetimes واعية).

## 2) جرد النماذج وحقولها (`core/models.py`)

| النموذج | الطبيعة | الحقول الأساسية |
|---|---|---|
| **`WeddingConfig`** | Singleton (`pk=1`, `.get()`) | الأسماء، الآباء، `wedding_datetime`، القاعة/الخريطة، النصوص، و**قوالب الرسائل**: `default_whatsapp_message_template`، `default_email_subject`، `default_email_body_template`. مُعرَّض لكل قالب عبر context processor باسم `config`. |
| **`WeddingGuest`** | مدعو | `full_name`، `phone_number` (نص حر)، `email`، `group` (choices)، `guest_count`، `invitation_token` (`secrets.token_urlsafe(16)`، unique، غير قابل للتحرير)، `invitation_status` (Status: draft→ready→sent_whatsapp→sent_email→opened→greeted)، `last_opened_at`، `invited_at`، `created_at/updated_at`. له `get_absolute_url()` → `invitation`. |
| **`Greeting`** | تهنئة (post-moderation) | `name`، `message`، `uploaded_photo`+`photo_thumbnail` (ImageField)، `card_template` (choices)، `status` (pending/approved/rejected؛ يُنشَر APPROVED فوراً)، `guest` FK (SET_NULL)، `ip_address` (للمراجعة فقط)، `country_code/name`. دوال: `hide()` (يحذف ملفّي الصورة + يعلّم rejected)، `visible()` (استثناء المحظور)، `effective_template()`. إشارة `post_delete` تنظّف الملفات. |
| **`GreetingSuggestion`** | تهاني جاهزة | `text_ar`، `category`، `active`، `sequence`. `active_suggestions()` أول 10. |

**دورة حالة `WeddingGuest.Status` موجودة بالفعل** وتشمل `SENT_WHATSAPP` و`OPENED` و`GREETED` — نبني عليها لا نستبدلها.

## 3) مسارات الـ URLs الحالية

- عامة: `home`, `thank_you`, `invitation` (`i/<str:token>/`), `privacy`.
- `admin/` — كامل سطح الإدارة.
- `/media/…` — عبر `re_path`+`serve` (DEBUG) أو `SERVE_MEDIA` (إنتاج).
- **لا يوجد بلوبرنت مصادَق للمستخدمين بعد** — طبقة اللوحة العائلية ستكون أول واجهة `login_required`.

## 4) تدفّق إرسال التهنئة (المرجع لإعادة الاستخدام)

`views.home` POST → `GreetingForm` يتحقّق (honeypot `website`، حدود الطول) → صورة اختيارية عبر `imaging.process_image` (تجريد EXIF، إعادة ترميز، thumbnail، أسماء `secrets`) → تُحفظ التهنئة **APPROVED فوراً** + IP + دولة best-effort → بيانات البطاقة في `request.session["card"]` (لا الـpk) → redirect لـ `thank_you` (يستهلكها مرة). القادم من `/i/<token>/` يُخزَّن توكنه في الجلسة فتُربط تهنئته بالمدعو وتقلبه إلى `GREETED`.

`invitation(request, token)`: **يضبط `last_opened_at` والحالة `opened`** ويخزّن التوكن في الجلسة. → **تتبّع الفتح جاهز بالفعل**؛ نضيف فوقه تتبّع تسليم/قراءة واتساب.

## 5) اللبنات الجاهزة القابلة لإعادة الاستخدام (لا تُكرَّر — §2 في GOAL)

- **`core/utils.render_message(template, mapping)`** — يستبدل `{{ key }}` (نص فقط، لا تنفيذ). المتغيّرات: `guest_name`, `invitation_link`, `groom_name`, `bride_name`, `wedding_date`, `venue_name`. **يُعاد استخدامه لبناء نص القالب/المعاينة الحيّة.**
- **`core/admin._message_context / _whatsapp_message / _email_subject_body`** — يبنيان سياق الرسالة والرابط المطلق (`SITE_URL + get_absolute_url`). منطق يُنقل/يُشارَك مع طبقة الإرسال الآلي.
- **`get_client_ip` / `country_from_request` / `flag_from_code`** — ترتيب رؤوس البروكسي الموثوق (CF-Connecting-IP أولاً). نفس الفلسفة ستُطبَّق على تحقّق الـwebhook.
- **`invitation_token`** لكل مدعو (`secrets.token_urlsafe(16)`) — أساس زر الرابط الديناميكي في قالب واتساب.
- **`invitation_status` + `last_opened_at` + `invited_at`** — قُمع الحالة موجود؛ نضيف `wa_status` كإشارة تسليم مكمّلة.
- **قوالب الرسائل في `WeddingConfig`** (قابلة للتعديل من الأدمن) — نموذج نتبعه لـ `WhatsAppConfig`/`WhatsAppTemplate`.
- **الأدمن كمجموعة أدوات المشغّل** — أنماط الإجراءات المجمّعة، معاينة `format_html`، أزرار جاهزة.
- **نظام التصميم في `tailwind/input.css`** — رموز اللون («Sunset on the Mediterranean»)، `.btn-primary`/`.btn-ghost`، `.panel`، `.field`، `.chip`، بطاقات، حركة تحترم `prefers-reduced-motion`. **نبني اللوحة فوقه بلا CDN** (build قائم عبر `npm run css:build`).

## 6) نقاط المخاطرة / الديون التقنية

1. **`phone_number` نص حر** بلا تطبيع — كشف التكرار يحتاج حقلاً مطبّعاً جديداً `phone_e164`. (خطر تكرار الأرقام.)
2. **لا مصادقة مستخدمين حتى الآن** — اللوحة تُدخل حسابات Django + `InviterProfile` + عزل queryset. لازم فرض العزل في الفيو لا القالب.
3. **`/media/` عام بلا مصادقة** — أي QR/أصول جديدة يجب ألا تُسرِّب بيانات حسّاسة؛ لا تُخزَّن أرقام هواتف في مسارات عامة.
4. **`SERVE_MEDIA`/`APPEND_SLASH`** — زر الرابط الديناميكي في واتساب حسّاس للشرطة المائلة؛ `i/<str:token>/` ينتهي بشرطة و`APPEND_SLASH` الافتراضي True، لكن يجب اختبار الرابط النهائي فعلياً (بعض العملاء لا يتبعون 301). قد نضيف نمطاً يتسامح مع/بدون `/`.
5. **الأسرار:** التوكن/App Secret/Verify Token في `.env` فقط — لا في قاعدة البيانات، لا في اللوجات، لا في Git. يجب تحديث `.env.example` و`deploy/.env.production.example`.
6. **الـwebhook يتطلّب HTTPS عاماً** — متوفّر عبر Cloudflare Tunnel؛ يجب `csrf_exempt` + تحقّق توقيع HMAC-SHA256 + `CSRF_TRUSTED_ORIGINS`، وإرجاع 200 سريعاً.
7. **الاعتماديات:** `requests` و`qrcode` (Python) **غير مثبّتة** في البيئة. القرار: استخدام `urllib` من المكتبة القياسية لاستدعاء Graph API (مع timeout) لتفادي اعتمادية جديدة؛ وحل الـQR بلا اعتمادية إلزامية جديدة (أو إضافتها بوعي في مرحلة التلميع).
8. **تطبيع الأرقام** مصدر أخطاء شائع (أصفار بادئة، `00`، رمز دولي مزدوج) — يحتاج اختبارات وحدة (مصر/فلسطين/الأردن).
9. **`core/tests.py` هيكل فارغ** — نكتب أول suite حقيقي لهذه الميزة (بوّابة إلزامية §10).
10. **التكلفة/الجودة** (واتساب): فوترة لكل رسالة، قوالب Utility أرخص، مراقبة Quality Rating، البدء بـ`enabled=False` (وضع آمن بلا تكلفة).

## 7) خطة البناء (مطابقة §13 من GOAL)

1. ✅ هذه المراجعة (`docs/REVIEW.md`).
2. المخطّط + الهجرات + الأدمن (توسعة `WeddingGuest` + `InviterProfile` + `WhatsAppConfig` + `WhatsAppTemplate` + `MessageLog`).
3. وحدة `core/whatsapp.py` + webhook خلف `enabled=False` + زر اختبار.
4. اللوحة العائلية (دخول + إضافة + كشف تكرار + إرسال + قوائم دعواتي/الكل).
5. تتبّع الحالة والعرض (خطوط زمنية + عدّادات).
6. التلميع البصري + QR.
7. الخصوصية + النصوص + `.env` + `check --deploy` + الاختبارات.

**قرارات تقنية مثبّتة في هذه المراجعة:** `urllib` بدل `requests`؛ الأسرار في `.env` فقط؛ العزل في طبقة الفيو؛ البناء فوق نظام التصميم القائم؛ هجرات إضافية غير هدّامة (لا حذف حقول).
