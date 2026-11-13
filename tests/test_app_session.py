import json
import sys
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

from test_mini_app import AppHarness, app_request
from test_menu_preview import TOKEN, FakeResponse, signed
from mini_app_auth import SESSION_TTL, authenticate_app


class SessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = AppHarness()
        await self.bot.config()
        self.started = 1794550000
        self.raw = signed(when=self.started)

    async def call(self, operation, now, session=None, raw=None, **values):
        request = app_request({'init_data': self.raw if raw is None else raw, 'operation': operation, **values})
        if session:
            request.headers['X-Sunpark-Session'] = session
        with patch.dict(sys.modules, {'workers': NS(Response=FakeResponse)}), patch('mini_app_auth.time.time', return_value=now):
            response = await self.bot.mini_app_http(request)
        return response.status, json.loads(response.body)

    async def test_long_open_app_can_load_messages_and_submit_after_initial_auth_expires(self):
        status, data = await self.call('bootstrap', self.started)
        self.assertEqual(status, 200, data)
        session = data['session']
        later = self.started + 2 * 3600
        status, data = await self.call('screen', later, session, screen='tickets', scope='guest')
        self.assertEqual((status, data['tickets']), (200, []))
        status, data = await self.call('submit_form', later, session, kind='inquiry', values={'message': 'Вопрос'}, request_key='session-inquiry-123456')
        self.assertEqual(status, 200, data)
        status, data = await self.call('bootstrap', later, session)
        self.assertEqual((status, data['session']), (200, session), 'Reload must not extend session lifetime')

    async def test_expired_launch_cannot_start_session_and_expired_session_cannot_renew(self):
        for session, now in [(None, self.started + 3601), (authenticate_app(self.raw, TOKEN, now=self.started)[1], self.started + SESSION_TTL + 1)]:
            status, data = await self.call('bootstrap', now, session)
            self.assertEqual((status, data['code']), (401, 'AUTH_REQUIRED'))
        self.assertEqual((await self.bot.db_first('SELECT COUNT(*) n FROM tickets')).n, 0)

    async def test_session_cannot_change_user_launch_expiry_or_bot(self):
        _, session = authenticate_app(self.raw, TOKEN, now=self.started)
        later = self.started + 7200
        for raw, credential in [(signed(uid=2, when=self.started), session), (self.raw, session.replace(str(self.started), str(later))), (self.raw, session[:-1] + ('a' if session[-1] != 'a' else 'b'))]:
            status, data = await self.call('screen', later, credential, raw=raw, screen='tickets')
            self.assertEqual(status, 401, data)
        with self.assertRaises(ValueError):
            authenticate_app(self.raw, 'other-bot-token', session, now=later)

    async def test_permissions_and_request_replay_still_apply_with_session(self):
        _, session = authenticate_app(self.raw, TOKEN, now=self.started)
        payload = {'kind': 'inquiry', 'values': {'message': 'Один вопрос'}, 'request_key': 'session-replay-123456'}
        self.assertEqual((await self.call('submit_form', self.started + 1, session, **payload))[0], 200)
        _, renewed = authenticate_app(self.raw, TOKEN, now=self.started + 2)
        self.assertEqual((await self.call('submit_form', self.started + 3, renewed, **payload))[0], 200)
        self.assertEqual((await self.bot.db_first('SELECT COUNT(*) n FROM tickets')).n, 1)
        self.bot.env.MANAGER_IDS = ''
        await self.bot.db_run("UPDATE config SET value='' WHERE key='manager_ids'")
        status, _ = await self.call('screen', self.started + 7200, session, screen='tickets', scope='staff')
        self.assertEqual(status, 403)
