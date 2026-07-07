"""Tests for the invitation layer: phone normalization, message rendering, the
Twilio send orchestration, the Twilio status webhook, and greeting anti-spam.

Panel access/dedupe tests live in panel/tests.py.
"""

from unittest.mock import patch

from django.core.management import call_command
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from core.models import Greeting, MessageLog, WeddingGuest, WhatsAppConfig, WhatsAppStatus
from core.utils import contains_link, has_arabic, looks_like_spam, render_message
from core.whatsapp import WhatsAppError, normalize_phone, send_invitation

WA_SETTINGS = dict(
    ALLOWED_HOSTS=["testserver"],
    SECURE_SSL_REDIRECT=False,
)


class NormalizePhoneTests(SimpleTestCase):
    def test_egyptian_local_trunk_zero(self):
        self.assertEqual(normalize_phone("01001234567", "20"), "201001234567")

    def test_spaces_and_dashes_stripped(self):
        self.assertEqual(normalize_phone(" 010-0123 4567 ", "20"), "201001234567")

    def test_plus_international(self):
        self.assertEqual(normalize_phone("+201001234567", "20"), "201001234567")

    def test_double_zero_international(self):
        self.assertEqual(normalize_phone("00201001234567", "20"), "201001234567")

    def test_palestinian_local(self):
        self.assertEqual(normalize_phone("0599123456", "970"), "970599123456")

    def test_jordanian_international(self):
        self.assertEqual(normalize_phone("+962790000000", "20"), "962790000000")

    def test_already_has_country_code(self):
        self.assertEqual(normalize_phone("201001234567", "20"), "201001234567")

    def test_bare_local_without_trunk_gets_cc(self):
        self.assertEqual(normalize_phone("1001234567", "20"), "201001234567")

    def test_invalid_values_return_none(self):
        for bad in ["", "   ", "abc", "12", None, "00"]:
            self.assertIsNone(normalize_phone(bad, "20"), bad)


class RenderMessageTests(SimpleTestCase):
    def test_substitutes_known_placeholders(self):
        out = render_message("مرحباً {{ guest_name }} — {{ invitation_link }}",
                             {"guest_name": "خالد", "invitation_link": "https://x/i/t/"})
        self.assertEqual(out, "مرحباً خالد — https://x/i/t/")

    def test_unknown_placeholder_left_as_is(self):
        self.assertEqual(render_message("{{ nope }}", {"guest_name": "x"}), "{{ nope }}")

    def test_empty_template(self):
        self.assertEqual(render_message("", {"a": "b"}), "")


@override_settings(**WA_SETTINGS)
class TwilioWebhookTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = reverse("twilio_status")
        self.guest = WeddingGuest.objects.create(
            full_name="رنا", phone_number="01009990000", phone_e164="201009990000",
            wa_message_id="SM123", wa_status=WhatsAppStatus.SENT,
        )

    def _post(self, status, message_sid="SM123"):
        return self.client.post(self.url, {"MessageSid": message_sid, "MessageStatus": status})

    @patch("core.webhooks.validate_twilio_request", return_value=True)
    def test_delivered_then_read_updates_guest(self, _v):
        self.assertEqual(self._post("delivered").status_code, 200)
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.wa_status, WhatsAppStatus.DELIVERED)
        self.assertIsNotNone(self.guest.delivered_at)

        self._post("read")
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.wa_status, WhatsAppStatus.READ)
        self.assertIsNotNone(self.guest.read_at)

    @patch("core.webhooks.validate_twilio_request", return_value=True)
    def test_late_event_does_not_downgrade(self, _v):
        self._post("read")
        self._post("sent")  # arrives late/out of order
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.wa_status, WhatsAppStatus.READ)

    @patch("core.webhooks.validate_twilio_request", return_value=True)
    def test_failed_status_logged(self, _v):
        self._post("failed")
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.wa_status, WhatsAppStatus.FAILED)
        self.assertTrue(MessageLog.objects.filter(wa_message_id="SM123",
                                                  status=WhatsAppStatus.FAILED).exists())

    def test_invalid_signature_rejected(self):
        # No Auth Token configured → validate_twilio_request returns False → 403.
        self.assertEqual(self._post("read").status_code, 403)


@override_settings(**WA_SETTINGS)
class SendInvitationTests(TestCase):
    def setUp(self):
        cfg = WhatsAppConfig.get()
        cfg.content_sid = "HXtest"
        cfg.twilio_account_sid = "ACtest"
        cfg.twilio_auth_token = "tok"
        cfg.twilio_from = "+14155238886"
        cfg.save()
        self.cfg = cfg
        self.guest = WeddingGuest.objects.create(
            full_name="سالم", phone_number="01005550000", phone_e164="201005550000")

    def test_safe_mode_simulates_without_network(self):
        self.cfg.enabled = False
        self.cfg.save()
        with patch("core.whatsapp.send_content_message") as mock_send:
            result = send_invitation(self.guest)
        mock_send.assert_not_called()
        self.assertTrue(result.simulated)
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.wa_status, WhatsAppStatus.QUEUED)
        self.assertEqual(self.guest.send_count, 1)
        self.assertEqual(self.guest.invitation_status, WeddingGuest.Status.SENT_WHATSAPP)

    def test_enabled_calls_twilio_and_records_sid(self):
        self.cfg.enabled = True
        self.cfg.save()
        with patch("core.whatsapp.send_content_message", return_value="SMsent1") as mock_send:
            result = send_invitation(self.guest)
        mock_send.assert_called_once()
        self.assertTrue(result.ok)
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.wa_message_id, "SMsent1")
        self.assertEqual(self.guest.wa_status, WhatsAppStatus.SENT)
        self.assertTrue(MessageLog.objects.filter(guest=self.guest,
                                                  wa_message_id="SMsent1").exists())

    def test_twilio_failure_captured_not_raised(self):
        self.cfg.enabled = True
        self.cfg.save()
        with patch("core.whatsapp.send_content_message", side_effect=WhatsAppError("رفض Twilio")):
            result = send_invitation(self.guest)
        self.assertFalse(result.ok)
        self.assertIn("رفض", result.error)
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.wa_status, WhatsAppStatus.FAILED)

    def test_invalid_phone_fails_gracefully(self):
        g = WeddingGuest.objects.create(full_name="بلا رقم", phone_number="", phone_e164="")
        result = send_invitation(g)
        self.assertFalse(result.ok)


class SpamHeuristicsTests(SimpleTestCase):
    def test_contains_link_detects_urls_and_domains(self):
        for s in ["visit http://x.com", "www.elzant.com", "check elzant.com now", "t.me/abc"]:
            self.assertTrue(contains_link(s), s)

    def test_contains_link_false_for_clean_arabic(self):
        for s in ["ألف مبروك للعروسين", "أجمل التهاني للعروسين", ""]:
            self.assertFalse(contains_link(s), s)

    def test_has_arabic(self):
        self.assertTrue(has_arabic("مبروك"))
        self.assertTrue(has_arabic("Mabrouk يا شباب"))
        self.assertFalse(has_arabic("Congratulations!"))
        self.assertFalse(has_arabic(""))

    def test_looks_like_spam(self):
        self.assertTrue(looks_like_spam("Bindra", "Submit elzant.com in GoogleSearchIndex"))
        self.assertTrue(looks_like_spam("x", "I can boost your website leads"))
        self.assertFalse(looks_like_spam("سالم", "ألف مبروك للعروسين"))


class GreetingFormSpamTests(TestCase):
    def _form(self, name, message):
        from core.forms import GreetingForm
        return GreetingForm({"name": name, "message": message, "website": ""})

    def test_link_in_message_rejected(self):
        f = self._form("سالم", "Submit http://elzant.com to GoogleSearchIndex")
        self.assertFalse(f.is_valid())
        self.assertIn("message", f.errors)

    def test_link_in_name_rejected(self):
        f = self._form("see elzant.com", "مبروك للعروسين")
        self.assertFalse(f.is_valid())
        self.assertIn("name", f.errors)

    def test_clean_arabic_greeting_valid(self):
        self.assertTrue(self._form("سالم", "ألف مبروك للعروسين").is_valid())


@override_settings(**WA_SETTINGS)
class GreetingModerationViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = reverse("home")

    def _post(self, name, message):
        return self.client.post(self.url, {"name": name, "message": message, "website": ""})

    def test_arabic_greeting_published(self):
        r = self._post("سالم", "ألف مبروك للعروسين، حياة سعيدة")
        self.assertEqual(r.status_code, 302)
        g = Greeting.objects.latest("created_at")
        self.assertEqual(g.status, Greeting.Status.APPROVED)
        self.assertIn(g, list(Greeting.visible()))

    def test_non_arabic_greeting_held_off_wall(self):
        r = self._post("Tracy", "Congratulations on your wedding")
        self.assertEqual(r.status_code, 302)
        g = Greeting.objects.latest("created_at")
        self.assertEqual(g.status, Greeting.Status.HELD)
        self.assertNotIn(g, list(Greeting.visible()))


@override_settings(**WA_SETTINGS)
class PurgeSpamCommandTests(TestCase):
    def setUp(self):
        Greeting.objects.create(name="سالم", message="ألف مبروك للعروسين",
                                status=Greeting.Status.APPROVED)
        Greeting.objects.create(name="Bindra", message="Submit elzant.com in GoogleSearchIndex",
                                status=Greeting.Status.APPROVED)
        Greeting.objects.create(name="Danish", message="I boost your website leads",
                                status=Greeting.Status.APPROVED)

    def test_dry_run_keeps_everything(self):
        call_command("purge_spam_greetings")
        self.assertEqual(Greeting.objects.count(), 3)

    def test_apply_removes_spam_only(self):
        call_command("purge_spam_greetings", "--apply")
        remaining = list(Greeting.objects.all())
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0].name, "سالم")
