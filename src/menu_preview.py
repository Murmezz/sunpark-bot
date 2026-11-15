"""Admin-only menu experiments; restaurant data stays in config.menu."""
import hashlib
import hmac
import html
import json
import re
import time
from urllib.parse import parse_qsl, urlparse

from menu_preview_assets import PREVIEW_HTML, PREVIEW_CSS, PREVIEW_JS, PREVIEW_LOGO

PREVIEW_ORIGIN = "https://sunparkbot.lovison1979.workers.dev"
VARIANTS = {
    1: ("Навигатор", "Короткие списки и кнопки с ценами"),
    2: ("Меню на листе", "Таблица с кнопками прямо в тексте"),
    3: ("Раскрывающийся состав", "Название и цена; состав по нажатию"),
    4: ("Фирменный SUNPARK", "Mini App · оформление печатного меню"),
    5: ("Вечерний SUNPARK", "Mini App · тёмный стиль кухни и бара"),
}


def esc(value):
    return html.escape(str(value or ""), quote=True)


def button(label, data):
    return {"text": label, "callback_data": data}


def keyboard(rows):
    return {"inline_keyboard": rows}


def preview_price_options(name, description, price, footer=""):
    """Exact prices in kopecks; an unpriced item never becomes a zero-price item."""
    parts = [part.strip() for part in str(price).split("/")]
    amounts = []
    for part in parts:
        match = re.fullmatch(r"\s*(\d[\d\s\u00a0\u202f]*(?:[,.]\d{1,2})?)\s*(?:₽|руб\.?|р\.?)?\s*", part, re.I)
        if not match:
            return [{"id": "0", "label": "", "price": str(price), "amount": None}]
        value = re.sub(r"\s", "", match.group(1)).replace(",", ".")
        rubles, _, fraction = value.partition(".")
        amount = int(rubles) * 100 + int((fraction + "00")[:2])
        if amount > 100_000_000:
            return [{"id": "0", "label": "", "price": str(price), "amount": None}]
        amounts.append(amount)
    labels = [""] if len(parts) == 1 else []
    lower_name = re.sub(r"[\s-]+", " ", str(name).casefold())
    if len(parts) == 2:
        if "капульк" in lower_name:
            labels = ["Алкогольное", "Безалкогольное"]
        elif "бенедикт" in lower_name:
            labels = ["С форелью", "С ростбифом"]
        elif "бокал" in footer.casefold() and "бутыл" in footer.casefold():
            labels = ["Бокал", "Бутылка"]
        else:
            pair = re.search(r"(\d+(?:[,.]\d+)?)\s*(мл|л|кг|гр|г)?\s*/\s*(\d+(?:[,.]\d+)?)\s*(мл|л|кг|гр|г)\b", description, re.I)
            measures = [(pair[1], pair[2] or pair[4]), (pair[3], pair[4])] if pair else re.findall(r"(\d+(?:[,.]\d+)?)\s*(мл|л|кг|гр|г)\b", description, re.I)
            if len(measures) == 2:
                labels = [f"{value.replace('.', ',')} {'г' if unit.casefold() == 'гр' else unit.casefold()}" for value, unit in measures]
    if len(labels) != len(parts):
        labels = [f"Вариант {i + 1}" for i in range(len(parts))]
    return [{"id": str(i), "label": label, "price": part, "amount": amount} for i, (label, part, amount) in enumerate(zip(labels, parts, amounts))]


def preview_catalog(menu, sections):
    groups, categories, seen = [], [], set()
    for group_title, keys in sections:
        group_keys = []
        for key in keys:
            cat = menu.get(key)
            if not cat or key == "banquet" or key in seen:
                continue
            seen.add(key)
            entries = []
            if cat.get("sections"):
                for subtitle, items in cat["sections"]:
                    for row in items:
                        entries.append({"name": str(row[0]), "description": str(row[1] or ""), "price": str(row[2]), "section": str(subtitle)})
            else:
                for row in cat.get("items", []):
                    entries.append({"name": str(row[0]), "description": str(row[1] or ""), "price": str(row[2]), "section": ""})
            for item in entries:
                identity = [key, item["section"], item["name"], item["description"]]
                item["id"] = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()[:24]
                item["options"] = preview_price_options(item["name"], item["description"], item["price"], str(cat.get("footer") or ""))
                item["cart_name"] = re.sub(r"\s*/\s*безалкогольн\w*", "", item["name"], flags=re.I).strip() if "капульк" in item["name"].casefold() else item["name"]
            categories.append({"key": key, "title": str(cat.get("title", key)), "emoji": str(cat.get("emoji", "")), "footer": str(cat.get("footer") or ""), "items": entries})
            group_keys.append(key)
        if group_keys:
            groups.append({"title": str(group_title), "keys": group_keys})
    return {"groups": groups, "categories": categories}


def validate_init_data(raw, token, now=None):
    """Verify Telegram HMAC before trusting user ID; never accept query user IDs."""
    if not isinstance(raw, str) or not raw or len(raw) > 16384:
        raise ValueError("Откройте меню кнопкой в Telegram.")
    pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=True)
    fields = dict(pairs)
    if len(fields) != len(pairs):
        raise ValueError("Некорректные данные авторизации.")
    supplied = fields.pop("hash", "")
    if len(supplied) != 64:
        raise ValueError("Некорректная подпись Telegram.")
    check = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", str(token).encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, supplied):
        raise ValueError("Некорректная подпись Telegram.")
    age = int(time.time() if now is None else now) - int(fields.get("auth_date", "0"))
    if age < -30 or age > 3600:
        raise ValueError("Сессия истекла. Откройте меню заново из бота.")
    user = json.loads(fields.get("user", "{}"))
    uid = user.get("id")
    if type(uid) is not int or uid <= 0:
        raise ValueError("Не удалось определить пользователя Telegram.")
    return uid


async def read_preview_body(request, limit=20000):
    length = request.headers.get("content-length")
    if length is not None and (not str(length).isdigit() or int(length) > limit):
        raise ValueError("Invalid body size")
    if not request.body:
        raise ValueError("Missing body")
    reader = request.body.getReader()
    chunks, size = [], 0
    try:
        while True:
            part = await reader.read()
            if part.done:
                break
            size += int(part.value.byteLength)
            if size > limit:
                await reader.cancel()
                raise ValueError("Body too large")
            chunks.append(bytes(part.value.to_py()))
    finally:
        reader.releaseLock()
    return b"".join(chunks).decode("utf-8")


class MenuPreviewMixin:
    def menu_preview_chooser(self):
        rows = [
            [{"text": "Sunpark", "web_app": {"url": f"{PREVIEW_ORIGIN}/app"}}],
            [{"text": "Sunpark · прежняя версия", "web_app": {"url": f"{PREVIEW_ORIGIN}/app/legacy"}}],
            [button("◀️ В админ-панель", "admin:panel")],
        ]
        text = "🛠 <b>Разработка</b>\n\nSUNPARK: меню и корзина, бронирование, мероприятия, сообщения и админ-панель. Тема меняется автоматически.\n\nДоступ только администраторам."
        return text, keyboard(rows)

    def menu_preview_root(self, variant, catalog):
        rows, lines = [], [f"🌿 <b>SUNPARK · {esc(VARIANTS[variant][0])}</b>", "<i>Кухня, напитки и бар</i>\n"]
        for group in catalog["groups"]:
            lines.append(f"<b>{esc(group['title'])}</b> · {len(group['keys'])} разделов")
            group_cats = [c for c in catalog["categories"] if c["key"] in group["keys"]]
            for i in range(0, len(group_cats), 2):
                rows.append([button(f"{c['emoji']} {c['title']}", f"mp:cat:{variant}:{c['key']}:0") for c in group_cats[i:i+2]])
        rows.append([button("↔️ Пять вариантов", "mp:home")])
        lines.append("\nВыберите раздел меню.")
        return "\n".join(lines), keyboard(rows)

    def menu_preview_category(self, variant, category, page=0, selected=None):
        size = 6 if variant == 1 else 10
        total = len(category["items"])
        page = max(0, min(int(page), max(0, (total-1)//size)))
        key, start = category["key"], page*size
        part = category["items"][start:start+size]
        title = f"{category['emoji']} {category['title']}"
        plain = [f"<b>{esc(title)}</b>", "<i>Нажмите на блюдо — откроется состав.</i>\n"]
        rich = [f"<h2>{esc(title)}</h2>"]
        rows = []
        if variant == 2:
            rich.append('<table compact><tr><th>Блюдо</th><th>Цена</th></tr>')
        for i, item in enumerate(part, start):
            data = f"mp:item:{variant}:{key}:{i}:{page}"
            if variant != 1:
                plain.append(f"<b>{i+1}. {esc(item['name'])}</b> — {esc(item['price'])}")
            if variant == 1:
                rows.append([button(f"{item['name']} · {item['price']}", data)])
            elif variant == 2:
                rich.append(f'<tr><td><tg-button type="callback_data" style="link" data="{esc(data)}">{esc(item["name"])}</tg-button></td><td>{esc(item["price"])}</td></tr>')
            else:
                desc = esc(item["description"] or "Состав не указан в меню.").replace("\n", "<br>")
                section = ("<p>" + esc(item["section"]) + "</p>") if item["section"] else ""
                rich.append(f'<details><summary>{esc(item["name"])} — {esc(item["price"])}</summary>{section}<p>{desc}</p></details>')
        if variant == 2:
            rich.append("</table>")
        if variant != 1:
            # These small numeric buttons also make the compatible fallback usable.
            for j in range(0, len(part), 5):
                rows.append([button(str(start+i+1), f"mp:item:{variant}:{key}:{start+i}:{page}") for i in range(j, min(j+5,len(part)))])
        if selected is not None and 0 <= selected < total:
            item = category["items"][selected]
            desc = item["description"] or "Состав не указан в меню."
            detail = f"\n<b>{esc(item['name'])}</b>\n{esc(item['section']) + chr(10) if item['section'] else ''}{esc(desc)}\n<b>{esc(item['price'])}</b>"
            plain.append(detail)
            rich.append(f"<hr><h3>{esc(item['name'])}</h3><p>{esc(desc).replace(chr(10), '<br>')}</p><p><b>{esc(item['price'])}</b></p>")
            rows.append([button("Свернуть состав", f"mp:cat:{variant}:{key}:{page}")])
        if category["footer"]:
            plain.append("\n"+esc(category["footer"]))
            rich.append(f"<footer>{esc(category['footer'])}</footer>")
        if not part:
            plain.append("В этом разделе пока нет блюд.")
            rich.append("<p>В этом разделе пока нет блюд.</p>")
        nav = []
        if page:
            nav.append(button("◀️", f"mp:cat:{variant}:{key}:{page-1}"))
        nav.append(button(f"{page+1} / {max(1,(total+size-1)//size)}", "mp:noop"))
        if start+size < total:
            nav.append(button("▶️", f"mp:cat:{variant}:{key}:{page+1}"))
        rows += [nav, [button("Разделы", f"mp:root:{variant}"), button("5 вариантов", "mp:home")]]
        return "\n".join(plain), "".join(rich) if variant in (2,3) else None, keyboard(rows)

    async def menu_preview_render(self, msg, plain, markup, rich=None):
        if rich:
            rich_markup = keyboard([row for row in markup["inline_keyboard"] if not all(str(b.get("text", "")).isdecimal() for b in row)])
            params = {"chat_id": msg["chat"]["id"], "message_id": msg["message_id"], "rich_message": {"html": rich}, "reply_markup": rich_markup}
            try:
                await self.tg("editMessageText", params)
                return
            except Exception as e:
                reason = str(e).lower()
                if "not modified" in reason:
                    return
                # Network/rate-limit failures must not cause a burst of retries.
                if not any(x in reason for x in ("bad request", "not found", "unsupported", "rich_message", "can't parse", "cannot parse")):
                    raise
                plain += "\n\n<i>Показан совместимый вид с кнопками ниже.</i>"
        await self.edit(msg, plain, markup)

    async def menu_preview_callback(self, cb, menu, sections, cfg):
        data = str(cb.get("data") or "")
        if not data.startswith("mp:"):
            return False
        uid = int((cb.get("from") or {})["id"])
        msg = cb.get("message") or {}
        if not await self.is_manager(uid, cfg) or msg.get("chat", {}).get("type") != "private" or msg.get("chat", {}).get("id") != uid:
            await self.answer(cb.get("id"), "Разработка доступна только администраторам.", True)
            return True
        await self.answer(cb.get("id"))
        if data == "mp:noop":
            return True
        # Old preview buttons also lead to the single current menu.
        text, markup = self.menu_preview_chooser()
        await self.menu_preview_render(msg, text, markup)
        return True

    async def menu_preview_http(self, request):
        from workers import Response
        parsed = urlparse(str(request.url))
        path = parsed.path.rstrip("/")
        if path not in ("/menu-preview", "/menu-preview.css", "/menu-preview.js", "/menu-preview-logo.svg", "/api/menu-preview"):
            return None
        method = str(request.method)
        headers = {"cache-control": "no-store", "x-content-type-options": "nosniff", "referrer-policy": "no-referrer"}
        if path != "/api/menu-preview":
            if method != "GET":
                return Response("Method not allowed", status=405, headers=headers)
            assets = {"/menu-preview": (PREVIEW_HTML, "text/html; charset=utf-8"), "/menu-preview.css": (PREVIEW_CSS, "text/css; charset=utf-8"), "/menu-preview.js": (PREVIEW_JS, "application/javascript; charset=utf-8"), "/menu-preview-logo.svg": (PREVIEW_LOGO, "image/svg+xml; charset=utf-8")}
            body, mime = assets[path]
            headers["content-type"] = mime
            headers["content-security-policy"] = "default-src 'self'; script-src 'self' https://telegram.org; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors https://web.telegram.org https://webk.telegram.org https://webz.telegram.org"
            return Response(body, headers=headers)
        headers["content-type"] = "application/json; charset=utf-8"
        def error(message, status):
            return Response(json.dumps({"error": message}, ensure_ascii=False), status=status, headers=headers)
        if method != "POST":
            return error("Откройте меню из Telegram.", 405)
        try:
            raw = await read_preview_body(request)
            payload = json.loads(raw)
            uid = validate_init_data(payload.get("init_data"), self.env.BOT_TOKEN)
        except (ValueError, TypeError, AttributeError):
            return error("Откройте меню заново через кнопку бота в Telegram.", 401)
        menu, sections, _, cfg = await self.config()
        if not await self.is_manager(uid, cfg):
            return error("Разработка доступна только администраторам.", 403)
        # Return menu only: no config secrets, profiles or event registrations.
        return Response(json.dumps(preview_catalog(menu, sections), ensure_ascii=False), headers=headers)


