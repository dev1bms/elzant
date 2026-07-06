"""Tests for the invitation layer: phone normalization, message rendering,
webhook signature + status handling, and the WhatsApp send orchestration.

Panel access/dedupe tests live in panel/tests.py.
"""

import hashlib
import hmac
import json
from unittest.mock import patch

from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from core.models import MessageLog, WeddingGuest, WhatsAppConfig, WhatsAppStatus
from core.utils import render_message
from core.whatsapp import WhatsAppError, normalize_phone, send_invitation

WA_SETTINGS = dict(
    ALLOWED_HOSTS=["testserver"],
    SECURE_SSL_REDIRECT=False,
    WHATSAPP_APP_SECRET="unit-test-secret",
    WHATSAPP_VERIFY_TOKEN="unit-verify-token",
    WHATSAPP_TOKEN="unit-token",
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
class WebhookTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = reverse("whatsapp_webhook")
        self.guest = WeddingGuest.objects.create(
            full_name="رنا", phone_number="01009990000", phone_e164="201009990000",
            wa_message_id="wamid.ABC", wa_status=WhatsAppStatus.SENT,
        )

    def _sign(self, raw):
        return "sha256=" + hmac.new(b"unit-test-secret", raw, hashlib.sha256).hexdigest()

    def _post(self, status, message_id="wamid.ABC", sign=True):
        body = {"entry": [{"changes": [{"value": {"statuses": [
            {"id": message_id, "status": status, "timestamp": "1700000000"}]}}]}]}
        raw = json.dumps(body).encode()
        headers = {"HTTP_X_HUB_SIGNATURE_256": self._sign(raw)} if sign else {}
        return self.client.generic("POST", self.url, raw,
                                   content_type="application/json", **headers)

    def test_get_subscription_verify_ok(self):
        r = self.client.get(self.url, {"hub.mode": "subscribe",
                                       "hub.verify_token": "unit-verify-token",
                                       "hub.challenge": "9988"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content, b"9988")

    def test_get_subscription_wrong_token_forbidden(self):
        r = self.client.get(self.url, {"hub.mode": "subscribe",
                                       "hub.verify_token": "nope", "hub.challenge": "1"})
        self.assertEqual(r.status_code, 403)

    def test_delivered_then_read_updates_guest(self):
        self.assertEqual(self._post("delivered").status_code, 200)
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.wa_status, WhatsAppStatus.DELIVERED)
        self.assertIsNotNone(self.guest.delivered_at)

        self._post("read")
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.wa_status, WhatsAppStatus.READ)
        self.assertIsNotNone(self.guest.read_at)

    def test_late_event_does_not_downgrade(self):
        self._post("read")
        self._post("sent")  # arrives late/out of order
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.wa_status, WhatsAppStatus.READ)

    def test_bad_signature_rejected(self):
        raw = json.dumps({"entry": []}).encode()
        r = self.client.generic("POST", self.url, raw, content_type="application/json",
                                HTTP_X_HUB_SIGNATURE_256="sha256=deadbeef")
        self.assertEqual(r.status_code, 403)

    def test_unsigned_rejected(self):
        self.assertEqual(self._post("read", sign=False).status_code, 403)

    def test_failed_status_logged(self):
        self._post("failed")
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.wa_status, WhatsAppStatus.FAILED)
        self.assertTrue(MessageLog.objects.filter(wa_message_id="wamid.ABC",
                                                  status=WhatsAppStatus.FAILED).exists())


@override_settings(**WA_SETTINGS)
class SendInvitationTests(TestCase):
    def setUp(self):
        cfg = WhatsAppConfig.get()
        cfg.default_template_name = "invite_ar"
        cfg.save()
        self.cfg = cfg
        self.guest = WeddingGuest.objects.create(
            full_name="سالم", phone_number="01005550000", phone_e164="201005550000")

    def test_safe_mode_simulates_without_network(self):
        self.cfg.enabled = False
        self.cfg.save()
        with patch("core.whatsapp.send_template") as mock_send:
            result = send_invitation(self.guest)
        mock_send.assert_not_called()
        self.assertTrue(result.simulated)
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.wa_status, WhatsAppStatus.QUEUED)
        self.assertEqual(self.guest.send_count, 1)
        self.assertEqual(self.guest.invitation_status, WeddingGuest.Status.SENT_WHATSAPP)

    def test_enabled_calls_api_and_records_message_id(self):
        self.cfg.enabled = True
        self.cfg.phone_number_id = "PN123"
        self.cfg.save()
        with patch("core.whatsapp.send_template", return_value="wamid.SENT1") as mock_send:
            result = send_invitation(self.guest)
        mock_send.assert_called_once()
        self.assertTrue(result.ok)
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.wa_message_id, "wamid.SENT1")
        self.assertEqual(self.guest.wa_status, WhatsAppStatus.SENT)
        self.assertTrue(MessageLog.objects.filter(guest=self.guest,
                                                  wa_message_id="wamid.SENT1").exists())

    def test_api_failure_captured_not_raised(self):
        self.cfg.enabled = True
        self.cfg.phone_number_id = "PN123"
        self.cfg.save()
        with patch("core.whatsapp.send_template", side_effect=WhatsAppError("رفض Meta")):
            result = send_invitation(self.guest)
        self.assertFalse(result.ok)
        self.assertIn("رفض", result.error)
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.wa_status, WhatsAppStatus.FAILED)

    def test_invalid_phone_fails_gracefully(self):
        g = WeddingGuest.objects.create(full_name="بلا رقم", phone_number="", phone_e164="")
        result = send_invitation(g)
        self.assertFalse(result.ok)
