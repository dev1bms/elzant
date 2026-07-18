"""Panel tests: access control, data isolation, and the dedupe/attribution flow.

Safe mode (WhatsAppConfig.enabled=False) is used throughout so sends are
simulated — no network, no mocking of the Cloud API needed here.
"""

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import InviterProfile, WeddingGuest, WhatsAppConfig, WhatsAppStatus

PANEL_SETTINGS = dict(ALLOWED_HOSTS=["testserver"], SECURE_SSL_REDIRECT=False)


def _make_inviter(username, display, side="both", can_view_all=False):
    user = User.objects.create_user(username=username, password="pw")
    InviterProfile.objects.create(user=user, display_name=display, side=side,
                                  can_view_all=can_view_all)
    return user


@override_settings(**PANEL_SETTINGS)
class AccessControlTests(TestCase):
    def setUp(self):
        cfg = WhatsAppConfig.get()
        cfg.enabled = False
        cfg.content_sid = "HXtest"
        cfg.save()
        self.groom = _make_inviter("groom_side", "أبو العريس", "groom")
        self.bride = _make_inviter("bride_side", "أبو العروس", "bride")
        self.admin = _make_inviter("family_admin", "المشرف", "both", can_view_all=True)

    def test_anonymous_redirected_to_login(self):
        r = self.client.get(reverse("panel:dashboard"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/panel/login/", r["Location"])

    def test_non_inviter_user_forbidden(self):
        User.objects.create_user(username="random", password="pw")
        self.client.login(username="random", password="pw")
        self.assertEqual(self.client.get(reverse("panel:dashboard")).status_code, 403)

    def test_inviter_can_open_dashboard(self):
        self.client.login(username="groom_side", password="pw")
        self.assertEqual(self.client.get(reverse("panel:dashboard")).status_code, 200)

    def test_cross_inviter_guest_access_forbidden(self):
        g = WeddingGuest.objects.create(full_name="ضيف العريس", phone_e164="201000000001",
                                        invited_by=self.groom)
        self.client.login(username="bride_side", password="pw")
        self.assertEqual(
            self.client.get(reverse("panel:guest_detail", args=[g.id])).status_code, 403)

    def test_owner_can_access_own_guest(self):
        g = WeddingGuest.objects.create(full_name="ضيف العريس", phone_e164="201000000002",
                                        invited_by=self.groom)
        self.client.login(username="groom_side", password="pw")
        self.assertEqual(
            self.client.get(reverse("panel:guest_detail", args=[g.id])).status_code, 200)

    def test_can_view_all_sees_others_guest(self):
        g = WeddingGuest.objects.create(full_name="ضيف العريس", phone_e164="201000000003",
                                        invited_by=self.groom)
        self.client.login(username="family_admin", password="pw")
        self.assertEqual(
            self.client.get(reverse("panel:guest_detail", args=[g.id])).status_code, 200)

    def test_scope_all_ignored_without_permission(self):
        WeddingGuest.objects.create(full_name="مدعو الغير", phone_e164="201000000004",
                                    invited_by=self.bride)
        self.client.login(username="groom_side", password="pw")
        r = self.client.get(reverse("panel:guests"), {"scope": "all"})
        self.assertEqual(r.status_code, 200)
        # Groom must not see the bride's guest even when asking for scope=all.
        self.assertNotContains(r, "مدعو الغير")


@override_settings(**PANEL_SETTINGS)
class AddAndDedupeTests(TestCase):
    def setUp(self):
        cfg = WhatsAppConfig.get()
        cfg.enabled = False
        cfg.content_sid = "HXtest"
        cfg.default_country_code = "20"
        cfg.save()
        self.groom = _make_inviter("groom_side", "أبو العريس", "groom")
        self.bride = _make_inviter("bride_side", "أبو العروس", "bride")

    def test_add_creates_guest_and_simulates_send(self):
        self.client.login(username="groom_side", password="pw")
        r = self.client.post(reverse("panel:guest_add"),
                             {"full_name": "خالد", "phone": "01001234567"})
        self.assertEqual(r.status_code, 302)
        g = WeddingGuest.objects.get(phone_e164="201001234567")
        self.assertEqual(g.invited_by, self.groom)
        self.assertEqual(g.wa_status, WhatsAppStatus.QUEUED)
        self.assertEqual(g.invitation_status, WeddingGuest.Status.SENT_WHATSAPP)
        self.assertEqual(g.send_count, 1)

    def test_invalid_phone_shows_error_no_guest(self):
        self.client.login(username="groom_side", password="pw")
        r = self.client.post(reverse("panel:guest_add"),
                             {"full_name": "خالد", "phone": "12"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "غير صالح")
        self.assertFalse(WeddingGuest.objects.filter(full_name="خالد").exists())

    def test_duplicate_phone_shows_confirmation_no_send(self):
        WeddingGuest.objects.create(full_name="خالد", phone_number="01001234567",
                                    phone_e164="201001234567", invited_by=self.groom)
        self.client.login(username="bride_side", password="pw")
        r = self.client.post(reverse("panel:guest_add"),
                             {"full_name": "خالد ثانٍ", "phone": "0100 123 4567"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "مدعوٌّ مسبقاً")
        # No new record, no send, until confirmed.
        self.assertEqual(WeddingGuest.objects.filter(phone_e164="201001234567").count(), 1)

    def test_confirm_resend_keeps_same_guest(self):
        g = WeddingGuest.objects.create(full_name="خالد", phone_number="01001234567",
                                        phone_e164="201001234567", invited_by=self.groom)
        self.client.login(username="bride_side", password="pw")
        r = self.client.post(reverse("panel:guest_add"), {
            "full_name": "خالد", "phone": "01001234567",
            "confirm": "1", "action": "resend"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(WeddingGuest.objects.filter(phone_e164="201001234567").count(), 1)
        g.refresh_from_db()
        self.assertEqual(g.invited_by, self.groom)  # attribution unchanged
        self.assertEqual(g.send_count, 1)

    def test_confirm_duplicate_creates_second_record(self):
        WeddingGuest.objects.create(full_name="خالد", phone_number="01001234567",
                                    phone_e164="201001234567", invited_by=self.groom)
        self.client.login(username="bride_side", password="pw")
        r = self.client.post(reverse("panel:guest_add"), {
            "full_name": "خالد مكرّر", "phone": "01001234567",
            "confirm": "1", "action": "duplicate"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(WeddingGuest.objects.filter(phone_e164="201001234567").count(), 2)
        dup = WeddingGuest.objects.get(full_name="خالد مكرّر")
        self.assertEqual(dup.invited_by, self.bride)


@override_settings(**PANEL_SETTINGS)
class InboundBadgeTests(TestCase):
    """عدّاد الردود الواردة: شارة بجانب اسم الضيف + قسم الردود في صفحته."""

    def setUp(self):
        from core.models import MessageLog

        self.inviter = _make_inviter("badge_user", "أبو الشباب")
        self.guest = WeddingGuest.objects.create(
            full_name="سالم", phone_number="01001112222", phone_e164="201001112222",
            invited_by=self.inviter,
        )
        for text in ("مبارك مقدماً!", "وين القاعة؟"):
            MessageLog.objects.create(
                guest=self.guest, template_name="inbound_text",
                status=WhatsAppStatus.READ, payload={"body": text, "media": 0},
            )
        self.client.login(username="badge_user", password="pw")

    def test_guests_list_shows_reply_count(self):
        resp = self.client.get(reverse("panel:guests"))
        self.assertContains(resp, "data-inbound-badge")
        self.assertContains(resp, ">سالم<", html=False)
        self.assertContains(resp, "2")

    def test_guest_detail_lists_replies(self):
        resp = self.client.get(reverse("panel:guest_detail", args=[self.guest.id]))
        self.assertContains(resp, "ردود واردة من الضيف")
        self.assertContains(resp, "وين القاعة؟")
        self.assertContains(resp, "مبارك مقدماً!")

    def test_activity_feed_excludes_inbound_rows(self):
        resp = self.client.get(reverse("panel:activity"))
        self.assertNotContains(resp, "وين القاعة؟")

    def test_no_badge_for_guest_without_replies(self):
        quiet = WeddingGuest.objects.create(
            full_name="هادئ", phone_number="01003334444", phone_e164="201003334444",
            invited_by=self.inviter,
        )
        resp = self.client.get(reverse("panel:guest_detail", args=[quiet.id]))
        self.assertNotContains(resp, "ردود واردة من الضيف")


@override_settings(**PANEL_SETTINGS)
class JourneyStripTests(TestCase):
    """شريط رحلة الضيف: أيقونات المراحل + مدة التصفح تظهر في القوائم."""

    def setUp(self):
        from django.utils import timezone as tz

        self.inviter = _make_inviter("journey_user", "أم العريس")
        self.guest = WeddingGuest.objects.create(
            full_name="نبيل", phone_number="01007776655", phone_e164="201007776655",
            invited_by=self.inviter, wa_status=WhatsAppStatus.READ,
            invitation_status=WeddingGuest.Status.GREETED,
            last_opened_at=tz.now(), time_on_site_seconds=195,
        )
        self.client.login(username="journey_user", password="pw")

    def test_list_shows_journey_and_time(self):
        resp = self.client.get(reverse("panel:guests"))
        self.assertContains(resp, 'title="كتب تهنئة"')       # مرحلة مضيئة
        self.assertContains(resp, "3د 15ث")                   # 195 ثانية
        self.assertContains(resp, 'title="أُرسلت"')

    def test_dashboard_recent_shows_journey(self):
        resp = self.client.get(reverse("panel:dashboard"))
        self.assertContains(resp, 'title="فتح الدعوة"')

    def test_activity_rows_carry_journey(self):
        from core.models import MessageLog

        MessageLog.objects.create(guest=self.guest, sender=self.inviter,
                                  template_name="HXtest", status=WhatsAppStatus.SENT)
        resp = self.client.get(reverse("panel:activity"))
        self.assertContains(resp, 'title="قُرئت"')
