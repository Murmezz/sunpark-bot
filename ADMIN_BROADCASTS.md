# Admin broadcast queue

The bot sends queued broadcasts to every manager ID returned by `manager_ids(cfg)`. Do not read or expose the bot token.

## Queue a message

Use the connected Cloudflare API tool to run a D1 query against the `sunpark-bot-db` database. The database ID is in `wrangler.toml`; resolve the account ID with Cloudflare's `GET /accounts` endpoint.

Send HTML in `body` (Telegram HTML parse mode, maximum 4096 characters). Generate one unique request key for the request and reuse it if retrying the same tool call.

```json
{
  "sql": "INSERT INTO admin_broadcasts(request_key,body,created_by) VALUES(?,?, 'assistant') ON CONFLICT(request_key) DO NOTHING",
  "params": ["<b>Update title</b>\n\nMessage text", "UUID-FOR-THIS-BROADCAST"]
}
```

Call `POST /accounts/{account_id}/d1/database/{database_id}/query` with this object as the JSON body. The bot's scheduled Worker processes the queue once per minute, so delivery can take up to a minute.

## Check delivery

After the next scheduled run, query:

```sql
SELECT b.id,b.status,d.manager_id,d.status AS delivery_status,d.last_error
FROM admin_broadcasts b
LEFT JOIN admin_broadcast_deliveries d ON d.broadcast_id=b.id
WHERE b.request_key=?
ORDER BY d.manager_id;
```

Broadcast status is `pending`, `sent`, `partial`, or `failed`. Each manager delivery is tracked as `pending`, `sending`, `sent`, or `failed`. Report only the statuses returned by D1; do not claim delivery when the queue is still pending.
