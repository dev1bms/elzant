import secrets
from datetime import datetime
from zoneinfo import ZoneInfo

from django.db import models
from django.urls import reverse


def default_wedding_datetime():
    """Placeholder wedding moment: 22/07/2026 20:00 Cairo time.

    Returned timezone-aware so Django stores the correct UTC instant; the
    countdown derives a fixed UTC target from it. Editable later from admin.
    """
    return datetime(2026, 7, 22, 20, 0, tzinfo=ZoneInfo("Africa/Cairo"))


# Default message templates (admin-editable). Placeholders: {{ guest_name }},
# {{ invitation_link }}, {{ groom_name }}, {{ bride_name }}, {{ wedding_date }},
# {{ venue_name }} — substituted by core.utils.render_message.
DEFAULT_WHATSAPP_TEMPLATE = (
    "السلام عليكم {{ guest_name }} 🤍\n"
    "يسعدنا دعوتكم لحضور حفل زفاف {{ groom_name }} و{{ bride_name }} "
    "يوم {{ wedding_date }}{{ venue_name }}.\n"
    "هذه دعوتكم الخاصة: {{ invitation_link }}"
)
DEFAULT_EMAIL_SUBJECT = "دعوة حفل زفاف {{ groom_name }} و{{ bride_name }}"
DEFAULT_EMAIL_BODY = (
    "السلام عليكم ورحمة الله،\n\n"
    "{{ guest_name }} الكريم،\n"
    "يتشرّف أهل العروسين بدعوتكم لحضور حفل زفاف {{ groom_name }} و{{ bride_name }} "
    "يوم {{ wedding_date }}{{ venue_name }}.\n\n"
    "تفضّلوا بفتح دعوتكم الخاصة من الرابط التالي:\n{{ invitation_link }}\n\n"
    "بانتظار تشريفكم،"
)
DEFAULT_PRIVACY_NOTICE = (
    "تُستخدم بياناتكم (الاسم ورقم الهاتف والبريد إن وُجد) فقط لإدارة دعوات الزفاف "
    "والتهاني. لا يُعرَض الهاتف أو البريد أو عنوان الـIP للعامة. يُستخدم الـIP داخلياً "
    "للمراجعة وقد يُستعمل لتحديد الدولة فقط. يمكنكم طلب حذف تهنئتكم أو بيانات دعوتكم "
    "بالتواصل مع المسؤول."
)


class WeddingConfig(models.Model):
    """Event settings — a single row (singleton), editable from the admin so the
    names, texts, venue, time and message templates change without a redeploy."""

    # Names
    groom_name = models.CharField("اسم العريس", max_length=60, default="محمود")
    bride_name = models.CharField("اسم العروس", max_length=60, default="رينان")
    groom_father = models.CharField(
        "والد العريس", max_length=160,
        default="رجل الأعمال السيّد سمير محمود الزنط (أبو إبراهيم)",
    )
    bride_father = models.CharField(
        "والد العروس", max_length=160, default="الشريف فلان الفولاني",
    )
    groom_family_name_ar = models.CharField("عائلة العريس", max_length=80, blank=True, default="الزنط")
    bride_family_name_ar = models.CharField("عائلة العروس", max_length=80, blank=True)

    # Event
    wedding_datetime = models.DateTimeField(
        "موعد الزفاف (يُخزَّن بتوقيت القاهرة)", default=default_wedding_datetime
    )
    venue_name = models.CharField("اسم القاعة", max_length=120, blank=True)
    venue_address = models.CharField("العنوان", max_length=255, blank=True)
    map_url = models.URLField("رابط الخريطة", blank=True)
    hijri_text = models.CharField("التاريخ الهجري (يدوي)", max_length=60, blank=True)

    # Texts
    invitation_intro_text = models.TextField(
        "نص الدعوة (سطر تمهيدي)", blank=True,
        default="يتشرّفان بدعوتكم لمشاركتهما فرحة العمر",
    )
    privacy_notice_short = models.TextField("إشعار الخصوصية المختصر", blank=True, default=DEFAULT_PRIVACY_NOTICE)

    # Message templates
    default_whatsapp_message_template = models.TextField("قالب رسالة واتساب", blank=True, default=DEFAULT_WHATSAPP_TEMPLATE)
    default_email_subject = models.CharField("عنوان بريد الدعوة", max_length=200, blank=True, default=DEFAULT_EMAIL_SUBJECT)
    default_email_body_template = models.TextField("قالب بريد الدعوة", blank=True, default=DEFAULT_EMAIL_BODY)

    class Meta:
        verbose_name = "إعدادات الزفاف"
        verbose_name_plural = "إعدادات الزفاف"

    def __str__(self):
        return f"{self.groom_name} & {self.bride_name}"

    def save(self, *args, **kwargs):
        self.pk = 1  # enforce a single row
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


def generate_invitation_token():
    return secrets.token_urlsafe(16)


class WeddingGuest(models.Model):
    """An invited guest with a private, unguessable invitation link."""

    class Group(models.TextChoices):
        GROOM_FAMILY = "groom_family", "عائلة العريس"
        BRIDE_FAMILY = "bride_family", "عائلة العروس"
        FRIENDS = "friends", "أصدقاء"
        COLLEAGUES = "colleagues", "زملاء"
        GENERAL = "general", "ضيوف عامون"

    class Status(models.TextChoices):
        DRAFT = "draft", "مسودة"
        READY = "ready", "جاهزة"
        SENT_WHATSAPP = "sent_whatsapp", "أُرسلت عبر واتساب"
        SENT_EMAIL = "sent_email", "أُرسلت عبر البريد"
        OPENED = "opened", "فُتحت"
        GREETED = "greeted", "كتب تهنئة"

    full_name = models.CharField("الاسم الكامل", max_length=120)
    phone_number = models.CharField("رقم الهاتف", max_length=30, blank=True)
    email = models.EmailField("البريد الإلكتروني", blank=True)
    group = models.CharField("المجموعة", max_length=20, choices=Group.choices, default=Group.GENERAL, db_index=True)
    guest_count = models.PositiveSmallIntegerField("عدد الأفراد", default=1)
    notes = models.TextField("ملاحظات", blank=True)
    invitation_token = models.CharField(max_length=32, unique=True, default=generate_invitation_token, editable=False)
    invitation_status = models.CharField("الحالة", max_length=15, choices=Status.choices, default=Status.DRAFT, db_index=True)
    last_opened_at = models.DateTimeField("آخر فتح", null=True, blank=True)
    invited_at = models.DateTimeField("تاريخ الإرسال", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["full_name"]
        verbose_name = "مدعو"
        verbose_name_plural = "المدعوون"

    def __str__(self):
        return self.full_name

    def save(self, *args, **kwargs):
        if not self.invitation_token:
            self.invitation_token = generate_invitation_token()
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("invitation", args=[self.invitation_token])


class GreetingSuggestion(models.Model):
    """Ready-made greeting text the visitor can pick with one tap."""

    class Category(models.TextChoices):
        RELIGIOUS = "religious", "ديني"
        FAMILY = "family", "عائلي"
        SHORT = "short", "قصير"
        FORMAL = "formal", "رسمي"
        NICE = "nice", "جميل"

    text_ar = models.TextField("نص التهنئة", max_length=300)
    category = models.CharField("الفئة", max_length=15, choices=Category.choices, blank=True)
    active = models.BooleanField("مفعّل", default=True)
    sequence = models.PositiveSmallIntegerField("الترتيب", default=0)

    class Meta:
        ordering = ["sequence", "id"]
        verbose_name = "تهنئة جاهزة"
        verbose_name_plural = "التهاني الجاهزة"

    def __str__(self):
        return (self.text_ar[:50] + "…") if len(self.text_ar) > 50 else self.text_ar

    @classmethod
    def active_suggestions(cls):
        return list(cls.objects.filter(active=True)[:10])


class Greeting(models.Model):
    """A visitor's greeting — published to the wall immediately; the admin can
    hide (ban) anything inappropriate afterwards (post-moderation)."""

    class Status(models.TextChoices):
        PENDING = "pending", "بانتظار"   # legacy; treated as visible
        APPROVED = "approved", "ظاهرة"   # published / live
        REJECTED = "rejected", "محظورة"  # hidden by the admin

    class CardTemplate(models.TextChoices):
        NO_PHOTO_MINIMAL = "no_photo_minimal", "بدون صورة — راقٍ"
        PHOTO_STORY = "photo_story", "ستوري بالصورة"
        PHOTO_FRAME = "photo_frame", "إطار أنيق"
        FAMILY_WARM = "family_warm", "عائلي دافئ"
        PALESTINIAN_SOFT = "palestinian_soft", "لمسة فلسطينية"
        CAIRO_EVENING = "cairo_evening", "غروب القاهرة"

    PHOTO_TEMPLATES = {
        "photo_story", "photo_frame", "family_warm", "palestinian_soft", "cairo_evening",
    }

    name = models.CharField("اسم المهنّئ", max_length=60)
    message = models.TextField("نص التهنئة", max_length=500)
    # Optional photo — processed/optimized (EXIF-stripped); original never stored.
    # Published with the greeting; hidden only if the admin bans it.
    uploaded_photo = models.ImageField("الصورة", upload_to="greetings/cards/", null=True, blank=True)
    photo_thumbnail = models.ImageField(upload_to="greetings/thumbs/", null=True, blank=True)
    card_template = models.CharField(
        "قالب البطاقة", max_length=20, choices=CardTemplate.choices,
        default=CardTemplate.NO_PHOTO_MINIMAL,
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.APPROVED, db_index=True
    )
    # Linked when the greeting was written from a guest's private invitation link.
    guest = models.ForeignKey(
        WeddingGuest, null=True, blank=True, on_delete=models.SET_NULL, related_name="greetings"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    # When it went live (set on creation; greetings publish immediately).
    approved_at = models.DateTimeField(null=True, blank=True)
    # Stored for moderation only — never displayed publicly.
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    # Optional, best-effort country (only the flag/name is ever shown publicly).
    country_code = models.CharField(max_length=2, blank=True)
    country_name = models.CharField(max_length=80, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "تهنئة"
        verbose_name_plural = "التهاني"

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"

    @property
    def country_flag(self):
        """Regional-indicator flag emoji from the 2-letter country code, or ''."""
        code = (self.country_code or "").strip().upper()
        if len(code) != 2 or not code.isalpha():
            return ""
        return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in code)

    @property
    def has_photo(self):
        return bool(self.uploaded_photo)

    @property
    def is_hidden(self):
        """True when the admin has banned/hidden this greeting."""
        return self.status == self.Status.REJECTED

    def effective_template(self):
        """The template actually used to render the card.

        A photo template only applies when a photo exists; otherwise (or when a
        photo was uploaded but no photo-template was picked) fall back sensibly.
        """
        if not self.has_photo:
            return self.CardTemplate.NO_PHOTO_MINIMAL
        if self.card_template in self.PHOTO_TEMPLATES:
            return self.card_template
        return self.CardTemplate.PHOTO_FRAME

    @classmethod
    def visible(cls):
        """Greetings shown publicly on the wall — everything except banned ones."""
        return cls.objects.exclude(status=cls.Status.REJECTED).order_by("-created_at")
