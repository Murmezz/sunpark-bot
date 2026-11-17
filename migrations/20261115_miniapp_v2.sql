-- Additive development schema. Existing tickets, messages and menu stay intact.
CREATE TABLE IF NOT EXISTS miniapp_v2_rates (
 id TEXT PRIMARY KEY,service TEXT NOT NULL CHECK(service IN ('wave','wake','hotel')),
 title TEXT NOT NULL,amount INTEGER NOT NULL CHECK(amount>0),
 unit TEXT NOT NULL CHECK(unit IN ('person','session','night')),
 duration INTEGER NOT NULL DEFAULT 30 CHECK(duration>0),
 max_guests INTEGER NOT NULL DEFAULT 1 CHECK(max_guests>0),
 included TEXT NOT NULL DEFAULT '',active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1))
);
CREATE TABLE IF NOT EXISTS miniapp_v2_resources (
 id TEXT PRIMARY KEY,service TEXT NOT NULL CHECK(service IN ('wave','wake','hotel')),
 name TEXT NOT NULL,kind TEXT NOT NULL DEFAULT 'installation',rate_id TEXT NOT NULL DEFAULT '',
 capacity INTEGER NOT NULL DEFAULT 1 CHECK(capacity>0),active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1))
);
CREATE TABLE IF NOT EXISTS miniapp_v2_slots (
 id TEXT PRIMARY KEY,service TEXT NOT NULL CHECK(service IN ('wave','wake')),
 rate_id TEXT NOT NULL REFERENCES miniapp_v2_rates(id),resource_id TEXT NOT NULL REFERENCES miniapp_v2_resources(id),
 resources TEXT NOT NULL DEFAULT '[]',starts_at INTEGER NOT NULL,ends_at INTEGER NOT NULL,
 capacity INTEGER NOT NULL CHECK(capacity>0),active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
 CHECK(ends_at>starts_at)
);
CREATE INDEX IF NOT EXISTS miniapp_v2_slot_dates ON miniapp_v2_slots(service,starts_at,active);
CREATE TABLE IF NOT EXISTS miniapp_v2_blocks (
 id TEXT PRIMARY KEY,resource_id TEXT NOT NULL REFERENCES miniapp_v2_resources(id),
 starts_at INTEGER NOT NULL,ends_at INTEGER NOT NULL,reason TEXT NOT NULL DEFAULT '',
 actor_id INTEGER NOT NULL,active INTEGER NOT NULL DEFAULT 1,CHECK(ends_at>starts_at)
);
CREATE TABLE IF NOT EXISTS miniapp_v2_addons (
 id TEXT PRIMARY KEY,service TEXT NOT NULL CHECK(service IN ('wave','wake')),
 title TEXT NOT NULL,amount INTEGER NOT NULL CHECK(amount>=0),capacity INTEGER NOT NULL DEFAULT 0 CHECK(capacity>=0),
 active INTEGER NOT NULL DEFAULT 0 CHECK(active IN (0,1))
);
CREATE TABLE IF NOT EXISTS miniapp_v2_orders (
 id TEXT PRIMARY KEY,user_id INTEGER NOT NULL,kind TEXT NOT NULL CHECK(kind IN ('booking','preorder')),
 service TEXT NOT NULL CHECK(service IN ('wave','wake','hotel','restaurant')),
 slot_id TEXT NOT NULL DEFAULT '',resource_id TEXT NOT NULL DEFAULT '',
 starts_at INTEGER NOT NULL,ends_at INTEGER NOT NULL,units INTEGER NOT NULL DEFAULT 1 CHECK(units>0),
 guests INTEGER NOT NULL CHECK(guests>0),name TEXT NOT NULL,phone TEXT NOT NULL,
 amount INTEGER NOT NULL CHECK(amount>0),currency TEXT NOT NULL DEFAULT 'RUB' CHECK(currency='RUB'),
 status TEXT NOT NULL DEFAULT 'hold' CHECK(status IN ('hold','checkout','paid','expired','payment_error','payment_review')),
 hold_until INTEGER NOT NULL,created_at INTEGER NOT NULL,updated_at INTEGER NOT NULL,
 data TEXT NOT NULL DEFAULT '{}',addons TEXT NOT NULL DEFAULT '[]',
 invoice_url TEXT NOT NULL DEFAULT '',telegram_charge TEXT,provider_charge TEXT NOT NULL DEFAULT '',
 UNIQUE(telegram_charge),CHECK(ends_at>starts_at)
);
CREATE INDEX IF NOT EXISTS miniapp_v2_order_owner ON miniapp_v2_orders(user_id,starts_at);
CREATE INDEX IF NOT EXISTS miniapp_v2_order_slot ON miniapp_v2_orders(slot_id,status,hold_until);
CREATE INDEX IF NOT EXISTS miniapp_v2_order_room ON miniapp_v2_orders(resource_id,starts_at,ends_at,status);
CREATE TABLE IF NOT EXISTS miniapp_v2_tables (
 id TEXT PRIMARY KEY,name TEXT NOT NULL,seats INTEGER NOT NULL CHECK(seats>0),
 zone TEXT NOT NULL DEFAULT '',active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1))
);
CREATE TABLE IF NOT EXISTS miniapp_v2_staff (
 user_id INTEGER PRIMARY KEY,name TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN ('waiter','manager')),
 active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1))
);
CREATE TABLE IF NOT EXISTS miniapp_v2_assignments (
 order_id TEXT PRIMARY KEY REFERENCES miniapp_v2_orders(id),table_id TEXT NOT NULL REFERENCES miniapp_v2_tables(id),
 waiter_id INTEGER NOT NULL,actor_id INTEGER NOT NULL,assigned_at INTEGER NOT NULL,updated_at INTEGER NOT NULL,
 active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1))
);
CREATE UNIQUE INDEX IF NOT EXISTS miniapp_v2_active_table ON miniapp_v2_assignments(table_id) WHERE active=1;
CREATE TABLE IF NOT EXISTS miniapp_v2_assignment_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT,order_id TEXT NOT NULL,table_id TEXT NOT NULL,
 from_waiter INTEGER NOT NULL,to_waiter INTEGER NOT NULL,actor_id INTEGER NOT NULL,created_at INTEGER NOT NULL,event TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS miniapp_v2_assignment_created AFTER INSERT ON miniapp_v2_assignments BEGIN
 INSERT INTO miniapp_v2_assignment_events(order_id,table_id,from_waiter,to_waiter,actor_id,created_at,event)
 VALUES(NEW.order_id,NEW.table_id,0,NEW.waiter_id,NEW.actor_id,NEW.updated_at,'assigned');
END;
CREATE TRIGGER IF NOT EXISTS miniapp_v2_assignment_changed AFTER UPDATE ON miniapp_v2_assignments
 WHEN NEW.waiter_id<>OLD.waiter_id OR NEW.active<>OLD.active BEGIN
 INSERT INTO miniapp_v2_assignment_events(order_id,table_id,from_waiter,to_waiter,actor_id,created_at,event)
 VALUES(NEW.order_id,NEW.table_id,OLD.waiter_id,NEW.waiter_id,NEW.actor_id,NEW.updated_at,CASE WHEN NEW.active=0 THEN 'completed' ELSE 'transferred' END);
END;
CREATE TABLE IF NOT EXISTS miniapp_v2_settings (key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS miniapp_v2_menu_status (item_id TEXT PRIMARY KEY,available INTEGER NOT NULL DEFAULT 1 CHECK(available IN (0,1)));
-- Stock checks execute in the same SQLite transaction as the authoritative hold.
CREATE TRIGGER IF NOT EXISTS miniapp_v2_addon_capacity BEFORE INSERT ON miniapp_v2_orders
 WHEN NEW.status IN ('hold','checkout','paid') AND json_array_length(NEW.addons)>0 BEGIN
 SELECT CASE WHEN EXISTS (
  SELECT 1 FROM json_each(NEW.addons) requested
  LEFT JOIN miniapp_v2_addons a ON a.id=json_extract(requested.value,'$.id')
  WHERE a.id IS NULL OR a.active<>1 OR a.capacity<json_extract(requested.value,'$.quantity')+COALESCE((
   SELECT SUM(json_extract(used.value,'$.quantity')) FROM miniapp_v2_orders o,json_each(o.addons) used
   WHERE json_extract(used.value,'$.id')=a.id AND o.starts_at<NEW.ends_at AND o.ends_at>NEW.starts_at
   AND (o.status='paid' OR (o.status IN ('hold','checkout') AND o.hold_until>NEW.created_at))
  ),0)
 ) THEN RAISE(ABORT,'ADDON_CAPACITY') END;
END;
CREATE TRIGGER IF NOT EXISTS miniapp_v2_slot_overlap_insert BEFORE INSERT ON miniapp_v2_slots WHEN NEW.active=1 BEGIN
 SELECT CASE WHEN EXISTS(SELECT 1 FROM miniapp_v2_slots s,json_each(s.resources) r
  WHERE s.starts_at<NEW.ends_at AND s.ends_at>NEW.starts_at AND r.value IN (SELECT value FROM json_each(NEW.resources))
  AND (s.active=1 OR EXISTS(SELECT 1 FROM miniapp_v2_orders o WHERE o.slot_id=s.id AND (o.status='paid' OR (o.status IN ('hold','checkout') AND o.hold_until>CAST(strftime('%s','now') AS INTEGER))))))
 THEN RAISE(ABORT,'RESOURCE_OVERLAP') END;
END;
CREATE TRIGGER IF NOT EXISTS miniapp_v2_slot_overlap_update BEFORE UPDATE ON miniapp_v2_slots WHEN NEW.active=1 BEGIN
 SELECT CASE WHEN EXISTS(SELECT 1 FROM miniapp_v2_slots s,json_each(s.resources) r
  WHERE s.id<>NEW.id AND s.starts_at<NEW.ends_at AND s.ends_at>NEW.starts_at AND r.value IN (SELECT value FROM json_each(NEW.resources))
  AND (s.active=1 OR EXISTS(SELECT 1 FROM miniapp_v2_orders o WHERE o.slot_id=s.id AND (o.status='paid' OR (o.status IN ('hold','checkout') AND o.hold_until>CAST(strftime('%s','now') AS INTEGER))))))
 THEN RAISE(ABORT,'RESOURCE_OVERLAP') END;
END;
CREATE TRIGGER IF NOT EXISTS miniapp_v2_slot_capacity_update BEFORE UPDATE ON miniapp_v2_slots BEGIN
 SELECT CASE WHEN NEW.capacity<COALESCE((SELECT SUM(units) FROM miniapp_v2_orders WHERE slot_id=NEW.id
  AND (status='paid' OR (status IN ('hold','checkout') AND hold_until>CAST(strftime('%s','now') AS INTEGER)))),0)
 THEN RAISE(ABORT,'BOOKED_CAPACITY') END;
END;
CREATE TRIGGER IF NOT EXISTS miniapp_v2_block_conflict BEFORE INSERT ON miniapp_v2_blocks WHEN NEW.active=1 BEGIN
 SELECT CASE WHEN EXISTS(SELECT 1 FROM miniapp_v2_orders o LEFT JOIN miniapp_v2_slots s ON s.id=o.slot_id
  WHERE o.starts_at<NEW.ends_at AND o.ends_at>NEW.starts_at AND (o.resource_id=NEW.resource_id OR NEW.resource_id IN (SELECT value FROM json_each(COALESCE(s.resources,'[]'))))
  AND (o.status='paid' OR (o.status IN ('hold','checkout') AND o.hold_until>CAST(strftime('%s','now') AS INTEGER))))
 THEN RAISE(ABORT,'BOOKING_CONFLICT') END;
END;
CREATE TRIGGER IF NOT EXISTS miniapp_v2_room_capacity_update BEFORE UPDATE ON miniapp_v2_resources WHEN OLD.kind='room' BEGIN
 SELECT CASE WHEN EXISTS(SELECT 1 FROM miniapp_v2_orders o WHERE o.resource_id=OLD.id AND o.ends_at>CAST(strftime('%s','now') AS INTEGER)
  AND (o.status='paid' OR (o.status IN ('hold','checkout') AND o.hold_until>CAST(strftime('%s','now') AS INTEGER))) AND (NEW.active=0 OR o.guests>NEW.capacity))
 THEN RAISE(ABORT,'BOOKING_CONFLICT') END;
END;
CREATE TRIGGER IF NOT EXISTS miniapp_v2_addon_capacity_update BEFORE UPDATE ON miniapp_v2_addons BEGIN
 SELECT CASE WHEN EXISTS(SELECT 1 FROM miniapp_v2_orders a,json_each(a.addons) item WHERE json_extract(item.value,'$.id')=NEW.id
  AND a.ends_at>CAST(strftime('%s','now') AS INTEGER) AND (a.status='paid' OR (a.status IN ('hold','checkout') AND a.hold_until>CAST(strftime('%s','now') AS INTEGER)))
  AND NEW.capacity<COALESCE((SELECT SUM(json_extract(other.value,'$.quantity')) FROM miniapp_v2_orders b,json_each(b.addons) other
   WHERE json_extract(other.value,'$.id')=NEW.id AND b.starts_at<=a.starts_at AND b.ends_at>a.starts_at
   AND (b.status='paid' OR (b.status IN ('hold','checkout') AND b.hold_until>CAST(strftime('%s','now') AS INTEGER)))),0))
 THEN RAISE(ABORT,'BOOKED_CAPACITY') END;
END;
CREATE TRIGGER IF NOT EXISTS miniapp_v2_order_addon_update BEFORE UPDATE OF starts_at,ends_at,addons,status ON miniapp_v2_orders
 WHEN NEW.status IN ('hold','checkout','paid') AND json_array_length(NEW.addons)>0 BEGIN
 SELECT CASE WHEN EXISTS(SELECT 1 FROM json_each(NEW.addons) requested LEFT JOIN miniapp_v2_addons a ON a.id=json_extract(requested.value,'$.id')
  WHERE a.id IS NULL OR a.capacity<json_extract(requested.value,'$.quantity')+COALESCE((SELECT SUM(json_extract(used.value,'$.quantity'))
   FROM miniapp_v2_orders o,json_each(o.addons) used WHERE o.id<>NEW.id AND json_extract(used.value,'$.id')=a.id
   AND o.starts_at<NEW.ends_at AND o.ends_at>NEW.starts_at
   AND (o.status='paid' OR (o.status IN ('hold','checkout') AND o.hold_until>CAST(strftime('%s','now') AS INTEGER)))),0))
 THEN RAISE(ABORT,'ADDON_CAPACITY') END;
END;
CREATE UNIQUE INDEX IF NOT EXISTS miniapp_v2_unique_table_name ON miniapp_v2_tables(name,zone);
