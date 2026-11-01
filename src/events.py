"""Event registration for the existing SUNPARK Cloudflare Python Worker.

Persistent FSM and registrations use the Worker's SQLite-compatible D1 binding.
No Telegram token or administrator IDs are stored in this module.
"""
import html
import json
import re
import uuid
from datetime import datetime, timedelta, timezone


def esc(value):
    return html.escape(str(value or ""), quote=False)


def button(text, callback):
    return {"text": text, "callback_data": callback}


def keyboard(rows):
    return {"inline_keyboard": rows}


def russian_phone(value):
    raw = str(value or "").strip()
    if not re.fullmatch(r"\+?[\d\s()\-]+", raw):
        return None
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10:
        digits = "7" + digits
    elif len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    if not re.fullmatch(r"7[3489]\d{9}", digits):
        return None
    return "+" + digits


FIELDS = [
    ("title", "Название мероприятия (до 100 символов):"),
    ("description", "Описание (до 1200 символов). Если не нужно, отправьте «—»:"),
    ("starts_at", "Дата и время по Москве: ДД.ММ.ГГГГ ЧЧ:ММ"),
    ("location", "Место проведения (до 200 символов):"),
    ("price", "Стоимость и условия оплаты (до 100 символов), например «Бесплатно» или «1500 ₽ с человека»:"),
    ("capacity", "Максимум гостей по самостоятельной регистрации (число от 1 до 100000). Ручные записи в этот лимит не входят:"),
]
FIELD_LABELS = {"title": "Название", "description": "Описание", "starts_at": "Дата и время", "location": "Место", "price": "Стоимость", "capacity": "Лимит самостоятельной записи"}
PERSON_FIELDS = [
    ("first_name", "Введите имя контактного лица:"),
    ("last_name", "Введите фамилию контактного лица:"),
    ("phone", "Введите российский номер телефона или отправьте контакт:"),
    ("party_size", "Сколько человек будет вместе с контактным лицом? Введите общее количество, включая его:"),
    ("telegram_username", "Telegram-ник контактного лица, если есть. Можно нажать «Пропустить»:"),
]
MSK = timezone(timedelta(hours=3))


class EventsMixin:
    async def event_init(self):
        await self.db_run("CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', starts_at TEXT NOT NULL, location TEXT NOT NULL, price TEXT NOT NULL, capacity INTEGER NOT NULL CHECK(capacity BETWEEN 1 AND 100000), is_open INTEGER NOT NULL DEFAULT 0, created_by INTEGER NOT NULL, creation_key TEXT NOT NULL UNIQUE, version INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT (datetime('now')))")
        await self.db_run("CREATE TABLE IF NOT EXISTS event_registrations (id INTEGER PRIMARY KEY AUTOINCREMENT, event_id INTEGER NOT NULL REFERENCES events(id), first_name TEXT NOT NULL, last_name TEXT NOT NULL, phone TEXT NOT NULL, party_size INTEGER NOT NULL CHECK(party_size BETWEEN 1 AND 100000), telegram_id INTEGER, telegram_username TEXT NOT NULL DEFAULT '', added_by_admin INTEGER NOT NULL DEFAULT 0, admin_id INTEGER, created_at TEXT NOT NULL DEFAULT (datetime('now')), UNIQUE(event_id,phone), UNIQUE(event_id,telegram_id))")
        await self.db_run("CREATE TABLE IF NOT EXISTS event_sessions (user_id INTEGER PRIMARY KEY, mode TEXT NOT NULL, event_id INTEGER NOT NULL DEFAULT 0, step INTEGER NOT NULL DEFAULT 0, payload TEXT NOT NULL, nonce TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL DEFAULT (datetime('now')))")
        await self.db_run("CREATE INDEX IF NOT EXISTS event_registrations_event_idx ON event_registrations(event_id,added_by_admin)")

    async def event_get(self, event_id):
        return await self.db_first(
            "SELECT e.*, COALESCE((SELECT SUM(party_size) FROM event_registrations r WHERE r.event_id=e.id AND r.added_by_admin=0),0) self_guests, COALESCE((SELECT SUM(party_size) FROM event_registrations r WHERE r.event_id=e.id),0) total_guests FROM events e WHERE e.id=?", event_id)

    async def event_clear_session(self, uid, nonce=None):
        if nonce is None:
            await self.db_run("DELETE FROM event_sessions WHERE user_id=?", uid)
        else:
            await self.db_run("DELETE FROM event_sessions WHERE user_id=? AND nonce=?", uid, nonce)

    async def event_new_session(self, uid, mode, event_id=0, payload=None):
        nonce = uuid.uuid4().hex[:16]
        await self.db_run("INSERT INTO event_sessions(user_id,mode,event_id,payload,nonce) VALUES(?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET mode=excluded.mode,event_id=excluded.event_id,step=0,payload=excluded.payload,nonce=excluded.nonce,version=event_sessions.version+1,updated_at=datetime('now')", uid, mode, event_id, json.dumps(payload or {}, ensure_ascii=False), nonce)
        await self.clear_action(uid)
        return await self.db_first("SELECT * FROM event_sessions WHERE user_id=?", uid)

    def event_fields(self, session):
        payload = json.loads(str(session.payload))
        if session.mode == "edit":
            return [field for field in FIELDS if field[0] == payload["field"]]
        return FIELDS if session.mode == "create" else (PERSON_FIELDS if session.mode == "manual" else PERSON_FIELDS[:4])

    async def event_prompt(self, uid, session):
        field, prompt = self.event_fields(session)[int(session.step)]
        rows = []
        if field == "phone":
            rows.append([{"text": "📱 Отправить контакт", "request_contact": True}])
        if field == "telegram_username":
            rows.append([{"text": "Пропустить"}])
        rows.append([{"text": "Отмена"}])
        await self.send(uid, prompt + "\n\n/cancel — отменить ввод.", {"keyboard": rows, "resize_keyboard": True, "one_time_keyboard": True})

    def event_text(self, event, admin=False):
        when = datetime.strptime(str(event.starts_at), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).astimezone(MSK).strftime("%d.%m.%Y %H:%M")
        remaining = max(0, int(event.capacity) - int(event.self_guests))
        lines = [f"🎟 <b>{esc(event.title)}</b>", f"📅 {when} (МСК)", f"📍 {esc(event.location)}", f"💳 {esc(event.price)}"]
        if event.description:
            lines.append("\n" + esc(event.description))
        lines.append(f"\nСвободно мест для самостоятельной записи: <b>{remaining}</b>")
        if not int(event.is_open):
            lines.append("Регистрация закрыта")
        if admin:
            lines.append(f"\nГостей всего: <b>{int(event.total_guests)}</b>\nСамостоятельно: {int(event.self_guests)} / {int(event.capacity)}\nВручную: {int(event.total_guests) - int(event.self_guests)}")
        return "\n".join(lines)

    async def event_list(self, uid, admin=False, page=0, msg=None):
        page = max(0, min(page, 100000))
        if admin:
            result = await self.db_all("SELECT id,title,is_open FROM events ORDER BY starts_at DESC,id DESC LIMIT 9 OFFSET ?", page * 8)
        else:
            result = await self.db_all("SELECT id,title,is_open FROM events e WHERE starts_at>=datetime('now') OR EXISTS (SELECT 1 FROM event_registrations r WHERE r.event_id=e.id AND r.telegram_id=?) ORDER BY starts_at,id LIMIT 9 OFFSET ?", uid, page * 8)
        rows = [[button(("🟢 " if int(e.is_open) else "🔒 ") + str(e.title)[:50], f"ev:{'admin' if admin else 'view'}:{e.id}")] for e in list(result.results)[:8]]
        nav = []
        if page:
            nav.append(button("◀️", f"ev:{'manage' if admin else 'list'}:{page-1}"))
        if len(result.results) > 8:
            nav.append(button("▶️", f"ev:{'manage' if admin else 'list'}:{page+1}"))
        if nav:
            rows.append(nav)
        if admin:
            rows.append([button("➕ Создать мероприятие", "ev:create")])
        rows.append([button("⚙️ Админ-панель" if admin else "🏠 На главную", "admin:panel" if admin else "back")])
        text = "🎟 <b>Мероприятия</b>\n\nВыберите мероприятие:" if result.results else "🎟 Мероприятий пока нет."
        if msg:
            await self.edit(msg, text, keyboard(rows))
        else:
            await self.send(uid, text, keyboard(rows))

    async def event_view(self, uid, event_id, admin=False, msg=None):
        event = await self.event_get(event_id)
        if not event:
            await self.send(uid, "Мероприятие не найдено.")
            return
        rows = []
        if admin:
            rows = [[button("Закрыть регистрацию" if int(event.is_open) else "Открыть регистрацию", f"ev:toggle:{event_id}:{event.version}")], [button("✏️ Настройки мероприятия", f"ev:settings:{event_id}")], [button("➕ Добавить вручную", f"ev:manual:{event_id}")], [button("📋 Посмотреть список / удалить запись", f"ev:guests:{event_id}:0")]]
        else:
            mine = await self.db_first("SELECT id,party_size FROM event_registrations WHERE event_id=? AND telegram_id=?", event_id, uid)
            if mine:
                rows.append([button(f"✅ Ваша запись: {mine.party_size} чел. · отменить", f"ev:cancelask:{event_id}:{mine.id}")])
            elif int(event.is_open) and int(event.self_guests) < int(event.capacity):
                rows.append([button("Зарегистрироваться", f"ev:join:{event_id}")])
        rows.append([button("◀️ К мероприятиям", "ev:manage:0" if admin else "ev:list:0")])
        if msg:
            await self.edit(msg, self.event_text(event, admin), keyboard(rows))
        else:
            await self.send(uid, self.event_text(event, admin), keyboard(rows))

    async def event_guest_list(self, uid, event_id, page, msg):
        event = await self.event_get(event_id)
        if not event:
            await self.send(uid, "Мероприятие не найдено.")
            return
        page = max(0, min(page, 100000))
        result = await self.db_all("SELECT * FROM event_registrations WHERE event_id=? ORDER BY id LIMIT 7 OFFSET ?", event_id, page * 6)
        lines = [f"📋 <b>{esc(event.title)}</b>\nГостей: {event.total_guests}. Страница {page+1}."]
        rows = []
        for r in list(result.results)[:6]:
            who = f"админ (ID {int(r.admin_id)})" if int(r.added_by_admin) else "пользователь"
            tag = "@" + esc(r.telegram_username) if r.telegram_username else "не указан"
            lines.append(f"\n#{r.id} · <b>{esc(r.first_name)} {esc(r.last_name)}</b>\n{esc(r.phone)} · {int(r.party_size)} чел.\nTelegram: {tag}\nДобавил: {who}")
            rows.append([button(f"🗑 Удалить запись #{r.id}", f"ev:deleteask:{event_id}:{r.id}")])
        if not result.results:
            lines.append("\nЗаписей пока нет.")
        nav = []
        if page:
            nav.append(button("◀️", f"ev:guests:{event_id}:{page-1}"))
        if len(result.results) > 6:
            nav.append(button("▶️", f"ev:guests:{event_id}:{page+1}"))
        if nav:
            rows.append(nav)
        rows.append([button("◀️ К мероприятию", f"ev:admin:{event_id}")])
        await self.edit(msg, "\n".join(lines), keyboard(rows))

    def event_parse_field(self, field, text):
        text = text.strip()
        limits = {"title": 100, "description": 1200, "location": 200, "price": 100, "first_name": 60, "last_name": 60}
        if field == "description" and text in ("—", "-"):
            return ""
        if field in limits:
            if not text or len(text) > limits[field] or (field in ("first_name", "last_name") and (not any(c.isalpha() for c in text) or any(c.isdigit() for c in text))):
                raise ValueError(f"Введите текст от 1 до {limits[field]} символов." if field not in ("first_name", "last_name") else "Введите имя или фамилию буквами, до 60 символов.")
            return text
        if field in ("capacity", "party_size"):
            if not re.fullmatch(r"[0-9]{1,6}", text) or not 1 <= int(text) <= 100000:
                raise ValueError("Введите целое число от 1 до 100000.")
            return int(text)
        if field == "starts_at":
            try:
                date = datetime.strptime(text, "%d.%m.%Y %H:%M").replace(tzinfo=MSK)
            except ValueError:
                raise ValueError("Введите дату и время по Москве в формате ДД.ММ.ГГГГ ЧЧ:ММ.")
            if date <= datetime.now(timezone.utc):
                raise ValueError("Дата мероприятия должна быть в будущем.")
            return date.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        if field == "phone":
            phone = russian_phone(text)
            if not phone:
                raise ValueError("Нужен российский номер: +7 999 123-45-67 или 8 999 123-45-67.")
            return phone
        if field == "telegram_username":
            if text.casefold() in ("пропустить", "-", "—"):
                return ""
            tag = text.lstrip("@")
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{3,31}", tag):
                raise ValueError("Введите Telegram-ник, например @username, или нажмите «Пропустить».")
            return tag
        raise ValueError("Неизвестное поле.")

    async def event_message(self, msg, cfg):
        if (msg.get("chat") or {}).get("type") != "private":
            return False
        uid = int((msg.get("from") or {})["id"])
        text = str(msg.get("text") or "").strip()
        command = text.split()[0].split("@")[0] if text else ""
        session = await self.db_first("SELECT * FROM event_sessions WHERE user_id=?", uid)
        mgr = await self.is_manager(uid, cfg)
        if command == "/events":
            await self.event_clear_session(uid)
            await self.clear_action(uid)
            await self.send(uid, "🎟 Мероприятия SUNPARK", self.persistent(mgr))
            await self.event_list(uid)
            return True
        if not session:
            return False
        if session.mode in ("create", "edit", "manual") and not mgr:
            await self.event_clear_session(uid)
            await self.send(uid, "Нет доступа.", self.persistent(False))
            return True
        if command in ("/start", "/admin") or text in ("🏠 Главное меню", "⚙️ Админ-панель", "👀 Как гость"):
            await self.event_clear_session(uid)
            return False
        if command == "/cancel" or text == "Отмена":
            await self.event_clear_session(uid)
            await self.send(uid, "Ввод отменён.", self.persistent(mgr))
            await self.event_list(uid, session.mode in ("create", "edit", "manual"))
            return True
        fields = self.event_fields(session)
        if int(session.step) >= len(fields):
            await self.send(uid, "Проверьте данные и нажмите «Подтвердить» в сообщении выше. /cancel — отмена.")
            return True
        field = fields[int(session.step)][0]
        payload = json.loads(str(session.payload))
        contact = msg.get("contact")
        if field == "phone" and contact:
            if session.mode != "manual" and int(contact.get("user_id") or 0) != uid:
                await self.send(uid, "Отправьте свой контакт или введите свой номер текстом.")
                return True
            text = str(contact.get("phone_number") or "")
        try:
            payload[field] = self.event_parse_field(field, text)
            if session.mode == "self" and field == "party_size":
                event = await self.event_get(int(session.event_id))
                if not event or not int(event.is_open):
                    await self.event_clear_session(uid)
                    await self.send(uid, "Регистрация закрыта", self.persistent(mgr))
                    return True
                available = max(0, int(event.capacity) - int(event.self_guests))
                if payload[field] > available:
                    raise ValueError(f"Для самостоятельной записи осталось {available} мест. Укажите меньшее количество или отмените ввод: /cancel.")
        except ValueError as e:
            await self.send(uid, str(e))
            return True
        if session.mode == "self":
            payload["telegram_id"] = uid
            payload["telegram_username"] = str((msg.get("from") or {}).get("username") or "")
        saved = await self.db_run("UPDATE event_sessions SET step=step+1,payload=?,version=version+1,updated_at=datetime('now') WHERE user_id=? AND nonce=? AND version=?", json.dumps(payload, ensure_ascii=False), uid, session.nonce, session.version)
        if not int(saved.meta.changes or 0):
            await self.send(uid, "Данные уже обновились. Ответьте на последний вопрос бота.")
            return True
        session = await self.db_first("SELECT * FROM event_sessions WHERE user_id=?", uid)
        if int(session.step) < len(fields):
            await self.event_prompt(uid, session)
        else:
            if session.mode in ("create", "edit"):
                summary = "\n".join(f"<b>{esc(FIELD_LABELS[k])}</b>: {esc(v)}" for k, v in payload.items() if k in FIELD_LABELS)
                if "starts_at" in payload:
                    summary = summary.replace(esc(payload["starts_at"]), esc(datetime.strptime(payload["starts_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).astimezone(MSK).strftime("%d.%m.%Y %H:%M МСК")))
            else:
                summary = f"<b>{esc(payload['first_name'])} {esc(payload['last_name'])}</b>\n{esc(payload['phone'])}\nГостей, включая контактное лицо: <b>{payload['party_size']}</b>"
                if payload.get("telegram_username"):
                    summary += "\n@" + esc(payload["telegram_username"])
            await self.send(uid, "Данные введены. Проверьте подтверждение ниже.", self.persistent(mgr))
            await self.send(uid, "Проверьте данные:\n\n" + summary, keyboard([[button("✅ Подтвердить", "ev:save:" + str(session.nonce))], [button("❌ Отмена", "ev:abort:" + str(session.nonce))]]))
        return True

    async def event_insert_registration(self, event_id, payload, uid, manual):
        # One SQLite statement serializes availability checking and insertion.
        return await self.db_run(
            "INSERT OR IGNORE INTO event_registrations(event_id,first_name,last_name,phone,party_size,telegram_id,telegram_username,added_by_admin,admin_id) SELECT e.id,?,?,?,?,CASE WHEN ?=1 THEN NULL ELSE ? END,?,?,CASE WHEN ?=1 THEN ? ELSE NULL END FROM events e WHERE e.id=? AND (?=1 OR (e.is_open=1 AND e.starts_at>datetime('now') AND COALESCE((SELECT SUM(party_size) FROM event_registrations r WHERE r.event_id=e.id AND r.added_by_admin=0),0)+?<=e.capacity))",
            payload["first_name"], payload["last_name"], payload["phone"], payload["party_size"], 1 if manual else 0, uid, payload.get("telegram_username") or "", 1 if manual else 0, 1 if manual else 0, uid, event_id, 1 if manual else 0, payload["party_size"])

    async def event_save(self, uid, nonce, mgr):
        s = await self.db_first("SELECT * FROM event_sessions WHERE user_id=? AND nonce=?", uid, nonce)
        if not s or int(s.step) != len(self.event_fields(s)):
            await self.send(uid, "Это подтверждение уже обработано или устарело.")
            return
        if s.mode in ("create", "edit", "manual") and not mgr:
            await self.event_clear_session(uid)
            await self.send(uid, "Нет доступа.")
            return
        p = json.loads(str(s.payload))
        event_id = int(s.event_id)
        if s.mode == "create":
            await self.db_run("INSERT OR IGNORE INTO events(title,description,starts_at,location,price,capacity,created_by,creation_key) VALUES(?,?,?,?,?,?,?,?)", p["title"], p["description"], p["starts_at"], p["location"], p["price"], p["capacity"], uid, nonce)
            event = await self.db_first("SELECT id FROM events WHERE creation_key=?", nonce)
            event_id = int(event.id)
            result = "✅ Мероприятие создано. Проверьте настройки и откройте регистрацию."
        elif s.mode == "edit":
            field = p["field"]
            if field not in {key for key, _ in FIELDS}:
                await self.send(uid, "Некорректное поле.")
                return
            changed = await self.db_run(f"UPDATE events SET {field}=?,version=version+1 WHERE id=? AND version=?", p[field], event_id, p["event_version"])
            result = "✅ Настройки сохранены." if int(changed.meta.changes or 0) else "Настройки уже изменил другой администратор. Откройте их заново."
        else:
            manual = s.mode == "manual"
            inserted = await self.event_insert_registration(event_id, p, uid, manual)
            if not int(inserted.meta.changes or 0):
                duplicate = await self.db_first("SELECT id FROM event_registrations WHERE event_id=? AND (phone=? OR (?=0 AND telegram_id=?))", event_id, p["phone"], 1 if manual else 0, uid)
                result = "Человек с таким телефоном или вашим Telegram уже зарегистрирован на это мероприятие." if duplicate else "Регистрация закрыта или для вашей компании уже недостаточно мест."
            else:
                result = "✅ Запись добавлена вручную." if manual else "Вы успешно зарегистрированы!"
                result += f"\nКоличество гостей: {p['party_size']}."
        await self.event_clear_session(uid, nonce)
        await self.send(uid, result, self.persistent(mgr))
        await self.event_view(uid, event_id, s.mode in ("create", "edit", "manual"))

    async def event_callback(self, cb, cfg):
        data = str(cb.get("data") or "")
        if not data.startswith("ev:"):
            # Navigation away cancels an unfinished event form, not a registration.
            uid = int((cb.get("from") or {})["id"])
            if data != "noop":
                active = await self.db_first("SELECT user_id FROM event_sessions WHERE user_id=?", uid)
                if active:
                    await self.event_clear_session(uid)
                    await self.send(uid, "Ввод отменён.", self.persistent(await self.is_manager(uid, cfg)))
            return False
        uid = int((cb.get("from") or {})["id"])
        msg = cb.get("message")
        if not msg or (msg.get("chat") or {}).get("type") != "private":
            await self.answer(cb.get("id"))
            return True
        mgr = await self.is_manager(uid, cfg)
        parts = data.split(":")
        action = parts[1] if len(parts) > 1 else ""
        admin_actions = {"manage", "create", "admin", "settings", "edit", "toggle", "manual", "guests", "deleteask", "delete"}
        if action in admin_actions and not mgr:
            await self.answer(cb.get("id"), "Нет доступа.", True)
            return True
        await self.answer(cb.get("id"))
        try:
            if action == "save":
                await self.event_save(uid, parts[2], mgr)
                return True
            if action == "abort":
                await self.event_clear_session(uid, parts[2])
                await self.send(uid, "Ввод отменён.", self.persistent(mgr))
                return True
            if action in ("list", "manage"):
                await self.event_clear_session(uid)
                await self.clear_action(uid)
                await self.event_list(uid, action == "manage", int(parts[2]), msg)
                return True
            if action == "create":
                s = await self.event_new_session(uid, "create")
                await self.event_prompt(uid, s)
                return True
            event_id = int(parts[2])
            event = await self.event_get(event_id)
            if not event:
                await self.send(uid, "Мероприятие не найдено.")
                return True
            if action in ("view", "admin"):
                await self.event_clear_session(uid)
                await self.event_view(uid, event_id, action == "admin", msg)
            elif action == "settings":
                await self.event_clear_session(uid)
                labels = ["Название", "Описание", "Дата и время", "Место", "Стоимость", "Лимит гостей"]
                rows = [[button(label, f"ev:edit:{event_id}:{key}")] for label, (key, _) in zip(labels, FIELDS)]
                rows.append([button("◀️ Назад", f"ev:admin:{event_id}")])
                await self.edit(msg, "✏️ Что изменить?", keyboard(rows))
            elif action == "edit":
                field = parts[3]
                if field not in {key for key, _ in FIELDS}:
                    return True
                s = await self.event_new_session(uid, "edit", event_id, {"field": field, "event_version": int(event.version)})
                await self.event_prompt(uid, s)
            elif action == "toggle":
                await self.db_run("UPDATE events SET is_open=1-is_open,version=version+1 WHERE id=? AND version=?", event_id, int(parts[3]))
                await self.event_view(uid, event_id, True, msg)
            elif action in ("join", "manual"):
                manual = action == "manual"
                duplicate = None if manual else await self.db_first("SELECT id FROM event_registrations WHERE event_id=? AND telegram_id=?", event_id, uid)
                if duplicate:
                    await self.send(uid, "Вы уже зарегистрированы на это мероприятие.")
                elif not manual and (not int(event.is_open) or int(event.self_guests) >= int(event.capacity) or str(event.starts_at) <= datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")):
                    await self.send(uid, "Регистрация закрыта")
                else:
                    if manual and int(event.self_guests) >= int(event.capacity):
                        await self.send(uid, "Лимит самостоятельных регистраций достигнут, но вы добавляете вручную")
                    s = await self.event_new_session(uid, "manual" if manual else "self", event_id)
                    await self.event_prompt(uid, s)
            elif action == "guests":
                await self.event_guest_list(uid, event_id, int(parts[3]), msg)
            elif action in ("deleteask", "cancelask", "delete", "cancel"):
                record_id = int(parts[3])
                admin = action.startswith("delete")
                record = await self.db_first("SELECT * FROM event_registrations WHERE event_id=? AND id=? AND (?=1 OR telegram_id=?)", event_id, record_id, 1 if admin else 0, uid)
                if not record:
                    await self.send(uid, "Запись не найдена.")
                    return True
                if action.endswith("ask"):
                    text = f"Удалить запись <b>{esc(record.first_name)} {esc(record.last_name)}</b> на {record.party_size} чел.?"
                    await self.edit(msg, text, keyboard([[button("✅ Да, удалить", f"ev:{'delete' if admin else 'cancel'}:{event_id}:{record_id}")], [button("Нет, вернуться", f"ev:{'admin' if admin else 'view'}:{event_id}")]]))
                else:
                    await self.db_run("DELETE FROM event_registrations WHERE event_id=? AND id=? AND (?=1 OR telegram_id=?)", event_id, record_id, 1 if admin else 0, uid)
                    await self.event_view(uid, event_id, admin, msg)
            else:
                await self.send(uid, "Откройте мероприятия заново: /events.")
        except (ValueError, IndexError):
            await self.send(uid, "Эта кнопка устарела. Откройте мероприятия заново: /events.")
        return True
