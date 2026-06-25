import csv
from urllib.parse import quote

from django.conf import settings
from django.contrib import admin
from django.db.models import Q
from django.http import HttpResponse
from django.template.defaultfilters import date as date_filter
from django.utils import timezone, translation
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .models import Greeting, GreetingSuggestion, WeddingConfig, WeddingGuest
from .utils import render_message

admin.site.site_header = "إدارة موقع زفاف محمود ورينان"
admin.site.site_title = "elzant.com"
admin.site.index_title = "لوحة التحكم"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _invitation_url(guest):
    return settings.SITE_URL.rstrip("/") + guest.get_absolute_url()


def _message_context(guest):
    config = WeddingConfig.get()
    with translation.override("ar"):
        wedding_date = date_filter(timezone.localtime(config.wedding_datetime), "l j F Y")
    return {
        "guest_name": guest.full_name,
        "invitation_link": _invitation_url(guest),
        "groom_name": config.groom_name,
        "bride_name": config.bride_name,
        "wedding_date": wedding_date,
        "venue_name": (" في " + config.venue_name) if config.venue_name else "",
    }


def _whatsapp_message(guest):
    config = WeddingConfig.get()
    return render_message(config.default_whatsapp_message_template, _message_context(guest))


def _email_subject_body(guest):
    config = WeddingConfig.get()
    ctx = _message_context(guest)
    return (
        render_message(config.default_email_subject, ctx),
        render_message(config.default_email_body_template, ctx),
    )


# --------------------------------------------------------------------------- #
# WeddingConfig (singleton)
# --------------------------------------------------------------------------- #
@admin.register(WeddingConfig)
class WeddingConfigAdmin(admin.ModelAdmin):
    fieldsets = (
        ("الأسماء", {"fields": ("groom_name", "bride_name", "groom_father", "bride_father",
                                "groom_family_name_ar", "bride_family_name_ar")}),
        ("المناسبة", {"fields": ("wedding_datetime", "venue_name", "venue_address", "map_url", "hijri_text")}),
        ("النصوص", {"fields": ("invitation_intro_text", "privacy_notice_short")}),
        ("قوالب الرسائل (placeholders: {{ guest_name }} {{ invitation_link }} {{ groom_name }} "
         "{{ bride_name }} {{ wedding_date }} {{ venue_name }})",
         {"fields": ("default_whatsapp_message_template", "default_email_subject", "default_email_body_template")}),
    )

    def has_add_permission(self, request):
        return not WeddingConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


# --------------------------------------------------------------------------- #
# WeddingGuest
# --------------------------------------------------------------------------- #
@admin.register(WeddingGuest)
class WeddingGuestAdmin(admin.ModelAdmin):
    list_display = ("full_name", "phone_number", "email", "group", "invitation_status",
                    "opened", "greeted", "guest_count")
    list_filter = ("invitation_status", "group")
    search_fields = ("full_name", "phone_number", "email")
    readonly_fields = ("invitation_token", "invitation_link", "whatsapp_link", "email_preview",
                       "last_opened_at", "invited_at", "created_at", "updated_at")
    list_per_page = 50
    actions = ("mark_ready", "mark_sent_whatsapp", "mark_sent_email",
               "send_email_invites", "export_csv", "export_links_csv")
    fieldsets = (
        ("المدعو", {"fields": ("full_name", "phone_number", "email", "group", "guest_count", "notes")}),
        ("الدعوة", {"fields": ("invitation_status", "invitation_link", "whatsapp_link", "email_preview",
                               "invitation_token")}),
        ("التتبّع", {"fields": ("last_opened_at", "invited_at", "created_at", "updated_at")}),
    )

    @admin.display(boolean=True, description="فُتحت")
    def opened(self, obj):
        return obj.last_opened_at is not None

    @admin.display(boolean=True, description="هنّأ")
    def greeted(self, obj):
        return obj.invitation_status == WeddingGuest.Status.GREETED

    @admin.display(description="رابط الدعوة")
    def invitation_link(self, obj):
        url = _invitation_url(obj)
        return format_html('<a href="{}" target="_blank" rel="noopener">{}</a>', url, url)

    @admin.display(description="رسالة واتساب جاهزة")
    def whatsapp_link(self, obj):
        msg = _whatsapp_message(obj)
        if obj.phone_number:
            phone = "".join(ch for ch in obj.phone_number if ch.isdigit())
            href = f"https://wa.me/{phone}?text={quote(msg)}"
            label = "فتح واتساب مع الرسالة"
        else:
            href = f"https://wa.me/?text={quote(msg)}"
            label = "فتح واتساب (لا رقم — أضف الرقم)"
        return format_html(
            '<a class="button" href="{}" target="_blank" rel="noopener">{}</a>'
            '<pre style="white-space:pre-wrap;margin-top:8px">{}</pre>', href, label, msg
        )

    @admin.display(description="معاينة البريد")
    def email_preview(self, obj):
        subject, body = _email_subject_body(obj)
        configured = "مُهيّأ ✓" if settings.email_is_configured() else "غير مُهيّأ (معاينة فقط)"
        return format_html(
            "<div>الإعداد: {}</div><div style='margin-top:6px'><b>{}</b></div>"
            "<pre style='white-space:pre-wrap'>{}</pre>", configured, subject, body
        )

    # ---- actions ----
    @admin.action(description="وسم: جاهزة للإرسال")
    def mark_ready(self, request, queryset):
        n = queryset.update(invitation_status=WeddingGuest.Status.READY)
        self.message_user(request, f"تم وسم {n} مدعو كجاهز.")

    @admin.action(description="وسم: أُرسلت عبر واتساب")
    def mark_sent_whatsapp(self, request, queryset):
        n = 0
        for g in queryset:
            g.invitation_status = WeddingGuest.Status.SENT_WHATSAPP
            if not g.invited_at:
                g.invited_at = timezone.now()
            g.save(update_fields=["invitation_status", "invited_at", "updated_at"])
            n += 1
        self.message_user(request, f"تم وسم {n} كمُرسَل عبر واتساب.")

    @admin.action(description="وسم: أُرسلت عبر البريد")
    def mark_sent_email(self, request, queryset):
        n = 0
        for g in queryset:
            g.invitation_status = WeddingGuest.Status.SENT_EMAIL
            if not g.invited_at:
                g.invited_at = timezone.now()
            g.save(update_fields=["invitation_status", "invited_at", "updated_at"])
            n += 1
        self.message_user(request, f"تم وسم {n} كمُرسَل عبر البريد.")

    @admin.action(description="إرسال بريد الدعوة (إن كان البريد مُهيّأً)")
    def send_email_invites(self, request, queryset):
        if not settings.email_is_configured():
            self.message_user(
                request,
                "البريد غير مُهيّأ — لم يُرسَل شيء. اضبط إعدادات SMTP في .env أولاً (معاينة فقط الآن).",
                level="warning",
            )
            return
        from django.core.mail import send_mail
        sent = skipped = 0
        for g in queryset:
            if not g.email:
                skipped += 1
                continue
            subject, body = _email_subject_body(g)
            send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [g.email], fail_silently=True)
            g.invitation_status = WeddingGuest.Status.SENT_EMAIL
            if not g.invited_at:
                g.invited_at = timezone.now()
            g.save(update_fields=["invitation_status", "invited_at", "updated_at"])
            sent += 1
        self.message_user(request, f"أُرسل {sent} بريداً، وتُخطّي {skipped} (بلا بريد).")

    @admin.action(description="تصدير CSV للمدعوين المحددين")
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = "attachment; filename=guests.csv"
        response.write("﻿")  # BOM so Excel reads Arabic
        w = csv.writer(response)
        w.writerow(["الاسم", "الهاتف", "البريد", "المجموعة", "الحالة", "العدد", "فُتحت", "هنّأ", "رابط الدعوة"])
        for g in queryset:
            w.writerow([g.full_name, g.phone_number, g.email, g.get_group_display(),
                        g.get_invitation_status_display(), g.guest_count,
                        "نعم" if g.last_opened_at else "لا",
                        "نعم" if g.invitation_status == WeddingGuest.Status.GREETED else "لا",
                        _invitation_url(g)])
        return response

    @admin.action(description="تصدير روابط الدعوة CSV")
    def export_links_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = "attachment; filename=invitation-links.csv"
        response.write("﻿")
        w = csv.writer(response)
        w.writerow(["الاسم", "رابط الدعوة"])
        for g in queryset:
            w.writerow([g.full_name, _invitation_url(g)])
        return response


# --------------------------------------------------------------------------- #
# GreetingSuggestion
# --------------------------------------------------------------------------- #
@admin.register(GreetingSuggestion)
class GreetingSuggestionAdmin(admin.ModelAdmin):
    list_display = ("text_ar", "category", "active", "sequence")
    list_editable = ("active", "sequence")
    list_filter = ("active", "category")
    search_fields = ("text_ar",)


# --------------------------------------------------------------------------- #
# Greeting
# --------------------------------------------------------------------------- #
class HasPhotoFilter(admin.SimpleListFilter):
    title = "الصورة"
    parameter_name = "has_photo"

    def lookups(self, request, model_admin):
        return (("yes", "بصورة"), ("no", "بدون صورة"))

    def queryset(self, request, queryset):
        # Legacy rows (pre-0006) have uploaded_photo NULL, not "" — handle both.
        empty = Q(uploaded_photo="") | Q(uploaded_photo__isnull=True)
        if self.value() == "yes":
            return queryset.exclude(empty)
        if self.value() == "no":
            return queryset.filter(empty)
        return queryset


@admin.register(Greeting)
class GreetingAdmin(admin.ModelAdmin):
    list_display = ("name", "short_message", "thumb", "status", "guest", "country", "created_at")
    list_filter = ("status", HasPhotoFilter, "card_template", "created_at", "country_code")
    search_fields = ("name", "message", "guest__full_name")
    readonly_fields = ("photo_review_note", "photo_preview", "card_template", "created_at",
                       "approved_at", "ip_address", "guest", "country_code", "country_name")
    actions = ("hide_selected", "show_selected")
    list_per_page = 50

    @admin.display(description="ملاحظة")
    def photo_review_note(self, obj):
        if obj and obj.is_hidden:
            return mark_safe('<b style="color:#b45309">هذه التهنئة محظورة — لا تظهر على الجدار.</b>')
        if obj and obj.has_photo:
            return mark_safe(
                'التهنئة وصورتها ظاهرتان للعامة فور الإرسال. '
                '<b style="color:#b45309">احظرها إن كانت غير لائقة.</b>'
            )
        return "التهنئة ظاهرة للعامة. احظرها إن لزم."

    @admin.display(description="معاينة الصورة")
    def photo_preview(self, obj):
        if obj and obj.uploaded_photo:
            return format_html('<img src="{}" style="max-height:320px;border-radius:8px">', obj.uploaded_photo.url)
        return "— لا صورة —"

    @admin.display(description="صورة")
    def thumb(self, obj):
        if obj.photo_thumbnail:
            return format_html('<img src="{}" style="height:42px;width:42px;object-fit:cover;border-radius:6px">', obj.photo_thumbnail.url)
        return ""

    @admin.display(description="التهنئة")
    def short_message(self, obj):
        return (obj.message[:60] + "…") if len(obj.message) > 60 else obj.message

    @admin.display(description="الدولة")
    def country(self, obj):
        if obj.country_name:
            return f"{obj.country_flag} {obj.country_name}".strip()
        return "—"

    @admin.action(description="حظر / إخفاء المحدد")
    def hide_selected(self, request, queryset):
        # Per-row (not .update) so each greeting's photo file is taken down too.
        n = 0
        for greeting in queryset:
            greeting.hide()
            n += 1
        self.message_user(request, f"تم حظر {n} تهنئة (وحُذفت صورها إن وُجدت).")

    @admin.action(description="إظهار / إلغاء الحظر")
    def show_selected(self, request, queryset):
        n = queryset.update(status=Greeting.Status.APPROVED, approved_at=timezone.now())
        self.message_user(request, f"تم إظهار {n} تهنئة على الجدار.")
