import csv
from urllib.parse import quote

from django.conf import settings
from django import forms
from django.contrib import admin
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import redirect
from django.template.defaultfilters import date as date_filter
from django.urls import path, reverse
from django.utils import timezone, translation
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .models import (
    Greeting, GreetingSuggestion, InviterProfile, MessageLog,
    WeddingConfig, WeddingGuest, WhatsAppConfig, WhatsAppTemplate,
)
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
    list_display = ("full_name", "phone_number", "group", "invitation_status",
                    "wa_status", "invited_by", "opened", "greeted", "guest_count")
    list_filter = ("invitation_status", "wa_status", "group", "invited_by")
    search_fields = ("full_name", "phone_number", "phone_e164", "email")
    readonly_fields = ("invitation_token", "invitation_link", "whatsapp_link", "email_preview",
                       "phone_e164", "wa_status", "wa_message_id", "delivered_at", "read_at",
                       "send_count", "last_sent_at", "last_opened_at", "invited_at",
                       "created_at", "updated_at")
    list_per_page = 50
    autocomplete_fields = ("invited_by",)
    actions = ("mark_ready", "mark_sent_whatsapp", "mark_sent_email",
               "send_email_invites", "export_csv", "export_links_csv")
    fieldsets = (
        ("المدعو", {"fields": ("full_name", "phone_number", "phone_e164", "email", "group",
                               "guest_count", "invited_by", "notes")}),
        ("الدعوة", {"fields": ("invitation_status", "invitation_link", "whatsapp_link", "email_preview",
                               "invitation_token")}),
        ("تتبّع واتساب", {"fields": ("wa_status", "wa_message_id", "delivered_at", "read_at",
                                     "send_count", "last_sent_at")}),
        ("التتبّع", {"fields": ("last_opened_at", "invited_at", "created_at", "updated_at")}),
    )

    def save_model(self, request, obj, form, change):
        # Keep the normalized phone (dedupe key) in sync with the typed number.
        from .models import WhatsAppConfig
        from .whatsapp import normalize_phone
        if obj.phone_number:
            obj.phone_e164 = normalize_phone(obj.phone_number, WhatsAppConfig.get().default_country_code) or ""
        else:
            obj.phone_e164 = ""
        super().save_model(request, obj, form, change)

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


# --------------------------------------------------------------------------- #
# Invitation layer — InviterProfile / WhatsAppConfig / WhatsAppTemplate / logs
# --------------------------------------------------------------------------- #
@admin.register(InviterProfile)
class InviterProfileAdmin(admin.ModelAdmin):
    list_display = ("display_name", "user", "side", "can_view_all", "invited_total")
    list_filter = ("side", "can_view_all")
    search_fields = ("display_name", "user__username", "phone")
    autocomplete_fields = ("user",)

    @admin.display(description="عدد دعواته")
    def invited_total(self, obj):
        return obj.user.invited_guests.count()


class WhatsAppConfigForm(forms.ModelForm):
    """Secrets are masked (never rendered back to the browser) and preserved when
    left blank — so re-saving the page never wipes a stored secret."""

    class Meta:
        model = WhatsAppConfig
        fields = "__all__"
        _mask = {"autocomplete": "new-password",
                 "placeholder": "••••••• (اتركه فارغاً للإبقاء على القيمة الحالية)"}
        widgets = {
            "api_token": forms.PasswordInput(render_value=False, attrs=_mask),
            "app_secret": forms.PasswordInput(render_value=False, attrs=_mask),
            "verify_token": forms.PasswordInput(render_value=False, attrs=_mask),
        }

    def _keep_if_blank(self, field):
        # Blank submission means "unchanged" — keep whatever is already stored.
        return self.cleaned_data.get(field) or getattr(self.instance, field, "")

    def clean_api_token(self):
        return self._keep_if_blank("api_token")

    def clean_app_secret(self):
        return self._keep_if_blank("app_secret")

    def clean_verify_token(self):
        return self._keep_if_blank("verify_token")


@admin.register(WhatsAppConfig)
class WhatsAppConfigAdmin(admin.ModelAdmin):
    form = WhatsAppConfigForm
    list_display = ("__str__", "enabled", "default_template_name", "template_lang")
    readonly_fields = ("secrets_state", "test_send_button")
    fieldsets = (
        ("التشغيل", {"fields": ("enabled",)}),
        ("Cloud API", {"fields": ("phone_number_id", "waba_id", "api_version")}),
        ("القالب الافتراضي", {"fields": ("default_template_name", "template_lang", "default_country_code")}),
        ("الأسرار (تُدار من هنا — مقنّعة، superuser فقط)",
         {"fields": ("api_token", "app_secret", "verify_token", "secrets_state"),
          "description": "تُخزَّن في قاعدة البيانات وتُعرَض مقنّعة. اترك الحقل فارغاً للإبقاء على قيمته الحالية. "
                         "احمِ ملف قاعدة البيانات ونسخه الاحتياطية."}),
        ("الاختبار", {"fields": ("test_recipient", "test_send_button")}),
    )

    def has_add_permission(self, request):
        return not WhatsAppConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    @admin.display(description="حالة الأسرار")
    def secrets_state(self, obj):
        if not obj or not obj.pk:
            return "—"
        def mark(v):
            return "مضبوط ✓" if v else "غير مضبوط ✗"
        return format_html(
            "التوكن: {} · App Secret: {} · Verify Token: {}",
            mark(obj.api_token), mark(obj.app_secret), mark(obj.verify_token),
        )

    @admin.display(description="إرسال رسالة اختبار")
    def test_send_button(self, obj):
        if not obj or not obj.pk:
            return "احفظ الإعدادات أولاً."
        if not obj.test_recipient:
            return "أضف «رقم اختبار الإرسال» واحفظ لتظهر الزر."
        url = reverse("admin:core_whatsappconfig_test_send")
        mode = "إرسال حقيقي" if obj.enabled else "محاكاة (وضع آمن — بلا إرسال فعلي)"
        return format_html(
            '<a class="button" href="{}">إرسال اختبار إلى {}</a>'
            '<div style="margin-top:6px;color:#6e5a4c">الوضع الحالي: {}</div>',
            url, obj.test_recipient, mode,
        )

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path("test-send/", self.admin_site.admin_view(self.test_send_view),
                 name="core_whatsappconfig_test_send"),
        ]
        return custom + urls

    def test_send_view(self, request):
        from .whatsapp import send_test_message

        config = WhatsAppConfig.get()
        result = send_test_message(config.test_recipient)
        if result.simulated:
            self.message_user(request, "وضع آمن: لم يُرسَل شيء فعلياً (فعّل الإرسال الحيّ للاختبار الحقيقي).",
                              level="warning")
        elif result.ok:
            self.message_user(request, f"تم الإرسال ✓ — معرّف الرسالة: {result.message_id}")
        else:
            self.message_user(request, f"فشل الإرسال: {result.error}", level="error")
        return redirect(reverse("admin:core_whatsappconfig_change", args=[config.pk]))


@admin.register(WhatsAppTemplate)
class WhatsAppTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "language", "category", "is_approved", "active")
    list_filter = ("category", "is_approved", "active", "language")
    list_editable = ("is_approved", "active")
    search_fields = ("name", "body_preview_ar")


@admin.register(MessageLog)
class MessageLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "guest", "sender", "template_name", "status", "short_error")
    list_filter = ("status", "template_name", "created_at")
    search_fields = ("guest__full_name", "wa_message_id", "error")
    readonly_fields = ("guest", "sender", "template_name", "wa_message_id", "status",
                       "error", "payload", "created_at")
    list_per_page = 100

    @admin.display(description="الخطأ")
    def short_error(self, obj):
        return (obj.error[:60] + "…") if obj.error and len(obj.error) > 60 else (obj.error or "—")

    def has_add_permission(self, request):
        return False
