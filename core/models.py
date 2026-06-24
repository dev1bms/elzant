from datetime import datetime
from zoneinfo import ZoneInfo

from django.db import models


def default_wedding_datetime():
    """Placeholder wedding moment: 22/07/2026 20:00 Cairo time.

    Returned timezone-aware so Django stores the correct UTC instant; the
    countdown derives a fixed UTC target from it. Editable later from admin.
    """
    return datetime(2026, 7, 22, 20, 0, tzinfo=ZoneInfo("Africa/Cairo"))


class WeddingConfig(models.Model):
    """Event settings — a single row (singleton), editable from the admin so
    the venue/time can change without a redeploy."""

    groom_name = models.CharField("اسم العريس", max_length=60, default="محمود")
    bride_name = models.CharField("اسم العروس", max_length=60, default="رينان")
    groom_father = models.CharField(
        "والد العريس", max_length=160,
        default="رجل الأعمال السيّد سمير محمود الزنط (أبو إبراهيم)",
    )
    bride_father = models.CharField(
        "والد العروس", max_length=160, default="الشريف فلان الفولاني",
    )
    wedding_datetime = models.DateTimeField(
        "موعد الزفاف (يُخزَّن بتوقيت القاهرة)", default=default_wedding_datetime
    )
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
        self.pk = 1  # enforce a single row
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Greeting(models.Model):
    """A visitor's greeting — shown on the wall only after approval."""

    class Status(models.TextChoices):
        PENDING = "pending", "قيد المراجعة"
        APPROVED = "approved", "معتمد"
        REJECTED = "rejected", "مرفوض"

    name = models.CharField("اسم المهنّئ", max_length=60)
    message = models.TextField("نص التهنئة", max_length=500)
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    # Stored for moderation / anti-spam only — never displayed publicly.
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "تهنئة"
        verbose_name_plural = "التهاني"

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"

    @classmethod
    def approved(cls):
        return cls.objects.filter(status=cls.Status.APPROVED).order_by(
            "-approved_at", "-created_at"
        )
