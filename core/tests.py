"""Tests for the invitation layer: phone normalization, message rendering, the
Twilio send orchestration, the Twilio status webhook, and greeting anti-spam.

Panel access/dedupe tests live in panel/tests.py.
"""

from unittest.mock import patch

from django.core.management import call_command
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from core.models import (
    Greeting, MessageLog, WeddingConfig, WeddingGuest, WhatsAppConfig, WhatsAppStatus,
)
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
class RsvpPageTests(TestCase):
    """The web RSVP buttons on the private invitation page."""

    def setUp(self):
        self.guest = WeddingGuest.objects.create(
            full_name="سميّة", phone_number="01008887777", phone_e164="201008887777",
        )
        self.url = reverse("rsvp", args=[self.guest.invitation_token])

    def test_attending_recorded_and_redirects(self):
        resp = self.client.post(self.url, {"choice": "attending"})
        self.assertRedirects(resp, reverse("invitation", args=[self.guest.invitation_token]))
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.rsvp, WeddingGuest.Rsvp.ATTENDING)
        self.assertIsNotNone(self.guest.rsvp_at)

    def test_declined_recorded(self):
        self.client.post(self.url, {"choice": "declined"})
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.rsvp, WeddingGuest.Rsvp.DECLINED)

    def test_bogus_choice_ignored(self):
        self.client.post(self.url, {"choice": "maybe"})
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.rsvp, WeddingGuest.Rsvp.NONE)

    def test_disabled_rsvp_is_noop(self):
        cfg = WeddingConfig.get()
        cfg.rsvp_enabled = False
        cfg.save()
        self.client.post(self.url, {"choice": "attending"})
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.rsvp, WeddingGuest.Rsvp.NONE)

    def test_invitation_page_shows_buttons_then_thanks(self):
        inv = reverse("invitation", args=[self.guest.invitation_token])
        self.assertContains(self.client.get(inv), "سأحضر بإذن الله")
        self.client.post(self.url, {"choice": "attending"})
        self.assertContains(self.client.get(inv), "بانتظار طلّتكم")


@override_settings(**WA_SETTINGS)
class TwilioInboundRsvpTests(TestCase):
    """Inbound WhatsApp quick-reply buttons → RSVP (signature-verified)."""

    def setUp(self):
        self.url = reverse("twilio_inbound")
        self.guest = WeddingGuest.objects.create(
            full_name="ماجد", phone_number="01005554444", phone_e164="201005554444",
        )

    @patch("core.webhooks.validate_twilio_request", return_value=True)
    def test_button_payload_maps_to_attending(self, _v):
        resp = self.client.post(self.url, {
            "From": "whatsapp:+201005554444", "ButtonPayload": "rsvp_yes",
            "ButtonText": "سأحضر بإذن الله",
        })
        self.assertEqual(resp.status_code, 200)
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.rsvp, WeddingGuest.Rsvp.ATTENDING)
        self.assertIn("بانتظار", resp.content.decode())  # TwiML thank-you

    @patch("core.webhooks.validate_twilio_request", return_value=True)
    def test_button_text_decline_without_payload(self, _v):
        self.client.post(self.url, {
            "From": "whatsapp:+201005554444", "ButtonText": "أعتذر مع خالص المحبّة",
        })
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.rsvp, WeddingGuest.Rsvp.DECLINED)

    @patch("core.webhooks.validate_twilio_request", return_value=True)
    def test_unknown_sender_is_noop_200(self, _v):
        resp = self.client.post(self.url, {"From": "whatsapp:+201000000000",
                                           "ButtonPayload": "rsvp_yes"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, b"")

    def test_invalid_signature_rejected(self):
        self.assertEqual(
            self.client.post(self.url, {"From": "whatsapp:+201005554444"}).status_code, 403)


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


@override_settings(**WA_SETTINGS)
class RsvpLinkTests(TestCase):
    """One-tap RSVP via WhatsApp URL buttons (GET /r/y|n/<token>/)."""

    def setUp(self):
        self.guest = WeddingGuest.objects.create(
            full_name="نادر", phone_e164="201007776666")

    def test_attend_link_records_and_renders_thanks(self):
        r = self.client.get(reverse("rsvp_attend", args=[self.guest.invitation_token]))
        self.assertEqual(r.status_code, 200)
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.rsvp, WeddingGuest.Rsvp.ATTENDING)

    def test_decline_link_records(self):
        self.client.get(reverse("rsvp_decline", args=[self.guest.invitation_token]))
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.rsvp, WeddingGuest.Rsvp.DECLINED)

    def test_can_switch_choice(self):
        self.client.get(reverse("rsvp_attend", args=[self.guest.invitation_token]))
        self.client.get(reverse("rsvp_decline", args=[self.guest.invitation_token]))
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.rsvp, WeddingGuest.Rsvp.DECLINED)

    def test_disabled_rsvp_is_noop(self):
        cfg = WeddingConfig.get()
        cfg.rsvp_enabled = False
        cfg.save()
        self.client.get(reverse("rsvp_attend", args=[self.guest.invitation_token]))
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.rsvp, WeddingGuest.Rsvp.NONE)


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


@override_settings(**WA_SETTINGS)
class CalendarIcsTests(TestCase):
    """«أضف إلى التقويم» — /wedding.ics builds a valid RFC 5545 event from
    WeddingConfig (nothing hardcoded), in UTC, with folded UTF-8 lines."""

    def setUp(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        self.config = WeddingConfig.get()
        self.config.venue_name = "قاعة الاختبار"
        self.config.venue_address = "شارع التجربة ١"
        self.config.map_url = "https://maps.example.com/x"
        self.config.wedding_datetime = datetime(2026, 7, 22, 20, 0, tzinfo=ZoneInfo("Africa/Cairo"))
        self.config.save()

    def _unfolded(self):
        resp = Client().get(reverse("calendar_ics"))
        self.assertEqual(resp.status_code, 200)
        return resp, resp.content.replace(b"\r\n ", b"").decode("utf-8")

    def test_headers_type_and_attachment_filename(self):
        resp, _ = self._unfolded()
        self.assertEqual(resp["Content-Type"], "text/calendar; charset=utf-8")
        self.assertIn('attachment; filename="elzant-wedding.ics"', resp["Content-Disposition"])

    def test_event_fields_come_from_config_in_utc(self):
        _, text = self._unfolded()
        # 20:00 Cairo (صيفاً UTC+3) == 17:00Z
        self.assertIn("DTSTART:20260722T170000Z", text)
        self.assertIn("DTEND:20260722T210000Z", text)
        self.assertIn("SUMMARY:حفل زفاف محمود ورينان", text)
        self.assertIn("قاعة الاختبار", text)
        self.assertIn("https://maps.example.com/x", text)
        self.assertIn("BEGIN:VALARM", text)
        self.assertIn("TRIGGER:-P1D", text)

    def test_datetime_not_hardcoded_and_winter_offset_correct(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        # شتاءً القاهرة UTC+2 → 19:30 == 17:30Z (يثبت أن التحويل يُحسب لا يُثبَّت)
        self.config.wedding_datetime = datetime(2027, 1, 5, 19, 30, tzinfo=ZoneInfo("Africa/Cairo"))
        self.config.save()
        _, text = self._unfolded()
        self.assertIn("DTSTART:20270105T173000Z", text)

    def test_lines_folded_within_75_octets_and_utf8_survives(self):
        resp = Client().get(reverse("calendar_ics"))
        raw = resp.content
        self.assertIn(b"\r\n", raw)
        for line in raw.split(b"\r\n"):
            self.assertLessEqual(len(line), 75, line[:80])
        raw.replace(b"\r\n ", b"").decode("utf-8")  # must not raise mid-character


@override_settings(**WA_SETTINGS)
class InvitationPrivacyTests(TestCase):
    """The private page greets the guest — but the name must never leak into
    link-preview surfaces (OG meta) or client storage keys."""

    def setUp(self):
        self.guest = WeddingGuest.objects.create(full_name="ضيف الاختبار الكريم")

    def test_private_page_renders_and_greets_guest(self):
        resp = Client().get(reverse("invitation", args=[self.guest.invitation_token]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "ضيف الاختبار الكريم")

    def test_bad_token_is_404(self):
        self.assertEqual(Client().get("/i/not-a-real-token/").status_code, 404)

    def test_guest_name_never_inside_meta_tags(self):
        import re

        html = Client().get(
            reverse("invitation", args=[self.guest.invitation_token])
        ).content.decode()
        for tag in re.findall(r"<meta[^>]+>", html):
            self.assertNotIn("ضيف الاختبار", tag, tag)

    def test_intro_storage_key_uses_pk_not_token(self):
        resp = Client().get(reverse("invitation", args=[self.guest.invitation_token]))
        self.assertContains(resp, f'data-key="elzant_envelope_opened-g{self.guest.pk}"')
        self.assertNotContains(resp, f"elzant_envelope_opened-{self.guest.invitation_token}")


@override_settings(**WA_SETTINGS)
class CountdownStateTests(TestCase):
    """Server-rendered countdown: real numbers without JS, and a post-wedding
    thank-you state instead of negative digits."""

    def test_past_wedding_hides_boxes_and_shows_thanks(self):
        import re
        from datetime import datetime, timezone as datetime_timezone

        config = WeddingConfig.get()
        config.wedding_datetime = datetime(2020, 1, 1, 18, 0, tzinfo=datetime_timezone.utc)
        config.save()
        resp = Client().get(reverse("home"))
        self.assertContains(resp, "تمّ الزفاف بحمد الله")
        html = resp.content.decode()
        box = re.search(r'id="countdown"[^>]*class="([^"]*)"', html)
        self.assertIn("hidden", box.group(1))
        self.assertNotIn("-", re.search(r'data-unit="days"[^>]*>([^<]*)<', html).group(1))

    def test_future_wedding_renders_positive_initials(self):
        import re
        from datetime import datetime
        from zoneinfo import ZoneInfo

        config = WeddingConfig.get()
        config.wedding_datetime = datetime(2030, 1, 1, 20, 0, tzinfo=ZoneInfo("Africa/Cairo"))
        config.save()
        html = Client().get(reverse("home")).content.decode()
        box = re.search(r'id="countdown"[^>]*class="([^"]*)"', html)
        self.assertNotIn("hidden", box.group(1))
        days = int(re.search(r'data-unit="days"[^>]*>(\d+)<', html).group(1))
        self.assertGreater(days, 0)


@override_settings(**WA_SETTINGS)
class BrandingFallbackTests(TestCase):
    """Branding resolution: admin uploads win; missing generated assets degrade
    gracefully instead of 500ing the whole site (manifest storage)."""

    def test_home_renders_with_no_admin_uploads(self):
        resp = Client().get(reverse("home"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "<img")

    def test_context_processor_never_500s_when_static_raises(self):
        with patch("core.context_processors.static", side_effect=ValueError("no manifest entry")):
            resp = Client().get(reverse("home"))
        self.assertEqual(resp.status_code, 200)

    def test_admin_uploaded_hero_and_og_take_precedence(self):
        import tempfile

        from django.core.files.base import ContentFile
        from django.test import override_settings as _override

        from core.context_processors import _hero, _og

        gif = (
            b"GIF87a\x01\x00\x01\x00\x80\x01\x00\x00\x00\x00ccc,\x00\x00\x00\x00"
            b"\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
        )
        with tempfile.TemporaryDirectory() as media:
            with _override(MEDIA_ROOT=media):
                config = WeddingConfig.get()
                config.hero_image.save("hero-admin.gif", ContentFile(gif), save=False)
                config.og_image.save("og-admin.gif", ContentFile(gif), save=True)

                hero_src, hero_srcset = _hero(config)
                self.assertIn("hero-admin", hero_src)
                self.assertEqual(hero_srcset, "")  # لا srcset لصورة الأدمن

                og_path, og_w, og_h = _og(config)
                self.assertIn("og-admin", og_path)
                self.assertIsNone(og_w)  # لا أبعاد مفترضة لصورة مجهولة الأبعاد

    def test_favicon_ico_probe_never_404s(self):
        resp = Client().get("/favicon.ico")
        self.assertIn(resp.status_code, (204, 302))

    def test_head_declares_a_favicon_link(self):
        self.assertContains(Client().get(reverse("home")), 'rel="icon"')


@override_settings(**WA_SETTINGS)
class InboundFreeTextTests(TestCase):
    """Non-RSVP WhatsApp replies are kept visible: stored in MessageLog and
    (optionally) emailed to the family — never lost in the API void."""

    def setUp(self):
        self.url = reverse("twilio_inbound")
        self.guest = WeddingGuest.objects.create(
            full_name="ماجد", phone_number="01005554444", phone_e164="201005554444",
        )

    @patch("core.webhooks.validate_twilio_request", return_value=True)
    def test_free_text_from_guest_is_logged(self, _v):
        resp = self.client.post(self.url, {
            "From": "whatsapp:+201005554444", "Body": "وين القاعة بالضبط؟",
            "ProfileName": "Majed", "MessageSid": "SM123",
        })
        self.assertEqual(resp.status_code, 200)
        entry = MessageLog.objects.filter(template_name="inbound_text").get()
        self.assertEqual(entry.guest, self.guest)
        self.assertEqual(entry.payload["body"], "وين القاعة بالضبط؟")
        # لم يتغيّر ردّ الحضور
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.rsvp, WeddingGuest.Rsvp.NONE)

    @patch("core.webhooks.validate_twilio_request", return_value=True)
    def test_unknown_sender_text_logged_without_guest(self, _v):
        self.client.post(self.url, {"From": "whatsapp:+201000000000", "Body": "مبروووك"})
        entry = MessageLog.objects.filter(template_name="inbound_text").get()
        self.assertIsNone(entry.guest)
        self.assertEqual(entry.payload["body"], "مبروووك")

    @patch("core.webhooks.validate_twilio_request", return_value=True)
    def test_rsvp_button_does_not_double_log(self, _v):
        self.client.post(self.url, {
            "From": "whatsapp:+201005554444", "ButtonPayload": "rsvp_yes",
            "ButtonText": "سأحضر بإذن الله",
        })
        self.assertFalse(MessageLog.objects.filter(template_name="inbound_text").exists())
        self.assertTrue(MessageLog.objects.filter(template_name="rsvp_inbound").exists())

    @patch("core.webhooks.validate_twilio_request", return_value=True)
    def test_empty_body_no_media_not_logged(self, _v):
        self.client.post(self.url, {"From": "whatsapp:+201005554444", "Body": "  "})
        self.assertFalse(MessageLog.objects.filter(template_name="inbound_text").exists())

    @override_settings(
        INBOUND_NOTIFY_EMAIL="family@example.com",
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    )
    @patch("core.webhooks.validate_twilio_request", return_value=True)
    def test_notify_email_sent_when_configured(self, _v):
        from django.core import mail

        self.client.post(self.url, {"From": "whatsapp:+201005554444", "Body": "ألف مبروك!"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("ماجد", mail.outbox[0].subject)
        self.assertIn("ألف مبروك!", mail.outbox[0].body)
