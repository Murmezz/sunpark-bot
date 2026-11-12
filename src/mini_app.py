"""Admin-only Mini App over the existing SUNPARK business rules and D1 data."""
import base64
import hashlib
import html
import json
import re
import time
import uuid
from urllib.parse import parse_qsl, urlparse

from menu_preview import preview_catalog, read_preview_body, validate_init_data
from mini_app_assets import APP_HTML, APP_CSS, APP_JS, APP_LOGO, APP_ICONS
from app_workflows import AppWorkflowsMixin, WorkflowError
from services import service_catalog

MINIAPP_ADMIN_ONLY = True
MAX_UPLOAD = 5 * 1024 * 1024


class AppError(WorkflowError):
    pass


def plain_row(row, keys):
    return {key: getattr(row, key, None) for key in keys}


def json_body(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class AppBridge:
    """Reuse bot handlers while collecting the acting user's screen responses.

    This object is request-local. Notifications to other participants still use
    the real bot. Virtual message IDs never replace real Telegram message IDs.
    """
    def __init__(self, bot, user):
        self.bot, self.user, self.uid = bot, user, int(user["id"])
        self.env = bot.env
        self.ctx = getattr(bot, "ctx", None)
        self.cards, self.toasts, self.counter = [], [], 0

    def __getattr__(self, name):
        method = getattr(type(self.bot), name, None)
        if callable(method):
            return method.__get__(self, type(self))
        return getattr(self.bot, name)

    def card(self, text, markup=None, attachment=None):
        self.counter += 1
        self.cards.append({"html": str(text), "keyboard": markup or {}, "attachment": attachment})
        return {"message_id": -self.counter}

    async def send(self, chat_id, text, markup=None):
        notification = any(str(b.get("callback_data", "")).startswith("claim:") for row in (markup or {}).get("inline_keyboard", []) for b in row)
        if int(chat_id) == self.uid and not notification:
            return self.card(text, markup)
        return await self.bot.send(chat_id, text, markup)

    async def edit(self, msg, text, markup=None):
        return self.card(text, markup)

    async def answer(self, callback_id, text="", alert=False):
        if text:
            self.toasts.append({"text": str(text), "alert": bool(alert)})

    async def tg(self, method, params):
        actor = int(params.get("chat_id", 0) or 0) == self.uid
        if actor and method == "sendContact":
            return self.card(str(params.get("phone_number", "")))
        if actor and method in ("sendPhoto", "sendDocument"):
            return self.card(params.get("caption", ""), params.get("reply_markup"))
        if actor and int(params.get("message_id", 0) or 0) < 0:
            if method == "editMessageText":
                return self.card(params.get("text", ""), params.get("reply_markup"))
            if method in ("editMessageReplyMarkup", "deleteMessage"):
                return True
        return await self.bot.tg(method, params)

    async def clear_history_messages(self, manager_id):
        # Telegram history messages belong to the Telegram UI, not this screen.
        return None

    async def remember_history_message(self, manager_id, ticket_number, result):
        return None

    async def send_ticket_attachments(self, chat_id, ticket_number):
        # The authenticated chat API supplies these without exposing bot tokens.
        return None


class MiniAppMixin(AppWorkflowsMixin):
    async def app_init(self):
        await self.db_run("CREATE TABLE IF NOT EXISTS miniapp_requests (user_id INTEGER NOT NULL, request_key TEXT NOT NULL, digest TEXT NOT NULL, response TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now')), PRIMARY KEY(user_id,request_key))")
        await self.db_run("CREATE TABLE IF NOT EXISTS miniapp_uploads (token TEXT PRIMARY KEY, user_id INTEGER NOT NULL, file_id TEXT NOT NULL, kind TEXT NOT NULL, file_name TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now')))")

    async def app_input(self, bridge, scope):
        uid = bridge.uid
        event = await self.db_first("SELECT * FROM event_sessions WHERE user_id=?", uid)
        if event:
            fields = self.event_fields(event)
            step = int(event.step)
            if 0 <= step < len(fields):
                name, prompt = fields[step]
                return {"field": name, "prompt": prompt, "step": step + 1, "total": len(fields), "kind": "event"}
        action = await self.get_action(uid)
        if scope == "staff" and action and not action.startswith("reply:"):
            return {"field": "text", "kind": "staff", "prompt": "Введите текст", "action": action}
        flow = await self.db_first("SELECT * FROM guest_flows WHERE user_id=?", uid)
        if flow and scope != "staff":
            fields = self.form_steps(str(flow.request_type))
            step = int(flow.step)
            if 0 <= step < len(fields):
                name, prompt = fields[step]
                return {"field": name, "prompt": prompt, "step": step + 1, "total": len(fields), "kind": str(flow.request_type)}
        if scope == "staff" and action.startswith("reply:"):
            return {"field": "message", "kind": "chat", "ticket": int(action.split(":", 1)[1])}
        return None

    async def app_ticket(self, uid, number, scope="guest"):
        if type(number) is not int or number <= 0:
            raise AppError("Заявка не найдена.", 404)
        row = await self.db_first("SELECT t.*,d.request_type,d.payload,u.username,u.first_name,u.last_name FROM tickets t LEFT JOIN ticket_details d ON d.ticket_number=t.number LEFT JOIN users u ON u.user_id=t.guest_id WHERE t.number=?", number)
        if not row or (scope != "staff" and int(row.guest_id) != uid):
            raise AppError("Заявка не найдена.", 404)
        return row

    async def app_chat(self, uid, number, scope, cfg=None, before=None):
        row = await self.app_ticket(uid, number, scope)
        data = plain_row(row, ("number", "guest_id", "manager_id", "status", "request_type", "username", "first_name", "last_name"))
        try:
            data["details"] = json.loads(str(row.payload or "{}"))
        except (ValueError, TypeError):
            data["details"] = {}
        can_reply = str(row.status) in ("waiting", "active", "waiting_guest")
        if scope == "staff":
            can_reply = can_reply and int(row.manager_id or 0) == uid and str(row.status) != "waiting"
            await self.mark_ticket_read(number, uid)
            note = await self.ticket_note(number)
            data["note"] = str(note.note) if note else ""
        data["can_reply"] = can_reply
        names = await self.manager_names(cfg if cfg is not None else (await self.config())[3])
        data["manager_name"] = names.get(str(row.manager_id), "Менеджер SUNPARK")
        data["guest_name"] = str(data["details"].get("name") or " ".join(str(getattr(row, key, "") or "") for key in ("first_name", "last_name")).strip() or "Гость")
        args = [number]
        clause = ""
        if before is not None:
            if type(before) is not int or before < 1:
                raise AppError("Не удалось загрузить историю.")
            clause = " AND id<?"
            args.append(before)
        result = await self.db_all(f"SELECT id,sender_id,sender_role,body,created_at FROM ticket_messages WHERE ticket_number=?{clause} ORDER BY id DESC LIMIT 101", *args)
        messages = []
        for item in reversed(list(result.results)[:100]):
            record = plain_row(item, ("id", "sender_id", "sender_role", "created_at"))
            record["text"] = str(item.body or "")
            if record["text"].startswith("ATTACH:"):
                try:
                    attachment = json.loads(record["text"][7:])
                    record["text"] = str(attachment.get("caption") or "")
                    record["attachment"] = {"kind": attachment.get("type"), "name": attachment.get("file_name", "Фото"), "message_id": int(item.id)}
                except (ValueError, TypeError):
                    record["text"] = "Вложение"
            messages.append(record)
        return {"ticket": data, "messages": messages, "has_more": len(result.results) > 100}

    async def app_send_chat(self, bridge, payload, cfg):
        uid, number = bridge.uid, payload.get("ticket")
        scope = payload.get("scope", "guest")
        row = await self.app_ticket(uid, number, scope)
        text = str(payload.get("text") or "").strip()
        if len(text) > 3500:
            raise AppError("Сообщение должно быть не длиннее 3500 символов.")
        if str(row.status) not in ("waiting", "active", "waiting_guest"):
            raise AppError("Заявка уже закрыта.", 409)
        attachment = None
        if payload.get("upload"):
            upload = await self.db_first("SELECT * FROM miniapp_uploads WHERE token=? AND user_id=? AND created_at>=datetime('now','-1 hour')", str(payload["upload"]), uid)
            if not upload:
                raise AppError("Загрузите вложение заново.")
            attachment = {"type": str(upload.kind), "file_id": str(upload.file_id), "file_name": str(upload.file_name)}
        if not text and not attachment:
            raise AppError("Введите сообщение или прикрепите фото/PDF.")
        role = "guest"
        if scope == "staff":
            if int(row.manager_id or 0) != uid or str(row.status) == "waiting":
                raise AppError("Сначала возьмите заявку в работу.", 409)
            role = "manager"
        condition = "manager_id=? AND status IN ('active','waiting_guest')" if role == "manager" else "guest_id=? AND status IN ('waiting','active','waiting_guest')"
        saved = await self.db_run(f"INSERT INTO ticket_messages(ticket_number,sender_id,sender_role,body) SELECT number,?,?,? FROM tickets WHERE number=? AND {condition}", uid, role, self.stored_message_body(text, attachment), number, uid)
        if not int(saved.meta.changes or 0):
            raise AppError("Заявка уже закрыта или передана. Обновите переписку.", 409)
        warning = ""
        if role == "manager":
            await self.db_run("UPDATE tickets SET status='waiting_guest' WHERE number=? AND status IN ('active','waiting_guest') AND manager_id=?", number, uid)
            try:
                await self.send_ticket_content(int(row.guest_id), "Новое сообщение менеджера:\n" + html.escape(text), attachment, await self.guest_persistent(int(row.guest_id)))
            except Exception as error:
                print("SUNPARK MINIAPP NOTIFICATION", type(error).__name__)
                warning = "Сообщение сохранено. Уведомление в Telegram не доставлено."
        else:
            await self.db_run("UPDATE tickets SET status='active' WHERE number=? AND status='waiting_guest'", number)
            targets = [int(row.manager_id)] if row.manager_id else sorted(await self.manager_ids(cfg))
            for mid in targets:
                markup = {"inline_keyboard": [[{"text": f"Открыть заявку #{number}", "callback_data": f"admin:open:{number}"}]]}
                try:
                    await self.send_ticket_content(mid, f"Новое сообщение по заявке #{number}:\n{html.escape(text)}", attachment, markup)
                except Exception as error:
                    print("SUNPARK MINIAPP NOTIFICATION", type(error).__name__)
                    warning = "Сообщение сохранено. Уведомление в Telegram не доставлено."
        result = await self.app_chat(uid, number, scope, cfg)
        if warning:
            result["warning"] = warning
        return result

    async def app_upload(self, uid, payload):
        encoded = payload.get("data")
        if not isinstance(encoded, str) or len(encoded) > MAX_UPLOAD * 4 // 3 + 8:
            raise AppError("Вложение должно быть не больше 5 МБ.")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError):
            raise AppError("Не удалось прочитать файл.")
        if not raw or len(raw) > MAX_UPLOAD:
            raise AppError("Вложение должно быть не больше 5 МБ.")
        signatures = [(b"%PDF-", "application/pdf", "document", "document.pdf"), (b"\xff\xd8\xff", "image/jpeg", "photo", "photo.jpg"), (b"\x89PNG\r\n\x1a\n", "image/png", "photo", "photo.png")]
        match = next((item for item in signatures if raw.startswith(item[0])), None)
        if not match:
            raise AppError("Можно прикрепить фото JPEG/PNG или PDF.")
        from workers import fetch
        from js import Blob, FormData, Object
        from pyodide.ffi import to_js
        _, mime, kind, safe_name = match
        form = FormData.new()
        form.append("chat_id", str(uid))
        form.append("disable_notification", "true")
        blob = Blob.new(to_js([raw]), to_js({"type": mime}, dict_converter=Object.fromEntries))
        form.append(kind, blob, safe_name)
        method = "sendPhoto" if kind == "photo" else "sendDocument"
        response = await fetch(f"https://api.telegram.org/bot{self.env.BOT_TOKEN}/{method}", method="POST", body=form)
        result = await response.json()
        if not result.get("ok"):
            raise AppError("Telegram не принял вложение. Попробуйте ещё раз.", 502)
        message = result["result"]
        file_id = message["photo"][-1]["file_id"] if kind == "photo" else message["document"]["file_id"]
        token = uuid.uuid4().hex
        name = str(payload.get("name") or safe_name).replace("\x00", "")[:150]
        await self.db_run("INSERT INTO miniapp_uploads(token,user_id,file_id,kind,file_name) VALUES(?,?,?,?,?)", token, uid, file_id, kind, name)
        try:
            await self.tg("deleteMessage", {"chat_id": uid, "message_id": message["message_id"]})
        except Exception:
            pass
        return {"token": token, "name": name, "kind": kind}

    async def app_media(self, uid, payload, headers):
        from workers import Response, fetch
        message_id = payload.get("message_id")
        if type(message_id) is not int:
            raise AppError("Вложение не найдено.", 404)
        message = await self.db_first("SELECT ticket_number,body FROM ticket_messages WHERE id=?", message_id)
        if not message:
            raise AppError("Вложение не найдено.", 404)
        await self.app_ticket(uid, int(message.ticket_number), payload.get("scope", "guest"))
        try:
            attachment = json.loads(str(message.body)[7:])
            file_id = str(attachment["file_id"])
        except (ValueError, KeyError, TypeError):
            raise AppError("Вложение не найдено.", 404)
        file = await self.tg("getFile", {"file_id": file_id})
        if int(file.get("file_size", 0)) > 20 * 1024 * 1024:
            raise AppError("Этот файл можно открыть в Telegram.", 413)
        path = file.get("file_path", "")
        if not path or ".." in path:
            raise AppError("Вложение не найдено.", 404)
        response = await fetch(f"https://api.telegram.org/file/bot{self.env.BOT_TOKEN}/{path}")
        if not response.ok:
            raise AppError("Не удалось загрузить вложение. Попробуйте ещё раз.", 502)
        media_headers = dict(headers)
        media_headers["content-type"] = "application/pdf" if attachment.get("type") == "document" else "image/jpeg"
        media_headers["content-disposition"] = "inline"
        return Response(response.body, headers=media_headers)

    async def app_dispatch(self, user, payload, menu, sections, info, cfg):
        bridge = AppBridge(self, user)
        uid, operation, scope = bridge.uid, payload.get("operation"), payload.get("scope", "guest")
        if scope not in ("guest", "staff"):
            raise AppError("Неизвестный режим.")
        if operation == "screen":
            return await self.workflow_screen(user, payload, info, cfg)
        if operation == "submit_form":
            return await self.workflow_submit(bridge, payload, cfg)
        if operation == "command":
            return await self.workflow_command(bridge, payload, cfg)
        if operation == "bootstrap":
            await self.db_run("INSERT INTO users(user_id,username,first_name,last_name,updated_at) VALUES(?,?,?,?,datetime('now')) ON CONFLICT(user_id) DO UPDATE SET username=excluded.username,first_name=excluded.first_name,last_name=excluded.last_name,updated_at=excluded.updated_at", uid, str(user.get("username") or ""), str(user.get("first_name") or ""), str(user.get("last_name") or ""))
            data = preview_catalog(menu, sections)
            manager = await self.is_manager(uid, cfg)
            data.update({"user": {key: user.get(key, "") for key in ("id", "first_name", "last_name", "username")}, "info": info, "admin": manager, "events_visible": self.events_visible(manager)})
            data["services"] = service_catalog()
            return data
        if operation == "tickets":
            clause, args = ("t.guest_id=?", [uid]) if scope == "guest" else ("t.status!='draft'", [])
            result = await self.db_all(f"SELECT t.number,t.status,t.guest_id,t.manager_id,d.request_type,d.payload,u.first_name,u.last_name,u.username,(SELECT body FROM ticket_messages m WHERE m.ticket_number=t.number ORDER BY id DESC LIMIT 1) last_body FROM tickets t LEFT JOIN ticket_details d ON d.ticket_number=t.number LEFT JOIN users u ON u.user_id=t.guest_id WHERE {clause} ORDER BY t.number DESC LIMIT 100", *args)
            rows = []
            for row in result.results:
                data = plain_row(row, ("number", "status", "guest_id", "manager_id", "request_type", "first_name", "last_name", "username"))
                data["preview"] = self.ticket_preview(row.last_body)
                rows.append(data)
            return {"tickets": rows}
        if operation == "chat":
            return await self.app_chat(uid, payload.get("ticket"), scope, cfg, payload.get("before"))
        if operation == "chat_send":
            return await self.app_send_chat(bridge, payload, cfg)
        if operation == "upload":
            return await self.app_upload(uid, payload)
        if operation == "action":
            data = payload.get("callback")
            if not isinstance(data, str) or len(data) > 120 or not (data in ("back", "faq", "info", "noop") or data.startswith(("booking:", "banquet:", "form:", "faq:", "ev:", "admin:", "claim:", "take:", "close:", "phone:", "template:"))):
                raise AppError("Неизвестное действие.")
            if data in ("booking:start", "banquet:request"):
                await self.clear_action(uid)
                await self.event_clear_session(uid)
            cb = {"id": "miniapp", "data": data, "from": user, "message": {"message_id": -1, "chat": {"id": uid, "type": "private"}}}
            await bridge.callback(cb, menu, sections, info, cfg)
        elif operation == "message":
            text = payload.get("text")
            if not isinstance(text, str) or not text.strip() or len(text) > 3500:
                raise AppError("Введите текст длиной от 1 до 3500 символов.")
            await bridge.message({"text": text.strip(), "from": user, "chat": {"id": uid, "type": "private"}}, menu, sections, info, cfg)
        else:
            raise AppError("Неизвестное действие.")
        input_context = await self.app_input(bridge, scope)
        if operation == "action" and input_context:
            if input_context["kind"] in ("booking", "banquet") and data not in ("booking:start", "banquet:request"):
                input_context = None
            elif input_context["kind"] == "event" and not data.startswith("ev:"):
                input_context = None
        return {"cards": bridge.cards[-15:], "toasts": bridge.toasts[-5:], "input": input_context}

    async def mini_app_http(self, request):
        from workers import Response
        parsed = urlparse(str(request.url))
        path = parsed.path.rstrip("/")
        if path != "/app" and not path.startswith(("/app/", "/api/app")):
            return None
        headers = {"cache-control": "no-store", "x-content-type-options": "nosniff", "referrer-policy": "no-referrer"}
        def respond(data, status=200):
            return Response(json_body(data), status=status, headers={**headers, "content-type": "application/json; charset=utf-8"})
        if not path.startswith("/api/app"):
            if str(request.method) != "GET":
                return respond({"error": "Method not allowed"}, 405)
            assets = {"/app": (APP_HTML, "text/html; charset=utf-8"), "/app/style.css": (APP_CSS, "text/css; charset=utf-8"), "/app/app.js": (APP_JS, "application/javascript; charset=utf-8"), "/app/logo.svg": (APP_LOGO, "image/svg+xml; charset=utf-8")}
            if path.startswith("/app/icons/"):
                name = path.rsplit("/", 1)[-1].removesuffix(".svg")
                if name in APP_ICONS:
                    assets[path] = (APP_ICONS[name], "image/svg+xml; charset=utf-8")
            asset = assets.get(path)
            if not asset:
                return respond({"error": "Not found"}, 404)
            headers["content-type"] = asset[1]
            headers["content-security-policy"] = "default-src 'self'; script-src 'self' https://telegram.org; style-src 'self'; font-src 'self' data:; img-src 'self' data: blob: https://sunparkspb.ru; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors https://web.telegram.org https://webk.telegram.org https://webz.telegram.org"
            return Response(asset[0], headers=headers)
        if str(request.method) != "POST":
            return respond({"error": "Откройте приложение в Telegram."}, 405)
        if path not in ("/api/app", "/api/app/media"):
            return respond({"error": "Not found"}, 404)
        try:
            raw = await read_preview_body(request, limit=8 * 1024 * 1024)
            payload = json.loads(raw)
            uid = validate_init_data(payload.get("init_data"), self.env.BOT_TOKEN)
            user = json.loads(dict(parse_qsl(payload["init_data"]))["user"])
            if user.get("id") != uid:
                raise ValueError()
        except (ValueError, TypeError, KeyError, AttributeError):
            return respond({"error": "Откройте приложение заново через бота."}, 401)
        try:
            menu, sections, info, cfg = await self.config()
            manager = await self.is_manager(uid, cfg)
            if MINIAPP_ADMIN_ONLY and not manager:
                return respond({"error": "Приложение пока доступно только администраторам."}, 403)
            if payload.get("scope") == "staff" and not manager:
                return respond({"error": "Доступ запрещён."}, 403)
            if path == "/api/app/media":
                return await self.app_media(uid, payload, headers)
            operation = payload.get("operation")
            if operation in ("bootstrap", "tickets", "chat", "screen"):
                return respond(await self.app_dispatch(user, payload, menu, sections, info, cfg))
            if len(raw) > 24000 and operation != "upload":
                raise AppError("Слишком большой запрос.", 413)
            key = payload.get("request_key", "")
            if not isinstance(key, str) or not re.fullmatch(r"[a-zA-Z0-9-]{16,64}", key):
                raise AppError("Не удалось определить запрос. Повторите действие.")
            await self.app_init()
            digest = hashlib.sha256(json_body({key: value for key, value in payload.items() if key != "init_data"}).encode()).hexdigest()
            claimed = await self.db_run("INSERT INTO miniapp_requests(user_id,request_key,digest) VALUES(?,?,?) ON CONFLICT(user_id,request_key) DO NOTHING", uid, key, digest)
            if not int(claimed.meta.changes or 0):
                previous = await self.db_first("SELECT digest,response FROM miniapp_requests WHERE user_id=? AND request_key=?", uid, key)
                if str(previous.digest) != digest:
                    raise AppError("Этот запрос уже использован для другого действия.", 409)
                if previous.response:
                    cached = json.loads(str(previous.response))
                    return respond(cached["data"], cached["status"])
                raise AppError("Действие уже выполняется. Обновите экран через несколько секунд.", 409)
            try:
                result = await self.app_dispatch(user, payload, menu, sections, info, cfg)
                status = 200
            except WorkflowError as error:
                result, status = {"error": str(error), "fields": error.fields}, error.status
            await self.db_run("UPDATE miniapp_requests SET response=? WHERE user_id=? AND request_key=?", json_body({"data": result, "status": status}), uid, key)
            return respond(result, status)
        except WorkflowError as error:
            return respond({"error": str(error), "fields": error.fields}, error.status)
        except Exception as error:
            print("SUNPARK MINIAPP API ERROR", type(error).__name__)
            return respond({"error": "Не удалось выполнить действие. Обновите экран."}, 500)
