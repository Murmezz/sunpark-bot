import ast
import sys
import asyncio
import json
import sqlite3
import unittest
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import events as event_module
from events import EventsMixin, russian_phone

tree = ast.parse((ROOT / 'src' / 'entry.py').read_text())
tree.body = [n for n in tree.body if not (isinstance(n, ast.ImportFrom) and n.module in ('workers', 'validation'))]
namespace = {'WorkerEntrypoint': type('WorkerEntrypoint', (), {})}
exec(compile(tree, 'entry.py', 'exec'), namespace)


class Harness(namespace['Bot']):
    def __init__(self, db=None):
        self.db = db or sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        self.sent, self.edited, self.answers = [], [], []

    async def db_run(self, sql, *args):
        if any(a is None for a in args):
            raise AssertionError('Do not bind Python None through the D1 FFI')
        cur = self.db.execute(sql, args)
        return NS(meta=NS(changes=max(0, cur.rowcount)))

    async def db_first(self, sql, *args):
        row = self.db.execute(sql, args).fetchone()
        return NS(**dict(row)) if row else None

    async def db_all(self, sql, *args):
        return NS(results=[NS(**dict(r)) for r in self.db.execute(sql, args).fetchall()])

    async def send(self, uid, text, markup=None):
        self.sent.append((uid, text, markup))

    async def edit(self, msg, text, markup=None):
        self.edited.append((msg, text, markup))

    async def answer(self, *args):
        self.answers.append(args)

    async def clear_action(self, uid):
        pass

    async def is_manager(self, uid, cfg):
        return uid == 1


def callback(data, uid=1):
    return {'id': 'cb', 'data': data, 'from': {'id': uid}, 'message': {'message_id': 1, 'chat': {'id': uid, 'type': 'private'}}}


def message(text='', uid=2, username=None, contact=None):
    result = {'text': text, 'from': {'id': uid, 'username': username}, 'chat': {'id': uid, 'type': 'private'}}
    if contact:
        result['contact'] = contact
    return result


class EventsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        event_module.EVENTS_ADMIN_ONLY = False
        self.bot = Harness()
        await self.bot.event_init()
        await self.bot.db_run("INSERT INTO events(title,description,starts_at,location,price,capacity,is_open,created_by,creation_key) VALUES(?,?,?,?,?,?,?,?,?)", 'Вечер', 'Описание', '2099-01-01 16:00:00', 'SUNPARK', 'Бесплатно', 5, 1, 1, 'fixture')

    async def test_admin_preview_hides_guest_button_and_preserves_admin_test_route(self):
        event_module.EVENTS_ADMIN_ONLY = True
        guest_buttons = [b['callback_data'] for row in self.bot.home_keyboard(False)['inline_keyboard'] for b in row]
        admin_buttons = [b['callback_data'] for row in self.bot.home_keyboard(True)['inline_keyboard'] for b in row]
        self.assertNotIn('ev:list:0', guest_buttons)
        self.assertIn('ev:list:0', admin_buttons)
        for data in ['ev:list:0', 'ev:view:1', 'ev:join:1', 'ev:save:old', 'ev:cancel:1:1']:
            await self.bot.event_callback(callback(data, 2), {})
            self.assertIn('только администраторам', self.bot.answers[-1][1])
        self.assertFalse(self.bot.edited)
        await self.bot.event_callback(callback('ev:join:1', 1), {})
        self.assertIsNotNone(await self.bot.db_first('SELECT * FROM event_sessions WHERE user_id=1'))
        self.assertEqual((await self.bot.event_get(1)).self_guests, 0)

    async def test_admin_preview_rejects_commands_and_unfinished_guest_sessions(self):
        event_module.EVENTS_ADMIN_ONLY = True
        await self.bot.event_message(message('/events'), {})
        self.assertIn('только администраторам', self.bot.sent[-1][1])
        await self.bot.event_new_session(2, 'self', 1)
        await self.bot.event_message(message('Иван'), {})
        self.assertIsNone(await self.bot.db_first('SELECT * FROM event_sessions WHERE user_id=2'))
        await self.bot.event_new_session(2, 'self', 1)
        await self.bot.event_save(2, 'anything', False)
        self.assertIsNone(await self.bot.db_first('SELECT * FROM event_sessions WHERE user_id=2'))
        await self.bot.event_message(message('/events', uid=1), {})
        self.assertIn('Мероприятия', self.bot.sent[-1][1])

    def person(self, phone='+79991234567', size=1):
        return {'first_name': 'Иван', 'last_name': 'Иванов', 'phone': phone, 'party_size': size, 'telegram_username': ''}

    async def test_phone_validation_and_normalization(self):
        for phone in ['89991234567', '+7 (999) 123-45-67', '9991234567']:
            self.assertEqual(russian_phone(phone), '+79991234567')
        for phone in ['текст', '+380991234567', '+77011234567', '+7999abc1234567', '123', '']:
            self.assertIsNone(russian_phone(phone))

    async def test_atomic_capacity_counts_company_and_excludes_manual(self):
        a = await self.bot.event_insert_registration(1, self.person(size=4), 2, False)
        b = await self.bot.event_insert_registration(1, self.person('+79992222222', 2), 3, False)
        c = await self.bot.event_insert_registration(1, self.person('+79993333333', 20), 1, True)
        d = await self.bot.event_insert_registration(1, self.person('+79994444444', 1), 4, False)
        self.assertEqual([x.meta.changes for x in [a, b, c, d]], [1, 0, 1, 1])
        event = await self.bot.event_get(1)
        self.assertEqual((event.self_guests, event.total_guests), (5, 25))
        manual = await self.bot.db_first('SELECT * FROM event_registrations WHERE added_by_admin=1')
        self.assertIsNone(manual.telegram_id)
        self.assertEqual(manual.admin_id, 1)

    async def test_duplicate_phone_and_telegram_per_event(self):
        await self.bot.event_insert_registration(1, self.person(), 2, False)
        same_phone = await self.bot.event_insert_registration(1, self.person(), 1, True)
        same_telegram = await self.bot.event_insert_registration(1, self.person('+79998888888'), 2, False)
        self.assertEqual((same_phone.meta.changes, same_telegram.meta.changes), (0, 0))
        await self.bot.db_run("INSERT INTO events(title,starts_at,location,price,capacity,is_open,created_by,creation_key) VALUES('Второе','2099-01-01 16:00:00','SUNPARK','0',5,1,1,'second')")
        other_event = await self.bot.event_insert_registration(2, self.person(), 2, False)
        self.assertEqual(other_event.meta.changes, 1)

    async def test_close_between_input_and_confirmation(self):
        await self.bot.db_run('UPDATE events SET is_open=0 WHERE id=1')
        own = await self.bot.event_insert_registration(1, self.person(), 2, False)
        admin = await self.bot.event_insert_registration(1, self.person(), 1, True)
        self.assertEqual((own.meta.changes, admin.meta.changes), (0, 1))

    async def test_concurrent_parties_cannot_overbook(self):
        results = await asyncio.gather(*(self.bot.event_insert_registration(1, self.person(f'+7999000000{i}', 3), i+2, False) for i in range(5)))
        self.assertEqual(sum(x.meta.changes for x in results), 1)

    async def test_simultaneous_connections_atomic_capacity(self):
        self.bot.db.commit()
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / 'concurrent.sqlite')
            target = sqlite3.connect(path)
            self.bot.db.backup(target)
            target.close()
            barrier = threading.Barrier(5)
            def worker(i):
                db = sqlite3.connect(path, timeout=10)
                bot = Harness(db)
                barrier.wait()
                result = asyncio.run(bot.event_insert_registration(1, self.person(f'+7999000000{i}', 3), i+2, False))
                db.commit()
                db.close()
                return result.meta.changes
            with ThreadPoolExecutor(max_workers=5) as pool:
                results = list(pool.map(worker, range(5)))
            self.assertEqual(sum(results), 1)

    async def test_guest_list_pagination_and_html_escaping(self):
        for i in range(7):
            p = self.person(f'+7999000000{i}')
            p['first_name'] = '<b>Иван</b>'
            await self.bot.event_insert_registration(1, p, 1, True)
        await self.bot.event_callback(callback('ev:guests:1:0'), {})
        text, markup = self.bot.edited[-1][1:]
        self.assertIn('&lt;b&gt;', text)
        self.assertLess(len(text), 4096)
        self.assertTrue(any(b['callback_data']=='ev:guests:1:1' for r in markup['inline_keyboard'] for b in r))

    async def test_edit_conflict_does_not_overwrite_another_admin(self):
        await self.bot.event_callback(callback('ev:edit:1:capacity'), {})
        await self.bot.event_message(message('20', uid=1), {})
        s = await self.bot.db_first('SELECT * FROM event_sessions WHERE user_id=1')
        await self.bot.db_run('UPDATE events SET capacity=10,version=version+1 WHERE id=1')
        await self.bot.event_callback(callback('ev:save:' + s.nonce), {})
        self.assertEqual((await self.bot.event_get(1)).capacity, 10)

    async def test_self_fsm_own_contact_username_and_restart(self):
        await self.bot.event_callback(callback('ev:join:1', 2), {})
        await self.bot.event_message(message('Иван'), {})
        await self.bot.event_message(message('Иванов'), {})
        await self.bot.event_message(message('это не телефон'), {})
        s = await self.bot.db_first('SELECT * FROM event_sessions WHERE user_id=2')
        self.assertEqual(s.step, 2)
        await self.bot.event_message(message(contact={'phone_number': '89991234567', 'user_id': 3}), {})
        self.assertEqual((await self.bot.db_first('SELECT * FROM event_sessions WHERE user_id=2')).step, 2)
        restarted = Harness(self.bot.db)
        await restarted.event_message(message(contact={'phone_number': '89991234567', 'user_id': 2}), {})
        await restarted.event_message(message('4', username='ivan'), {})
        s = await restarted.db_first('SELECT * FROM event_sessions WHERE user_id=2')
        self.assertEqual(s.step, 4)
        self.assertEqual(json.loads(s.payload)['telegram_username'], 'ivan')
        await restarted.event_callback(callback('ev:save:' + s.nonce, 2), {})
        await restarted.event_callback(callback('ev:save:' + s.nonce, 2), {})
        rows = await restarted.db_all('SELECT * FROM event_registrations')
        self.assertEqual(len(rows.results), 1)
        self.assertEqual(rows.results[0].party_size, 4)
        self.assertTrue(any('Вы успешно зарегистрированы!' in text for _, text, _ in restarted.sent))

    async def test_manual_fsm_no_username_after_limit(self):
        await self.bot.event_insert_registration(1, self.person(size=5), 2, False)
        await self.bot.event_callback(callback('ev:manual:1'), {})
        self.assertTrue(any('Лимит самостоятельных регистраций достигнут' in t for _, t, _ in self.bot.sent))
        for text in ['Анна', 'Петрова', '89992222222', '7', 'Пропустить']:
            await self.bot.event_message(message(text, uid=1), {})
        s = await self.bot.db_first('SELECT * FROM event_sessions WHERE user_id=1')
        await self.bot.event_callback(callback('ev:save:' + s.nonce), {})
        r = await self.bot.db_first('SELECT * FROM event_registrations WHERE added_by_admin=1')
        self.assertEqual((r.party_size, r.telegram_username, r.telegram_id), (7, '', None))

    async def test_admin_create_edit_toggle_and_repeated_confirmation(self):
        await self.bot.event_callback(callback('ev:create'), {})
        for text in ['Ужин', '—', '01.01.2099 19:00', 'Зал 1', '1500 ₽ с человека', '50']:
            await self.bot.event_message(message(text, uid=1), {})
        s = await self.bot.db_first('SELECT * FROM event_sessions WHERE user_id=1')
        await self.bot.event_callback(callback('ev:save:' + s.nonce), {})
        await self.bot.event_callback(callback('ev:save:' + s.nonce), {})
        events = await self.bot.db_all('SELECT * FROM events')
        self.assertEqual(len(events.results), 2)
        new = events.results[1]
        self.assertEqual((new.starts_at, new.is_open), ('2099-01-01 16:00:00', 0))
        await self.bot.event_callback(callback(f'ev:toggle:2:{new.version}'), {})
        await self.bot.event_callback(callback('ev:edit:2:capacity'), {})
        await self.bot.event_message(message('20', uid=1), {})
        s = await self.bot.db_first('SELECT * FROM event_sessions WHERE user_id=1')
        await self.bot.event_callback(callback('ev:save:' + s.nonce), {})
        new = await self.bot.event_get(2)
        self.assertEqual((new.capacity, new.is_open), (20, 1))

    async def test_non_admin_privileged_callbacks_and_stale_sessions(self):
        for data in ['ev:create', 'ev:manage:0', 'ev:manual:1', 'ev:toggle:1:0', 'ev:guests:1:0', 'ev:delete:1:1', 'ev:edit:1:capacity']:
            await self.bot.event_callback(callback(data, 2), {})
        self.assertTrue(all(a[1] == 'Нет доступа.' for a in self.bot.answers))
        await self.bot.event_new_session(2, 'create')
        await self.bot.event_message(message('Нельзя'), {})
        self.assertIsNone(await self.bot.db_first('SELECT * FROM event_sessions WHERE user_id=2'))

    async def test_private_lists_and_owned_cancellation(self):
        await self.bot.event_insert_registration(1, self.person(size=5), 2, False)
        await self.bot.event_callback(callback('ev:cancel:1:1', 3), {})
        self.assertEqual((await self.bot.event_get(1)).self_guests, 5)
        await self.bot.event_callback(callback('ev:guests:1:0'), {})
        self.assertIn('+79991234567', self.bot.edited[-1][1])
        await self.bot.event_callback(callback('ev:cancelask:1:1', 2), {})
        self.assertEqual((await self.bot.event_get(1)).self_guests, 5)
        await self.bot.event_callback(callback('ev:cancel:1:1', 2), {})
        self.assertEqual((await self.bot.event_get(1)).self_guests, 0)

    async def test_session_cas_and_stale_confirmations(self):
        old = await self.bot.event_new_session(2, 'self', 1)
        await self.bot.event_message(message('Иван'), {})
        result = await self.bot.db_run("UPDATE event_sessions SET step=step+1 WHERE user_id=? AND nonce=? AND version=?", 2, old.nonce, old.version)
        self.assertEqual(result.meta.changes, 0)
        new = await self.bot.event_new_session(2, 'self', 1)
        await self.bot.event_callback(callback('ev:abort:' + old.nonce, 2), {})
        self.assertEqual((await self.bot.db_first('SELECT * FROM event_sessions WHERE user_id=2')).nonce, new.nonce)

    async def test_new_navigation_and_no_cart(self):
        guest = self.bot.home_keyboard(False)['inline_keyboard']
        admin = self.bot.admin_keyboard()['inline_keyboard']
        self.assertTrue(any(b['callback_data'] == 'ev:list:0' for r in guest for b in r))
        self.assertTrue(any(b['callback_data'] == 'ev:manage:0' for r in admin for b in r))
        self.assertFalse(any(b['callback_data'].startswith('cart:') for r in guest for b in r))
        self.assertEqual(namespace['MENU_ONLY'], False)


if __name__ == '__main__':
    unittest.main()
