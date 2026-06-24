# خطة تنفيذ موقع elzant.com — النسخة الأولى (MVP)

**المناسبة:** زفاف محمود ورينان · **التاريخ:** 22/07/2026 · **المكان:** القاهرة
**التقنية:** Django + PostgreSQL + Tailwind CSS · عربي بالكامل (RTL) · بنية جاهزة لإضافة الإنجليزية لاحقاً
**الجمهور:** هذا المستند مكتوب ليُسلَّم مباشرة إلى Claude Code كمواصفة تنفيذ.

---

## 0) سير العمل المطلوب (مهم لـ Claude Code)

اتبع تسلسلاً متدرّجاً ولا تقفز للتنفيذ:
`Discovery → Planning → Implementation → Review → Commit`

- لا تنفّذ أي أمر مدمّر (حذف بيانات/مجلدات/قواعد) إطلاقاً دون شرح واضح وانتظار تأكيد صريح.
- بعد كل مرحلة، توقّف واعرض ملخّصاً قصيراً للتغييرات قبل الانتقال للتي تليها.
- الكود والمعرّفات بالإنجليزية، والنصوص الظاهرة للمستخدم بالعربية.

---

## 1) Goal

إطلاق نسخة أولى **فاخرة وعملية** من `elzant.com` تخلّد زفاف محمود ورينان، مع التركيز على قلب المشروع:
**ترك التهاني + توليد بطاقة تهنئة أنيقة قابلة للمشاركة + جدار تهاني خاضع لمراجعة الإدارة.**
يجب أن يعمل الموقع محلياً بجودة إنتاجية، وأن تكون إعداداته جاهزة للنشر على VPS لاحقاً (النشر خارج نطاق هذه المرحلة).

---

## 2) Scope

| داخل النطاق (MVP) | خارج النطاق (نسخ لاحقة) |
|---|---|
| واجهة Hero: صورة العروسين + الاسمان + عدّاد تنازلي | RSVP / تأكيد الحضور |
| تفاصيل الحفل + رابط خريطة | رفع صور/فيديو من المستخدمين |
| نموذج تهنئة (اسم + رسالة) | الرسائل الصوتية |
| بطاقة تهنئة HTML/CSS + تحميلها كصورة (JS) | اللغة الإنجليزية (لكن البنية تدعمها) |
| جدار تهاني — يُعرض المعتمد فقط | توليد البطاقة سيرفر-سايد (Pillow) |
| لوحة إدارة لمراجعة/اعتماد/رفض التهاني | حسابات مستخدمين / تسجيل دخول للزوار |
| Open Graph metadata (مشاركة واتساب) | إشعارات / بريد |
| ظرف رقمي خفيف قابل للتخطّي | تعدد اللغات الفعلي |
| RTL كامل + خطوط عربية فاخرة | |

---

## 3) Project structure

```
elzant/
├── manage.py
├── requirements.txt
├── .env.example
├── .gitignore
├── config/                 # مشروع Django
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── core/                   # التطبيق الرئيسي
│   ├── models.py
│   ├── forms.py
│   ├── views.py
│   ├── admin.py
│   ├── urls.py
│   ├── context_processors.py
│   ├── utils.py            # get_client_ip ...
│   └── migrations/
├── templates/
│   ├── base.html           # head + OG + RTL + الخطوط
│   ├── core/
│   │   ├── home.html
│   │   ├── thank_you.html
│   │   └── partials/
│   │       ├── _hero.html
│   │       ├── _countdown.html
│   │       ├── _details.html
│   │       ├── _greeting_form.html
│   │       ├── _wall.html
│   │       ├── _card.html       # قالب البطاقة القابلة للمشاركة
│   │       ├── _share.html
│   │       └── _envelope.html
├── static/
│   ├── css/                # مخرجات Tailwind
│   ├── js/
│   │   ├── countdown.js
│   │   └── card.js         # توليد الصورة + المشاركة
│   ├── fonts/              # خطوط عربية (إن لم تُحمَّل من Google Fonts)
│   └── img/
│       └── og-image.png    # صورة Open Graph 1200×630
└── tailwind/               # مصدر Tailwind (input.css + config)
```

---

## 4) إعدادات المشروع (settings)

- **قاعدة البيانات:** PostgreSQL عبر `psycopg[binary]`، القيم من متغيّرات بيئة (`.env`) — لا تكتب أسراراً في الكود.
- **التوقيت (حرج للعدّاد):**
  ```python
  TIME_ZONE = "Africa/Cairo"
  USE_TZ = True
  ```
- **بنية الترجمة جاهزة (دون تفعيل الإنجليزية فعلياً الآن):**
  ```python
  USE_I18N = True
  LANGUAGE_CODE = "ar"
  LANGUAGES = [("ar", "العربية"), ("en", "English")]   # en placeholder
  # أضف django.middleware.locale.LocaleMiddleware بعد SessionMiddleware
  LOCALE_PATHS = [BASE_DIR / "locale"]
  ```
  لفّ النصوص الظاهرة بـ `{% trans %}` / `gettext` حيث يكون عملياً، حتى تصبح إضافة الإنجليزية لاحقاً مسألة ترجمة لا إعادة هيكلة. لا داعي لترجمة كل سلسلة الآن — يكفي تفعيل البنية + لفّ النصوص الرئيسية.
- **الستاتيك:** WhiteNoise للإنتاج (متوافق مع خبرتك السابقة)، `STATIC_ROOT`, `collectstatic`.
- **إعدادات الإنتاج (جهّزها لكن لا تكسر التطوير المحلي — اقرأها من البيئة):**
  ```python
  DEBUG = env.bool("DEBUG", default=False)
  ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])
  CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])
  SECURE_SSL_REDIRECT = not DEBUG
  SESSION_COOKIE_SECURE = not DEBUG
  CSRF_COOKIE_SECURE = not DEBUG
  SECURE_HSTS_SECONDS = 0  # فعّلها بعد التأكد من HTTPS على الـ VPS
  ```
- **Context processor:** أضف `core.context_processors.wedding` لإتاحة `config` و`canonical_url`/`og` في كل القوالب.

---

## 5) Models

نموذجان فقط: `Greeting` للتهاني، و`WeddingConfig` (singleton) لتفاصيل المناسبة (يجعل تعديل القاعة/الوقت من لوحة الإدارة دون إعادة نشر).

```python
# core/models.py
from django.db import models
from django.utils import timezone


class WeddingConfig(models.Model):
    """إعدادات المناسبة — سجل واحد فقط (singleton)."""
    groom_name = models.CharField("اسم العريس", max_length=60, default="محمود")
    bride_name = models.CharField("اسم العروس", max_length=60, default="رينان")
    wedding_datetime = models.DateTimeField("موعد الزفاف (يُخزَّن بتوقيت القاهرة)")
    venue_name = models.CharField("اسم القاعة", max_length=120, blank=True)
    venue_address = models.CharField("العنوان", max_length=255, blank=True)
    map_url = models.URLField("رابط الخريطة", blank=True)
    hijri_text = models.CharField("التاريخ الهجري (يدوي)", max_length=60, blank=True)

    class Meta:
        verbose_name = "إعدادات الزفاف"
        verbose_name_plural = "إعدادات الزفاف"

    def __str__(self):
        return f"{self.groom_name} & {self.bride_name}"

    def save(self, *args, **kwargs):
        self.pk = 1                      # يفرض سجلاً واحداً
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Greeting(models.Model):
    """تهنئة زائر — لا تظهر على الجدار إلا بعد الاعتماد."""
    class Status(models.TextChoices):
        PENDING = "pending", "قيد المراجعة"
        APPROVED = "approved", "معتمد"
        REJECTED = "rejected", "مرفوض"

    name = models.CharField("اسم المهنّئ", max_length=60)
    message = models.TextField("نص التهنئة", max_length=500)
    status = models.CharField(max_length=10, choices=Status.choices,
                              default=Status.PENDING, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)  # للمراجعة ومكافحة السبام فقط

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "تهنئة"
        verbose_name_plural = "التهاني"

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"

    @classmethod
    def approved(cls):
        return cls.objects.filter(status=cls.Status.APPROVED) \
                          .order_by("-approved_at", "-created_at")
```

> **ملاحظة خصوصية:** تخزين `ip_address` اختياري وغرضه المراجعة/مكافحة السبام فقط. إن فضّلت عدم تخزينه، احذف الحقل واكتفِ بالـ honeypot. لا يُعرض الـ IP علناً أبداً.

`makemigrations core && migrate`.

---

## 6) Pages (URLs & Views)

| المسار | الغرض | الوصول |
|---|---|---|
| `/` | الصفحة الرئيسية: Hero + عدّاد + تفاصيل + نموذج + الجدار + مشاركة | عام |
| `/tahnia/shukran/` | صفحة الشكر: تعرض بطاقة المهنّئ القابلة للتحميل/المشاركة فوراً | عام (عبر جلسة) |
| `/admin/` | لوحة المراجعة والاعتماد | الإدارة فقط |

منطق العرض — التهنئة الجديدة تُحفظ `pending`، ثم نمرّر الاسم والرسالة عبر الجلسة (لا عبر pk) لصفحة الشكر، حفاظاً على خصوصية السجلات قيد المراجعة ومنعاً لتعدادها:

```python
# core/views.py
from django.shortcuts import render, redirect
from .models import WeddingConfig, Greeting
from .forms import GreetingForm
from .utils import get_client_ip


def home(request):
    config = WeddingConfig.get()
    if request.method == "POST":
        form = GreetingForm(request.POST)
        if form.is_valid():
            g = form.save(commit=False)
            g.ip_address = get_client_ip(request)
            g.save()
            request.session["card"] = {"name": g.name, "message": g.message}
            return redirect("thank_you")
    else:
        form = GreetingForm()
    return render(request, "core/home.html", {
        "config": config,
        "form": form,
        "greetings": Greeting.approved(),
    })


def thank_you(request):
    card = request.session.pop("card", None)   # تُستهلك مرة واحدة
    if not card:
        return redirect("home")
    return render(request, "core/thank_you.html", {
        "config": WeddingConfig.get(),
        "card": card,
    })
```

> **العدّاد بتوقيت ثابت:** مرّر لحظة الزفاف كـ epoch/ISO **بتوقيت UTC** المشتق من توقيت القاهرة في `data-target` بالقالب، واحسب الفرق في JS مقابلها — حتى يرى كل الزوار نفس العدّاد بغضّ النظر عن توقيت أجهزتهم.

---

## 7) Admin

- تسجيل `Greeting` مع: عرض القائمة، فلترة بالحالة/التاريخ، بحث بالاسم/النص، و**إجراءَين جماعيين**: «اعتماد المحدد» و«رفض المحدد».
- تسجيل `WeddingConfig` كـ singleton (منع إضافة أكثر من سجل، ومنع الحذف).

```python
# core/admin.py
from django.contrib import admin
from django.utils import timezone
from .models import Greeting, WeddingConfig


@admin.register(WeddingConfig)
class WeddingConfigAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not WeddingConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Greeting)
class GreetingAdmin(admin.ModelAdmin):
    list_display = ("name", "short_message", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("name", "message")
    readonly_fields = ("created_at", "ip_address")
    actions = ("approve_selected", "reject_selected")
    list_per_page = 50

    @admin.display(description="التهنئة")
    def short_message(self, obj):
        return (obj.message[:60] + "…") if len(obj.message) > 60 else obj.message

    @admin.action(description="اعتماد المحدد")
    def approve_selected(self, request, queryset):
        n = queryset.update(status=Greeting.Status.APPROVED, approved_at=timezone.now())
        self.message_user(request, f"تم اعتماد {n} تهنئة.")

    @admin.action(description="رفض المحدد")
    def reject_selected(self, request, queryset):
        n = queryset.update(status=Greeting.Status.REJECTED)
        self.message_user(request, f"تم رفض {n} تهنئة.")
```

---

## 8) UI/UX

- **RTL كامل:** `<html dir="rtl" lang="ar">`، واستخدم الخصائص المنطقية (logical properties) ومتغيّرات Tailwind المتوافقة مع RTL.
- **Mobile-first:** الأولوية للموبايل (أغلب الزوار من واتساب)، ثم توسعة للديسكتوب.
- **الخطوط (إحساس فاخر):** خط عرض للعناوين (مثل `Amiri` أو `Aref Ruqaa`) + خط نصوص واضح (`Cairo` أو `Tajawal`). حمّلها من Google Fonts أو `@font-face` محلياً مع `font-display: swap`.
- **لوحة ألوان راقية:** قاعدة كريمية/عاجية + لمسة وردية/عنابية (burgundy/rose) كلون أساسي للأزرار + لمسة ذهبية خفيفة للزخارف. مسطّحة بلا تدرّجات صارخة.
- **Tailwind:** استخدم بناء فعلياً (Tailwind CLI أو `django-tailwind`) لا CDN — لإخراج CSS منقّى وداعم للـ RTL. عرّف الخطوط والألوان في `tailwind.config`.
- **الأقسام** (حسب الـ wireframe): ظرف رقمي خفيف ← Hero (صورة + اسمان + عدّاد) ← تفاصيل الحفل + خريطة ← نموذج التهنئة ← الجدار (المعتمد فقط) ← مشاركة (واتساب + QR) ← فوتر.
- **حركات لطيفة:** ظهور تدريجي عند التمرير، لا مبالغة، لا يضرّ الأداء.
- **العدّاد:** بارز، أربع خانات (يوم/ساعة/دقيقة/ثانية) بأرقام عربية، تحديث حي كل ثانية.

---

## 9) Card generation (قلب التجربة)

البطاقة عنصر **HTML/CSS** يُملأ بإدخال الزائر، ويُصدَّر كصورة في المتصفّح:

- **القالب:** عنصر بنسبة ثابتة (مثلاً 1080×1350 عمودي مناسب لقصص واتساب/إنستغرام، أو 1080×1080 مربّع). يحوي: «محمود & رينان» + زخرفة أنيقة + نص التهنئة + اسم المهنّئ + `elzant.com` صغيراً.
- **مكتبة التصدير:** **استخدم `modern-screenshot` (toPng) أو `html-to-image`** بدل `html2canvas` — لأنها أفضل في عرض الخطوط العربية و RTL. هذه نقطة حسّاسة، اختبرها مبكراً على نص عربي حقيقي.
  - انتظر تحميل الخطوط قبل الالتقاط: `await document.fonts.ready`.
  - ارفع الدقة: `pixelRatio: 2` (أو 3) لإخراج حادّ.
  - اسم الملف: `tahnia-elzant.png`.
- **الأزرار:**
  - «تحميل صورة» — يعمل دائماً (المسار الأضمن).
  - «مشاركة عبر واتساب» — استخدم Web Share API لمشاركة **ملف الصورة** على الأجهزة الداعمة:
    ```js
    if (navigator.canShare && navigator.canShare({ files: [file] })) {
      await navigator.share({ files: [file], title: "تهنئة" });
    } else {
      // fallback: مشاركة رابط الموقع نصياً
      window.open(`https://wa.me/?text=${encodeURIComponent("شاركت تهنئتي 🤍 " + location.origin)}`);
    }
    ```
- **مهم:** رابط `wa.me` لا يُرفِق صورة (نصّ/رابط فقط). إذا لم يدعم الجهاز مشاركة الملفات، يُنزّل المستخدم الصورة ويرفقها يدوياً — وضّح هذا في الواجهة بجملة صغيرة.
- **تحسين اختياري:** معاينة حية للبطاقة أثناء كتابة الزائر (قبل الإرسال).

---

## 10) Open Graph / المشاركة

في `base.html` ضمن `<head>` لكل صفحة:

```html
<meta property="og:type" content="website">
<meta property="og:site_name" content="elzant.com">
<meta property="og:title" content="زفاف محمود ورينان — شاركنا الفرحة">
<meta property="og:description" content="اترك تهنئتك للعروسين قبل ٢٢ يوليو ٢٠٢٦">
<meta property="og:image" content="{{ og_image_absolute_url }}">  {# 1200×630 #}
<meta property="og:url" content="{{ canonical_url }}">
<meta name="twitter:card" content="summary_large_image">
```

- صمّم `static/img/og-image.png` (صورة العروسين + الاسمان + التاريخ) بمقاس 1200×630.
- **تنبيه:** واتساب يخزّن الـ OG بقوة (cache)، فثبّت `og:image` قبل بدء المشاركة على نطاق واسع — تغييره لاحقاً صعب الانتشار.

---

## 11) Security and moderation

- **المراجعة (المتطلب الأساسي):** كل تهنئة `pending` افتراضياً، والجدار يعرض `approved` فقط — لا يظهر شيء قبل موافقتك.
- **XSS:** اعرض نص التهنئة دائماً عبر `{{ greeting.message }}` (autoescape مفعّل) — **لا تستخدم `|safe` إطلاقاً**، وكذلك داخل البطاقة. عامل الإدخال كنصّ لا كـ HTML.
- **CSRF:** مفعّل افتراضياً في Django؛ تأكّد من `{% csrf_token %}` في النموذج.
- **مكافحة السبام (خفيفة، لا تزعج المستخدم):**
  - حقل **honeypot** مخفي (`website`) يُرفض إن مُلئ.
  - حدّ معدّل اختياري بـ `django-ratelimit` (مثلاً 5 إرسالات/ساعة لكل IP) على الـ POST فقط.
- **حدود الطول:** مفروضة على `name`/`message` في الـ Model والـ Form.
- **تقسية الإدارة (للإنتاج لاحقاً):** كلمة مرور قوية، `DEBUG=False`، ضبط `ALLOWED_HOSTS`، كوكيز آمنة، HTTPS، وإمكانية تغيير مسار `/admin/`.
- **الظرف الرقمي:** طبقة/شريط خفيف **لا يحجب الموقع** — المحتوى محمّل تحته فيعمل حتى مع تعطّل JS، قابل للتخطّي، ويُتذكَّر إغلاقه عبر `localStorage` لكل زائر.

```python
# core/forms.py
from django import forms
from .models import Greeting


class GreetingForm(forms.ModelForm):
    website = forms.CharField(required=False, widget=forms.HiddenInput)  # honeypot

    class Meta:
        model = Greeting
        fields = ["name", "message"]
        widgets = {
            "name": forms.TextInput(attrs={"maxlength": 60, "placeholder": "اسمك"}),
            "message": forms.Textarea(attrs={"maxlength": 500, "rows": 4,
                                             "placeholder": "رسالتك للعروسين…"}),
        }

    def clean_website(self):
        if self.cleaned_data.get("website"):
            raise forms.ValidationError("spam")
        return ""
```

---

## 12) Expected result after implementation

عند اكتمال المرحلة، يعمل التالي محلياً (وجاهز للنشر على VPS):

- ✅ صفحة رئيسية RTL فاخرة، Mobile-first، بخطوط عربية أنيقة.
- ✅ عدّاد تنازلي حيّ يصل لـ 22/07/2026 بتوقيت القاهرة الثابت لكل الزوار.
- ✅ تفاصيل الحفل + رابط خريطة، قابلة للتعديل من لوحة الإدارة.
- ✅ نموذج تهنئة يحفظ الإدخال كـ `pending` ويحوّل لصفحة الشكر.
- ✅ صفحة شكر تولّد بطاقة HTML/CSS أنيقة قابلة للتحميل كصورة والمشاركة عبر واتساب.
- ✅ جدار تهاني يعرض **المعتمد فقط**.
- ✅ لوحة إدارة لاعتماد/رفض التهاني (إجراءات جماعية + فلترة + بحث).
- ✅ Open Graph يظهر رابط الموقع بشكل جميل عند مشاركته في واتساب.
- ✅ حماية XSS/CSRF + honeypot، وظرف رقمي خفيف لا يحجب الموقع.
- ✅ بنية i18n جاهزة لإضافة الإنجليزية لاحقاً دون إعادة هيكلة.

---

## 13) Risks / warnings

1. **عرض العربية في تصدير الصورة:** `html2canvas` ضعيف مع العربية — استخدم `html-to-image`/`modern-screenshot` + `document.fonts.ready`، واختبر مبكراً على نص عربي حقيقي.
2. **مشاركة الملف عبر Web Share:** الدعم يتفاوت (ضعيف على الديسكتوب) — اجعل «تحميل الصورة» المسار الأضمن دائماً.
3. **`wa.me` لا يُرفِق صورة:** يشارك رابطاً/نصاً فقط — وضّح ذلك للمستخدم.
4. **توقيت العدّاد:** أي خلط بين توقيت الجهاز وتوقيت القاهرة يكسر العدّاد — اعتمد لحظة UTC ثابتة مشتقة من توقيت القاهرة.
5. **التاريخ الهجري:** التحويل الآلي غير موثوق — استخدم حقل `hijri_text` اليدوي.
6. **cache واتساب لصورة OG:** ثبّت `og:image` قبل النشر الواسع.
7. **السبام:** الـ honeypot يقلّل الضجيج، لكن **المراجعة اليدوية هي خط الدفاع الأساسي**.
8. **PostgreSQL/الستاتيك على VPS:** إعدادات النشر (psycopg، collectstatic، WhiteNoise، HTTPS) تُضبط في مرحلة النشر اللاحقة.

---

## 14) Git commands

```bash
git init
git checkout -b main

# .gitignore: __pycache__/, *.pyc, .venv/, .env, *.sqlite3,
#             /staticfiles/, /media/, node_modules/, /static/css/output.css
git add .
git commit -m "chore: bootstrap Django project for elzant wedding site"

# المرحلة: النماذج والإدارة
git checkout -b feature/core-models
git add .
git commit -m "feat(core): Greeting + WeddingConfig models, migrations, admin moderation"
git checkout main && git merge --no-ff feature/core-models

# المرحلة: الواجهة الأمامية
git checkout -b feature/frontend
git add .
git commit -m "feat(ui): RTL homepage, hero, countdown, congratulations form, approved wall"
git checkout main && git merge --no-ff feature/frontend

# المرحلة: البطاقة والمشاركة و OG
git checkout -b feature/card-share
git add .
git commit -m "feat(card): shareable HTML/CSS card with image export, WhatsApp share, OG metadata"
git checkout main && git merge --no-ff feature/card-share

# المرحلة: الظرف الرقمي والتقسية
git checkout -b feature/envelope-hardening
git add .
git commit -m "feat: lightweight digital envelope; honeypot, length limits, security headers"
git checkout main && git merge --no-ff feature/envelope-hardening

git tag -a v1.0.0-mvp -m "elzant.com MVP — Mahmoud & Rinan wedding"
```

---

## 15) ترتيب البناء المقترح لـ Claude Code

1. تهيئة المشروع + `settings` (PostgreSQL، i18n جاهز، TZ القاهرة، Tailwind فعلي).
2. `Greeting` + `WeddingConfig` + migrations + admin (المراجعة).
3. `base.html` (RTL + الخطوط + OG placeholders) + `home` view (config + form + الجدار).
4. العدّاد التنازلي (لحظة القاهرة الثابتة).
5. صفحة الشكر + بطاقة HTML/CSS + تصدير الصورة + المشاركة.
6. Open Graph + تصميم `og-image.png`.
7. الظرف الرقمي (خفيف، قابل للتخطّي، لا يحجب).
8. مراجعة أمنية + تعبئة `WeddingConfig` الأولية ببيانات المناسبة.
9. مراجعة نهائية + Commits + `tag`.

> **خارج هذه المرحلة:** نشر الإنتاج على VPS (Nginx/Gunicorn، PostgreSQL، HTTPS، DNS لـ elzant.com) — يُخطَّط له بعد اعتماد الـ MVP.
