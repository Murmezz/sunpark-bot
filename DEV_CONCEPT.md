# SunPark Mini App — development integration

The requested concept is being integrated into the existing administrator-only Mini App at `/admin → Разработка → Sunpark`. The old interface remains available at `/app/legacy`; it is frozen from the live version, not regenerated from the changed UI.

Backup completed before editing:

- Source commit `f822404072b39c3bb556024c4ca53b1ffe66a703`.
- GitHub branch `backup/miniapp-before-full-concept-20261115` and annotated tag `miniapp-before-full-concept-20261115`.
- Live Worker version `0020f18b-4b87-4065-b89f-8cdc131f7db0`.
- Private full backup `/workspace/backups/sunpark-miniapp-before-concept-20261115.tar.gz`; SHA-256 `d8a54c01861fbbeac149a4c794b9b414acb3155156c6d9818e92569ae5dc8190`.
- Full D1 SQL export restored into an isolated SQLite database and passed integrity checking. No database rollback was performed. SQL/Worker raw backups contain private operational data and are kept outside Git.

Implementation scope: new UI with actual catalogue and current session/auth; automatic availability for wave/wake/hotel; full-payment checkout contract; prepaid restaurant preorder and staff QR/table workflow; existing restaurant/banquet messaging, team and events stay available. No guest wishes, wave-manager chat, manual approval, or guest cancellation/refund action.

There is no payment provider secret in the current Worker. Checkout must fail closed until `PAYMENT_PROVIDER_TOKEN` is configured; never manufacture paid bookings or active QR codes. Slots, room numbers and restaurant tables must come from configured inventory rather than the gallery's demonstrative data. Existing `MINIAPP_ADMIN_ONLY` remains enabled.

New records use the `miniapp_v2_` namespace. Migrations are additive; old tickets, messages and menu configuration are retained. The gallery remains the visual reference and feedback channel.

Baseline: 63 server tests pass. Chromium and Playwright are available for loopback fixture tests; no physical Telegram device is available. Closed administrator development is for that device review; no guest rollout is requested.

## Setup and rollback

Apply the two SQL migrations in filename order. They create only `miniapp_v2_*` tables, indexes and triggers; the second file seeds verified catalogue prices and known installations. It does **not** publish slots or invent room/table numbers. Reapplying is safe through `IF NOT EXISTS` and `INSERT OR IGNORE`.

In the administrator UI, open Messages → Management → Services and resources. Configure real room numbers with hotel rates, restaurant tables, staff Telegram IDs, stock and wave/wake slots. Slots sharing an installation or trainer cannot overlap. A slot's capacity is places for group rates and one booking for a private rate. Closing sales does not cancel an existing payment hold. Blocks cannot displace occupied bookings. Unblocking preserves the block record as inactive.

`PAYMENT_PROVIDER_TOKEN` must be a Cloudflare secret for a Telegram-supported RUB provider. Optional `PAYMENT_PROVIDER_DATA` is passed through to that provider. Provider-specific receipt/configuration requirements and a real test-mode payment need verification before enabling guest access. Current deployments retain the administrator-only gate. The callback's `paid` value never settles an order. Duplicate charge IDs are rejected, and capacity conflicts after a late payment enter `payment_review` for manager handling; no automatic refund is implemented.

Rules (`miniapp_v2_settings.rules`): hold length is a backend setting (default 900 seconds, no invented countdown shown); guest transfer and children's accommodation start disabled; restaurant lead time starts at zero. Transfers keep the original booking until one atomic update succeeds and currently support the same format/category and paid amount. Different-price transfers require a future settlement policy. No restaurant table is reserved in advance: the staff member chooses an available fitting table at arrival.

Restore code by deploying the backup tag or original Worker version. The legacy screen is available without a rollback. Additive v2 tables can remain when restoring old code. Do not restore the full SQL export over current operational data without a separately authorized database recovery; doing so would erase later work. The backup manifest includes the original D1 bookmark and module hashes.

## Verification

- 88 Python unit tests, including 25 booking/payment/seating tests with isolated SQLite and mocked Telegram calls.
- Chromium loopback browser tests at 320×640, 390×844 and 820×1024, both themes: wave/time drums, hotel date range and whole-period price, real-menu cart, prepaid restaurant flow, server-only payment confirmation, QR, seating/completion and inventory forms. No JavaScript errors.
- Fullscreen safe-area regression at widths 320, 393 and 820 with device/content top inset pairs 32+56, 44+64 and 0+0; legacy Mini App boots with its original navigation.
- Generated static bundle passes JS syntax checking; original frozen legacy constants match the backup source.

No physical Telegram device or real provider payment has been tested. This is a closed development publication for the owner's device review, not a guest release. Tests use local fixture inventory only. Browser QA photos are verified source photographs routed locally; no fixture code ships in the Worker.

## Closed development publication

Published 2026-11-15 at 20:15 UTC to `sunparkbot`, Worker version `e4d77a2e-6820-4dc9-9a80-7760df4b641f`, deployment `42ac076e-cb96-4edb-8d94-1f7d5f176968`. Runtime source: `508881720cd6af0aede1c2bbe30c31a6bf73f39d`. The content-only API upload preserved all 47 module paths (including existing runtime packages), compatibility settings, D1 binding and existing secrets. Uploaded source hashes match the tested files.

Applied 48 additive migration statements. Verification found 15 source-price rates and zero v2 orders, published slots, room records or restaurant tables. The existing ticket count stayed 18. No fixture records were inserted into D1.

The new and legacy HTML/JS/CSS endpoints return HTTP 200 and exactly match the tested bundles. Icons return 200; unauthenticated API access returns 401. Chromium also loaded the deployed shell successfully. Python HTTP checks use the descriptive `SunPark-Development-Verification/1.0` user agent because Cloudflare rejects default urllib clients on workers.dev ([Cloudflare error 1010](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-1xxx-errors/error-1010/)). No security setting was changed. Authenticated business flows were checked on isolated local data; the owner's physical Telegram review remains outstanding.

GitHub Actions passed for the runtime commit: [Tests](https://github.com/Murmezz/sunpark-bot/actions/runs/43756666083). Source review: [draft PR #7](https://github.com/Murmezz/sunpark-bot/pull/7). Main branch remains at the backup commit.
