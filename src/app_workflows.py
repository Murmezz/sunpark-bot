"""Typed Mini App screens and submissions over the existing D1 business model."""
import json
import html
import re
from datetime import datetime, timezone
from events import FIELDS, MSK, russian_phone


class WorkflowError(Exception):
    def __init__(self, message, status=400, fields=None):
        super().__init__(message)
        self.status, self.fields = status, fields or {}


def record(row, keys):
    return {key: getattr(row, key, None) for key in keys}


def object_json(value):
    try:
        data = json.loads(str(value or "{}"))
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        return {}


def positive(value, label="Запись"):
    if type(value) is not int or value < 1:
        raise WorkflowError(label + " не найдена.", 404)
    return value


def sql_russian_fold(expression, alphabet):
    # SQLite lower() only folds ASCII. Separate CTEs keep parser nesting small.
    for letter in alphabet:
        expression = f"replace({expression},'{letter}','{letter.lower()}')"
    return expression


class AppWorkflowsMixin:
    async def workflow_screen(self, user, p, info, cfg):
        uid, name = int(user["id"]), p.get("screen")
        staff = p.get("scope") == "staff"
        manager = await self.is_manager(uid, cfg)
        admin_screens = ("dashboard", "managers", "event_guests", "event_create", "event_edit", "manual", "note", "templates")
        if (staff or name in admin_screens) and not manager:
            raise WorkflowError("Доступ запрещён.", 403)
        now = datetime.now(MSK)
        common = {"screen": name, "now": now.isoformat(), "today": now.strftime("%Y-%m-%d")}
        if name in ("booking", "banquet", "inquiry"):
            active = await self.db_first("SELECT number,status FROM tickets WHERE guest_id=? AND status IN ('waiting','active','waiting_guest') ORDER BY number DESC LIMIT 1", uid)
            if active:
                return {**common, "existing_ticket": int(active.number)}
            flow = await self.db_first("SELECT request_type,payload FROM guest_flows WHERE user_id=?", uid)
            data = object_json(flow.payload) if flow and str(flow.request_type) == name else {}
            if data.get("date"):
                try:
                    data["date"] = datetime.strptime(data["date"], "%d.%m.%Y").strftime("%Y-%m-%d")
                except ValueError:
                    pass
            return {**common, "data": data, "profile_name": " ".join(str(user.get(k) or "") for k in ("first_name", "last_name")).strip()}
        if name == "dashboard":
            row = await self.db_first("SELECT SUM(status='waiting') waiting,SUM(status IN ('active','waiting_guest')) active,SUM(status='closed') closed,SUM(status IN ('active','waiting_guest') AND manager_id=?) mine FROM tickets", uid)
            return {**common, "stats": {key: int(getattr(row, key, 0) or 0) for key in ("waiting", "active", "closed", "mine")}, "managers": len(await self.manager_ids(cfg))}
        if name == "tickets":
            return {**common, **await self.workflow_tickets(uid, p, cfg)}
        if name == "managers":
            names = await self.manager_names(cfg)
            rows = []
            for mid in sorted(await self.manager_ids(cfg)):
                person = await self.db_first("SELECT username,first_name,last_name FROM users WHERE user_id=?", mid)
                fixed_ids = {int(value.strip()) for value in str(getattr(self.env, "MANAGER_IDS", "") or "").split(",") if value.strip().isdigit()}
                rows.append({"id": mid, "name": names.get(str(mid)) or (str(person.first_name or "") if person else "") or "Менеджер", "username": str(person.username or "") if person else "", "self": mid == uid, "fixed": mid in fixed_ids})
            return {**common, "managers": rows}
        if name == "info":
            return {**common, "rules": info, "address": cfg.get("address") or "Санкт-Петербург, ул. Никольская, 9", "hours": cfg.get("hours") or "Пн–пт: 12:00–23:00\nСб–вс и праздничные дни: 11:00–23:00", "phone": cfg.get("phone") or getattr(self.env, "MANAGER_PHONE", "") or "+7 (911) 714-40-12", "map_url": cfg.get("map_url") or "https://yandex.ru/maps/org/sunpark/1696243668", "website": cfg.get("website") or "https://sunparkspb.ru/"}
        if name in ("note", "templates"):
            ticket = await self.app_ticket(uid, p.get("ticket"), "staff")
            if int(ticket.manager_id or 0) != uid or ticket.status not in ("active", "waiting_guest"):
                raise WorkflowError("Заявка уже закрыта или передана.", 409)
            if name == "templates":
                return {**common, "choices": [{"text": text, "callback": f"template:{ticket.number}:{index}"} for index, text in enumerate(self.quick_reply_choices())]}
            note = await self.ticket_note(ticket.number)
            return {**common, "ticket": int(ticket.number), "data": {"note": str(note.note or "") if note else ""}}
        if name == "events":
            if not self.events_visible(manager):
                raise WorkflowError("Мероприятия пока доступны только администраторам.", 403)
            page = min(max(0, int(p.get("page", 0))), 100000)
            clause, args = ("1=1", []) if staff else ("e.starts_at>=datetime('now') OR EXISTS(SELECT 1 FROM event_registrations r WHERE r.event_id=e.id AND r.telegram_id=?)", [uid])
            result = await self.db_all(f"SELECT e.id FROM events e WHERE {clause} ORDER BY e.starts_at {'DESC' if staff else 'ASC'},e.id LIMIT 13 OFFSET ?", *args, page * 12)
            rows = [await self.workflow_event(uid, int(row.id), staff) for row in list(result.results)[:12]]
            return {**common, "events": rows, "more": len(result.results) > 12, "page": page}
        if name in ("event", "event_edit", "manual", "register", "event_guests"):
            if not self.events_visible(manager):
                raise WorkflowError("Мероприятия пока доступны только администраторам.", 403)
            event_id = positive(p.get("event"), "Мероприятие")
            event = await self.workflow_event(uid, event_id, staff or name in admin_screens)
            if name == "event_guests":
                page = min(max(0, int(p.get("page", 0))), 100000)
                result = await self.db_all("SELECT * FROM event_registrations WHERE event_id=? ORDER BY id LIMIT 21 OFFSET ?", event_id, page * 20)
                rows = [record(row, ("id", "first_name", "last_name", "phone", "party_size", "telegram_username", "added_by_admin", "admin_id")) for row in list(result.results)[:20]]
                return {**common, "event": event, "registrations": rows, "more": len(result.results) > 20, "page": page}
            data = {key: event[key] for key, _ in FIELDS} if name == "event_edit" else {}
            if name == "register":
                data = {"first_name": user.get("first_name") or "", "last_name": user.get("last_name") or "", "party_size": 1}
            return {**common, "event": event, "data": data}
        if name == "event_create":
            return {**common, "data": {"capacity": 50, "location": "SUNPARK"}}
        raise WorkflowError("Экран не найден.", 404)

    async def workflow_event(self, uid, event_id, staff):
        row = await self.event_get(event_id)
        if not row:
            raise WorkflowError("Мероприятие не найдено.", 404)
        keys = ("id", "title", "description", "starts_at", "location", "price", "capacity", "is_open", "version", "self_guests", "total_guests")
        data = record(row, keys)
        data["starts_at"] = datetime.strptime(str(row.starts_at), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).astimezone(MSK).strftime("%Y-%m-%dT%H:%M")
        data["available"] = max(0, int(row.capacity) - int(row.self_guests))
        mine = await self.db_first("SELECT id,party_size FROM event_registrations WHERE event_id=? AND telegram_id=?", event_id, uid)
        data["mine"] = record(mine, ("id", "party_size")) if mine else None
        if not staff:
            data.pop("total_guests", None)
        return data

    async def workflow_tickets(self, uid, p, cfg):
        staff, mode = p.get("scope") == "staff", p.get("filter", "all")
        page = min(max(0, int(p.get("page", 0))), 100000)
        clauses, args = ["t.status!='draft'"], []
        if not staff:
            clauses.append("t.guest_id=?"); args.append(uid)
        elif mode == "waiting":
            clauses.append("t.status='waiting'")
        elif mode == "mine":
            clauses.append("t.manager_id=? AND t.status IN ('active','waiting_guest')"); args.append(uid)
        elif mode == "others":
            clauses.append("t.manager_id!=? AND t.status IN ('active','waiting_guest')"); args.append(uid)
        elif mode == "closed":
            clauses.append("t.status='closed'")
        elif mode not in ("all", "search"):
            raise WorkflowError("Неизвестный фильтр.")
        query = str(p.get("query") or "").strip()[:150]
        base = "SELECT t.number,t.status,t.guest_id,t.manager_id,t.created_at,d.request_type,d.payload,u.first_name,u.last_name,u.username FROM tickets t LEFT JOIN ticket_details d ON d.ticket_number=t.number LEFT JOIN users u ON u.user_id=t.guest_id WHERE " + " AND ".join(clauses)
        if query:
            alphabet = "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ"
            half = sql_russian_fold("COALESCE(first_name,'')||' '||COALESCE(last_name,'')||' '||COALESCE(username,'')||' '||COALESCE(payload,'')||' #'||number", alphabet[:16])
            folded = sql_russian_fold("search_half", alphabet[16:])
            folded_query = query.casefold().lstrip("#@")
            if re.fullmatch(r"[+\d\s()\-]+", folded_query) and len(re.sub(r"\D", "", folded_query)) >= 4:
                folded_query = re.sub(r"\D", "", folded_query)
            escaped = folded_query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            sql = f"WITH source AS ({base}),half AS (SELECT *,{half} search_half FROM source),folded AS (SELECT *,lower({folded}) search_fold FROM half) SELECT * FROM folded WHERE search_fold LIKE ? ESCAPE '\\' ORDER BY number DESC LIMIT 21 OFFSET ?"
            args.append("%" + escaped + "%")
        else:
            sql = base + " ORDER BY t.number DESC LIMIT 21 OFFSET ?"
        rows = await self.db_all(sql, *args, page * 20)
        names = await self.manager_names(cfg)
        tickets = []
        for row in list(rows.results)[:20]:
            item = record(row, ("number", "status", "guest_id", "manager_id", "created_at", "request_type", "first_name", "last_name", "username"))
            item["details"] = object_json(row.payload)
            last = await self.db_first("SELECT body,created_at FROM ticket_messages WHERE ticket_number=? ORDER BY id DESC LIMIT 1", row.number)
            item["preview"] = self.ticket_preview(last.body) if last else "Переписка ещё не началась"
            item["last_at"] = str(last.created_at) if last else str(row.created_at or "")
            item["manager_name"] = names.get(str(row.manager_id), "Менеджер") if row.manager_id else ""
            unread = await self.db_first("SELECT COUNT(*) n FROM ticket_messages WHERE ticket_number=? AND sender_role='guest' AND id>COALESCE((SELECT last_read_message_id FROM ticket_reads WHERE ticket_number=? AND manager_id=?),0)", row.number, row.number, uid) if staff else None
            item["unread"] = int(unread.n or 0) if unread else 0
            tickets.append(item)
        return {"tickets": tickets, "page": page, "more": len(rows.results) > 20}

    async def workflow_submit(self, bridge, p, cfg):
        uid, kind = bridge.uid, p.get("kind")
        values = p.get("values")
        if not isinstance(values, dict):
            raise WorkflowError("Проверьте поля формы.")
        manager = await self.is_manager(uid, cfg)
        if kind in ("event_create", "event_edit", "manual", "manager_add", "manager_edit", "note") and not manager:
            raise WorkflowError("Доступ запрещён.", 403)
        if kind == "inquiry":
            text = str(values.get("message") or "").strip()
            if not 1 <= len(text) <= 3500:
                raise WorkflowError("Введите ваш вопрос.", fields={"message": "От 1 до 3500 символов."})
            reserved = await self.db_run("INSERT INTO tickets(guest_id,status) SELECT ?,'draft' WHERE NOT EXISTS(SELECT 1 FROM tickets WHERE guest_id=? AND status IN ('draft','waiting','active','waiting_guest'))", uid, uid)
            if not int(reserved.meta.changes or 0):
                raise WorkflowError("У вас уже есть заявка или её черновик. Откройте раздел «Сообщения».", 409)
            ticket = await self.db_first("SELECT number FROM tickets WHERE guest_id=? AND status='draft' ORDER BY number DESC LIMIT 1", uid)
            number = int(ticket.number)
            await self.save_ticket_message(number, uid, "guest", text)
            await self.db_run("INSERT INTO ticket_details(ticket_number,request_type,payload,created_at) VALUES(?,'inquiry','{}',datetime('now'))", number)
            await self.db_run("UPDATE tickets SET status='waiting' WHERE number=? AND status='draft'", number)
            body = f"💬 <b>Новое обращение #{number}</b>\n\n{bridge.guest_label(bridge.user)}\n\n{html.escape(text)}"
            for mid in sorted(await self.manager_ids(cfg)):
                try:
                    sent = await self.send(mid, body, {"inline_keyboard": [[{"text": "Взять обращение", "callback_data": f"claim:{uid}"}]]})
                    await self.db_run("INSERT OR REPLACE INTO ticket_manager_notices(ticket_number,manager_id,message_id,body) VALUES(?,?,?,?)", number, mid, sent["message_id"], body)
                except Exception as error:
                    print("SUNPARK INQUIRY NOTIFICATION", type(error).__name__)
            return {"ok": True, "ticket": number, "notice": "Обращение создано. Переписка доступна в сообщениях."}
        if kind in ("booking", "banquet"):
            data = self.workflow_booking_values(kind, values)
            await self.clear_action(uid)
            await self.event_clear_session(uid)
            existing = await self.db_first("SELECT number FROM tickets WHERE guest_id=? AND status IN ('waiting','active','waiting_guest') LIMIT 1", uid)
            if existing:
                raise WorkflowError("У вас уже есть открытая заявка. Продолжите переписку в разделе «Сообщения».", 409)
            flow = await self.db_first("SELECT * FROM guest_flows WHERE user_id=?", uid)
            if flow and str(flow.request_type) != kind:
                raise WorkflowError("У вас есть черновик другой заявки. Завершите или отмените его.", 409)
            if not flow:
                await bridge.start_form(uid, kind)
                flow = await self.db_first("SELECT * FROM guest_flows WHERE user_id=?", uid)
            if not flow:
                raise WorkflowError("Не удалось открыть заявку. Обновите экран.", 409)
            fields = self.form_steps(kind)
            last_field = fields[-1][0]
            prepared = {key: value for key, value in data.items() if key != last_field}
            changed = await self.db_run("UPDATE guest_flows SET step=?,payload=?,updated_at=datetime('now') WHERE user_id=? AND ticket_number=? AND step>=0 AND EXISTS(SELECT 1 FROM tickets WHERE number=? AND status='draft')", len(fields)-1, json.dumps(prepared, ensure_ascii=False), uid, flow.ticket_number, flow.ticket_number)
            if not int(changed.meta.changes or 0):
                raise WorkflowError("Заявка уже отправляется. Откройте сообщения.", 409)
            await bridge.accept_form_answer(uid, str(data[last_field] or "—"), bridge.user, await self.manager_ids(cfg))
            row = await self.db_first("SELECT status FROM tickets WHERE number=?", flow.ticket_number)
            if not row or row.status == "draft":
                raise WorkflowError("Не удалось отправить заявку. Проверьте поля.", 409)
            return {"ok": True, "ticket": int(flow.ticket_number), "notice": "Заявка отправлена. Менеджер подтвердит возможность бронирования."}
        if kind in ("event_create", "event_edit"):
            errors, data = {}, {}
            previous = await self.event_get(positive(p.get("event"), "Мероприятие")) if kind == "event_edit" else None
            for key, _ in FIELDS:
                value = str(values.get(key) or "").strip()
                if key == "starts_at":
                    try:
                        value = datetime.strptime(value, "%Y-%m-%dT%H:%M").strftime("%d.%m.%Y %H:%M")
                    except ValueError:
                        pass
                    if previous and value == datetime.strptime(str(previous.starts_at), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).astimezone(MSK).strftime("%d.%m.%Y %H:%M"):
                        data[key] = str(previous.starts_at)
                        continue
                try:
                    data[key] = self.event_parse_field(key, value or ("—" if key == "description" else ""))
                except ValueError as error:
                    errors[key] = str(error)
            if errors:
                raise WorkflowError("Проверьте поля мероприятия.", fields=errors)
            if kind == "event_create":
                key = str(p["request_key"])
                await self.db_run("INSERT OR IGNORE INTO events(title,description,starts_at,location,price,capacity,created_by,creation_key) VALUES(?,?,?,?,?,?,?,?)", *(data[k] for k, _ in FIELDS), uid, key)
                row = await self.db_first("SELECT id FROM events WHERE creation_key=?", key)
                event_id = int(row.id)
            else:
                event_id = positive(p.get("event"), "Мероприятие")
                version = p.get("version")
                if type(version) is not int or version < 0:
                    raise WorkflowError("Обновите настройки мероприятия.", 409)
                changed = await self.db_run("UPDATE events SET title=?,description=?,starts_at=?,location=?,price=?,capacity=?,version=version+1 WHERE id=? AND version=?", *(data[k] for k, _ in FIELDS), event_id, version)
                if not int(changed.meta.changes or 0):
                    raise WorkflowError("Настройки изменил другой администратор. Откройте их заново.", 409)
            return {"ok": True, "event": event_id, "notice": "Мероприятие создано. Регистрацию можно открыть в его карточке." if kind == "event_create" else "Настройки сохранены."}
        if kind in ("manual", "register"):
            if not self.events_visible(manager):
                raise WorkflowError("Мероприятия пока доступны только администраторам.", 403)
            event_id = positive(p.get("event"), "Мероприятие")
            event = await self.event_get(event_id)
            if not event:
                raise WorkflowError("Мероприятие не найдено.", 404)
            errors, data = {}, {}
            for key in ("first_name", "last_name", "phone", "party_size", "telegram_username"):
                value = str(values.get(key) or "").strip()
                if key == "telegram_username" and kind == "register":
                    data[key] = str(bridge.user.get("username") or "")
                    continue
                try:
                    data[key] = self.event_parse_field(key, value or ("—" if key == "telegram_username" else ""))
                except ValueError as error:
                    errors[key] = str(error)
            if errors:
                raise WorkflowError("Проверьте данные гостя.", fields=errors)
            inserted = await self.event_insert_registration(event_id, data, uid, kind == "manual")
            if not int(inserted.meta.changes or 0):
                duplicate = await self.db_first("SELECT id FROM event_registrations WHERE event_id=? AND (phone=? OR (?=0 AND telegram_id=?))", event_id, data["phone"], int(kind == "manual"), uid)
                raise WorkflowError("Этот человек уже зарегистрирован." if duplicate else "Регистрация закрыта или недостаточно мест для вашей компании.", 409, {"phone": "Этот номер уже есть в списке."} if duplicate else {})
            return {"ok": True, "event": event_id, "notice": "Запись добавлена вручную." if kind == "manual" else "Вы успешно зарегистрированы!"}
        if kind == "note":
            number = positive(p.get("ticket"), "Заявка")
            ticket = await self.app_ticket(uid, number, "staff")
            note = str(values.get("note") or "").strip()
            if len(note) > 1500:
                raise WorkflowError("Заметка слишком длинная.", fields={"note": "Не больше 1500 символов."})
            if int(ticket.manager_id or 0) != uid or ticket.status not in ("active", "waiting_guest"):
                raise WorkflowError("Заявка уже закрыта или передана.", 409)
            changed = await self.db_run("INSERT INTO ticket_notes(ticket_number,manager_id,note) SELECT number,?,? FROM tickets WHERE number=? AND manager_id=? AND status IN ('active','waiting_guest') ON CONFLICT(ticket_number) DO UPDATE SET manager_id=excluded.manager_id,note=excluded.note,updated_at=datetime('now')", uid, note, number, uid)
            if not int(changed.meta.changes or 0):
                raise WorkflowError("Заявка уже закрыта или передана.", 409)
            return {"ok": True, "ticket": number, "notice": "Заметка сохранена. Её видят только менеджеры."}
        if kind in ("manager_add", "manager_edit"):
            ids = await self.manager_ids(cfg)
            names = await self.manager_names(cfg)
            display = str(values.get("name") or "").strip()
            if not 1 <= len(display) <= 50:
                raise WorkflowError("Укажите имя менеджера.", fields={"name": "От 1 до 50 символов."})
            if kind == "manager_add":
                tag = str(values.get("username") or "").strip().lstrip("@").lower()
                if not re.fullmatch(r"[a-zA-Z0-9_]{5,32}", tag):
                    raise WorkflowError("Проверьте Telegram-ник.", fields={"username": "Введите @username Telegram."})
                target = await self.db_first("SELECT user_id FROM users WHERE lower(username)=?", tag)
                if not target:
                    raise WorkflowError("Пользователь ещё не найден.", fields={"username": "Пусть пользователь сначала напишет боту /start."})
                mid = int(target.user_id)
                if mid in ids:
                    raise WorkflowError("Этот менеджер уже есть в списке.", 409)
                ids.add(mid)
            else:
                mid = positive(p.get("manager"), "Менеджер")
                if mid not in ids:
                    raise WorkflowError("Менеджер не найден.", 404)
            names[str(mid)] = display
            await self.save_manager_names(names)
            await self.save_manager_ids(ids)
            return {"ok": True, "notice": "Менеджер добавлен." if kind == "manager_add" else "Имя сохранено."}
        raise WorkflowError("Неизвестная форма.")

    def workflow_booking_values(self, kind, values):
        errors, data = {}, {}
        now = datetime.now(MSK)
        for key, _ in self.form_steps(kind):
            value = str(values.get(key) or "").strip()
            if key == "date":
                try:
                    parsed = datetime.strptime(value, "%Y-%m-%d")
                    if parsed.date() < now.date():
                        raise ValueError()
                    value = parsed.strftime("%d.%m.%Y")
                except ValueError:
                    errors[key] = "Выберите сегодняшнюю или будущую дату."
            elif key == "time":
                if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
                    errors[key] = "Выберите время."
                elif str(values.get("date")) == now.strftime("%Y-%m-%d") and value <= now.strftime("%H:%M"):
                    errors[key] = "Выберите время позднее текущего (МСК)."
            elif key == "guests":
                if not re.fullmatch(r"\d{1,3}", value) or not 1 <= int(value) <= 200:
                    errors[key] = "От 1 до 200 гостей."
            elif key == "phone":
                value = russian_phone(value)
                if not value:
                    errors[key] = "Введите российский номер, например +7 900 123-45-67."
            elif key == "name":
                if not value or len(value) > 100:
                    errors[key] = "Введите имя, до 100 символов."
            elif key not in ("comment", "wishes") and not value:
                errors[key] = "Заполните это поле."
            elif len(value) > 1200:
                errors[key] = "Не больше 1200 символов."
            data[key] = value or ""
        if errors:
            raise WorkflowError("Проверьте поля заявки.", fields=errors)
        return data

    async def workflow_command(self, bridge, p, cfg):
        uid, action = bridge.uid, p.get("command")
        manager = await self.is_manager(uid, cfg)
        if action == "discard_draft":
            flow = await self.db_first("SELECT f.ticket_number FROM guest_flows f JOIN tickets t ON t.number=f.ticket_number WHERE f.user_id=? AND t.guest_id=? AND t.status='draft'", uid, uid)
            if flow:
                await self.db_run("DELETE FROM guest_flows WHERE user_id=? AND ticket_number=? AND EXISTS(SELECT 1 FROM tickets WHERE number=? AND status='draft')", uid, flow.ticket_number, flow.ticket_number)
                await self.db_run("DELETE FROM ticket_details WHERE ticket_number=? AND EXISTS(SELECT 1 FROM tickets WHERE number=? AND status='draft')", flow.ticket_number, flow.ticket_number)
                await self.db_run("DELETE FROM tickets WHERE number=? AND guest_id=? AND status='draft'", flow.ticket_number, uid)
            return {"ok": True, "notice": "Черновик очищен."}
        if action == "cancel_ticket":
            number = positive(p.get("ticket"), "Заявка")
            await self.app_ticket(uid, number, "guest")
            changed = await self.db_run("UPDATE tickets SET status='closed',closed_at=datetime('now') WHERE number=? AND guest_id=? AND status='waiting' AND manager_id IS NULL", number, uid)
            if not int(changed.meta.changes or 0):
                raise WorkflowError("Заявку уже взял менеджер. Обсудите отмену в переписке.", 409)
            notices = await self.db_all("SELECT manager_id,message_id,body FROM ticket_manager_notices WHERE ticket_number=?", number)
            for notice in notices.results:
                try:
                    await self.tg("editMessageText", {"chat_id": int(notice.manager_id), "message_id": int(notice.message_id), "text": str(notice.body or "")+"\n\n❌ <b>Гость отменил заявку.</b>", "parse_mode": "HTML", "reply_markup": {"inline_keyboard": []}})
                except Exception as error:
                    print("SUNPARK CANCELLATION NOTICE", type(error).__name__)
            return {"ok": True, "notice": "Заявка отменена."}
        if action == "remove_manager":
            if not manager:
                raise WorkflowError("Доступ запрещён.", 403)
            mid = positive(p.get("manager"), "Менеджер")
            ids = await self.manager_ids(cfg)
            fixed_ids = {int(value.strip()) for value in str(getattr(self.env, "MANAGER_IDS", "") or "").split(",") if value.strip().isdigit()}
            if mid in fixed_ids:
                raise WorkflowError("Права этого администратора закреплены в настройках бота.", 409)
            if mid not in ids:
                raise WorkflowError("Менеджер уже удалён.", 409)
            if len(ids) <= 1:
                raise WorkflowError("Нельзя удалить последнего менеджера.", 409)
            ids.remove(mid)
            names = await self.manager_names(cfg)
            names.pop(str(mid), None)
            await self.save_manager_ids(ids)
            await self.save_manager_names(names)
            return {"ok": True, "notice": "Менеджер удалён.", "access_revoked": mid == uid}
        event_id = positive(p.get("event"), "Мероприятие")
        if not self.events_visible(manager):
            raise WorkflowError("Доступ запрещён.", 403)
        if action == "toggle_event":
            if not manager or p.get("scope") != "staff":
                raise WorkflowError("Доступ запрещён.", 403)
            version = p.get("version")
            if type(version) is not int or version < 0:
                raise WorkflowError("Обновите мероприятие.", 409)
            result = await self.db_run("UPDATE events SET is_open=1-is_open,version=version+1 WHERE id=? AND version=?", event_id, version)
        elif action in ("delete_registration", "cancel_registration"):
            if action == "delete_registration" and (not manager or p.get("scope") != "staff"):
                raise WorkflowError("Доступ запрещён.", 403)
            rid = positive(p.get("registration"))
            result = await self.db_run("DELETE FROM event_registrations WHERE event_id=? AND id=? AND (?=1 OR telegram_id=?)", event_id, rid, int(action == "delete_registration" and manager), uid)
        else:
            raise WorkflowError("Неизвестное действие.")
        if not int(result.meta.changes or 0):
            raise WorkflowError("Данные уже изменились. Обновите экран.", 409)
        return {"ok": True, "event": event_id, "notice": "Изменения сохранены."}
