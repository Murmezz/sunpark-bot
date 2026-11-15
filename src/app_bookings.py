"""Paid Mini App bookings, published inventory and restaurant seating.

All writes use the v2 namespace. Holds are inserted by a guarded statement;
the browser never chooses a price, payment state, QR signature or staff role.
"""
import hashlib
import hmac
import json
import re
import time
import uuid
from datetime import datetime, timedelta

from app_workflows import WorkflowError, object_json
from events import MSK, russian_phone
from menu_preview import preview_catalog

ORDER_KEYS = ('id', 'user_id', 'kind', 'service', 'slot_id', 'resource_id', 'starts_at', 'ends_at', 'units', 'guests', 'name', 'phone', 'amount', 'currency', 'status', 'hold_until', 'created_at', 'updated_at', 'data', 'addons', 'invoice_url')
RATE_KEYS = ('id', 'service', 'title', 'amount', 'unit', 'duration', 'max_guests', 'included', 'active')
RESOURCE_KEYS = ('id', 'service', 'name', 'kind', 'rate_id', 'capacity', 'active')
SLOT_KEYS = ('id', 'service', 'rate_id', 'resource_id', 'resources', 'starts_at', 'ends_at', 'capacity', 'active', 'title', 'amount', 'unit', 'duration', 'max_guests', 'included', 'remaining')


def data_row(row, keys):
    return {key: getattr(row, key, None) for key in keys}


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def integer(value, label, minimum=1, maximum=100000):
    if type(value) is not int or not minimum <= value <= maximum:
        readable = {'guests': 'Гости', 'amount': 'Цена', 'quantity': 'Количество', 'capacity': 'Вместимость', 'seats': 'Места', 'duration': 'Длительность', 'max_guests': 'Число гостей', 'user_id': 'Telegram ID', 'waiter_id': 'Официант'}.get(label, label)
        raise WorkflowError('Проверьте поле «' + readable + '».', fields={label: 'Укажите допустимое целое число.'})
    return value


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', value):
        raise WorkflowError('Не удалось определить запись. Обновите экран.', 400)
    return value


def date_value(value, with_time=False):
    try:
        return datetime.strptime(str(value), '%Y-%m-%dT%H:%M' if with_time else '%Y-%m-%d').replace(tzinfo=MSK)
    except (ValueError, TypeError):
        raise WorkflowError('Проверьте дату и время.', fields={'date': 'Выберите корректную дату.'})


def present(value):
    text = str(value or '')
    return '' if text in ('undefined', 'null', 'None') else text


class BookingsMixin:
    def booking_provider(self):
        return present(getattr(self.env, 'PAYMENT_PROVIDER_TOKEN', ''))

    async def booking_ready(self):
        return bool(await self.db_first("SELECT name FROM sqlite_master WHERE type='table' AND name='miniapp_v2_orders'"))

    async def booking_capabilities(self):
        ready = await self.booking_ready()
        return {'ready': ready, 'payments': bool(self.booking_provider()), 'admin_only': True, 'currency': 'RUB'}

    async def booking_rules(self):
        row = await self.db_first("SELECT value FROM miniapp_v2_settings WHERE key='rules'")
        saved = object_json(row.value) if row else {}
        return {'hold_seconds': max(60, min(3600, int(saved.get('hold_seconds', 900)))),
                'transfers_enabled': saved.get('transfers_enabled') is True,
                'children_enabled': saved.get('children_enabled') is True,
                'child_night_amount': max(0, int(saved.get('child_night_amount', 0))),
                'restaurant_lead_minutes': max(0, min(1440, int(saved.get('restaurant_lead_minutes', 0))))}

    async def booking_role(self, uid, cfg):
        if await self.is_manager(uid, cfg):
            return 'manager'
        person = await self.db_first('SELECT role FROM miniapp_v2_staff WHERE user_id=? AND active=1', uid)
        return str(person.role) if person else 'guest'

    async def booking_require_manager(self, uid, cfg):
        if await self.booking_role(uid, cfg) != 'manager':
            raise WorkflowError('Доступ запрещён.', 403)

    async def booking_require_staff(self, uid, cfg):
        if await self.booking_role(uid, cfg) not in ('waiter', 'manager'):
            raise WorkflowError('Нужен доступ сотрудника.', 403)

    async def booking_rates(self, service=''):
        rows = await self.db_all('SELECT * FROM miniapp_v2_rates WHERE active=1' + (' AND service=?' if service else '') + ' ORDER BY amount,id', *([service] if service else []))
        return [data_row(row, RATE_KEYS) for row in rows.results]

    async def booking_slot_rows(self, service, start, end, now, addons=(), guests=1):
        extra_guard = ''
        params = [now, service, max(start, now), end]
        if addons:
            extra_guard = """ AND NOT EXISTS(SELECT 1 FROM json_each(?) requested LEFT JOIN miniapp_v2_addons a ON a.id=requested.value
              WHERE a.id IS NULL OR a.active<>1 OR a.service<>? OR a.capacity<?+COALESCE((SELECT SUM(json_extract(used.value,'$.quantity'))
              FROM miniapp_v2_orders o,json_each(o.addons) used WHERE json_extract(used.value,'$.id')=a.id AND o.starts_at<s.ends_at AND o.ends_at>s.starts_at
              AND (o.status='paid' OR (o.status IN ('hold','checkout') AND o.hold_until>?))),0))"""
            params += [compact(list(addons)), service, guests, now]
        rows = await self.db_all("""SELECT s.*,r.title,r.amount,r.unit,r.duration,r.max_guests,r.included,
          s.capacity-COALESCE((SELECT SUM(o.units) FROM miniapp_v2_orders o WHERE o.slot_id=s.id
           AND (o.status='paid' OR (o.status IN ('hold','checkout') AND o.hold_until>?))),0) remaining
          FROM miniapp_v2_slots s JOIN miniapp_v2_rates r ON r.id=s.rate_id
          JOIN miniapp_v2_resources resource ON resource.id=s.resource_id
          WHERE s.service=? AND s.active=1 AND r.active=1 AND resource.active=1
          AND s.starts_at>=? AND s.starts_at<? AND NOT EXISTS (
           SELECT 1 FROM miniapp_v2_blocks b WHERE b.active=1 AND b.starts_at<s.ends_at AND b.ends_at>s.starts_at
           AND (b.resource_id=s.resource_id OR b.resource_id IN (SELECT value FROM json_each(s.resources))))
          AND NOT EXISTS(SELECT 1 FROM json_each(s.resources) dependency LEFT JOIN miniapp_v2_resources linked ON linked.id=dependency.value WHERE linked.id IS NULL OR linked.active<>1)
          """ + extra_guard + ' ORDER BY s.starts_at,s.id LIMIT 5000', *params)
        return [data_row(row, SLOT_KEYS) for row in rows.results]

    async def booking_addons(self, service, start, end, guests, now):
        rows = await self.db_all("""SELECT a.*,a.capacity-COALESCE((SELECT SUM(json_extract(j.value,'$.quantity'))
          FROM miniapp_v2_orders o,json_each(o.addons) j WHERE json_extract(j.value,'$.id')=a.id
          AND o.starts_at<? AND o.ends_at>? AND (o.status='paid' OR (o.status IN ('hold','checkout') AND o.hold_until>?))),0) remaining
          FROM miniapp_v2_addons a WHERE a.service=? AND a.active=1 ORDER BY a.title""", end, start, now, service)
        return [{**data_row(row, ('id', 'title', 'amount', 'capacity', 'remaining')), 'available': int(row.remaining) >= guests} for row in rows.results]

    async def booking_read(self, user, p, menu, sections, cfg):
        if not await self.booking_ready():
            raise WorkflowError('Новый раздел ещё подготавливается. Вернитесь немного позже.', 503)
        uid, action, now = int(user['id']), p.get('action'), int(time.time())
        if action == 'availability':
            service = p.get('service')
            if service not in ('wave', 'wake', 'hotel'):
                raise WorkflowError('Выберите направление.')
            rates = await self.booking_rates(service)
            if service == 'hotel':
                if not p.get('arrival') or not p.get('departure'):
                    return {'rates': rates, 'rooms': [], 'rules': await self.booking_rules()}
                return await self.booking_hotel_quote(p, now, rates=rates)
            month = str(p.get('month') or datetime.now(MSK).strftime('%Y-%m'))
            start = date_value(month + '-01')
            end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
            addons = p.get('addons', [])
            if not isinstance(addons, list) or len(addons) > 20 or any(not isinstance(a, str) for a in addons):
                raise WorkflowError('Проверьте выбранное снаряжение.')
            guests = integer(p.get('guests', 1), 'guests', 1, 200)
            rows = await self.booking_slot_rows(service, int(start.timestamp()), int(end.timestamp()), now, addons, guests)
            return {'rates': rates, 'slots': [row for row in rows if int(row['remaining']) > 0], 'month': month}
        if action == 'quote':
            return await self.booking_prepare(p.get('values', {}), uid, menu, sections, now)
        if action == 'addons':
            service = p.get('service')
            if service not in ('wave', 'wake'):
                raise WorkflowError('Выберите направление.')
            rows = await self.db_all('SELECT * FROM miniapp_v2_addons WHERE service=? AND active=1 AND capacity>0 ORDER BY title', service)
            return {'addons': [data_row(row, ('id', 'title', 'amount', 'capacity')) for row in rows.results]}
        if action == 'lookup_order':
            await self.booking_require_staff(uid, cfg)
            code = str(p.get('code') or '').strip().upper()
            if not re.fullmatch(r'[0-9A-F]{8,32}', code):
                raise WorkflowError('Введите код предзаказа из карточки гостя.')
            rows = await self.db_all("SELECT id FROM miniapp_v2_orders WHERE kind='preorder' AND status='paid' AND upper(substr(id,1,?))=? LIMIT 2", len(code), code)
            records = list(rows.results)
            if len(records) != 1:
                raise WorkflowError('Однозначный оплаченный предзаказ не найден. Проверьте QR.', 404)
            return await self.booking_read(user, {**p, 'action': 'qr', 'token': self.booking_qr(str(records[0].id))}, menu, sections, cfg)
        if action == 'plans':
            rows = await self.db_all("SELECT * FROM miniapp_v2_orders WHERE user_id=? AND status IN ('paid','hold','checkout','payment_review') ORDER BY starts_at DESC LIMIT 200", uid)
            return {'orders': [await self.booking_public(row, uid, cfg, now) for row in rows.results]}
        if action == 'order':
            row = await self.booking_owned_order(uid, p.get('order'), cfg)
            return {'order': await self.booking_public(row, uid, cfg, now), 'rules': await self.booking_rules()}
        if action == 'qr':
            await self.booking_require_staff(uid, cfg)
            row = await self.booking_qr_order(str(p.get('token') or ''))
            order = await self.booking_public(row, uid, cfg, now, scanned=True)
            tables = await self.db_all("SELECT t.* FROM miniapp_v2_tables t WHERE t.active=1 AND NOT EXISTS(SELECT 1 FROM miniapp_v2_assignments a WHERE a.table_id=t.id AND a.active=1) ORDER BY t.name")
            return {'order': order, 'token': self.booking_qr(str(row.id)), 'tables': [data_row(t, ('id', 'name', 'seats', 'zone')) for t in tables.results]}
        if action == 'staff_tables':
            await self.booking_require_staff(uid, cfg)
            rows = await self.db_all("SELECT o.* FROM miniapp_v2_assignments a JOIN miniapp_v2_orders o ON o.id=a.order_id WHERE a.waiter_id=? AND a.active=1 ORDER BY a.assigned_at", uid)
            return {'orders': [await self.booking_public(row, uid, cfg, now) for row in rows.results]}
        await self.booking_require_manager(uid, cfg)
        if action == 'inventory':
            rates = await self.db_all('SELECT * FROM miniapp_v2_rates ORDER BY service,amount,id')
            result = {'rates': [data_row(row, RATE_KEYS) for row in rates.results], 'rules': await self.booking_rules(), 'payments': bool(self.booking_provider())}
            for table, keys in [('resources', RESOURCE_KEYS), ('tables', ('id', 'name', 'seats', 'zone', 'active')), ('staff', ('user_id', 'name', 'role', 'active')), ('addons', ('id', 'service', 'title', 'amount', 'capacity', 'active'))]:
                rows = await self.db_all('SELECT * FROM miniapp_v2_' + table + ' LIMIT 500')
                result[table] = [data_row(row, keys) for row in rows.results]
            result['users'] = []
            blocks = await self.db_all('SELECT b.*,r.name resource_name FROM miniapp_v2_blocks b JOIN miniapp_v2_resources r ON r.id=b.resource_id WHERE b.active=1 AND b.ends_at>? ORDER BY b.starts_at LIMIT 500', now)
            result['blocks'] = [data_row(row, ('id','resource_name','starts_at','ends_at','reason')) for row in blocks.results]
            stopped = await self.db_all('SELECT item_id FROM miniapp_v2_menu_status WHERE available=0')
            stopped_ids = {str(row.item_id) for row in stopped.results}
            result['menu_items'] = [{**item, 'category': category['title'], 'available': item['id'] not in stopped_ids} for category in preview_catalog(menu, sections)['categories'] for item in category['items']]
            return result
        if action in ('calendar', 'preorders', 'all_orders'):
            start = date_value(p.get('date') or datetime.now(MSK).strftime('%Y-%m-%d'))
            end = start + timedelta(days=1)
            if action == 'calendar':
                service = p.get('service', 'wave')
                if service in ('wave', 'wake'):
                    slots = await self.db_all('SELECT s.*,r.title FROM miniapp_v2_slots s JOIN miniapp_v2_rates r ON r.id=s.rate_id WHERE s.service=? AND s.starts_at>=? AND s.starts_at<? ORDER BY s.starts_at', service, int(start.timestamp()), int(end.timestamp()))
                    slot_list = []
                    for slot in slots.results:
                        occupied = await self.db_first("SELECT COALESCE(SUM(units),0) n FROM miniapp_v2_orders WHERE slot_id=? AND (status='paid' OR (status IN ('hold','checkout') AND hold_until>?))", slot.id, now)
                        slot_list.append({**data_row(slot, ('id', 'title', 'rate_id', 'resource_id', 'resources', 'starts_at', 'ends_at', 'capacity', 'active')), 'occupied': int(occupied.n)})
                    return {'slots': slot_list}
            clause, args = "starts_at>=? AND starts_at<?", [int(start.timestamp()), int(end.timestamp())]
            if action == 'preorders':
                clause += " AND kind='preorder'"
            elif action == 'calendar' and p.get('service') == 'hotel':
                clause, args = "service='hotel' AND starts_at<? AND ends_at>?", [int(end.timestamp()), int(start.timestamp())]
            rows = await self.db_all("SELECT * FROM miniapp_v2_orders WHERE " + clause + " AND status IN ('paid','payment_review','hold','checkout') ORDER BY starts_at LIMIT 300", *args)
            return {'orders': [await self.booking_public(row, uid, cfg, now) for row in rows.results]}
        raise WorkflowError('Экран не найден.', 404)

    async def booking_hotel_quote(self, values, now, rates=None, exclude=''):
        arrival, departure = date_value(values.get('arrival')), date_value(values.get('departure'))
        if arrival.date() < datetime.now(MSK).date() or departure <= arrival or (departure - arrival).days > 365:
            raise WorkflowError('Выберите будущий период проживания.', fields={'departure': 'Выезд должен быть позже заезда.'})
        adults = integer(values.get('guests', 2), 'guests', 1, 20)
        children = values.get('children', [])
        if not isinstance(children, list) or len(children) > 10 or any(type(age) is not int or not 0 <= age <= 17 for age in children):
            raise WorkflowError('Укажите возраст каждого ребёнка.')
        rules = await self.booking_rules()
        if children and not rules['children_enabled']:
            raise WorkflowError('Правила размещения детей ещё не опубликованы. Уточните условия отеля.', 409)
        start, end = int(arrival.timestamp()), int(departure.timestamp())
        rooms = await self.db_all("""SELECT resource.*,r.title,r.amount,r.included FROM miniapp_v2_resources resource
          JOIN miniapp_v2_rates r ON r.id=resource.rate_id WHERE resource.service='hotel' AND resource.kind='room'
          AND resource.active=1 AND r.active=1 AND resource.capacity>=? AND NOT EXISTS (
           SELECT 1 FROM miniapp_v2_orders o WHERE o.id<>? AND o.resource_id=resource.id AND o.starts_at<? AND o.ends_at>?
           AND (o.status='paid' OR (o.status IN ('hold','checkout') AND o.hold_until>?)))
          AND NOT EXISTS(SELECT 1 FROM miniapp_v2_blocks b WHERE b.resource_id=resource.id AND b.active=1 AND b.starts_at<? AND b.ends_at>?) ORDER BY r.amount,resource.name""", adults + len(children), exclude, end, start, now, end, start)
        nights = (departure - arrival).days
        return {'rates': rates or await self.booking_rates('hotel'), 'rooms': [{**data_row(room, RESOURCE_KEYS), 'title': room.title, 'included': room.included, 'night_amount': int(room.amount), 'amount': (int(room.amount) + len(children) * rules['child_night_amount']) * nights} for room in rooms.results], 'nights': nights, 'arrival': values['arrival'], 'departure': values['departure'], 'rules': rules}

    async def booking_prepare(self, v, uid, menu, sections, now):
        if not isinstance(v, dict):
            raise WorkflowError('Проверьте данные заказа.')
        name, phone = str(v.get('name') or '').strip(), russian_phone(v.get('phone'))
        errors = {}
        if not name or len(name) > 100:
            errors['name'] = 'Введите имя.'
        if not phone:
            errors['phone'] = 'Введите телефон полностью.'
        if errors:
            raise WorkflowError('Проверьте контакты.', fields=errors)
        service = v.get('service')
        guests = integer(v.get('guests', 1), 'guests', 1, 200)
        result = {'user_id': uid, 'service': service, 'guests': guests, 'name': name, 'phone': phone, 'currency': 'RUB', 'slot_id': '', 'resource_id': '', 'units': 1, 'addons': []}
        if service in ('wave', 'wake'):
            slot_id = identifier(v.get('slot'))
            row = await self.db_first('SELECT * FROM miniapp_v2_slots WHERE id=? AND service=?', slot_id, service)
            if not row:
                raise WorkflowError('Сеанс не найден.', 404)
            available = await self.booking_slot_rows(service, int(row.starts_at), int(row.ends_at), now)
            slot = next((s for s in available if s['id'] == slot_id), None)
            if not slot or guests > int(slot['max_guests']):
                raise WorkflowError('Этот вариант уже недоступен. Выберите другое время.', 409)
            units = guests if slot['unit'] == 'person' else 1
            if units > int(slot['remaining']):
                raise WorkflowError('В этом сеансе осталось меньше мест.', 409)
            addons = v.get('addons', [])
            if not isinstance(addons, list) or len(set(str(a) for a in addons)) != len(addons) or len(addons) > 20:
                raise WorkflowError('Проверьте выбранное снаряжение.')
            stock = await self.booking_addons(service, int(slot['starts_at']), int(slot['ends_at']), guests, now)
            selected = []
            for key in addons:
                addon = next((a for a in stock if a['id'] == key and a['available']), None)
                if not addon:
                    raise WorkflowError('Выбранное снаряжение сейчас недоступно.', 409)
                selected.append({'id': addon['id'], 'title': addon['title'], 'quantity': guests, 'amount': int(addon['amount'])})
            result.update(kind='booking', slot_id=slot_id, resource_id=slot['resource_id'], starts_at=int(slot['starts_at']), ends_at=int(slot['ends_at']), units=units,
                          amount=int(slot['amount']) * (guests if slot['unit'] == 'person' else 1) + sum(a['amount'] * a['quantity'] for a in selected), addons=selected,
                          data={'title': slot['title'], 'included': slot['included'], 'rate_id': slot['rate_id']})
        elif service == 'hotel':
            quote = await self.booking_hotel_quote(v, now)
            room = next((r for r in quote['rooms'] if r['id'] == v.get('room')), None)
            if not room:
                raise WorkflowError('Этот номер недоступен на весь период. Выберите другой.', 409)
            result.update(kind='booking', resource_id=room['id'], starts_at=int(date_value(v['arrival']).timestamp()), ends_at=int(date_value(v['departure']).timestamp()), amount=room['amount'],
                          guests=guests + len(v.get('children', [])), data={'title': room['title'], 'rate_id': room['rate_id'], 'room_name': room['name'], 'included': room['included'], 'arrival': v['arrival'], 'departure': v['departure'], 'nights': quote['nights'], 'adults': guests, 'children': v.get('children', [])})
        elif service == 'restaurant':
            arrival = date_value(v.get('arrival'), True)
            rules = await self.booking_rules()
            if arrival.timestamp() < now + rules['restaurant_lead_minutes'] * 60 or not (11 if arrival.weekday() >= 5 else 12) <= arrival.hour or (arrival.hour, arrival.minute) > (22, 30):
                raise WorkflowError('Выберите доступное время прихода. Кухня работает до 22:30.', fields={'arrival': 'Проверьте время прихода.'})
            lines = v.get('items')
            if not isinstance(lines, list) or not 1 <= len(lines) <= 300:
                raise WorkflowError('Добавьте блюда в предзаказ.')
            products = {item['id']: item for category in preview_catalog(menu, sections)['categories'] for item in category['items']}
            snapshot, seen = [], set()
            for line in lines:
                if not isinstance(line, dict):
                    raise WorkflowError('Проверьте состав предзаказа.')
                item = products.get(str(line.get('itemId')))
                option = next((o for o in item['options'] if str(o['id']) == str(line.get('optionId'))), None) if item else None
                if not option or type(option.get('amount')) is not int or option['amount'] <= 0:
                    raise WorkflowError('Цена или вариант блюда изменились. Проверьте корзину.', 409)
                key = (item['id'], str(option['id']))
                if key in seen:
                    raise WorkflowError('Позиция повторяется. Обновите корзину.')
                seen.add(key)
                stopped = await self.db_first('SELECT available FROM miniapp_v2_menu_status WHERE item_id=?', item['id'])
                if stopped and not int(stopped.available):
                    raise WorkflowError('Одно из блюд сейчас недоступно. Обновите корзину.', 409)
                quantity = integer(line.get('quantity'), 'quantity', 1, 99)
                snapshot.append({'item_id': item['id'], 'option_id': str(option['id']), 'name': item.get('cart_name') or item['name'], 'option': option['label'], 'quantity': quantity, 'amount': option['amount']})
            amount = sum(line['quantity'] * line['amount'] for line in snapshot)
            if amount > 100000000:
                raise WorkflowError('Слишком большая сумма предзаказа.')
            result.update(kind='preorder', starts_at=int(arrival.timestamp()), ends_at=int(arrival.timestamp()) + 60, amount=amount, data={'title': 'Предзаказ ресторана', 'items': snapshot, 'arrival': v['arrival']})
        else:
            raise WorkflowError('Выберите направление.')
        expected = v.get('expected_amount')
        if expected is not None and (type(expected) is not int or expected != result['amount']):
            raise WorkflowError('Итог изменился. Проверьте новую сумму перед оплатой.', 409)
        result['payments'] = bool(self.booking_provider())
        return result

    async def booking_owned_order(self, uid, order_id, cfg):
        row = await self.db_first('SELECT * FROM miniapp_v2_orders WHERE id=?', identifier(order_id))
        if not row:
            raise WorkflowError('Бронь не найдена.', 404)
        if int(row.user_id) != uid and await self.booking_role(uid, cfg) != 'manager':
            assignment = await self.db_first('SELECT waiter_id FROM miniapp_v2_assignments WHERE order_id=?', row.id)
            if not assignment or int(assignment.waiter_id) != uid or await self.booking_role(uid, cfg) != 'waiter':
                raise WorkflowError('Бронь не найдена.', 404)
        return row

    def booking_qr(self, order_id):
        signature = hmac.new(str(self.env.BOT_TOKEN).encode(), ('sunpark-preorder-v2:' + order_id).encode(), hashlib.sha256).hexdigest()
        return 'sunpark:preorder:' + order_id + ':' + signature

    async def booking_qr_order(self, token):
        match = re.fullmatch(r'sunpark:preorder:([a-zA-Z0-9_-]{1,80}):([0-9a-f]{64})', token)
        if not match or not hmac.compare_digest(token, self.booking_qr(match[1])):
            raise WorkflowError('QR не относится к действующему предзаказу.', 404)
        row = await self.db_first("SELECT * FROM miniapp_v2_orders WHERE id=? AND kind='preorder' AND status='paid'", match[1])
        if not row:
            raise WorkflowError('Действующий оплаченный предзаказ не найден.', 409)
        return row

    async def booking_public(self, row, uid, cfg, now, scanned=False):
        result = data_row(row, ORDER_KEYS)
        if int(row.user_id) != uid or row.status not in ('hold', 'checkout') or int(row.hold_until) <= now:
            result.pop('invoice_url', None)
        result['data'] = object_json(row.data)
        try:
            result['addons'] = json.loads(str(row.addons))
        except (ValueError, TypeError):
            result['addons'] = []
        if result['status'] in ('hold', 'checkout') and int(row.hold_until) <= now:
            result['status'] = 'expired'
        assignment = await self.db_first('SELECT a.*,t.name table_name,t.zone FROM miniapp_v2_assignments a JOIN miniapp_v2_tables t ON t.id=a.table_id WHERE a.order_id=?', row.id)
        result['assignment'] = data_row(assignment, ('table_id', 'table_name', 'zone', 'waiter_id', 'active', 'assigned_at')) if assignment else None
        if assignment:
            person = await self.db_first('SELECT name FROM miniapp_v2_staff WHERE user_id=?', assignment.waiter_id)
            result['assignment']['waiter_name'] = str(person.name) if person else 'Сотрудник'
        if row.kind == 'preorder' and row.status == 'paid' and not assignment and (int(row.user_id) == uid or await self.booking_role(uid, cfg) == 'manager'):
            result['qr'] = self.booking_qr(str(row.id))
        if int(row.user_id) != uid and await self.booking_role(uid, cfg) != 'manager':
            result.pop('phone', None)
            result.pop('user_id', None)
        return result

    async def booking_checkout(self, user, values, menu, sections):
        uid, now = int(user['id']), int(time.time())
        quote = await self.booking_prepare(values, uid, menu, sections, now)
        if not self.booking_provider():
            raise WorkflowError('Оплата ещё не подключена. Бронь не создана и деньги не списаны.', 503)
        if quote['kind'] == 'preorder' and not await self.db_first('SELECT id FROM miniapp_v2_tables WHERE active=1 AND seats>=? LIMIT 1', quote['guests']):
            raise WorkflowError('Для этого числа гостей пока нет настроенного стола. Проверьте условия ресторана.', 409)
        rules = await self.booking_rules()
        order_id, until = uuid.uuid4().hex, now + rules['hold_seconds']
        columns = 'id,user_id,kind,service,slot_id,resource_id,starts_at,ends_at,units,guests,name,phone,amount,currency,status,hold_until,created_at,updated_at,data,addons'
        params = [order_id, uid, quote['kind'], quote['service'], quote['slot_id'], quote['resource_id'], quote['starts_at'], quote['ends_at'], quote['units'], quote['guests'], quote['name'], quote['phone'], quote['amount'], 'RUB', 'hold', until, now, now, compact(quote['data']), compact(quote['addons'])]
        condition, guard = '1=1', []
        if quote['slot_id']:
            condition = """EXISTS(SELECT 1 FROM miniapp_v2_slots s JOIN miniapp_v2_resources resource ON resource.id=s.resource_id
              WHERE s.id=? AND s.active=1 AND resource.active=1 AND s.starts_at>?
              AND s.capacity>=?+COALESCE((SELECT SUM(units) FROM miniapp_v2_orders o WHERE o.slot_id=s.id AND (o.status='paid' OR (o.status IN ('hold','checkout') AND o.hold_until>?))),0)
              AND NOT EXISTS(SELECT 1 FROM json_each(s.resources) dependency LEFT JOIN miniapp_v2_resources linked ON linked.id=dependency.value WHERE linked.id IS NULL OR linked.active<>1)
              AND NOT EXISTS(SELECT 1 FROM miniapp_v2_blocks b WHERE b.active=1 AND (b.resource_id=s.resource_id OR b.resource_id IN (SELECT value FROM json_each(s.resources))) AND b.starts_at<s.ends_at AND b.ends_at>s.starts_at))"""
            guard = [quote['slot_id'], now, quote['units'], now]
        elif quote['service'] == 'hotel':
            condition = """EXISTS(SELECT 1 FROM miniapp_v2_resources r WHERE r.id=? AND r.active=1 AND r.capacity>=?
              AND NOT EXISTS(SELECT 1 FROM miniapp_v2_orders o WHERE o.resource_id=r.id AND o.starts_at<? AND o.ends_at>? AND (o.status='paid' OR (o.status IN ('hold','checkout') AND o.hold_until>?)))
              AND NOT EXISTS(SELECT 1 FROM miniapp_v2_blocks b WHERE b.active=1 AND b.resource_id=r.id AND b.starts_at<? AND b.ends_at>?))"""
            guard = [quote['resource_id'], quote['guests'], quote['ends_at'], quote['starts_at'], now, quote['ends_at'], quote['starts_at']]
        try:
            inserted = await self.db_run('INSERT INTO miniapp_v2_orders(' + columns + ') SELECT ' + ','.join('?' for _ in params) + ' WHERE ' + condition, *params, *guard)
        except Exception as error:
            if 'ADDON_CAPACITY' in str(error):
                raise WorkflowError('Снаряжение уже заняли. Проверьте выбор ещё раз.', 409)
            raise
        if not int(inserted.meta.changes or 0):
            raise WorkflowError('Выбранный вариант уже заняли. Проверьте доступность ещё раз.', 409)
        try:
            params = {'title': ('SunPark · ' + quote['data']['title'])[:32], 'description': 'Полная оплата выбранной услуги SunPark', 'payload': 'sunpark-order:' + order_id,
                      'provider_token': self.booking_provider(), 'currency': 'RUB', 'prices': [{'label': quote['data']['title'][:32], 'amount': quote['amount']}]}
            provider_data = present(getattr(self.env, 'PAYMENT_PROVIDER_DATA', ''))
            if provider_data:
                params['provider_data'] = provider_data
            url = await self.tg('createInvoiceLink', params)
            if not isinstance(url, str) or not url.startswith('https://t.me/'):
                raise ValueError('Invalid invoice link')
            await self.db_run("UPDATE miniapp_v2_orders SET invoice_url=?,status='checkout',updated_at=? WHERE id=? AND status='hold'", url, now, order_id)
        except Exception:
            await self.db_run("UPDATE miniapp_v2_orders SET status='payment_error',hold_until=?,updated_at=? WHERE id=? AND status='hold'", now, now, order_id)
            raise WorkflowError('Не удалось открыть оплату. Деньги не списаны; попробуйте позже.', 503)
        return {'order': order_id, 'invoice_url': url, 'amount': quote['amount'], 'currency': 'RUB'}

    async def booking_write(self, user, p, menu, sections, cfg):
        if not await self.booking_ready():
            raise WorkflowError('Новый раздел ещё подготавливается.', 503)
        uid, action, now = int(user['id']), p.get('action'), int(time.time())
        if action == 'checkout':
            return await self.booking_checkout(user, p.get('values', {}), menu, sections)
        if action == 'transfer':
            return await self.booking_transfer(uid, p.get('values', {}), cfg, now)
        if action == 'assign_table':
            await self.booking_require_staff(uid, cfg)
            order = await self.booking_qr_order(str(p.get('token') or ''))
            old = await self.db_first('SELECT * FROM miniapp_v2_assignments WHERE order_id=?', order.id)
            if old:
                if int(old.active) and int(old.waiter_id) == uid:
                    return {'order': await self.booking_public(order, uid, cfg, now), 'repeated': True}
                raise WorkflowError('Предзаказ уже принят другим официантом или завершён. Передача доступна управляющему.', 409)
            if datetime.fromtimestamp(int(order.starts_at), MSK).date() != datetime.now(MSK).date():
                raise WorkflowError('Дата прихода не совпадает с сегодняшней. Проверьте предзаказ.', 409)
            table_id = identifier(p.get('table'))
            try:
                changed = await self.db_run("""INSERT INTO miniapp_v2_assignments(order_id,table_id,waiter_id,actor_id,assigned_at,updated_at)
                  SELECT ?,t.id,?,?,?,? FROM miniapp_v2_tables t WHERE t.id=? AND t.active=1 AND t.seats>=?
                  AND NOT EXISTS(SELECT 1 FROM miniapp_v2_assignments a WHERE a.table_id=t.id AND a.active=1)""", order.id, uid, uid, now, now, table_id, order.guests)
            except Exception as error:
                if 'UNIQUE' in str(error):
                    raise WorkflowError('Назначение уже изменилось. Проверьте стол ещё раз.', 409)
                raise
            if not int(changed.meta.changes or 0):
                raise WorkflowError('Стол занят или не подходит числу гостей.', 409)
            return {'order': await self.booking_public(order, uid, cfg, now)}
        if action == 'complete_table':
            order = await self.booking_owned_order(uid, p.get('order') or (p.get('values') or {}).get('order'), cfg)
            changed = await self.db_run('UPDATE miniapp_v2_assignments SET active=0,actor_id=?,updated_at=? WHERE order_id=? AND active=1 AND (waiter_id=? OR ?=1)', uid, now, order.id, uid, 1 if await self.booking_role(uid, cfg) == 'manager' else 0)
            if not int(changed.meta.changes or 0):
                raise WorkflowError('Назначение уже изменилось.', 409)
            return {'ok': True}
        await self.booking_require_manager(uid, cfg)
        try:
            return await self.booking_admin_write(uid, action, p.get('values', {}), now, cfg)
        except WorkflowError:
            raise
        except Exception as error:
            if 'UNIQUE' in str(error):
                raise WorkflowError('Такая запись уже существует. Проверьте название и зону.', 409)
            if any(code in str(error) for code in ('RESOURCE_OVERLAP', 'BOOKED_CAPACITY', 'BOOKING_CONFLICT')):
                raise WorkflowError('Доступность уже изменилась. Есть занятый ресурс, место или действующее удержание.', 409)
            raise

    async def booking_admin_write(self, uid, action, v, now, cfg):
        if not isinstance(v, dict):
            raise WorkflowError('Проверьте форму.')
        if action == 'save_rate':
            key = identifier(v.get('id') or uuid.uuid4().hex)
            if v.get('service') not in ('wave', 'wake', 'hotel') or v.get('unit') not in ('person', 'session', 'night'):
                raise WorkflowError('Проверьте направление и единицу цены.')
            if (v['service'] == 'hotel') != (v['unit'] == 'night'):
                raise WorkflowError('Для отеля цена задаётся за ночь, для катания — за человека или сеанс.')
            previous = await self.db_first('SELECT service FROM miniapp_v2_rates WHERE id=?', key)
            if previous and previous.service != v['service']:
                raise WorkflowError('Направление существующего тарифа менять нельзя. Добавьте новый.')
            title = str(v.get('title') or '').strip()[:120]
            if not title:
                raise WorkflowError('Укажите название тарифа.')
            await self.db_run('INSERT INTO miniapp_v2_rates(id,service,title,amount,unit,duration,max_guests,included,active) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,amount=excluded.amount,unit=excluded.unit,duration=excluded.duration,max_guests=excluded.max_guests,included=excluded.included,active=excluded.active', key, v['service'], title, integer(v.get('amount'), 'amount', 1, 100000000), v['unit'], integer(v.get('duration'), 'duration', 1, 1440), integer(v.get('max_guests'), 'max_guests', 1, 200), str(v.get('included') or '')[:500], 1 if v.get('active', True) else 0)
        elif action == 'save_resource':
            key = identifier(v.get('id') or uuid.uuid4().hex)
            if v.get('service') not in ('wave', 'wake', 'hotel') or v.get('kind') not in ('installation', 'room', 'trainer'):
                raise WorkflowError('Проверьте тип ресурса.')
            if (v['service'] == 'hotel') != (v['kind'] == 'room'):
                raise WorkflowError('Номер относится к отелю; установки и тренеры — к катанию.')
            previous = await self.db_first('SELECT service,kind FROM miniapp_v2_resources WHERE id=?', key)
            if previous and (previous.service != v['service'] or previous.kind != v['kind']):
                raise WorkflowError('Тип и направление существующего ресурса менять нельзя. Добавьте новый.')
            name = str(v.get('name') or '').strip()[:100]
            rate_id = str(v.get('rate_id') or '')
            if not name:
                raise WorkflowError('Укажите название ресурса.')
            if v['kind'] == 'room' and not await self.db_first("SELECT id FROM miniapp_v2_rates WHERE id=? AND service='hotel' AND active=1", rate_id):
                raise WorkflowError('Выберите категорию номера.')
            await self.db_run('INSERT INTO miniapp_v2_resources VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,rate_id=excluded.rate_id,capacity=excluded.capacity,active=excluded.active', key, v['service'], name, v['kind'], rate_id, integer(v.get('capacity', 1), 'capacity', 1, 200), 1 if v.get('active', True) else 0)
        elif action == 'save_slot':
            key = identifier(v.get('id') or uuid.uuid4().hex)
            rate = await self.db_first("SELECT * FROM miniapp_v2_rates WHERE id=? AND active=1 AND service IN ('wave','wake')", identifier(v.get('rate_id')))
            resource = await self.db_first('SELECT * FROM miniapp_v2_resources WHERE id=? AND active=1', identifier(v.get('resource_id')))
            if not rate or not resource or rate.service != resource.service:
                raise WorkflowError('Выберите подходящий тариф и ресурс.')
            start = int(date_value(v.get('start'), True).timestamp())
            if start <= now:
                raise WorkflowError('Выберите будущее время.')
            end, capacity = start + int(rate.duration) * 60, integer(v.get('capacity'), 'capacity', 1, 200)
            if rate.unit != 'person' and capacity != 1:
                raise WorkflowError('Для индивидуального сеанса или аренды лимит — одна бронь. Число гостей задано тарифом.')
            dependencies = v.get('resources', [])
            if not isinstance(dependencies, list) or len(dependencies) > 20:
                raise WorkflowError('Проверьте связанные ресурсы.')
            dependencies = sorted(set([str(resource.id)] + [identifier(x) for x in dependencies]))
            for dependency in dependencies:
                if not await self.db_first('SELECT id FROM miniapp_v2_resources WHERE id=? AND active=1', dependency):
                    raise WorkflowError('Связанный ресурс недоступен.')
            old = await self.db_first('SELECT * FROM miniapp_v2_slots WHERE id=?', key)
            count = await self.db_first("SELECT COALESCE(SUM(units),0) n FROM miniapp_v2_orders WHERE slot_id=? AND (status='paid' OR (status IN ('hold','checkout') AND hold_until>?))", key, now)
            if int(count.n) > capacity:
                raise WorkflowError('Лимит ниже числа уже занятых мест.', 409)
            if old and int(count.n) and (int(old.starts_at) != start or int(old.ends_at) != end or old.rate_id != rate.id or old.resource_id != resource.id or str(old.resources) != compact(dependencies)):
                raise WorkflowError('Нельзя изменить условия уже занятых мест. Используйте перенос.', 409)
            collision = await self.db_first("""SELECT s.id FROM miniapp_v2_slots s,json_each(s.resources) resource WHERE s.id<>? AND s.starts_at<? AND s.ends_at>?
              AND resource.value IN (SELECT value FROM json_each(?)) AND (s.active=1 OR EXISTS(SELECT 1 FROM miniapp_v2_orders o WHERE o.slot_id=s.id AND (o.status='paid' OR (o.status IN ('hold','checkout') AND o.hold_until>?)))) LIMIT 1""", key, end, start, compact(dependencies), now)
            if collision:
                raise WorkflowError('Этот ресурс уже занят другим сеансом.', 409)
            await self.db_run('INSERT INTO miniapp_v2_slots VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET rate_id=excluded.rate_id,resource_id=excluded.resource_id,resources=excluded.resources,starts_at=excluded.starts_at,ends_at=excluded.ends_at,capacity=excluded.capacity,active=excluded.active', key, str(rate.service), str(rate.id), str(resource.id), compact(dependencies), start, end, capacity, 1 if v.get('active', True) else 0)
        elif action == 'block':
            resource_id = identifier(v.get('resource_id'))
            start, end = int(date_value(v.get('start'), True).timestamp()), int(date_value(v.get('end'), True).timestamp())
            if end <= start or not await self.db_first('SELECT id FROM miniapp_v2_resources WHERE id=?', resource_id):
                raise WorkflowError('Проверьте ресурс и интервал.')
            conflict = await self.db_first("""SELECT o.id FROM miniapp_v2_orders o LEFT JOIN miniapp_v2_slots s ON s.id=o.slot_id
              WHERE o.starts_at<? AND o.ends_at>? AND (o.resource_id=? OR ? IN (SELECT value FROM json_each(COALESCE(s.resources,'[]'))))
              AND (o.status='paid' OR (o.status IN ('hold','checkout') AND o.hold_until>?)) LIMIT 1""", end, start, resource_id, resource_id, now)
            if conflict:
                raise WorkflowError('В этом интервале есть бронь или удержание. Сначала решите перенос.', 409)
            await self.db_run('INSERT INTO miniapp_v2_blocks VALUES(?,?,?,?,?,?,1)', uuid.uuid4().hex, resource_id, start, end, str(v.get('reason') or 'Техническая недоступность')[:200], uid)
        elif action == 'save_table':
            key = identifier(v.get('id') or uuid.uuid4().hex)
            name = str(v.get('name') or '').strip()[:60]
            if not name:
                raise WorkflowError('Укажите номер стола.')
            active, seats = 1 if v.get('active', True) else 0, integer(v.get('seats'), 'seats', 1, 200)
            used = await self.db_first('SELECT o.guests FROM miniapp_v2_assignments a JOIN miniapp_v2_orders o ON o.id=a.order_id WHERE a.table_id=? AND a.active=1', key)
            if used and (not active or seats < int(used.guests)):
                raise WorkflowError('У стола есть гости. Нельзя скрыть его или уменьшить вместимость.', 409)
            await self.db_run('INSERT INTO miniapp_v2_tables VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,seats=excluded.seats,zone=excluded.zone,active=excluded.active', key, name, seats, str(v.get('zone') or '')[:80], active)
        elif action == 'unblock':
            await self.db_run('UPDATE miniapp_v2_blocks SET active=0 WHERE id=?', identifier(v.get('id')))
        elif action == 'save_staff':
            staff_id = integer(v.get('user_id'), 'user_id', 1, 9007199254740991)
            if v.get('role') not in ('manager', 'waiter') or not str(v.get('name') or '').strip():
                raise WorkflowError('Укажите имя и роль сотрудника.')
            if not v.get('active', True) and await self.db_first('SELECT order_id FROM miniapp_v2_assignments WHERE waiter_id=? AND active=1', staff_id):
                raise WorkflowError('Сначала передайте активные столы сотрудника.', 409)
            await self.db_run('INSERT INTO miniapp_v2_staff VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET name=excluded.name,role=excluded.role,active=excluded.active', staff_id, str(v['name'])[:100], v['role'], 1 if v.get('active', True) else 0)
        elif action == 'transfer_table':
            new_waiter = integer(v.get('waiter_id'), 'waiter_id', 1, 9007199254740991)
            if not await self.db_first("SELECT user_id FROM miniapp_v2_staff WHERE user_id=? AND active=1 AND role IN ('waiter','manager')", new_waiter) and not await self.is_manager(new_waiter, cfg):
                raise WorkflowError('Выберите действующего сотрудника.')
            changed = await self.db_run('UPDATE miniapp_v2_assignments SET waiter_id=?,actor_id=?,updated_at=? WHERE order_id=? AND waiter_id=? AND active=1', new_waiter, uid, now, identifier(v.get('order')), integer(v.get('previous_waiter'), 'previous_waiter', 1, 9007199254740991))
            if not int(changed.meta.changes or 0):
                raise WorkflowError('Ответственный уже изменился. Обновите предзаказ.', 409)
        elif action == 'save_addon':
            key = identifier(v.get('id') or uuid.uuid4().hex)
            if v.get('service') not in ('wave', 'wake') or not str(v.get('title') or '').strip():
                raise WorkflowError('Укажите снаряжение и направление.')
            await self.db_run('INSERT INTO miniapp_v2_addons VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,amount=excluded.amount,capacity=excluded.capacity,active=excluded.active', key, v['service'], str(v['title'])[:100], integer(v.get('amount'), 'amount', 0, 100000000), integer(v.get('capacity'), 'capacity', 0, 10000), 1 if v.get('active', True) else 0)
        elif action == 'menu_status':
            await self.db_run('INSERT INTO miniapp_v2_menu_status VALUES(?,?) ON CONFLICT(item_id) DO UPDATE SET available=excluded.available', identifier(v.get('item_id')), 1 if v.get('available') else 0)
        elif action == 'save_rules':
            allowed = {'hold_seconds', 'transfers_enabled', 'children_enabled', 'child_night_amount', 'restaurant_lead_minutes'}
            if any(k not in allowed for k in v):
                raise WorkflowError('Неизвестное правило.')
            old = await self.booking_rules()
            old.update(v)
            for key, minimum, maximum in [('hold_seconds', 60, 3600), ('child_night_amount', 0, 100000000), ('restaurant_lead_minutes', 0, 1440)]:
                integer(old[key], key, minimum, maximum)
            if type(old['transfers_enabled']) is not bool or type(old['children_enabled']) is not bool:
                raise WorkflowError('Проверьте настройки правил.')
            await self.db_run("INSERT INTO miniapp_v2_settings VALUES('rules',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", compact(old))
        else:
            raise WorkflowError('Действие не найдено.', 404)
        return {'ok': True}

    async def booking_transfer(self, uid, values, cfg, now):
        row = await self.booking_owned_order(uid, values.get('order'), cfg)
        rules = await self.booking_rules()
        if await self.booking_role(uid, cfg) != 'manager' and not rules['transfers_enabled']:
            raise WorkflowError('Условия переноса ещё не опубликованы. Текущая бронь сохраняется.', 409)
        if row.kind != 'booking' or row.status != 'paid' or int(row.starts_at) <= now:
            raise WorkflowError('Для этой брони перенос недоступен.', 409)
        if values.get('expected_start') != int(row.starts_at):
            raise WorkflowError('Бронь уже изменилась. Обновите её перед переносом.', 409)
        old = object_json(row.data)
        if row.service == 'hotel':
            query = {'arrival': values.get('arrival'), 'departure': values.get('departure'), 'guests': old.get('adults', row.guests), 'children': old.get('children', [])}
            quote = await self.booking_hotel_quote(query, now, exclude=str(row.id))
            category = old.get('rate_id')
            if not category:
                resource = await self.db_first('SELECT rate_id FROM miniapp_v2_resources WHERE id=?', row.resource_id)
                category = str(resource.rate_id) if resource else ''
            rooms = [room for room in quote['rooms'] if room['rate_id'] == category]
            room = next((room for room in rooms if room['id'] == values.get('room')), rooms[0] if rooms else None)
            if not room:
                raise WorkflowError('На весь новый период подходящего номера нет.', 409)
            if int(room['amount']) != int(row.amount):
                raise WorkflowError('Стоимость нового периода отличается. Нужен отдельный расчёт; прежняя бронь сохранена.', 409)
            start, end = int(date_value(query['arrival']).timestamp()), int(date_value(query['departure']).timestamp())
            slot_id, resource_id = '', room['id']
            new_data = {**old, 'arrival': query['arrival'], 'departure': query['departure'], 'nights': quote['nights'], 'room_name': room['name']}
            guard = """NOT EXISTS(SELECT 1 FROM miniapp_v2_orders o WHERE o.id<>? AND o.resource_id=? AND o.starts_at<? AND o.ends_at>?
             AND (o.status='paid' OR (o.status IN ('hold','checkout') AND o.hold_until>?)))
             AND NOT EXISTS(SELECT 1 FROM miniapp_v2_blocks b WHERE b.resource_id=? AND b.active=1 AND b.starts_at<? AND b.ends_at>?)"""
            guard_args = [row.id, resource_id, end, start, now, resource_id, end, start]
        else:
            target = await self.db_first('SELECT * FROM miniapp_v2_slots WHERE id=? AND service=?', identifier(values.get('slot')), row.service)
            if not target:
                raise WorkflowError('Новый сеанс не найден.', 404)
            slots = await self.booking_slot_rows(str(row.service), int(target.starts_at), int(target.ends_at), now)
            slot = next((s for s in slots if s['id'] == target.id and s['rate_id'] == old.get('rate_id')), None)
            if not slot or int(slot['remaining']) < int(row.units):
                raise WorkflowError('Новый сеанс уже недоступен.', 409)
            addons = json.loads(str(row.addons))
            amount = int(slot['amount']) * (int(row.guests) if slot['unit'] == 'person' else 1) + sum(int(a['amount']) * int(a['quantity']) for a in addons)
            if amount != int(row.amount):
                raise WorkflowError('Стоимость сеанса изменилась. Прежняя бронь сохранена.', 409)
            start, end, slot_id, resource_id = int(slot['starts_at']), int(slot['ends_at']), slot['id'], slot['resource_id']
            new_data = {**old, 'title': slot['title'], 'included': slot['included']}
            guard = """EXISTS(SELECT 1 FROM miniapp_v2_slots s WHERE s.id=? AND s.active=1 AND s.capacity>=?+COALESCE((
             SELECT SUM(o.units) FROM miniapp_v2_orders o WHERE o.id<>? AND o.slot_id=s.id
             AND (o.status='paid' OR (o.status IN ('hold','checkout') AND o.hold_until>?))),0)
             AND NOT EXISTS(SELECT 1 FROM miniapp_v2_blocks b WHERE b.active=1 AND (b.resource_id=s.resource_id OR b.resource_id IN (SELECT value FROM json_each(s.resources))) AND b.starts_at<s.ends_at AND b.ends_at>s.starts_at))"""
            guard_args = [slot_id, int(row.units), row.id, now]
        new_data['changes'] = (old.get('changes', []) + [{'from': int(row.starts_at), 'to': start, 'at': now, 'actor': uid}])[-50:]
        try:
            changed = await self.db_run("UPDATE miniapp_v2_orders SET slot_id=?,resource_id=?,starts_at=?,ends_at=?,data=?,updated_at=? WHERE id=? AND starts_at=? AND status='paid' AND " + guard,
                                        slot_id, resource_id, start, end, compact(new_data), now, row.id, int(row.starts_at), *guard_args)
        except Exception as error:
            if 'ADDON_CAPACITY' in str(error):
                raise WorkflowError('Снаряжение на новое время уже занято. Прежняя бронь сохранена.', 409)
            raise
        if not int(changed.meta.changes or 0):
            raise WorkflowError('Доступность изменилась. Прежняя бронь сохранена.', 409)
        updated = await self.booking_owned_order(uid, row.id, cfg)
        return {'order': await self.booking_public(updated, uid, cfg, now)}

    async def booking_payment_update(self, update):
        query = update.get('pre_checkout_query')
        payment = (update.get('message') or {}).get('successful_payment')
        data = query or payment
        if not data or not str(data.get('invoice_payload') or '').startswith('sunpark-order:'):
            return False
        order_id = str(data['invoice_payload']).split(':', 1)[1]
        row = await self.db_first('SELECT * FROM miniapp_v2_orders WHERE id=?', order_id)
        uid = int(((query or update.get('message') or {}).get('from') or {}).get('id') or 0)
        valid = bool(row and uid == int(row.user_id) and data.get('currency') == 'RUB' and type(data.get('total_amount')) is int and data['total_amount'] == int(row.amount))
        now = int(time.time())
        if query:
            valid = valid and row.status in ('hold', 'checkout') and int(row.hold_until) > now
            await self.tg('answerPreCheckoutQuery', {'pre_checkout_query_id': query['id'], 'ok': bool(valid), **({} if valid else {'error_message': 'Бронь недоступна или время удержания истекло. Проверьте её в SunPark.'})})
            return True
        if not row:
            print('SUNPARK UNKNOWN PAYMENT ORDER')
            return True
        charge = str(payment.get('telegram_payment_charge_id') or '')
        if not charge:
            print('SUNPARK PAYMENT WITHOUT CHARGE')
            return True
        duplicate = await self.db_first('SELECT id FROM miniapp_v2_orders WHERE telegram_charge=? AND id<>?', charge, order_id)
        if duplicate:
            print('SUNPARK PAYMENT CHARGE ALREADY USED')
            return True
        if row.status == 'paid':
            existing = await self.db_first('SELECT telegram_charge FROM miniapp_v2_orders WHERE id=?', order_id)
            if str(existing.telegram_charge or '') != charge:
                print('SUNPARK DUPLICATE ORDER PAYMENT')
            return True
        condition, args = '1=1', []
        if row.slot_id:
            condition = """EXISTS(SELECT 1 FROM miniapp_v2_slots s WHERE s.id=miniapp_v2_orders.slot_id AND (s.active=1 OR miniapp_v2_orders.hold_until>?)
              AND s.capacity>=miniapp_v2_orders.units+COALESCE((SELECT SUM(o.units) FROM miniapp_v2_orders o WHERE o.id<>miniapp_v2_orders.id AND o.slot_id=s.id
              AND (o.status='paid' OR (o.status IN ('hold','checkout') AND o.hold_until>?))),0))"""
            args = [now, now]
        elif row.service == 'hotel':
            condition = """NOT EXISTS(SELECT 1 FROM miniapp_v2_orders o WHERE o.id<>miniapp_v2_orders.id AND o.resource_id=miniapp_v2_orders.resource_id
              AND o.starts_at<miniapp_v2_orders.ends_at AND o.ends_at>miniapp_v2_orders.starts_at AND (o.status='paid' OR (o.status IN ('hold','checkout') AND o.hold_until>?)))"""
            args = [now]
        condition += """ AND NOT EXISTS(SELECT 1 FROM json_each(miniapp_v2_orders.addons) requested LEFT JOIN miniapp_v2_addons a ON a.id=json_extract(requested.value,'$.id')
          WHERE a.id IS NULL OR a.capacity<json_extract(requested.value,'$.quantity')+COALESCE((SELECT SUM(json_extract(other.value,'$.quantity'))
          FROM miniapp_v2_orders o,json_each(o.addons) other WHERE o.id<>miniapp_v2_orders.id AND json_extract(other.value,'$.id')=a.id
          AND o.starts_at<miniapp_v2_orders.ends_at AND o.ends_at>miniapp_v2_orders.starts_at AND (o.status='paid' OR (o.status IN ('hold','checkout') AND o.hold_until>?))),0))"""
        args.append(now)
        changed = await self.db_run("UPDATE miniapp_v2_orders SET status='paid',telegram_charge=?,provider_charge=?,updated_at=? WHERE id=? AND status IN ('hold','checkout') AND ?=1 AND " + condition, charge, str(payment.get('provider_payment_charge_id') or ''), now, order_id, 1 if valid else 0, *args)
        if not int(changed.meta.changes or 0):
            await self.db_run("UPDATE miniapp_v2_orders SET status='payment_review',telegram_charge=?,provider_charge=?,updated_at=? WHERE id=? AND status<>'paid'", charge, str(payment.get('provider_payment_charge_id') or ''), now, order_id)
        return True
