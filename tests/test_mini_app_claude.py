"""The visual experiment shares the app's assets, API and security policy."""
import sys
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

from test_mini_app import AppHarness, app_request
from test_menu_preview import FakeResponse
from mini_app_assets import APP_HTML, APP_CSS, APP_JS
from mini_app_claude import CLAUDE_HTML, CLAUDE_STYLE, CLAUDE_EXTRA_CSS


class ClaudeVariantTests(unittest.IsolatedAsyncioTestCase):
    async def request(self, path, method='GET'):
        with patch.dict(sys.modules, {'workers': NS(Response=FakeResponse)}):
            return await AppHarness().mini_app_http(app_request(path=path, method=method))

    async def test_variant_changes_only_stylesheet_and_page_title(self):
        expected = APP_HTML.replace('/app/style.css', '/app-claude/style.css').replace(
            '<title>SunPark</title>', '<title>SunPark · Клод тест</title>')
        response = await self.request('/app-claude')
        self.assertEqual((response.status, response.body), (200, expected))
        self.assertEqual(response.body, CLAUDE_HTML)
        self.assertIn('/app/app.js', response.body)
        self.assertEqual((await self.request('/app')).body, APP_HTML)
        self.assertEqual((await self.request('/app/style.css')).body, APP_CSS)
        self.assertEqual((await self.request('/app/app.js')).body, APP_JS)

    async def test_variant_styles_and_security_headers(self):
        original = await self.request('/app')
        for path, body, mime in [('/app-claude/', CLAUDE_HTML, 'text/html'),
                                 ('/app-claude/style.css', CLAUDE_STYLE, 'text/css')]:
            response = await self.request(path)
            self.assertEqual((response.status, response.body), (200, body))
            self.assertTrue(response.headers['content-type'].startswith(mime))
            for header in ('cache-control', 'content-security-policy', 'x-content-type-options', 'referrer-policy'):
                self.assertEqual(response.headers[header], original.headers[header])
        self.assertEqual(CLAUDE_STYLE, APP_CSS + '\n' + CLAUDE_EXTRA_CSS)

    async def test_variant_does_not_add_an_api_or_shared_asset_copy(self):
        self.assertEqual((await self.request('/app-claude', 'POST')).status, 405)
        self.assertEqual((await self.request('/app-claude/missing')).status, 404)
        self.assertEqual((await self.request('/app-claude/app.js')).status, 404)
        self.assertEqual((await self.request('/api/app', 'POST')).status, 401)
        self.assertIsNone(await self.request('/app-claude-other'))
