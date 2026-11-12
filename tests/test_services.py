"""Service navigation uses public content and never creates restaurant tickets."""
import json
import sys
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

from test_mini_app import AppHarness, app_request
from test_menu_preview import FakeResponse, signed
from services import SERVICES, service_text


def callback(data, photo=False):
    msg = {"message_id": 7, "chat": {"id": 2}}
    if photo:
        msg["photo"] = [{"file_id": "fixture"}]
    return {"id": "fixture", "data": data, "from": {"id": 2}, "message": msg}


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = AppHarness()
        await self.bot.config()

    async def test_all_sections_are_reachable_without_creating_a_request(self):
        buttons = [b["callback_data"] for row in self.bot.home_keyboard(False)["inline_keyboard"] for b in row]
        for service in SERVICES:
            data = "service:" + service["id"]
            self.assertIn(data, buttons)
            self.assertTrue(await self.bot.service_callback(callback(data)))
            method, params = self.bot.notifications[-1]
            self.assertEqual(method, "editMessageText")
            self.assertIn(service["phone_label"], params["text"])
            self.assertIn('service:'+service['id']+':photo:0', json.dumps(params["reply_markup"]))
            self.assertIn(service["booking_url"], json.dumps(params["reply_markup"]))
        self.assertIsNone(await self.bot.db_first("SELECT * FROM tickets"))

    async def test_photo_carousel_edits_existing_photo_and_recovers_from_source_failure(self):
        await self.bot.service_callback(callback("service:wake:photo:0"))
        self.assertEqual(self.bot.notifications[-1][0], "sendPhoto")
        await self.bot.service_callback(callback("service:wake:photo:1", photo=True))
        method, params = self.bot.notifications[-1]
        self.assertEqual(method, "editMessageMedia")
        self.assertEqual(params["message_id"], 7)
        self.assertEqual(params["media"]["media"], SERVICES[0]["photos"][1])
        async def failed(method, params):
            if method == "sendPhoto":
                raise RuntimeError("remote image unavailable")
        self.bot.tg = failed
        await self.bot.service_callback(callback("service:hotel:photo:0"))
        self.assertIn("Фото временно не загрузилось", self.bot.notifications[-1][1])

    async def test_unknown_service_or_photo_index_does_not_send_media(self):
        for value in ("service:missing", "service:wake:photo:-1", "service:wave:photo:99", "service:hotel:photo:NaN"):
            self.assertTrue(await self.bot.service_callback(callback(value)))
        self.assertFalse(any(n[0] in ("sendPhoto", "editMessageMedia") for n in self.bot.notifications))
        self.assertFalse(await self.bot.service_callback(callback("booking:start")))

    async def test_bootstrap_contains_services_and_the_image_policy_allows_only_the_source(self):
        with patch.dict(sys.modules, {"workers": NS(Response=FakeResponse)}):
            response = await self.bot.mini_app_http(app_request({"operation": "bootstrap", "init_data": signed()}))
            data = json.loads(response.body)
            self.assertEqual(response.status, 200)
            self.assertEqual([s["id"] for s in data["services"]["items"]], ["wake", "wave", "hotel"])
            response = await self.bot.mini_app_http(app_request(path="/app", method="GET"))
            self.assertIn("img-src 'self' data: blob: https://sunparkspb.ru;", response.headers["content-security-policy"])
            response = await self.bot.mini_app_http(app_request({"operation": "bootstrap"}))
            self.assertEqual(response.status, 401)

    def test_full_tariffs_fit_telegram_and_identify_the_season(self):
        for service in SERVICES:
            self.assertLess(len(service_text(service, True)), 4096)
        self.assertIn("лето 2026", service_text(SERVICES[0], True))
        self.assertIn("оплачивается отдельно", service_text(SERVICES[0], True))
