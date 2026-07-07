"""Remove spam greetings from the wall.

Runs a DRY RUN by default (prints what would be removed and stops). Pass --apply
to actually delete them — deletion is PERMANENT and cleans up any photo files via
the Greeting post_delete signal.

Match (high precision): a link/URL or a known spam keyword in the name/message.
Add --nonarabic to ALSO match greetings whose message has no Arabic letters.

Examples:
    python manage.py purge_spam_greetings                 # معاينة فقط
    python manage.py purge_spam_greetings --nonarabic     # معاينة (تشمل غير العربية)
    python manage.py purge_spam_greetings --apply         # حذف نهائي
"""
from django.core.management.base import BaseCommand

from core.models import Greeting
from core.utils import has_arabic, looks_like_spam


class Command(BaseCommand):
    help = "حذف تهاني السبام (معاينة افتراضياً؛ --apply للحذف النهائي)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="نفّذ الحذف فعلياً (الافتراضي: معاينة فقط).",
        )
        parser.add_argument(
            "--nonarabic", action="store_true",
            help="طابِق أيضاً التهاني التي لا تحوي أي حرف عربي.",
        )

    def handle(self, *args, **opts):
        apply_changes = opts["apply"]
        include_nonarabic = opts["nonarabic"]

        matched = []
        # Full objects (not .only) so the post_delete signal can clean photo files.
        for g in Greeting.objects.all():
            spam = looks_like_spam(g.name, g.message)
            if not spam and include_nonarabic and not has_arabic(g.message):
                spam = True
            if spam:
                matched.append(g)

        if not matched:
            self.stdout.write(self.style.SUCCESS("لا يوجد سبام مطابق. ✓"))
            return

        self.stdout.write(f"مطابِق للسبام: {len(matched)} تهنئة")
        for g in matched[:40]:
            snippet = (g.message or "")[:60].replace("\n", " ")
            self.stdout.write(f"  #{g.id} — {g.name!r}: {snippet}")
        if len(matched) > 40:
            self.stdout.write(f"  … و{len(matched) - 40} أخرى")

        if not apply_changes:
            self.stdout.write(self.style.WARNING(
                "\nمعاينة فقط (dry-run). للحذف النهائي أعِد التشغيل مع --apply."
            ))
            return

        count = 0
        for g in matched:
            g.delete()  # per-object delete → post_delete cleans photo files
            count += 1
        self.stdout.write(self.style.SUCCESS(f"\nحُذف {count} تهنئة نهائياً (مع صورها إن وُجدت)."))
