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

## Phone responsive fix — 16 November 2026

The owner's 393×853-equivalent phone screenshot exposed overly wide fixed page gutters and the bottom bar meeting the last row of cards. The current app now uses a shared 12–18 px fluid gutter (13.75 px at 393 px), a wider fluid shell, viewport-aware home photos and a four-column layout for wide landscape phones. Forms, menu rails, cards, cart, QR and modals use the same available width.

Navigation clearance is measured from the rendered bottom bar, including both native inset families. Keyboard editing temporarily hides navigation, viewport changes are clamped to the actual window, and SDK inset properties back up missing CSS variables. The calendar's top edge now respects Telegram controls in landscape; chat also reserves the native top inset. Physical page zoom remains available.

Chromium and WebKit each passed 14 viewport profiles from 280 px wide phones through 1024 px tablets, both themes and twelve page/state checks per profile. A separate 393 px regression covers keyboard resize and rotation of the existing form. Results are in `artifacts/responsive/*-results.json`; fixture photos and screenshots stay outside tracked source. WebKit ran headlessly with missing Debian libraries extracted into the task user's browser cache, without changing system packages or app dependencies. This validates layout engines, not every physical phone.

The 88 server tests still pass. No booking rules, database, payment configuration, access gate or frozen legacy assets change. The pre-fix source is tagged `miniapp-before-responsive-20261116`; the prior Worker version is `e4d77a2e-6820-4dc9-9a80-7760df4b641f`.

Responsive assets were published on 2026-11-16 at 20:18 UTC from `571c5a25ce33507426414f0e1e8400eef922290a`, Worker version `4287ce09-81ba-46db-8bb6-052ba001f375`, deployment `1cdc9dac-5e47-437f-91db-fe57e418cea0`. Only `mini_app_assets.py` changed in the 47-module runtime. Live new and frozen legacy HTML/CSS/JS return 200 and match the tested source; unauthenticated API returns 401. [GitHub Actions passed](https://github.com/Murmezz/sunpark-bot/actions/runs/43948309554). No database operation or configuration mutation was performed for this UI fix.

## Whole botanical asset — 16 November 2026

The prior `monstera.webp` was cropped inside its source image, not only by layout. A generated complete-leaf transparent cutout replaces it in the current UI as `monstera-whole.webp` (512×512, 78,346 bytes). The visible alpha silhouette has clear margins on all four sides. The original generated PNG remains in `/workspace/generated_images/exec-a7c520da-efc2-41b6-a047-a5ce03d2fd8f.png`; production conversion preserves transparency. The old asset and frozen legacy module are unchanged. Header text and the leaf now occupy separate grid columns at all breakpoints. Responsive browser checks additionally reject leaf clipping and intersections with either title or subtitle.

The whole-leaf header was published on 2026-11-16 at 20:45 UTC from `7f2b1d2df52b4759016df6665a6e240238e87f56`, Worker version `02b9db6d-db01-4dc2-8e02-7f5de92f6c44`. Current HTML/CSS and legacy HTML return 200 and match source. Chromium and WebKit passed all 14 viewport profiles with the added leaf containment/no-text-overlap assertions; [CI passed](https://github.com/Murmezz/sunpark-bot/actions/runs/43952956438). The original cropped asset and legacy UI remain preserved under the backup tag.

## Restored decoration and loading motion — 17 November 2026

The owner explicitly requested the old `monstera.webp` image back. Its original bytes are restored as the current header asset, contained in the existing separate column. The complete-leaf alternative remains available in source. No new botanical image or unrelated redesign is introduced.

A shared branded bootstrap screen, foreground request loaders, skeleton placeholders, button waiting states, image waiting/failure states and short opacity-only transitions now cover the current app. They follow actual request lifetimes, use existing wordmark/type and Phosphor wave assets, never show invented percentages, and never delay cached navigation. Native reduced-motion preferences disable the motion. A request-scoped completion token prevents stale responses from clearing a newer screen's loader. Initial failures can retry; background chat/payment refreshes retain the existing data. Authentication, payment verification and idempotency are unchanged.

Product Design guidance was used for the existing selected UI and state consistency. Its saved-context preflight found no saved profile. The plugin's shared browser surface is not exposed in this chat; verification uses this repository's existing Chromium/WebKit headless runners, not a claim of a separate Product Design prototype/browser handoff. Canva assets are unnecessary for this code-level motion change.

Restored art and loading states were published on 2026-11-17 at 05:53 UTC from `e6b6722fc2313c38f787c8f6553b7dd9e8ed339e`, Worker version `193d81c4-f95e-4ea1-831a-c25742cfb34e`. Only `mini_app_assets.py` changed in the preserved 47-module runtime. Live current and legacy HTML/CSS/JS return 200 and match source; unauthenticated API returns 401. [CI passed](https://github.com/Murmezz/sunpark-bot/actions/runs/44027124986). No database or deployment binding was changed.
