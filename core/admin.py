from django.contrib import admin
from django.utils import timezone

from .models import Greeting, WeddingConfig

admin.site.site_header = "إدارة موقع زفاف محمود ورينان"
admin.site.site_title = "elzant.com"
admin.site.index_title = "لوحة المراجعة"


@admin.register(WeddingConfig)
class WeddingConfigAdmin(admin.ModelAdmin):
    """Singleton: allow editing the one row, but no adding or deleting."""

    def has_add_permission(self, request):
        return not WeddingConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Greeting)
class GreetingAdmin(admin.ModelAdmin):
    list_display = ("name", "short_message", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("name", "message")
    readonly_fields = ("created_at", "approved_at", "ip_address")
    actions = ("approve_selected", "reject_selected")
    list_per_page = 50

    @admin.display(description="التهنئة")
    def short_message(self, obj):
        return (obj.message[:60] + "…") if len(obj.message) > 60 else obj.message

    @admin.action(description="اعتماد المحدد")
    def approve_selected(self, request, queryset):
        n = queryset.update(
            status=Greeting.Status.APPROVED, approved_at=timezone.now()
        )
        self.message_user(request, f"تم اعتماد {n} تهنئة.")

    @admin.action(description="رفض المحدد")
    def reject_selected(self, request, queryset):
        n = queryset.update(status=Greeting.Status.REJECTED, approved_at=None)
        self.message_user(request, f"تم رفض {n} تهنئة.")
