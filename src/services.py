"""Public SUNPARK service content, checked against sunparkspb.ru on 2026-11-12.

Amounts are in roubles, unlike the restaurant menu's kopeck amounts.
Keep the seasonal price label: wakeprice is explicitly the summer 2026 tariff.
"""
import html

CHECKED_AT = "2026-11-12"
CONTACTS_URL = "https://sunparkspb.ru/contacts/"
ADDRESS = "Санкт-Петербург, ул. Никольская, 9 · м. Озерки"
WAKE_PRICE_IMAGE = "https://sunparkspb.ru/wp-content/uploads/2026/05/wake_price_26.jpg"


def price(label, amount, unit="", note=""):
    return {"label": label, "amount": amount, "unit": unit, "note": note}


SERVICES = [
    {
        "id": "wake", "title": "Вейк", "subtitle": "На доске по озеру",
        "description": "Кольцевая лебёдка Rixen и реверсивная лебёдка для обучения. Можно заниматься с тренером и взять снаряжение в прокат.",
        "price_label": "Прайс на лето 2026", "teaser": "Кольцо · от 1 900 ₽ / час",
        "notice": "Катание сезонное. На сайте опубликован прайс на лето 2026. Даты открытия и актуальные тарифы уточните перед поездкой.",
        "phone": "+79817549368", "phone_label": "+7 (981) 754-93-68",
        "hours": "Летний график: пн 15:00–23:00, вт–пт 12:00–23:00, сб–вс и праздники 11:00–23:00. Время зависит от светового дня.",
        "url": "https://sunparkspb.ru/portfolio/wakepark/", "prices_url": "https://sunparkspb.ru/wakeprice/",
        "booking_url": "https://w895407.yclients.com/", "booking_label": "Запись на вейк",
        "photos": ["https://sunparkspb.ru/wp-content/uploads/2018/11/wake1.jpg", "https://sunparkspb.ru/wp-content/uploads/2018/11/wake2.jpg", "https://sunparkspb.ru/wp-content/uploads/2018/11/wake3.jpg"],
        "groups": [
            {"title": "Кольцевая лебёдка · будни", "rows": [price("1 час",1900),price("2 часа",3100),price("День",4300)]},
            {"title": "Кольцевая лебёдка · выходные и праздники", "rows": [price("1 час",2300),price("2 часа",3700),price("День",5100)]},
            {"title": "Реверсивная лебёдка", "note": "Сет — 10 минут, вводный инструктаж включён. Прокат оплачивается отдельно.", "rows": [price("Сет в будни",1000),price("Сет в выходные и праздники",1100),price("Комплект снаряжения",500,"/ 10 мин", "Вейкборд или вейкскейт, жилет и шлем"),price("Гидрокостюм",500,"/ 30 мин")]},
            {"title": "Прокат на кольце", "note": "Цены за 1 час / 2 часа / день.", "rows": [price("Вейкборд или вейкскейт",600,"/ час", "2 часа — 1 200 ₽; день — 2 400 ₽"),price("Спасательный жилет",150,"/ час", "2 часа — 300 ₽; день — 600 ₽"),price("Шлем",150,"/ час", "2 часа — 300 ₽; день — 600 ₽"),price("Гидрокостюм",600,"/ час", "2 часа — 1 200 ₽; день — 2 400 ₽")]},
            {"title": "Тренировки", "note": "Катание оплачивается отдельно, кроме пакета Beginner.", "rows": [price("Индивидуальное занятие",2800),price("Beginner · начинающим",4200,"", "10 минут теории, 2 сета на реверсе с тренером и прокат оборудования"),price("Занятие в группе до 6 человек",2100),price("Rough rider · 3 тренировки на кольце",7500),price("Pro rider · 5 тренировок на кольце",12000),price("God of wake · 10 тренировок на кольце",22000)]},
            {"title": "Безлимитные абонементы на кольцо", "rows": [price("5 дней из 7",14000),price("30 последовательных дней",29000),price("90 последовательных дней",64000),price("Сезон · 1 мая — 27 сентября",89500)]},
        ],
    },
    {
        "id": "wave", "title": "Волна", "subtitle": "Сёрфинг круглый год",
        "description": "Искусственная волна в помещении. Подойдёт и для первого знакомства с доской: вводный инструктаж и аренда бодиборда или флоуборда входят в стоимость.",
        "price_label": "Цены на сайте SUNPARK", "teaser": "В группе · 2 200 ₽ / человек",
        "notice": "Приходите не менее чем за 30 минут. Возьмите купальник или плавки и полотенце. При недоборе группы сокращается продолжительность, цена за человека остаётся той же.",
        "phone": "+79119262650", "phone_label": "+7 (911) 926-26-50",
        "hours": "Пн–пт 12:00–23:00, сб–вс и праздники 11:00–23:00.",
        "url": "https://sunparkspb.ru/portfolio/surf/", "prices_url": "https://sunparkspb.ru/surfprice/",
        "booking_url": "https://w895504.yclients.com/", "booking_label": "Запись на волну",
        "photos": ["https://sunparkspb.ru/wp-content/uploads/2018/11/Wave9.jpg", "https://sunparkspb.ru/wp-content/uploads/2018/11/Wave8.jpg", "https://sunparkspb.ru/wp-content/uploads/2018/11/Wave7.jpg"],
        "groups": [
            {"title": "Катание", "rows": [price("Группа 3–4 человека · 30 минут",2200,"/ человек"),price("Группа 5–8 человек · 60 минут",2200,"/ человек"),price("Индивидуально · 15 минут",2650,"", "Для 1 человека"),price("Индивидуально · 30 минут",5300,"", "Для 1–2 человек"),price("Начинающий сёрфер · 30 минут",6900,"", "Для 1–2 человек, тренер и оборудование включены"),price("Аренда волны · 1 час",21500,"/ группа", "До 20 человек, работа двух инструкторов включена")]},
            {"title": "Дополнительно с тренером", "rows": [price("15 минут · 1 человек",800),price("30 минут · 1–2 человека",1600),price("45 минут · 1–3 человека",2400),price("60 минут · 1–4 человека",3200),price("60 минут · 5–8 человек",650,"/ человек")]},
            {"title": "Абонемент", "rows": [price("10 сетов индивидуального катания",23200,"", "Именной, действует 1 год")]},
        ],
    },
    {
        "id": "hotel", "title": "Отель", "subtitle": "Проснуться у озера",
        "description": "SUNPARK HOTEL — 19 номеров на берегу Среднего Суздальского озера, в 15 минутах пешком от метро Озерки. Завтрак включён в опубликованные тарифы.",
        "price_label": "За номер в сутки · с завтраком", "teaser": "С завтраком · от 5 000 ₽ / сутки",
        "notice": "Стоимость и наличие номера на нужные даты проверьте при бронировании.",
        "phone": "+79119262650", "phone_label": "+7 (911) 926-26-50",
        "additional_phone": "+78129262650", "additional_phone_label": "+7 (812) 926-26-50",
        "phone_note": "Основной телефон — со страницы «Контакты». На странице отеля также указан городской номер.",
        "hours": "Время заезда и выезда уточните при бронировании.",
        "url": "https://sunparkspb.ru/portfolio/hotel/", "prices_url": "https://sunparkspb.ru/portfolio/hotel/",
        "booking_url": "https://booking-online.agast.ru/?hms_system_id=8736/", "booking_label": "Бронирование номера",
        "photos": ["https://sunparkspb.ru/wp-content/uploads/2018/11/hotel9.jpg", "https://sunparkspb.ru/wp-content/uploads/2018/10/IMG_9325.png", "https://sunparkspb.ru/wp-content/uploads/2018/10/IMG_9324.png"],
        "groups": [{"title": "Номера с завтраком", "rows": [price("Стандарт двухместный",5000,"/ сутки"),price("Улучшенный двухместный",6000,"/ сутки"),price("Стандарт трёхместный",7000,"/ сутки"),price("Люкс с видом на озеро",15000,"/ сутки")]}],
    },
]


def service_catalog():
    return {"checked_at": CHECKED_AT, "address": ADDRESS, "contacts_url": CONTACTS_URL, "items": SERVICES}


def roubles(amount):
    return f"{amount:,}".replace(",", " ") + " ₽"


def service_text(service, full=False):
    esc = html.escape
    lines = [f"<b>{esc(service['title'])} · SUNPARK</b>", esc(service["description"]), ""]
    groups = service["groups"] if full else service["groups"][:2 if service["id"] == "wake" else 1]
    lines.append(f"<b>{esc(service['price_label'])}</b>")
    for group in groups:
        lines.append(f"\n<b>{esc(group['title'])}</b>")
        for row in group["rows"]:
            lines.append(f"{esc(row['label'])} — {roubles(row['amount'])} {esc(row['unit'])}".rstrip())
            if row["note"]:
                lines.append(esc(row["note"]))
        if group.get("note"):
            lines.append(esc(group["note"]))
    lines.extend(["", esc(service["notice"]), "", f"Телефон: <b>{service['phone_label']}</b>"])
    if service.get("additional_phone"):
        lines.extend([f"Городской: <b>{service['additional_phone_label']}</b>", esc(service["phone_note"])])
    lines.extend([esc(service["hours"]), esc(ADDRESS), f'\n<a href="{service["prices_url"]}">Цены на сайте SUNPARK</a> · проверено 12.11.2026'])
    return "\n".join(lines)


class ServicesMixin:
    async def service_callback(self, cb):
        data = cb.get("data", "")
        if not data.startswith("service:"):
            return False
        msg = cb.get("message")
        if not msg:
            await self.answer(cb.get("id"))
            return True
        parts = data.split(":")
        service = next((s for s in SERVICES if len(parts) > 1 and s["id"] == parts[1]), None)
        if not service:
            await self.answer(cb.get("id"), "Раздел не найден.")
            return True
        await self.answer(cb.get("id"))
        if len(parts) == 4 and parts[2] == "photo":
            try:
                index = int(parts[3])
            except ValueError:
                return True
            if not 0 <= index < len(service["photos"]):
                return True
            caption = f"{service['title']} · SUNPARK\nФото {index + 1} из {len(service['photos'])}\n{ADDRESS}"
            controls = []
            if index:
                controls.append({"text": "Предыдущее фото", "callback_data": f"service:{service['id']}:photo:{index-1}"})
            if index + 1 < len(service["photos"]):
                controls.append({"text": "Следующее фото", "callback_data": f"service:{service['id']}:photo:{index+1}"})
            keyboard = {"inline_keyboard": [controls, [{"text": "К описанию и ценам", "callback_data": f"service:{service['id']}"}]]}
            params = {"chat_id": msg["chat"]["id"], "reply_markup": keyboard}
            try:
                if msg.get("photo"):
                    await self.tg("editMessageMedia", {**params, "message_id": msg["message_id"], "media": {"type": "photo", "media": service["photos"][index], "caption": caption}})
                else:
                    await self.tg("sendPhoto", {**params, "photo": service["photos"][index], "caption": caption})
            except Exception as error:
                if "not modified" not in str(error).lower():
                    await self.send(msg["chat"]["id"], f"Фото временно не загрузилось. Посмотреть фотографии можно на сайте: {service['url']}")
            return True
        full = len(parts) == 3 and parts[2] == "prices"
        if len(parts) != 2 and not full:
            return True
        key = service["id"]
        rows = [[{"text": "Фотографии", "callback_data": f"service:{key}:photo:0"}]]
        if not full and len(service["groups"]) > (2 if key == "wake" else 1):
            rows.append([{"text": "Все тарифы и прокат", "callback_data": f"service:{key}:prices"}])
        rows.extend([[{"text": service["booking_label"], "url": service["booking_url"]}], [{"text": "На главную", "callback_data": "back"}]])
        await self.edit(msg, service_text(service, full), {"inline_keyboard": rows})
        return True
