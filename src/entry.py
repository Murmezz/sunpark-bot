from workers import WorkerEntrypoint, Response
from js import fetch, JSON
from urllib.parse import urlparse
import json
import html

BANQUET_MAIN_SECTIONS = [
    ("🥂 Банкетные пакеты", [0, 1, 2, 31]),
    ("🥗 Холодные закуски", [3, 4, 5, 6, 7, 8, 9]),
    ("🍤 Горячие закуски", [10, 11]),
    ("🥗 Салаты", [12, 13, 14, 15, 16]),
    ("🍖 Горячие блюда", [17, 18, 19]),
    ("🥂 Фуршет", [20, 21, 22, 23, 24, 25, 26, 27, 28, 29]),
    ("🍰 Десерты", [30]),
    ("🧒 Детское меню", [32]),
    ("ℹ️ Информация", []),
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
    async def db_first(self, sql, *args):
        return await self.env.DB.prepare(sql).bind(*args).first()

    async def db_all(self, sql, *args):
        return await self.env.DB.prepare(sql).bind(*args).all()

    async def db_run(self, sql, *args):
        return await self.env.DB.prepare(sql).bind(*args).run()

    async def tg(self, method, params):
        token = self.env.BOT_TOKEN
        r = await fetch(
            f"https://api.telegram.org/bot{token}/{method}",
            {
                "method": "POST",
                "headers": {"content-type": "application/json"},
                "body": json.dumps(params),
            },
        )
        data = await r.json()
        if not data.ok:
            raise Exception(f"{method}: {data.description}")
        return data.result

    async def send(self, chat_id, text, markup=None):
        p = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if markup is not None:
            p["reply_markup"] = markup
        return await self.tg("sendMessage", p)

    async def edit(self, msg, text, markup=None):
        p = {
            "chat_id": msg.chat.id,
            "message_id": msg.message_id,
            "text": text,
            "parse_mode": "HTML",
        }
        if markup is not None:
            p["reply_markup"] = markup
        try:
            await self.tg("editMessageText", p)
        except Exception as e:
            if "not modified" not in str(e).lower():
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
                "chat_id": msg.chat.id,
                "message_id": msg.message_id,
                "reply_markup": {"inline_keyboard": []},
            })
        except Exception:
            pass

    async def config(self):
        await self.db_run("CREATE TABLE IF NOT EXISTS manager_states (user_id INTEGER PRIMARY KEY, action TEXT NOT NULL)")
        await self.db_run(
            "CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, last_name TEXT, updated_at TEXT NOT NULL)"
        )
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
        raw = ",".join([str(cfg.get("manager_ids") or ""), str(self.env.MANAGER_IDS or "")]).strip(",")
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
        ]
        if manager:
            rows.append([btn("⚙️ Админ-панель", "admin:panel")])
        return ikb(rows)

    def persistent(self, manager):
        rows = [[{"text": "🏠 Главное меню"}]]
        if manager:
            rows.append([{"text": "👀 Как гость"}, {"text": "⚙️ Админ-панель"}])
        return {"keyboard": rows, "resize_keyboard": True, "is_persistent": True}

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

    def banquet_keyboard(self):
        return ikb([[btn(title, f"banquet:section:{i}")] for i, (title, _) in enumerate(BANQUET_MAIN_SECTIONS)] + [[btn("🏠 На главную", "back")]])

    def banquet_section_keyboard(self, menu, idx):
        all_items = items(menu.get("banquet", {}))
        rows = []
        for source in BANQUET_MAIN_SECTIONS[idx][1]:
            if source < len(all_items):
                it = all_items[source]
                rows.append([btn(it[1] if len(it) > 1 and it[1] else it[0], f"item:banquet:{source}")])
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
            [btn("📥 Активные обращения", "admin:active")],
            [btn("✅ Закрытые обращения", "admin:closed")],
            [btn("📊 Статистика", "admin:stats")],
            [btn("👥 Менеджеры", "admin:managers")],
            [btn("👀 Открыть как гость", "admin:guest")],
        ])

    def admin_back(self):
        return ikb([[btn("◀️ В админ-панель", "admin:panel")], [btn("🏠 На главную", "back")]])

    def managers_keyboard(self):
        return ikb([
            [btn("➕ Добавить менеджера", "admin:manager_add")],
            [btn("✏️ Изменить имя", "admin:manager_rename")],
            [btn("➖ Удалить менеджера", "admin:manager_remove")],
            [btn("◀️ В админ-панель", "admin:panel")],
        ])

    async def active_text(self, names):
        r = await self.db_all(
            "SELECT t.number,t.manager_id,u.username,u.first_name,u.last_name FROM tickets t LEFT JOIN users u ON u.user_id=t.guest_id WHERE t.status='active' ORDER BY t.number"
        )
        if not r.results:
            return "📥 <b>Активные обращения</b>\n\nСейчас активных обращений нет."
        out = ["📥 <b>Активные обращения</b>", ""]
        for t in r.results:
            guest = ("@" + t.username) if t.username else (" ".join(x for x in [t.first_name,t.last_name] if x) or "без username")
            manager = names.get(str(t.manager_id), "ID " + str(t.manager_id))
            out.append(f"🟡 Обращение #{t.number} — гость <b>{esc(guest)}</b> — менеджер <b>{esc(manager)}</b>")
        return "\n".join(out)

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
        text = msg.get("text")
        frm = msg.get("from") or {}
        chat = msg.get("chat") or {}
        if not text or chat.get("type") != "private":
            return
        uid = int(frm.get("id"))

        await self.db_run(
            "INSERT INTO users(user_id,username,first_name,last_name,updated_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET username=excluded.username,first_name=excluded.first_name,last_name=excluded.last_name,updated_at=excluded.updated_at",
            uid, frm.get("username"), frm.get("first_name"), frm.get("last_name"), "now",
        )
        managers = await self.manager_ids(cfg)
        mgr = uid in managers
        action = await self.get_action(uid) if mgr else ""

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
            await self.send(uid, "Нижняя кнопка «🏠 Главное меню» всегда вернёт вас сюда.", self.persistent(mgr))
            return
        if text == "/admin" and mgr:
            await self.send(uid, await self.admin_panel_text(), self.admin_keyboard())
            return
        if text == "🏠 Главное меню":
            await self.send(uid, self.home_text(), self.home_keyboard(mgr))
            await self.send(uid, "Меню обновлено.", self.persistent(mgr))
            return
        if text == "👀 Как гость" and mgr:
            await self.send(uid, "👀 <b>Режим просмотра как гость</b>", self.home_keyboard(mgr))
            return
        if text == "⚙️ Админ-панель" and mgr:
            await self.send(uid, await self.admin_panel_text(), self.admin_keyboard())
            return
        if text in ("👀 Как гость", "⚙️ Админ-панель"):
            return

        if mgr:
            t = await self.db_first("SELECT guest_id FROM tickets WHERE manager_id=? AND status='active' ORDER BY claimed_at DESC,number DESC LIMIT 1", uid)
            if t:
                await self.send(int(t.guest_id), f"👨‍💼 <b>Менеджер:</b>\n{esc(text)}")
                await self.send(uid, "✅ Сообщение отправлено гостю.")
                return

        own = await self.db_first("SELECT * FROM tickets WHERE guest_id=? AND status IN ('draft','waiting','active') ORDER BY number DESC LIMIT 1", uid)
        if not own:
            return
        if own.status == "active":
            await self.send(int(own.manager_id), f"💬 <b>Обращение #{own.number}</b>\n👤 {self.guest_label(frm)}\n\n{esc(text)}",
                            ikb([[btn("❌ Завершить обращение", f"close:{uid}")]]))
            await self.send(uid, "📨 Сообщение отправлено менеджеру.")
            return
        body = f"🆕 <b>Новое обращение #{own.number}</b>\n\n👤 <b>Гость:</b> {self.guest_label(frm)}\n🆔 <b>ID:</b> <code>{uid}</code>\n\n💬 <b>Сообщение:</b>\n{esc(text)}"
        for mid in managers:
            try:
                await self.send(mid, body, ikb([[btn("🤝 Взять обращение", f"claim:{uid}")]]))
            except Exception:
                pass
        await self.db_run("UPDATE tickets SET status='waiting' WHERE number=?", own.number)
        await self.send(uid, "📨 Спасибо! Ваше сообщение отправлено менеджерам SUNPARK.\n\nКак только один из менеджеров возьмёт обращение, мы продолжим общение здесь.")

    async def callback(self, cb, menu, sections, info, cfg):
        data = cb.get("data", "")
        uid = int((cb.get("from") or {}).get("id"))
        msg = cb.get("message")
        if not msg:
            await self.answer(cb.get("id"))
            return
        managers = await self.manager_ids(cfg)
        mgr = uid in managers
        if data == "noop":
            await self.answer(cb.get("id")); return
        if data == "back":
            await self.edit(msg, self.home_text(), self.home_keyboard(mgr)); await self.answer(cb.get("id")); return
        if data == "home:menu":
            await self.edit(msg, "🍽 <b>Основное меню SUNPARK</b>\n\nВыберите раздел:", self.main_keyboard(menu, sections)); await self.answer(cb.get("id")); return
        if data == "home:banquet":
            await self.edit(msg, "🎉 <b>Банкетное меню</b>\n\nЗдесь вы можете посмотреть варианты банкетных блюд или связаться с менеджером.", ikb([[btn("📋 Посмотреть банкетное меню","banquet:list")],[btn("💬 Связаться с менеджером","manager:start")],[btn("🏠 На главную","back")]])); await self.answer(cb.get("id")); return
        if data == "banquet:list":
            await self.edit(msg, "🎉 <b>Банкетное меню SUNPARK · 2026</b>", self.banquet_keyboard()); await self.answer(cb.get("id")); return
        if data.startswith("banquet:section:"):
            idx = int(data.split(":")[-1])
            if idx == 8:
                arr = items(menu.get("banquet", {}))
                text = arr[33][3] if len(arr) > 33 and len(arr[33]) > 3 else "Информация отсутствует."
                await self.edit(msg, "<b>ℹ️ Информация</b>\n\n" + esc(text), ikb([[btn("◀️ К банкетному меню","banquet:list")],[btn("🏠 На главную","back")]]))
            elif idx == 7:
                rows = [[btn(x[0], f"bchild:{i}")] for i,x in enumerate(BANQUET_CHILD)]
                rows += [[btn("◀️ К банкетному меню","banquet:list")],[btn("🏠 На главную","back")]]
                await self.edit(msg, "🧒 <b>Детское меню</b>\n\nВыберите блюдо:", ikb(rows))
            else:
                await self.edit(msg, "🎉 <b>"+esc(BANQUET_MAIN_SECTIONS[idx][0])+"</b>\n\nВыберите позицию:", self.banquet_section_keyboard(menu, idx))
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
            phone = cfg.get("phone") or getattr(self.env, "MANAGER_PHONE", None) or "+76767676767"
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
            await self.db_run("DELETE FROM tickets WHERE guest_id=? AND status IN ('draft','waiting')", uid)
            await self.edit(msg, "🎉 <b>Банкетное меню</b>\n\nЗдесь вы можете посмотреть варианты банкетных блюд или связаться с менеджером.", ikb([[btn("📋 Посмотреть банкетное меню","banquet:list")],[btn("💬 Связаться с менеджером","manager:start")],[btn("🏠 На главную","back")]])); await self.answer(cb.get("id")); return
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
            await self.tg("editMessageReplyMarkup", {"chat_id": msg.chat.id, "message_id": msg.message_id, "reply_markup": ikb([[btn("❌ Завершить обращение",f"close:{guest_id}")]])})
            await self.send(msg.chat.id, f"✅ <b>Обращение #{t.number} взято вами.</b>\n\nТеперь сообщения этого гостя будут приходить вам, а ваши ответы — гостю.")
            await self.send(guest_id, "👨‍💼 <b>Вашим обращением занимается менеджер SUNPARK.</b>\n\nМожете продолжать писать сообщения прямо здесь.")
            await self.answer(cb.get("id"), "Обращение закреплено за вами."); return
        if data.startswith("close:"):
            if not mgr:
                await self.answer(cb.get("id"), "Эта кнопка доступна только менеджерам.", True); return
            guest_id = int(data[6:])
            t = await self.db_first("SELECT number FROM tickets WHERE guest_id=? AND manager_id=? AND status='active'", guest_id, uid)
            if not t:
                await self.answer(cb.get("id"), "Это обращение вам не назначено.", True); return
            await self.db_run("UPDATE tickets SET status='closed',closed_at=datetime('now') WHERE number=?", t.number)
            await self.clear_markup(msg)
            await self.send(msg.chat.id, f"✅ Обращение #{t.number} завершено.")
            await self.send(guest_id, "✅ <b>Обращение завершено.</b>\n\nЕсли у вас появится новый вопрос по банкету, просто нажмите «💬 Связаться с менеджером» снова.")
            await self.answer(cb.get("id")); return
        if data.startswith("admin:"):
            if not mgr:
                await self.answer(cb.get("id"), "Доступ запрещён.", True); return
            what = data[6:]
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
                await self.edit(msg, await self.active_text(await self.manager_names(cfg)), self.admin_back())
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
        if request.method != "POST":
            return Response("SUNPARK bot is running")
        try:
            update = await request.json()
        except Exception:
            return Response("bad request", status=400)
        try:
            menu, sections, info, cfg = await self.config()
            if update.get("message"):
                await self.message(update["message"], menu, sections, info, cfg)
            elif update.get("callback_query"):
                await self.callback(update["callback_query"], menu, sections, info, cfg)
        except Exception as e:
            print("worker error:", e)
        return Response("ok")


class Default(Bot):
    pass
