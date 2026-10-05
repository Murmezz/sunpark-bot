from workers import WorkerEntrypoint, Response, fetch
from urllib.parse import urlparse
import json
import html
import hmac
import asyncio
from validation import valid_date, valid_time, valid_guests, normalize_phone

BANQUET_MAIN_SECTIONS = [
    ("🥗 Закуски", [0, 1, 2]),
    ("🍖 Горячие блюда", [3, 4]),
    ("🍽 Гарниры", [5]),
    ("🍰 Фрукты и десерты", [6, 7]),
]

BANQUET_CHILD = [
    ["🍗 Наггетсы", "Куриные наггетсы", "450 ₽"],
    ["🍢 Куриный шашлычок", "Куриный шашлычок", "490 ₽"],
    ["🦃 Шашлычок из индейки", "Шашлычок из индейки", "610 ₽"],
    ["🐟 Шашлычок из форели", "Шашлычок из форели", "750 ₽"],
    ["🍕 Пицца мясная", "Мясная пицца", "770 ₽"],
    ["🍕 Пицца Маргарита", "Пицца Маргарита", "720 ₽"],
    ["🧀 Пицца сырная", "Сырная пицца", "710 ₽"],
    ["🍍 Пицца гавайская", "Пицца с ветчиной и ананасом", "740 ₽"],
    ["🍟 Картофель фри", "С кетчупом", "380 ₽"],
    ["🍠 Батат фри", "Со сметаной", "510 ₽"],
]


def esc(value):
    return html.escape(str(value or ""), quote=False)


def db_optional(value):
    # In Python Workers, D1 can receive None as JS undefined, which it rejects.
    # Optional Telegram profile fields are stored as empty text instead.
    if value is None:
        return ""
    try:
        if str(value) == "undefined":
            return ""
    except Exception:
        return ""
    return value


def btn(text, callback):
    return {"text": str(text), "callback_data": callback}


def ikb(rows):
    return {"inline_keyboard": rows}


def kb1(*buttons):
    return ikb([[b] for b in buttons])


def items(cat):
    if not cat:
        return []
    if cat.get("items"):
        return cat["items"]
    out = []
    for section in cat.get("sections", []):
        title, its = section
        for it in its:
            out.append([title, *it])
    return out


class Bot(WorkerEntrypoint):
    def db_args(self, args):
        """Normalize Pyodide/JavaScript values before binding them to D1.

        Telegram objects are JavaScript-backed in Python Workers. Missing optional
        properties can therefore arrive as JS `undefined` rather than Python
        `None`, which D1 refuses to bind.
        """
        out = []
        for value in args:
            if value is None:
                out.append(None)
                continue
            try:
                if str(value) == "undefined":
                    out.append(None)
                    continue
            except Exception:
                out.append(None)
                continue
            out.append(value)
        return tuple(out)

    async def db_first(self, sql, *args):
        return await self.env.DB.prepare(sql).bind(*self.db_args(args)).first()

    async def db_all(self, sql, *args):
        return await self.env.DB.prepare(sql).bind(*self.db_args(args)).all()

    async def db_run(self, sql, *args):
        return await self.env.DB.prepare(sql).bind(*self.db_args(args)).run()

    async def tg(self, method, params):
        token = self.env.BOT_TOKEN
        r = await fetch(
            f"https://api.telegram.org/bot{token}/{method}",
            method="POST",
            headers={"content-type": "application/json"},
            body=json.dumps(params),
        )
        data = await r.json()
        if not data.get("ok"):
            raise Exception(f"{method}: {data.get('description', 'Telegram API error')}")
        return data.get("result")

    async def send(self, chat_id, text, markup=None):
        p = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if markup is not None:
            p["reply_markup"] = markup
        return await self.tg("sendMessage", p)

    def message_attachment(self, msg):
        photos = msg.get("photo") or []
        if photos:
            attachment = {"type": "photo", "file_id": photos[-1].get("file_id")}
            if msg.get("media_group_id"):
                attachment["media_group_id"] = str(msg["media_group_id"])
            return attachment, None
        doc = msg.get("document")
        if doc:
            name = str(doc.get("file_name") or "document.pdf")
            mime = str(doc.get("mime_type") or "").lower()
            if mime == "application/pdf" or name.lower().endswith(".pdf"):
                return {"type": "document", "file_id": doc.get("file_id"), "file_name": name}, None
            return None, "unsupported"
        return None, None

    def stored_message_body(self, text, attachment=None):
        if attachment:
            record = dict(attachment)
            record["caption"] = str(text or "")
            return "ATTACH:" + json.dumps(record, ensure_ascii=False)
        return str(text or "")

    async def send_ticket_content(self, chat_id, text, attachment=None, markup=None):
        if not attachment:
            return await self.send(chat_id, text, markup)
        method = "sendPhoto" if attachment.get("type") == "photo" else "sendDocument"
        key = "photo" if method == "sendPhoto" else "document"
        params = {"chat_id": chat_id, key: attachment.get("file_id"), "caption": text[:950], "parse_mode": "HTML"}
        if markup is not None:
            params["reply_markup"] = markup
        return await self.tg(method, params)

    async def edit(self, msg, text, markup=None):
        chat_id = msg.get("chat", {}).get("id")
        message_id = msg.get("message_id")
        p = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
        }
        if markup is not None:
            p["reply_markup"] = markup
        try:
            await self.tg("editMessageText", p)
            return
        except Exception as e:
            # If Telegram refuses to edit the existing message, send the
            # requested screen as a new message instead of failing the whole callback.
            if "not modified" in str(e).lower():
                return
            print("SUNPARK EDIT FALLBACK:", repr(e))
            try:
                await self.send(chat_id, text, markup)
            except Exception:
                raise

    async def answer(self, callback_id, text="", alert=False):
        try:
            await self.tg("answerCallbackQuery", {
                "callback_query_id": callback_id,
                "text": text,
                "show_alert": alert,
            })
        except Exception:
            pass

    async def clear_markup(self, msg):
        try:
            await self.tg("editMessageReplyMarkup", {
                "chat_id": msg.get("chat", {}).get("id"),
                "message_id": msg.get("message_id"),
                "reply_markup": {"inline_keyboard": []},
            })
        except Exception:
            pass

    async def config(self):
        await self.db_run("CREATE TABLE IF NOT EXISTS manager_states (user_id INTEGER PRIMARY KEY, action TEXT NOT NULL)")
        await self.db_run(
            "CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, last_name TEXT, updated_at TEXT NOT NULL)"
        )
        await self.db_run("CREATE TABLE IF NOT EXISTS ticket_details (ticket_number INTEGER PRIMARY KEY, request_type TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now')), last_reminder_at TEXT)")
        await self.db_run("CREATE TABLE IF NOT EXISTS guest_flows (user_id INTEGER PRIMARY KEY, ticket_number INTEGER NOT NULL, request_type TEXT NOT NULL, step INTEGER NOT NULL, payload TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT (datetime('now')))")
        await self.db_run("CREATE TABLE IF NOT EXISTS ticket_messages (id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_number INTEGER NOT NULL, sender_id INTEGER NOT NULL, sender_role TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now')))")
        await self.db_run("CREATE TABLE IF NOT EXISTS ticket_album_events (ticket_number INTEGER NOT NULL, media_group_id TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now')), PRIMARY KEY(ticket_number,media_group_id))")
        await self.db_run("CREATE TABLE IF NOT EXISTS ticket_album_dispatch (ticket_number INTEGER NOT NULL, media_group_id TEXT NOT NULL, target_id INTEGER NOT NULL, sent_at TEXT NOT NULL DEFAULT (datetime('now')), PRIMARY KEY(ticket_number,media_group_id,target_id))")
        await self.db_run("CREATE TABLE IF NOT EXISTS manager_history_messages (manager_id INTEGER NOT NULL, ticket_number INTEGER NOT NULL, message_id INTEGER NOT NULL, PRIMARY KEY(manager_id,message_id))")
        rows = await self.db_all("SELECT key,value FROM config")
        cfg = {str(r.key): r.value for r in rows.results}
        if not cfg.get("menu"):
            return {}, [], "", cfg
        try:
            m = json.loads(cfg["menu"])
            return m.get("MENU", {}), m.get("MENU_SECTIONS", []), m.get("INFO_TEXT", ""), cfg
        except Exception:
            return {}, [], "", cfg

    async def manager_ids(self, cfg):
        env_ids = getattr(self.env, "MANAGER_IDS", "") or ""
        raw = ",".join([str(cfg.get("manager_ids") or ""), str(env_ids)]).strip(",")
        out = set()
        for x in raw.split(","):
            try:
                if x.strip():
                    out.add(int(x.strip()))
            except Exception:
                pass
        return out

    async def manager_names(self, cfg):
        try:
            return json.loads(cfg.get("manager_names") or "{}")
        except Exception:
            return {}

    async def save_manager_ids(self, ids):
        value = ",".join(str(x) for x in sorted(set(int(i) for i in ids)))
        await self.db_run(
            "INSERT INTO config(key,value) VALUES('manager_ids',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            value,
        )

    async def save_manager_names(self, names):
        await self.db_run(
            "INSERT INTO config(key,value) VALUES('manager_names',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            json.dumps(names, ensure_ascii=False),
        )

    async def is_manager(self, uid, cfg):
        return uid in await self.manager_ids(cfg)

    def home_text(self):
        return "👋 <b>Здравствуйте!</b>\n\n🌿 Это меню <b>SUNPARK</b>.\nВыберите, что хотите посмотреть:"

    def home_keyboard(self, manager):
        rows = [
            [btn("🍽 Основное меню", "home:menu")],
            [btn("🎉 Банкетное меню", "home:banquet")],
            [btn("📅 Забронировать стол", "booking:start")],
            [btn("ℹ️ Частые вопросы", "faq")],
        ]
        if manager:
            rows.append([btn("⚙️ Админ-панель", "admin:panel")])
        return ikb(rows)

    def persistent(self, manager, has_open_ticket=False):
        rows = [[{"text": "🏠 Главное меню"}]]
        if not manager and has_open_ticket:
            rows.insert(0, [{"text": "💬 Ответить менеджеру"}])
        if manager:
            rows.append([{"text": "👀 Как гость"}, {"text": "⚙️ Админ-панель"}])
        return {"keyboard": rows, "resize_keyboard": True, "is_persistent": True}

    async def guest_persistent(self, uid, manager=False):
        if manager:
            return self.persistent(True)
        ticket = await self.db_first(
            "SELECT 1 FROM tickets WHERE guest_id=? AND status IN ('waiting','active') LIMIT 1", uid
        )
        return self.persistent(False, bool(ticket))

    def main_keyboard(self, menu, sections):
        rows = []
        for title, keys in sections:
            rows.append([btn("— " + title + " —", "noop")])
            row = []
            for key in keys:
                cat = menu.get(key)
                if not cat:
                    continue
                row.append(btn(f'{cat.get("emoji","")} {cat.get("title",key)}', "cat:" + key))
                if len(row) == 2:
                    rows.append(row)
                    row = []
            if row:
                rows.append(row)
        rows.append([btn("ℹ️ Информация для гостей", "info")])
        rows.append([btn("🏠 На главную", "back")])
        return ikb(rows)

    def category_keyboard(self, menu, key):
        cat = menu.get(key)
        rows = []
        if not cat:
            return ikb([[btn("🏠 На главную", "back")]])
        if cat.get("sections"):
            idx = 0
            for title, its in cat["sections"]:
                rows.append([btn("— " + title + " —", "noop")])
                for it in its:
                    label = str(it[0]) if key == "banquet" else (str(it[0]) + " — " + str(it[2]))[:64]
                    rows.append([btn(label, f"item:{key}:{idx}")])
                    idx += 1
        else:
            for i, it in enumerate(items(cat)):
                rows.append([btn((str(it[0]) + " — " + str(it[2]))[:64], f"item:{key}:{i}")])
        if key == "banquet":
            rows.append([btn("◀️ К разделам", "home:banquet")])
        rows.append([btn("🏠 На главную", "back")])
        return ikb(rows)

    def banquet_keyboard(self, menu):
        available = items(menu.get("banquet", {}))
        categories = [
            btn(title, f"banquet:section:{i}")
            for i, (title, indexes) in enumerate(BANQUET_MAIN_SECTIONS)
            if any(index < len(available) for index in indexes)
        ]
        rows = [categories[i:i + 2] for i in range(0, len(categories), 2)]
        rows.extend([
            [btn("🥂 Хочу провести банкет", "banquet:contact")],
            [btn("🏠 На главную", "back")],
        ])
        return ikb(rows)

    def banquet_section_keyboard(self, menu, idx):
        all_items = items(menu.get("banquet", {}))
        rows = []
        for source in BANQUET_MAIN_SECTIONS[idx][1]:
            if source < len(all_items):
                it = all_items[source]
                rows.append([btn((str(it[0]) + " — " + str(it[2]))[:64], f"item:banquet:{source}")])
        rows.append([btn("◀️ К банкетному меню", "banquet:list")])
        rows.append([btn("🏠 На главную", "back")])
        return ikb(rows)

    def item_text(self, menu, key, index):
        cat = menu.get(key)
        arr = items(cat)
        if index < 0 or index >= len(arr):
            return "Позиция не найдена."
        it = arr[index]
        if cat.get("sections"):
            subtitle, name, desc, price = it
        else:
            name, desc, price = it[:3]
            subtitle = ""
        lines = [f'<b>{esc(cat.get("emoji",""))} {esc(name)}</b>']
        if subtitle:
            lines.append(f"<u>{esc(subtitle)}</u>")
        if desc:
            lines.append("\n" + esc(desc))
        lines.append(f"\n💰 <b>{esc(price)}</b>")
        return "\n".join(lines)

    def item_back(self, key):
        return ikb([
            [btn("◀️ К банкетному меню" if key == "banquet" else "◀️ К списку блюд",
                 "banquet:list" if key == "banquet" else "cat:" + key)],
            [btn("🏠 На главную", "back")],
        ])

    async def admin_panel_text(self):
        r = await self.db_first(
            "SELECT SUM(status='active') a,SUM(status IN ('draft','waiting')) w,SUM(status='closed') c FROM tickets"
        )
        a, w, c = int(r.a or 0), int(r.w or 0), int(r.c or 0)
        return f"⚙️ <b>Админ-панель SUNPARK</b>\n\n🟡 Активных обращений: <b>{a}</b>\n🆕 Ожидают менеджера: <b>{w}</b>\n✅ Закрытых обращений: <b>{c}</b>\n\nВыберите нужный раздел:"

    def admin_keyboard(self):
        return ikb([
            [btn("🆕 Очередь заявок", "admin:waiting")],
            [btn("🟡 Мои активные · закрыть", "admin:active")],
            [btn("✅ Закрытые обращения", "admin:closed")],
            [btn("📊 Статистика", "admin:stats")],
            [btn("👥 Менеджеры", "admin:managers")],
            [btn("👀 Открыть как гость", "admin:guest")],
        ])

    def faq_keyboard(self):
        return ikb([[btn("📋 Правила для гостей", "faq:rules")], [btn("📍 Адрес и часы работы", "faq:contact")], [btn("🏠 На главную", "back")]])

    def form_steps(self, kind):
        if kind == "booking":
            return [("date", "📅 На какую дату хотите забронировать? Формат: ДД.ММ.ГГГГ"), ("time", "🕒 На какое время? Формат: ЧЧ:ММ"), ("guests", "👥 Сколько будет гостей? Введите число от 1 до 200."), ("name", "👤 На чьё имя оформить заявку?"), ("phone", "📱 Оставьте номер телефона для связи. Он обязателен."), ("comment", "💬 Есть пожелания? Напишите их или отправьте «—».")]
        return [("date", "📅 На какую дату планируется банкет? Формат: ДД.ММ.ГГГГ"), ("guests", "👥 Сколько будет гостей? Введите число от 1 до 200."), ("event", "🥂 Какой повод или формат мероприятия?"), ("wishes", "🍽 Есть пожелания по меню или организации?"), ("name", "👤 На чьё имя оформить заявку?"), ("phone", "📱 Оставьте номер телефона для связи. Он обязателен.")]

    async def start_form(self, uid, kind):
        existing = await self.db_first("SELECT number FROM tickets WHERE guest_id=? AND status IN ('draft','waiting','active') ORDER BY number DESC LIMIT 1", uid)
        if existing:
            await self.send(uid, "У вас уже есть открытое обращение. Менеджер ответит здесь; чтобы начать другую заявку, сначала завершите текущее обращение.")
            return
        await self.db_run("INSERT INTO tickets(guest_id,status) VALUES(?,'draft')", uid)
        ticket = await self.db_first("SELECT number FROM tickets WHERE guest_id=? AND status='draft' ORDER BY number DESC LIMIT 1", uid)
        await self.db_run("INSERT INTO guest_flows(user_id,ticket_number,request_type,step,payload) VALUES(?,?,?,0,'{}')", uid, ticket.number, kind)
        title = "бронирования стола" if kind == "booking" else "банкета"
        await self.send(uid, f"📝 <b>Заявка: {title}</b>\n\nЗаявка отправится менеджеру на подтверждение. Бронирование будет считаться подтверждённым только после ответа менеджера.\n\n{self.form_steps(kind)[0][1]}", kb1(btn("❌ Отменить", "form:cancel")))

    async def accept_form_answer(self, uid, text, frm, managers):
        flow = await self.db_first("SELECT ticket_number,request_type,step,payload FROM guest_flows WHERE user_id=?", uid)
        if not flow:
            return False
        steps = self.form_steps(str(flow.request_type))
        field, _ = steps[int(flow.step)]
        value = str(text).strip()
        if field == "date" and not valid_date(value):
            await self.send(uid, "⚠️ Укажите сегодняшнюю или будущую дату в формате ДД.ММ.ГГГГ.")
            return True
        if field == "time" and not valid_time(value):
            await self.send(uid, "⚠️ Укажите время в формате ЧЧ:ММ, например 19:30.")
            return True
        if field == "guests" and not valid_guests(value):
            await self.send(uid, "⚠️ Укажите число гостей от 1 до 200.")
            return True
        if field == "phone":
            value = normalize_phone(value)
            if not value:
                await self.send(uid, "⚠️ Не удалось распознать номер. Укажите телефон с кодом страны, например +7 900 123-45-67.")
                return True
        if not value:
            await self.send(uid, "⚠️ Ответ не должен быть пустым.")
            return True
        try:
            payload = json.loads(str(flow.payload))
        except Exception:
            payload = {}
        payload[field] = "Без дополнительных пожеланий" if field in ("comment", "wishes") and value == "—" else value
        next_step = int(flow.step) + 1
        if next_step < len(steps):
            await self.db_run("UPDATE guest_flows SET step=?,payload=?,updated_at=datetime('now') WHERE user_id=?", next_step, json.dumps(payload, ensure_ascii=False), uid)
            await self.send(uid, steps[next_step][1], kb1(btn("❌ Отменить", "form:cancel")))
            return True
        await self.db_run("DELETE FROM guest_flows WHERE user_id=?", uid)
        await self.db_run("UPDATE tickets SET status='waiting' WHERE number=? AND status='draft'", flow.ticket_number)
        await self.db_run("INSERT INTO ticket_details(ticket_number,request_type,payload,created_at,last_reminder_at) VALUES(?,?,?,datetime('now'),NULL) ON CONFLICT(ticket_number) DO UPDATE SET request_type=excluded.request_type,payload=excluded.payload,created_at=datetime('now'),last_reminder_at=NULL", flow.ticket_number, flow.request_type, json.dumps(payload, ensure_ascii=False))
        title = "Бронирование стола" if flow.request_type == "booking" else "Заявка на банкет"
        body = f"🆕 <b>{title} #{flow.ticket_number}</b>\n\n" + "\n".join(f"• <b>{esc(k)}</b>: {esc(v)}" for k, v in payload.items()) + f"\n\n👤 <b>Гость:</b> {self.guest_label(frm)}\n🆔 <code>{uid}</code>\n\n⚠️ Требуется подтверждение менеджера."
        for mid in managers:
            try:
                await self.send(mid, body, ikb([[btn("🤝 Взять заявку", f"claim:{uid}")]]))
            except Exception as e:
                print("SUNPARK MANAGER DELIVERY ERROR:", repr(e))
        await self.send(uid, "✅ Заявка отправлена менеджерам. Ожидайте ответа: бронирование пока не подтверждено.", await self.guest_persistent(uid))
        return True

    def admin_back(self):
        return ikb([[btn("◀️ В админ-панель", "admin:panel")], [btn("🏠 На главную", "back")]])

    def managers_keyboard(self):
        return ikb([
            [btn("➕ Добавить менеджера", "admin:manager_add")],
            [btn("✏️ Изменить имя", "admin:manager_rename")],
            [btn("➖ Удалить менеджера", "admin:manager_remove")],
            [btn("◀️ В админ-панель", "admin:panel")],
        ])

    async def active_view(self, names, manager_id):
        r = await self.db_all(
            "SELECT t.number,t.guest_id,t.manager_id,u.username,u.first_name,u.last_name FROM tickets t LEFT JOIN users u ON u.user_id=t.guest_id WHERE t.status='active' AND t.manager_id=? ORDER BY t.number", manager_id
        )
        if not r.results:
            return "🟡 <b>Мои активные заявки</b>\n\nУ вас нет заявок в работе.", self.admin_back()
        out = ["🟡 <b>Мои активные заявки</b>", "Откройте нужный чат кнопкой «💬 Ответить». Закрытие — отдельной кнопкой рядом.", ""]
        rows = []
        for t in r.results:
            guest = ("@" + t.username) if t.username else (" ".join(x for x in [t.first_name,t.last_name] if x) or "без username")
            manager = names.get(str(t.manager_id), "ID " + str(t.manager_id))
            out.append(f"🟡 Заявка #{t.number} — гость <b>{esc(guest)}</b> — менеджер <b>{esc(manager)}</b>")
            rows.append([btn(f"💬 Ответить #{t.number}", f"admin:chat:{t.guest_id}"), btn(f"✅ Закрыть #{t.number}", f"close:{t.guest_id}")])
        rows.extend([[btn("◀️ В админ-панель", "admin:panel")], [btn("🏠 На главную", "back")]])
        return "\n".join(out), ikb(rows)

    async def save_ticket_message(self, ticket_number, sender_id, sender_role, body):
        await self.db_run(
            "INSERT INTO ticket_messages(ticket_number,sender_id,sender_role,body) VALUES(?,?,?,?)",
            ticket_number, sender_id, sender_role, str(body),
        )

    async def is_first_album_item(self, ticket_number, attachment):
        group_id = attachment.get("media_group_id") if attachment else None
        if not group_id:
            return True
        result = await self.db_run(
            "INSERT OR IGNORE INTO ticket_album_events(ticket_number,media_group_id) VALUES(?,?)",
            ticket_number, str(group_id),
        )
        return int(result.meta.changes or 0) > 0

    async def remember_history_message(self, manager_id, ticket_number, result):
        if not result:
            return
        rows = result if isinstance(result, list) else [result]
        for sent in rows:
            try:
                message_id = int(sent.get("message_id"))
            except Exception:
                continue
            await self.db_run(
                "INSERT OR IGNORE INTO manager_history_messages(manager_id,ticket_number,message_id) VALUES(?,?,?)",
                manager_id, ticket_number, message_id,
            )

    async def clear_history_messages(self, manager_id):
        rows = await self.db_all(
            "SELECT message_id FROM manager_history_messages WHERE manager_id=? ORDER BY message_id",
            manager_id,
        )
        for row in rows.results:
            try:
                await self.tg("deleteMessage", {"chat_id": manager_id, "message_id": int(row.message_id)})
            except Exception:
                pass
        await self.db_run("DELETE FROM manager_history_messages WHERE manager_id=?", manager_id)

    async def album_photos(self, ticket_number, media_group_id):
        rows = await self.db_all(
            "SELECT body FROM ticket_messages WHERE ticket_number=? ORDER BY id DESC LIMIT 60",
            ticket_number,
        )
        photos = []
        for row in reversed(rows.results):
            body = str(row.body or "")
            if not body.startswith("ATTACH:"):
                continue
            try:
                attachment = json.loads(body[7:])
            except Exception:
                continue
            if attachment.get("type") != "photo":
                continue
            if str(attachment.get("media_group_id") or "") != str(media_group_id):
                continue
            if attachment.get("file_id"):
                photos.append(attachment)
        return photos

    async def send_album_once(self, target_id, ticket_number, media_group_id, caption, telegram_message_id):
        # Telegram sends every album item as a separate webhook and does not
        # include the total item count. Debounce by Telegram message_id:
        # only the webhook belonging to the newest album item may dispatch.
        # Any newer item that arrives during the quiet period supersedes this one.
        await asyncio.sleep(2.0)
        photos = await self.album_photos(ticket_number, media_group_id)
        if len(photos) < 2:
            return False

        latest_message_id = max(
            [int(p.get("telegram_message_id") or 0) for p in photos] or [0]
        )
        if int(telegram_message_id or 0) != latest_message_id:
            return False

        # One more quiet-period check protects against a later webhook that was
        # delayed while this invocation was sleeping.
        await asyncio.sleep(1.0)
        photos = await self.album_photos(ticket_number, media_group_id)
        final_latest_message_id = max(
            [int(p.get("telegram_message_id") or 0) for p in photos] or [0]
        )
        if int(telegram_message_id or 0) != final_latest_message_id:
            return False

        claim = await self.db_run(
            "INSERT OR IGNORE INTO ticket_album_dispatch(ticket_number,media_group_id,target_id) VALUES(?,?,?)",
            ticket_number, str(media_group_id), target_id,
        )
        if int(claim.meta.changes or 0) <= 0:
            return False

        media = []
        for i, photo in enumerate(photos[:10]):
            item = {"type": "photo", "media": photo["file_id"]}
            if i == 0 and caption:
                item["caption"] = caption[:950]
                item["parse_mode"] = "HTML"
            media.append(item)

        await self.tg("sendMediaGroup", {"chat_id": target_id, "media": media})
        return True

    async def ticket_history(self, ticket_number):
        ticket = await self.db_first(
            "SELECT t.number,u.username,u.first_name,u.last_name FROM tickets t LEFT JOIN users u ON u.user_id=t.guest_id WHERE t.number=?",
            ticket_number,
        )
        if not ticket:
            return "Заявка не найдена."
        guest = ("@" + ticket.username) if ticket.username else (" ".join(x for x in [ticket.first_name, ticket.last_name] if x) or "без username")
        out = [f"💬 <b>Заявка #{ticket.number} · переписка</b>", f"Гость: <b>{esc(guest)}</b>"]
        detail = await self.db_first("SELECT request_type,payload FROM ticket_details WHERE ticket_number=?", ticket_number)
        if detail:
            title = {"booking": "Бронирование стола", "banquet": "Банкет"}.get(str(detail.request_type), "Заявка")
            out.extend([f"\n📋 <b>{title}</b>"])
            try:
                payload = json.loads(str(detail.payload or "{}"))
            except Exception:
                payload = {}
            for key, value in payload.items():
                value = str(value or "")
                if len(value) > 350:
                    value = value[:347] + "…"
                out.append(f"• {esc(key)}: {esc(value)}")
        messages = await self.db_all(
            "SELECT sender_role,body,created_at FROM ticket_messages WHERE ticket_number=? ORDER BY id DESC LIMIT 30",
            ticket_number,
        )
        history = []
        album_rows = {}
        for item in reversed(messages.results):
            author = "👤 Гость" if item.sender_role == "guest" else "👨‍💼 Менеджер"
            body = str(item.body or "")
            if body.startswith("ATTACH:"):
                try:
                    attachment = json.loads(body[7:])
                    note = str(attachment.get("caption") or "")
                    group_id = attachment.get("media_group_id") if attachment.get("type") == "photo" else None
                    if group_id:
                        group_id = str(group_id)
                        if group_id in album_rows:
                            album = album_rows[group_id]
                            album["count"] += 1
                            if not album["caption"] and note:
                                album["caption"] = note
                            label = f"📷 Альбом · {album['count']} фото"
                            if album["caption"]:
                                label += "\n" + album["caption"]
                            history[album["index"]] = f"\n<b>{album['author']}</b> · {esc(album['created_at'])}\n{esc(label)}"
                            continue
                        body = "📷 Альбом · 1 фото" + ("\n" + note if note else "")
                        album_rows[group_id] = {
                            "index": len(history), "count": 1, "caption": note,
                            "author": author, "created_at": item.created_at,
                        }
                    else:
                        label = "📷 Фото" if attachment.get("type") == "photo" else "📄 PDF: " + str(attachment.get("file_name") or "document.pdf")
                        body = label + ("\n" + note if note else "")
                except Exception:
                    body = "📎 Вложение"
            if len(body) > 400:
                body = body[:397] + "…"
            history.append(f"\n<b>{author}</b> · {esc(item.created_at)}\n{esc(body)}")
        if history:
            while history and len("\n".join(out + history)) > 3400:
                history.pop(0)
            out.extend(history)
        else:
            out.extend(["", "История сообщений начнётся с этого обновления."])
        out.extend(["", "✍️ Режим ответа включён: отправляйте сообщения в этот чат, они пойдут этому гостю. Чтобы переключиться, снова откройте список активных заявок."])
        return "\n".join(out)

    async def send_ticket_attachments(self, chat_id, ticket_number):
        await self.clear_history_messages(chat_id)
        messages = await self.db_all(
            "SELECT sender_role,body,created_at FROM ticket_messages WHERE ticket_number=? ORDER BY id DESC LIMIT 30",
            ticket_number,
        )
        photos = []
        documents = []
        for item in reversed(messages.results):
            body = str(item.body or "")
            if not body.startswith("ATTACH:"):
                continue
            try:
                attachment = json.loads(body[7:])
                if not attachment.get("file_id"):
                    continue
                author = "гостя" if item.sender_role == "guest" else "менеджера"
                timestamp = esc(str(item.created_at or ""))
                caption = f"📷 Фото от {author} · {timestamp}"
                note = str(attachment.get("caption") or "")
                if note:
                    caption += "\n" + esc(note[:700])
                if attachment.get("type") == "photo":
                    photos.append({
                        "type": "photo",
                        "media": attachment["file_id"],
                        "caption": caption,
                        "parse_mode": "HTML",
                    })
                else:
                    name = str(attachment.get("file_name") or "document.pdf")
                    doc_caption = f"📄 PDF от {author} · {timestamp}\n{esc(name)}"
                    if note:
                        doc_caption += "\n" + esc(note[:700])
                    documents.append((attachment, doc_caption))
            except Exception as e:
                print("SUNPARK ATTACHMENT HISTORY ERROR:", repr(e))

        for start in range(0, len(photos), 10):
            album = photos[start:start + 10]
            try:
                if len(album) == 1:
                    result = await self.send_ticket_content(
                        chat_id,
                        album[0].get("caption", "📷 Фото"),
                        {"type": "photo", "file_id": album[0]["media"]},
                    )
                else:
                    result = await self.tg("sendMediaGroup", {"chat_id": chat_id, "media": album})
                await self.remember_history_message(chat_id, ticket_number, result)
            except Exception as e:
                print("SUNPARK PHOTO ALBUM ERROR:", repr(e))

        for attachment, caption in documents:
            result = await self.send_ticket_content(chat_id, caption, attachment)
            await self.remember_history_message(chat_id, ticket_number, result)

    async def closed_text(self, names):
        r = await self.db_all(
            "SELECT t.number,t.manager_id,u.username,u.first_name,u.last_name FROM tickets t LEFT JOIN users u ON u.user_id=t.guest_id WHERE t.status='closed' ORDER BY t.closed_at DESC,t.number DESC LIMIT 20"
        )
        if not r.results:
            return "✅ <b>Закрытые обращения</b>\n\nЗакрытых обращений пока нет."
        out = ["✅ <b>Последние закрытые обращения</b>", ""]
        for t in r.results:
            guest = ("@" + t.username) if t.username else (" ".join(x for x in [t.first_name,t.last_name] if x) or "без username")
            manager = names.get(str(t.manager_id), "ID " + str(t.manager_id))
            out.append(f"#{t.number} — гость <b>{esc(guest)}</b> — менеджер <b>{esc(manager)}</b>")
        return "\n".join(out)

    async def waiting_queue(self):
        r = await self.db_all("SELECT t.number,t.guest_id,t.status,u.username,u.first_name,d.request_type,d.payload,d.created_at FROM tickets t LEFT JOIN users u ON u.user_id=t.guest_id LEFT JOIN ticket_details d ON d.ticket_number=t.number WHERE t.status IN ('draft','waiting') ORDER BY t.number DESC LIMIT 30")
        if not r.results:
            return "🆕 <b>Очередь заявок</b>\n\nНовых заявок пока нет.", self.admin_back()
        out = ["🆕 <b>Очередь заявок</b>", ""]
        rows = []
        for t in r.results:
            guest = ("@" + t.username) if t.username else (t.first_name or "гость")
            kind = {"booking": "Бронирование", "banquet": "Банкет"}.get(t.request_type, "Обращение")
            out.append(f"<b>#{t.number} · {kind}</b> — {esc(guest)}")
            try:
                payload = json.loads(str(t.payload or "{}"))
            except Exception:
                payload = {}
            for key, value in payload.items():
                out.append(f"  {esc(key)}: {esc(value)}")
            rows.append([btn(f"Взять #{t.number}", f"claim:{t.guest_id}")])
        rows.extend([[btn("◀️ В админ-панель", "admin:panel")], [btn("🏠 На главную", "back")]])
        return "\n".join(out), ikb(rows)

    async def set_action(self, uid, action):
        await self.db_run(
            "INSERT INTO manager_states(user_id,action) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET action=excluded.action",
            uid, action,
        )

    async def get_action(self, uid):
        r = await self.db_first("SELECT action FROM manager_states WHERE user_id=?", uid)
        return str(r.action) if r else ""

    async def clear_action(self, uid):
        await self.db_run("DELETE FROM manager_states WHERE user_id=?", uid)

    def guest_label(self, user):
        name = " ".join(x for x in [user.get("first_name"), user.get("last_name")] if x) or "Без имени"
        return esc(name) + (f" @{esc(user.get('username'))}" if user.get("username") else "")

    async def message(self, msg, menu, sections, info, cfg):
        text = msg.get("text") or msg.get("caption") or ""
        attachment, attachment_error = self.message_attachment(msg)
        if attachment and attachment.get("media_group_id") and msg.get("message_id") is not None:
            attachment["telegram_message_id"] = int(msg.get("message_id"))
        frm = msg.get("from") or {}
        chat = msg.get("chat") or {}
        if (not text and not attachment and not attachment_error) or chat.get("type") != "private":
            return
        uid = int(frm.get("id"))

        await self.db_run(
            "INSERT INTO users(user_id,username,first_name,last_name,updated_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET username=excluded.username,first_name=excluded.first_name,last_name=excluded.last_name,updated_at=excluded.updated_at",
            uid, db_optional(frm.get("username")), db_optional(frm.get("first_name")), db_optional(frm.get("last_name")), "now",
        )
        managers = await self.manager_ids(cfg)
        mgr = uid in managers
        action = await self.get_action(uid) if mgr else ""

        if attachment_error:
            await self.send(uid, "Пока можно отправить только фото или PDF.")
            return
        if mgr and attachment and not action.startswith("reply:"):
            await self.send(uid, "Сначала откройте конкретную заявку через «Мои активные → Ответить», затем отправьте фото или PDF.")
            return

        if mgr and action.startswith("reply:") and (text.startswith("/start") or text == "/admin" or text in ("🏠 Главное меню", "⚙️ Админ-панель", "👀 Как гость")):
            await self.clear_history_messages(uid)
            await self.clear_action(uid)
            action = ""

        if action.startswith("add_name:") or action.startswith("rename_name:"):
            target = action.split(":")[1]
            name = str(text).strip()
            if not name or len(name) > 50:
                await self.send(uid, "⚠️ Введите имя от 1 до 50 символов.")
                return
            names = await self.manager_names(cfg)
            names[target] = name
            await self.save_manager_names(names)
            await self.clear_action(uid)
            await self.send(uid, f"✅ Имя менеджера изменено на <b>{esc(name)}</b>.", self.persistent(mgr))
            return

        if mgr and action in ("add", "remove", "rename"):
            tag = str(text).strip().lstrip("@").lower()
            if not (5 <= len(tag) <= 32):
                await self.send(uid, "⚠️ Введите @username Telegram.")
                return
            target_row = await self.db_first("SELECT user_id,username FROM users WHERE lower(username)=? LIMIT 1", tag)
            if not target_row:
                await self.send(uid, f"❌ Пользователь <b>@{esc(tag)}</b> ещё не найден. Пусть он сначала напишет боту.")
                return
            target_id = int(target_row.user_id)
            ids = set(managers)
            if action == "rename":
                if target_id not in ids:
                    await self.clear_action(uid)
                    await self.send(uid, "ℹ️ Этот пользователь не является менеджером.", self.persistent(mgr))
                    return
                await self.set_action(uid, "rename_name:" + str(target_id))
                await self.send(uid, "✏️ Введите новое имя менеджера.")
                return
            if action == "add":
                if target_id in ids:
                    await self.clear_action(uid)
                    await self.send(uid, "ℹ️ Этот менеджер уже есть в списке.", self.persistent(mgr))
                    return
                ids.add(target_id)
                await self.save_manager_ids(ids)
                await self.set_action(uid, "add_name:" + str(target_id))
                await self.send(uid, "✏️ Введите имя менеджера, которое будет отображаться везде.\nНапример: <b>Алексей</b>")
                return
            if len(ids) <= 1:
                await self.clear_action(uid)
                await self.send(uid, "⚠️ Нельзя удалить последнего менеджера.", self.persistent(mgr))
                return
            if target_id not in ids:
                await self.clear_action(uid)
                await self.send(uid, "ℹ️ Этого менеджера нет в списке.", self.persistent(mgr))
                return
            ids.remove(target_id)
            await self.save_manager_ids(ids)
            names = await self.manager_names(cfg)
            names.pop(str(target_id), None)
            await self.save_manager_names(names)
            await self.clear_action(uid)
            await self.send(uid, "✅ Менеджер удалён.", self.persistent(mgr))
            return

        if text.startswith("/start"):
            await self.send(uid, self.home_text(), self.home_keyboard(mgr))
            await self.send(uid, "Нижняя кнопка «🏠 Главное меню» всегда вернёт вас сюда.", await self.guest_persistent(uid, mgr))
            return
        if text == "/admin" and mgr:
            await self.send(uid, await self.admin_panel_text(), self.admin_keyboard())
            return
        if text == "🏠 Главное меню":
            await self.send(uid, self.home_text(), self.home_keyboard(mgr))
            return
        if text == "👀 Как гость" and mgr:
            await self.send(uid, "👀 <b>Режим просмотра как гость</b>", self.home_keyboard(mgr))
            return
        if text == "⚙️ Админ-панель" and mgr:
            await self.send(uid, await self.admin_panel_text(), self.admin_keyboard())
            return
        if text in ("👀 Как гость", "⚙️ Админ-панель"):
            return

        if text == "💬 Ответить менеджеру":
            own = await self.db_first("SELECT number,status FROM tickets WHERE guest_id=? AND status IN ('draft','waiting','active') ORDER BY number DESC LIMIT 1", uid)
            if not own:
                await self.send(uid, "Сейчас у вас нет открытой заявки. Откройте главное меню и выберите «Связаться с менеджером» или оформите бронь.", await self.guest_persistent(uid, mgr))
            elif own.status == "active":
                await self.send(uid, "Ваша заявка открыта. Напишите следующим сообщением — оно уйдёт менеджеру. Ответ придёт сюда, даже если вы сейчас смотрите меню.", await self.guest_persistent(uid, mgr))
            elif own.status == "waiting":
                await self.send(uid, "⏳ Ваша заявка уже у менеджеров. Напишите дополнение следующим сообщением — оно прикрепится к заявке.", await self.guest_persistent(uid, mgr))
            else:
                await self.send(uid, "Вы ещё заполняете заявку. Продолжите отвечать на вопросы формы; после отправки можно будет писать менеджеру.", await self.guest_persistent(uid, mgr))
            return

        if attachment and not mgr and await self.db_first("SELECT 1 FROM guest_flows WHERE user_id=?", uid):
            await self.send(uid, "Сначала закончите форму текстовыми ответами. После отправки заявки можно будет приложить фото или PDF.")
            return

        if await self.accept_form_answer(uid, text, frm, managers):
            return

        if mgr:
            if action.startswith("reply:"):
                try:
                    ticket_number = int(action.split(":", 1)[1])
                except Exception:
                    ticket_number = 0
                ticket = await self.db_first(
                    "SELECT guest_id FROM tickets WHERE number=? AND manager_id=? AND status='active'",
                    ticket_number, uid,
                )
                if not ticket:
                    await self.clear_action(uid)
                    await self.send(uid, "Эта заявка уже закрыта или передана другому менеджеру. Откройте список своих активных заявок.")
                    return
                guest_id = int(ticket.guest_id)
                first_album_item = await self.is_first_album_item(ticket_number, attachment)
                await self.save_ticket_message(ticket_number, uid, "manager", self.stored_message_body(text, attachment))
                caption = f"👨‍💼 <b>Менеджер:</b>\n{esc(text)}" if text else "👨‍💼 <b>Менеджер отправил вложение.</b>"
                await self.send_ticket_content(guest_id, caption, attachment, await self.guest_persistent(guest_id))
                if first_album_item:
                    await self.send(uid, f"✅ Ответ отправлен гостю по заявке #{ticket_number}. Можно продолжать писать — выбран этот чат.", ikb([[btn(f"📜 История #{ticket_number}", f"admin:chat:{guest_id}")], [btn("🟡 Выбрать другой чат", "admin:active")], [btn(f"✅ Закрыть заявку #{ticket_number}", f"close:{guest_id}")]]))
                return
            await self.send(uid, "Чтобы ответить конкретному гостю, откройте «Админ-панель → Мои активные» и нажмите «💬 Ответить» у нужной заявки.")
            return

        own = await self.db_first("SELECT * FROM tickets WHERE guest_id=? AND status IN ('draft','waiting','active') ORDER BY number DESC LIMIT 1", uid)
        if not own:
            if attachment:
                await self.send(uid, "Чтобы отправить фото или PDF, сначала оставьте заявку через «Связаться с менеджером» или оформите бронь.", await self.guest_persistent(uid))
            return
        if own.status == "active":
            first_album_item = await self.is_first_album_item(own.number, attachment)
            await self.save_ticket_message(own.number, uid, "guest", self.stored_message_body(text, attachment))
            content = esc(text) if text else ("📷 Фото во вложении." if attachment.get("type") == "photo" else "📄 PDF во вложении.") if attachment else ""
            body = f"💬 <b>Обращение #{own.number}</b>\n👤 {self.guest_label(frm)}\n\n{content}"
            markup = ikb([[btn(f"📜 История / ответить #{own.number}", f"admin:chat:{uid}"), btn(f"✅ Закрыть #{own.number}", f"close:{uid}")]])
            media_group_id = attachment.get("media_group_id") if attachment and attachment.get("type") == "photo" else None
            if media_group_id:
                self.ctx.waitUntil(
                    self.send_album_once(
                        int(own.manager_id), own.number, media_group_id, body,
                        attachment.get("telegram_message_id"),
                    )
                )
                if first_album_item:
                    await self.send(uid, "📨 Фото добавляются к заявке и будут отправлены менеджеру одним альбомом. Его ответ появится в этом чате.", await self.guest_persistent(uid))
            elif first_album_item:
                await self.send_ticket_content(int(own.manager_id), body, attachment, markup)
                await self.send(uid, "📨 Сообщение отправлено менеджеру. Его ответ появится в этом чате; можно продолжать смотреть меню.", await self.guest_persistent(uid))
            return
        prefix = "➕ <b>Дополнение к заявке" if own.status == "waiting" else "🆕 <b>Новое обращение"
        first_album_item = await self.is_first_album_item(own.number, attachment)
        content = esc(text) if text else ("📷 Фото во вложении." if attachment.get("type") == "photo" else "📄 PDF во вложении.") if attachment else ""
        body = f"{prefix} #{own.number}</b>\n\n👤 <b>Гость:</b> {self.guest_label(frm)}\n🆔 <b>ID:</b> <code>{uid}</code>\n\n💬 <b>Сообщение:</b>\n{content}"
        await self.save_ticket_message(own.number, uid, "guest", self.stored_message_body(text, attachment))
        media_group_id = attachment.get("media_group_id") if attachment and attachment.get("type") == "photo" else None
        for mid in managers:
            try:
                if media_group_id:
                    self.ctx.waitUntil(
                        self.send_album_once(
                            mid, own.number, media_group_id, body,
                            attachment.get("telegram_message_id"),
                        )
                    )
                elif first_album_item:
                    await self.send_ticket_content(mid, body, attachment, ikb([[btn("🤝 Взять обращение", f"claim:{uid}")]]))
            except Exception as e:
                print("SUNPARK GUEST DELIVERY ERROR:", repr(e))
        await self.db_run("UPDATE tickets SET status='waiting' WHERE number=?", own.number)
        if first_album_item:
            confirmation = "📨 Фото добавлены к заявке и отправлены менеджерам одним альбомом. Ответ придёт в этот чат." if media_group_id else "📨 Сообщение добавлено к заявке и отправлено менеджерам SUNPARK. Ответ придёт в этот чат."
            await self.send(uid, confirmation, await self.guest_persistent(uid))

    async def callback(self, cb, menu, sections, info, cfg):
        data = cb.get("data", "")
        uid = int((cb.get("from") or {}).get("id"))
        msg = cb.get("message")
        if not msg:
            await self.answer(cb.get("id"))
            return
        managers = await self.manager_ids(cfg)
        mgr = uid in managers
        current_action = await self.get_action(uid) if mgr else ""
        if mgr and current_action.startswith("reply:") and data != "noop":
            await self.clear_history_messages(uid)
        if data == "noop":
            await self.answer(cb.get("id")); return
        if data == "back":
            await self.edit(msg, self.home_text(), self.home_keyboard(mgr)); await self.answer(cb.get("id")); return
        if data == "home:menu":
            await self.edit(msg, "🍽 <b>Основное меню SUNPARK</b>\n\nВыберите раздел:", self.main_keyboard(menu, sections)); await self.answer(cb.get("id")); return
        if data == "home:banquet":
            await self.edit(msg, "🎉 <b>Банкетное меню</b>\n\nПосмотрите банкетное меню или выберите «Хочу провести банкет», чтобы узнать, как связаться с менеджерами.", ikb([[btn("📋 Посмотреть банкетное меню","banquet:list")],[btn("🥂 Хочу провести банкет","banquet:contact")],[btn("ℹ️ Частые вопросы","faq")],[btn("🏠 На главную","back")]])); await self.answer(cb.get("id")); return
        if data == "booking:start":
            await self.start_form(uid, "booking"); await self.answer(cb.get("id")); return
        if data == "banquet:request":
            await self.start_form(uid, "banquet"); await self.answer(cb.get("id")); return
        if data == "banquet:contact":
            phone = cfg.get("phone") or getattr(self.env, "MANAGER_PHONE", None) or "+7 (911) 714-40-12"
            text = (
                "🥂 <b>Хотите провести банкет в SUNPARK?</b>\n\n"
                f"Позвоните по телефону: <b>{esc(phone)}</b>\n"
                "Или оставьте заявку — менеджеры свяжутся с вами и обсудят детали."
            )
            markup = ikb([[btn("📝 Оставить заявку менеджерам", "banquet:request")], [btn("◀️ К банкетному меню", "home:banquet")]])
            await self.edit(msg, text, markup); await self.answer(cb.get("id")); return
        if data == "faq":
            await self.edit(msg, "ℹ️ <b>Частые вопросы</b>\n\nВыберите тему:", self.faq_keyboard()); await self.answer(cb.get("id")); return
        if data.startswith("faq:"):
            topic = data.split(":", 1)[1]
            if topic == "booking":
                text = "📅 <b>Бронирование стола</b>\n\nЗаполните короткую форму. Менеджер свяжется с вами и подтвердит бронь. До подтверждения бронь не считается оформленной."
            elif topic == "banquet":
                text = "🎉 <b>Банкет</b>\n\nОставьте заявку с датой, числом гостей и пожеланиями. Менеджер уточнит детали и подтвердит возможность проведения."
            elif topic == "rules":
                text = info or "Информация для гостей пока не добавлена. Напишите менеджеру, и он поможет."
            else:
                address = cfg.get("address") or "Санкт-Петербург, ул. Никольская, 9"
                hours = cfg.get("hours") or "Пн–пт: 12:00–23:00\nСб–вс и праздничные дни: 11:00–23:00"
                phone = cfg.get("phone") or getattr(self.env, "MANAGER_PHONE", None) or "+7 (911) 714-40-12"
                map_url = cfg.get("map_url") or "https://yandex.ru/maps/org/sunpark/1696243668"
                website = cfg.get("website") or "https://sunparkspb.ru/"
                text = (
                    "📍 <b>Адрес и часы работы</b>\n\n"
                    f"📍 {esc(address)}\n\n"
                    f"⏰ {esc(hours)}\n\n"
                    f"📞 <a href=\"tel:{esc(phone)}\">{esc(phone)}</a>\n\n"
                    f"🗺 <a href=\"{esc(map_url)}\">Открыть на Яндекс Картах</a>\n"
                    f"🌐 <a href=\"{esc(website)}\">Официальный сайт</a>"
                )
            await self.edit(msg, text, ikb([[btn("◀️ К частым вопросам", "faq")], [btn("🏠 На главную", "back")]])); await self.answer(cb.get("id")); return
        if data == "form:cancel":
            flow = await self.db_first("SELECT ticket_number FROM guest_flows WHERE user_id=?", uid)
            if flow:
                await self.db_run("DELETE FROM guest_flows WHERE user_id=?", uid)
                await self.db_run("DELETE FROM ticket_details WHERE ticket_number=?", flow.ticket_number)
                await self.db_run("DELETE FROM tickets WHERE number=? AND status='draft'", flow.ticket_number)
            await self.send(uid, "Заявка отменена.", await self.guest_persistent(uid, mgr)); await self.answer(cb.get("id")); return
        if data == "banquet:list":
            await self.edit(msg, "🎉 <b>Банкетное меню SUNPARK</b>\n\nВыберите раздел. В карточке блюда указаны состав и цена.", self.banquet_keyboard(menu)); await self.answer(cb.get("id")); return
        if data.startswith("banquet:section:"):
            idx = int(data.split(":")[-1])
            if idx == 7:
                rows = [[btn(x[0], f"bchild:{i}")] for i,x in enumerate(BANQUET_CHILD)]
                rows += [[btn("◀️ К банкетному меню","banquet:list")],[btn("🏠 На главную","back")]]
                await self.edit(msg, "🧒 <b>Детское меню</b>\n\nВыберите блюдо:", ikb(rows))
            elif 0 <= idx < len(BANQUET_MAIN_SECTIONS):
                await self.edit(msg, "🎉 <b>"+esc(BANQUET_MAIN_SECTIONS[idx][0])+"</b>\n\nВыберите блюдо, чтобы посмотреть состав и цену:", self.banquet_section_keyboard(menu, idx))
            else:
                await self.answer(cb.get("id"), "Раздел не найден.", True); return
            await self.answer(cb.get("id")); return
        if data.startswith("item:"):
            p = data.split(":")
            if len(p) != 3:
                await self.answer(cb.get("id"), "Позиция не найдена", True); return
            key, idx = p[1], int(p[2])
            if key not in menu:
                await self.answer(cb.get("id"), "Раздел не найден", True); return
            await self.edit(msg, self.item_text(menu, key, idx), self.item_back(key)); await self.answer(cb.get("id")); return
        if data.startswith("bchild:"):
            i = int(data.split(":")[1])
            x = BANQUET_CHILD[i]
            await self.edit(msg, f"<b>{esc(x[0])}</b>\n\n{esc(x[1])}\n\n💰 <b>{esc(x[2])}</b>",
                            ikb([[btn("◀️ К детскому меню","banquet:section:7")],[btn("🏠 На главную","back")]]))
            await self.answer(cb.get("id")); return
        if data == "info":
            await self.edit(msg, info, kb1(btn("🏠 На главную","back"))); await self.answer(cb.get("id")); return
        if data.startswith("cat:"):
            key = data[4:]
            if key not in menu:
                await self.answer(cb.get("id"), "Раздел не найден", True); return
            cat = menu[key]
            await self.edit(msg, f'<b>{esc(cat.get("emoji",""))} {esc(cat.get("title",key))}</b>\n\nНажмите на позицию, чтобы посмотреть состав.\n\nВнизу можно вернуться к разделам или на главную:', self.category_keyboard(menu,key)); await self.answer(cb.get("id")); return
        if data == "manager:start":
            await self.edit(msg, "💬 <b>Связаться с менеджером</b>\n\nКак вам удобнее?", ikb([[btn("📞 Позвонить","manager:call")],[btn("✉️ Написать сообщение","manager:write")],[btn("◀️ Назад","home:banquet")]])); await self.answer(cb.get("id")); return
        if data == "manager:call":
            phone = cfg.get("phone") or getattr(self.env, "MANAGER_PHONE", None)
            if not phone:
                await self.edit(msg, "📞 Номер телефона пока не настроен. Напишите менеджеру через бота.", ikb([[btn("✉️ Написать сообщение","manager:write")],[btn("◀️ Назад","manager:start")]])); await self.answer(cb.get("id")); return
            await self.edit(msg, f"📞 <b>Позвонить менеджеру</b>\n\nНомер для связи:\n{esc(phone)}\n\nНажмите на номер, чтобы позвонить.", ikb([[btn("✉️ Написать сообщение","manager:write")],[btn("◀️ Назад","manager:start")]])); await self.answer(cb.get("id")); return
        if data == "manager:write":
            active = await self.db_first("SELECT 1 FROM tickets WHERE guest_id=? AND status='active'", uid)
            if active:
                await self.answer(cb.get("id"), "Ваше обращение уже отправлено менеджерам.", True); return
            open_ticket = await self.db_first("SELECT 1 FROM tickets WHERE guest_id=? AND status IN ('draft','waiting')", uid)
            if not open_ticket:
                await self.db_run("INSERT INTO tickets(guest_id,status) VALUES(?,'draft')", uid)
            await self.edit(msg, "💬 <b>Связь с менеджером по банкетам</b>\n\nНапишите здесь ваш вопрос — сообщение получат наши менеджеры.\n\nПервый менеджер, который возьмёт обращение, продолжит общение с вами через этого бота.\n\nНапример: количество гостей, дата банкета, пожелания по меню и другие вопросы.\n\n<b>✍️ Напишите сообщение следующим сообщением.</b>", kb1(btn("❌ Отменить обращение","manager:cancel"))); await self.answer(cb.get("id")); return
        if data == "manager:cancel":
            tickets = await self.db_all("SELECT number FROM tickets WHERE guest_id=? AND status IN ('draft','waiting')", uid)
            for ticket in tickets.results:
                await self.db_run("DELETE FROM ticket_details WHERE ticket_number=?", ticket.number)
            await self.db_run("DELETE FROM tickets WHERE guest_id=? AND status IN ('draft','waiting')", uid)
            await self.edit(msg, "🎉 <b>Банкетное меню</b>\n\nЗдесь вы можете посмотреть варианты банкетных блюд или связаться с менеджером.", ikb([[btn("📋 Посмотреть банкетное меню","banquet:list")],[btn("💬 Связаться с менеджером","manager:start")],[btn("🏠 На главную","back")]]))
            await self.send(uid, "Заявка отменена.", await self.guest_persistent(uid, mgr)); await self.answer(cb.get("id")); return
        if data.startswith("claim:"):
            if not mgr:
                await self.answer(cb.get("id"), "Эта кнопка доступна только менеджерам.", True); return
            guest_id = int(data[6:])
            res = await self.db_run("UPDATE tickets SET status='active',manager_id=?,claimed_at=datetime('now') WHERE guest_id=? AND status='waiting'", uid, guest_id)
            if not int(res.meta.changes or 0):
                taken = await self.db_first("SELECT 1 FROM tickets WHERE guest_id=? AND status='active'", guest_id)
                await self.answer(cb.get("id"), "Обращение уже взял другой менеджер." if taken else "Это обращение уже недоступно.", True)
                await self.clear_markup(msg); return
            t = await self.db_first("SELECT number FROM tickets WHERE guest_id=? AND manager_id=? AND status='active' ORDER BY number DESC", guest_id, uid)
            await self.tg("editMessageReplyMarkup", {"chat_id": msg.get("chat", {}).get("id"), "message_id": msg.get("message_id"), "reply_markup": ikb([[btn(f"📜 История / ответить #{t.number}", f"admin:chat:{guest_id}"), btn(f"✅ Закрыть #{t.number}",f"close:{guest_id}")]])})
            await self.send(msg.get("chat", {}).get("id"), f"✅ <b>Заявка #{t.number} закреплена за вами.</b>\n\nОтветьте гостю обычным сообщением. Закрыть заявку можно кнопкой «✅ Закрыть заявку #{t.number}» здесь или в разделе активных заявок админ-панели.")
            await self.send(guest_id, "👨‍💼 <b>Менеджер SUNPARK взял заявку в работу.</b>\n\nЧтобы ответить, нажмите «💬 Ответить менеджеру» внизу и отправьте следующее сообщение. Меню можно открывать — переписка по заявке сохранится здесь.", await self.guest_persistent(guest_id))
            await self.answer(cb.get("id"), "Обращение закреплено за вами."); return
        if data.startswith("close:"):
            if not mgr:
                await self.answer(cb.get("id"), "Эта кнопка доступна только менеджерам.", True); return
            guest_id = int(data[6:])
            t = await self.db_first("SELECT number FROM tickets WHERE guest_id=? AND manager_id=? AND status='active'", guest_id, uid)
            if not t:
                await self.answer(cb.get("id"), "Это обращение вам не назначено.", True); return
            await self.db_run("UPDATE tickets SET status='closed',closed_at=datetime('now') WHERE number=?", t.number)
            if await self.get_action(uid) == "reply:" + str(t.number):
                await self.clear_action(uid)
            if "Мои активные заявки" in str(msg.get("text") or ""):
                text, markup = await self.active_view(await self.manager_names(cfg), uid)
                await self.edit(msg, text, markup)
            else:
                await self.clear_markup(msg)
            await self.send(msg.get("chat", {}).get("id"), f"✅ Заявка #{t.number} закрыта.")
            await self.send(guest_id, "✅ <b>Заявка закрыта.</b>\n\nЧтобы задать новый вопрос или оформить другую заявку, откройте главное меню.", await self.guest_persistent(guest_id))
            await self.answer(cb.get("id")); return
        if data.startswith("admin:"):
            if not mgr:
                await self.answer(cb.get("id"), "Доступ запрещён.", True); return
            what = data[6:]
            if what.startswith("chat:"):
                try:
                    guest_id = int(what.split(":", 1)[1])
                except Exception:
                    await self.answer(cb.get("id"), "Заявка не найдена.", True); return
                ticket = await self.db_first("SELECT number FROM tickets WHERE guest_id=? AND manager_id=? AND status='active' ORDER BY number DESC LIMIT 1", guest_id, uid)
                if not ticket:
                    await self.answer(cb.get("id"), "Эта заявка уже закрыта или не назначена вам.", True); return
                ticket_number = int(ticket.number)
                await self.set_action(uid, "reply:" + str(ticket_number))
                history = await self.ticket_history(ticket_number)
                markup = ikb([[btn("🟡 Выбрать другой чат", "admin:active")], [btn(f"✅ Закрыть заявку #{ticket_number}", f"close:{guest_id}")]])
                await self.edit(msg, history, markup)
                await self.send_ticket_attachments(uid, ticket_number)
            else:
                await self.clear_action(uid)
            if what == "panel":
                await self.edit(msg, await self.admin_panel_text(), self.admin_keyboard())
            elif what == "managers":
                await self.clear_action(uid)
                names = await self.manager_names(cfg)
                ids = sorted(managers)
                listing = "\n".join(f"{i+1}. <b>{esc(names.get(str(mid),'ID '+str(mid)))}</b>" for i,mid in enumerate(ids)) or "Список пуст."
                await self.edit(msg, f"👥 <b>Менеджеры</b>\n\n{listing}\n\nВсе менеджеры имеют одинаковые права: получают новые обращения и могут добавлять или удалять менеджеров.", self.managers_keyboard())
            elif what == "manager_add":
                await self.set_action(uid,"add")
                await self.edit(msg,"➕ <b>Добавление менеджера</b>\n\nОтправьте @username нового менеджера.",kb1(btn("❌ Отмена","admin:managers")))
            elif what == "manager_rename":
                await self.set_action(uid,"rename")
                await self.edit(msg,"✏️ <b>Изменение имени менеджера</b>\n\nОтправьте @username менеджера.",kb1(btn("❌ Отмена","admin:managers")))
            elif what == "manager_remove":
                await self.set_action(uid,"remove")
                await self.edit(msg,"➖ <b>Удаление менеджера</b>\n\nОтправьте @username менеджера.",kb1(btn("❌ Отмена","admin:managers")))
            elif what == "active":
                text, markup = await self.active_view(await self.manager_names(cfg), uid)
                await self.edit(msg, text, markup)
            elif what == "waiting":
                text, markup = await self.waiting_queue()
                await self.edit(msg, text, markup)
            elif what == "closed":
                await self.edit(msg, await self.closed_text(await self.manager_names(cfg)), self.admin_back())
            elif what == "stats":
                r = await self.db_first("SELECT SUM(status='active') a,SUM(status IN ('draft','waiting')) w,SUM(status='closed') c FROM tickets")
                await self.edit(msg, f"📊 <b>Статистика</b>\n\n🟡 Активных: <b>{int(r.a or 0)}</b>\n🆕 Ожидают: <b>{int(r.w or 0)}</b>\n✅ Завершено: <b>{int(r.c or 0)}</b>\n👨‍💼 Менеджеров в белом списке: <b>{len(managers)}</b>", self.admin_back())
            elif what == "guest":
                await self.edit(msg, self.home_text(), self.home_keyboard(mgr))
            await self.answer(cb.get("id")); return
        await self.answer(cb.get("id"))

    async def fetch(self, request):
        # Telegram webhook must always receive HTTP 200.
        # Keep diagnostics inside the response path so one bad update
        # cannot make the webhook return 500.
        try:
            method = str(request.method)
        except Exception:
            method = "UNKNOWN"

        if method != "POST":
            try:
                has_token = bool(getattr(self.env, "BOT_TOKEN", None))
                has_db = bool(getattr(self.env, "DB", None))

                db_status = "SKIP"
                if has_db:
                    try:
                        test = await self.db_first("SELECT 1 AS ok")
                        db_status = "OK:" + str(test.ok)
                    except Exception as e:
                        db_status = "ERROR:" + repr(e)

                tg_status = "SKIP"
                webhook_status = "SKIP"
                if has_token:
                    try:
                        r = await fetch(
                            f"https://api.telegram.org/bot{self.env.BOT_TOKEN}/getMe",
                            method="GET",
                        )
                        data = await r.json()
                        tg_status = "OK" if data.get("ok") else "ERROR:" + str(data.get("description", "Telegram API error"))

                        wr = await fetch(
                            f"https://api.telegram.org/bot{self.env.BOT_TOKEN}/getWebhookInfo",
                            method="GET",
                        )
                        wd = await wr.json()
                        if wd.get("ok"):
                            w = wd.get("result") or {}
                            webhook_status = (
                                "URL_CONFIGURED=" + str(bool(w.get("url"))) +
                                " | PENDING=" + str(w.get("pending_update_count", 0)) +
                                " | LAST_ERROR=" + ("present" if w.get("last_error_message") else "none")
                            )
                        else:
                            webhook_status = "ERROR:" + str(wd.get("description", "Telegram API error"))
                    except Exception as e:
                        tg_status = "ERROR:" + repr(e)

                return Response(
                    "SUNPARK | DB=" + ("OK" if has_db else "MISSING") +
                    " | DB_TEST=" + db_status +
                    " | BOT_TOKEN=" + ("OK" if has_token else "MISSING") +
                    " | TG_TEST=" + tg_status +
                    " | WEBHOOK=" + webhook_status
                )
            except Exception as e:
                print("SUNPARK HEALTH ERROR:", repr(e))
                return Response("SUNPARK health error: " + repr(e), status=500)

        expected_secret = getattr(self.env, "WEBHOOK_SECRET", None)
        if expected_secret:
            supplied_secret = request.headers.get("x-telegram-bot-api-secret-token", "")
            if not hmac.compare_digest(str(expected_secret), str(supplied_secret)):
                print("SUNPARK WEBHOOK REJECTED: invalid secret header")
                return Response("Forbidden", status=403)

        update = None
        try:
            update = await request.json()
            kind = "message" if update.get("message") else "callback_query" if update.get("callback_query") else "other"
            print("SUNPARK UPDATE RECEIVED:", kind)

            menu, sections, info, cfg = await self.config()

            if update.get("message"):
                await self.message(update["message"], menu, sections, info, cfg)
            elif update.get("callback_query"):
                await self.callback(update["callback_query"], menu, sections, info, cfg)

            return Response("ok")
        except Exception as e:
            import traceback
            print("SUNPARK WEBHOOK ERROR:", repr(e))
            print(traceback.format_exc())

            # Try to notify the user, but NEVER allow notification failure
            # to turn the webhook response into HTTP 500.
            try:
                if update:
                    source = update.get("message") or update.get("callback_query") or {}
                    chat = source.get("chat") or (source.get("message") or {}).get("chat") or {}
                    chat_id = chat.get("id")
                    if chat_id:
                        try:
                            await self.send(
                                int(chat_id),
                                "⚠️ Временно произошла ошибка бота. Попробуйте ещё раз через несколько секунд."
                            )
                        except Exception as notify_error:
                            print("SUNPARK ERROR NOTIFY FAILED:", repr(notify_error))
            except Exception as secondary_error:
                print("SUNPARK ERROR HANDLER FAILED:", repr(secondary_error))

            return Response("ok")

    async def scheduled(self, controller, env, ctx):
        """Send one manager reminder for form requests still waiting after 30 minutes."""
        try:
            rows = await self.db_all(
                "SELECT t.number,t.guest_id,d.request_type,d.payload FROM tickets t "
                "JOIN ticket_details d ON d.ticket_number=t.number "
                "WHERE t.status='waiting' AND d.last_reminder_at IS NULL "
                "AND datetime(d.created_at)<=datetime('now','-30 minutes') ORDER BY t.number LIMIT 50"
            )
            if not rows.results:
                return
            _, _, _, cfg = await self.config()
            managers = await self.manager_ids(cfg)
            for row in rows.results:
                kind = {"booking": "Бронирование", "banquet": "Банкет"}.get(row.request_type, "Заявка")
                try:
                    payload = json.loads(str(row.payload or "{}"))
                except Exception:
                    payload = {}
                details = "\n".join(f"• <b>{esc(k)}</b>: {esc(v)}" for k, v in payload.items())
                reminder = f"⏰ <b>Напоминание: ожидает ответа более 30 минут</b>\n\n{kind} #{row.number}\n{details}"
                sent = False
                for mid in managers:
                    try:
                        await self.send(mid, reminder, ikb([[btn("🤝 Взять обращение", f"claim:{row.guest_id}")]]))
                        sent = True
                    except Exception as e:
                        print("SUNPARK REMINDER DELIVERY ERROR:", repr(e))
                if sent:
                    await self.db_run("UPDATE ticket_details SET last_reminder_at=datetime('now') WHERE ticket_number=? AND last_reminder_at IS NULL", row.number)
        except Exception as e:
            print("SUNPARK SCHEDULED ERROR:", repr(e))



class Default(Bot):
    pass
