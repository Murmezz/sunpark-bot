# SUNPARK Mini App — Product Design QA

final result: passed

## Restaurant actions and long-open sessions — 13 November 2026

final result: passed

The user clarified that the restaurant's menu/table/banquet actions were the disliked controls, and confirmed that reopening resolved Messages. Production telemetry showed HTTP 401 responses from the current Worker after a previously successful open; the retained one-hour initData check explained the long-open failure. Fresh Telegram data now exchanges for a launch-bound twelve-hour app session. Signature validation, per-request roles, ownership and replay protection remain in place. Expiry has its own recovery screen; an actual server error retains retry and never becomes a false empty inbox.

The existing coded restaurant screen is the source for this scoped revision. Opened the [before/after comparison](artifacts/restaurant-actions-comparison.webp): both captures are 390 × 844 CSS/pixel dimensions, density 1, light theme, same fixture and 32/56 px Telegram top insets, restaurant at its initial scroll position. The replacement of filled/outlined buttons and movement above the gallery are intentional requested improvements. Also opened the final [320 px dark actions](artifacts/restaurant-actions-after-dark-320.png) and [session recovery](artifacts/session-expired-dark-390.png). Controls are readable at native capture size; no additional crop was needed to inspect their labels and icons.

- **Typography:** retained Manrope and Cormorant families; menu entry uses a clear heading and short description. Table and banquet labels wrap as two readable lines with whole words.
- **Layout:** menu row, two neighboring request actions and telephone link precede the gallery. All three actions remain above the cart launcher at 320/390/820 px. Their existing handlers and contextual returns are retained.
- **Color:** ivory/forest and forest/sage tokens are unchanged. Initial immediate theme-switch captures caught the existing 120 ms button transition; final captures wait for the requested theme and settled transition.
- **Images and icons:** same official restaurant photos, inert gallery and existing Phosphor fork/knife, calendar, people and arrow assets. No generated replacement artwork or native-device chrome is part of the implementation.
- **Copy and states:** clear menu/table/banquet/telephone labels. Empty Messages, server failure/retry, long-open session and absolute expiry are distinct states.

P2 found and fixed: the selected Restaurant direction label wrapped its last letter at 320 px. Narrow-screen tab gaps and padding now preserve a single line; the browser test explicitly checks line boxes, and the final dark 320 px capture confirms the fix. No unresolved P0/P1/P2 visual findings.

Validation: 63 Python tests passed, including session tampering, user/launch binding, absolute expiry, role removal and replay protection. [Focused Chromium results](artifacts/session-restaurant-browser-results.json) passed at 320/390/820 px: menu/table/banquet paths, two-hour Messages, sessionStorage reload, genuine 500/retry, twelve-hour expiry and closing. The complete existing booking/cart/chat/events/staff suite also passed in both themes with no console errors. Physical Telegram testing was not repeated; the user's earlier publication authorization remains applicable.

## Fullscreen top inset correction — 12 November 2026

final result: passed

The user's Android screenshot showed Telegram's floating Close/menu controls covering the Sunpark title and leaf. The earlier header removal left fixed 12/18 px shell padding, so the already defined device/content top safe area was not applied. A browser reproduction failed with the title at 28 px inside an 88 px reserved region.

The shell now adds the existing combined top inset, and sticky menu/form return controls stay below it during scrolling. Typography, leaf size, cards, colors and bottom navigation are unchanged. Opened and inspected the [corrected dark 393 px home](artifacts/safe-area-home-dark-393.png), captured with representative test-only Telegram controls. These overlays are browser evidence and are never bundled into the app.

[Safe-area regression results](artifacts/safe-area-browser-results.json) passed at 320 × 853, 393 × 853 and 820 × 1024, with device/content top inset pairs 32/56, 44/64 and 0/0. The title and leaf clear the reserved region, all four directions remain visible, dynamic inset changes update layout, and restaurant/menu/messages return buttons remain reachable. No page errors or horizontal overflow; 59 Python tests passed. This verifies the screenshot's layout failure using Chromium and SDK mocks; physical Telegram retesting remains with the user. No unresolved P0/P1/P2 visual findings in these inspected states.

## Navigation, compact home and Messages — 12 November 2026

final result: passed

This scoped revision follows the user's latest instructions and supersedes the retained-header and four-tab navigation descriptions below. The unavailable user screenshot was requested for clarification; restaurant category controls and food/drink/bar tabs were restyled using the existing design as the source.

Opened and visually inspected the current 390 × 844 light home, menu, empty Messages and dark home. [Previous/current home comparison](artifacts/navigation-home-comparison.webp) records the intentional removal of the app-owned brand/profile/close header and home inquiry row, restoration of the compact leaf and reduction of bottom navigation to two tabs. [Menu](artifacts/navigation-menu-light-390.png) uses divided category rows and underlined group tabs. [Empty Messages](artifacts/navigation-messages-light-390.png) provides booking, banquet and inquiry actions, secondary information and administrative access.

- **Typography:** retained Cormorant display and Manrope controls; Sunpark is the home title and app launch label. Category labels, counts and return labels remain readable at all tested widths.
- **Layout:** four directions remain visible at 320 × 640. The leaf occupies at most 118 px of width. Cart appears only in restaurant/menu. Visible return buttons connect menu to restaurant, category to menu and forms to their entry context. The only bottom tabs are Home and Messages.
- **Colors and assets:** existing ivory/forest and forest/sage palettes, original leaf and official service photos; no replacement imagery or icon family introduced. Gallery images remain inert.
- **Copy and states:** true empty Messages offers three restaurant/contact actions. Server errors remain distinguishable from an empty inbox. The legacy production schema issue was fixed without migrating tickets. Management remains restricted to existing administrators.

Validation: 59 Python tests passed against a fixture matching the actual legacy tickets schema. Both browser suites passed at 320/390/820 px in light/dark themes with no console errors or horizontal overflow. [Navigation results](artifacts/navigation-browser-results.json) cover entry/return paths, empty-state actions, two tabs, scoped cart, old/unsupported Telegram clients and close. Existing booking, calendar, cart, chat, events and staff workflows also passed. No unresolved P0/P1/P2 visual findings in the inspected states. Headless Chromium and SDK mocks do not establish physical-device testing; the user's existing publication waiver remains applicable.

## Whole-complex hub and requested corrections — 12 November 2026

final result: passed

The user explicitly changed the hierarchy from a restaurant-led home to an equal four-direction SUNPARK hub, retained the in-app header, requested removal of Telegram's native header, and preserved restaurant forms while removing external booking. This section supersedes the previous service-extension layout and link behavior below.

Opened evidence: [old/new home at identical 390 × 844 viewport](artifacts/complex-home-comparison.png), [all four direction pages](artifacts/complex-directions-light.png), [small dark home](artifacts/complex-home-dark-320.png), [hotel tariffs](artifacts/complex-hotel-prices-light-390.png). The actual source room and restaurant images were also opened. The comparison was assembled into the same input; the requested structural changes are intentional, not accidental deviations from the former home.

- **Typography:** existing Manrope interface and Cormorant display family; readable card labels, telephone numbers and tariff rows at 320/390/820 px. The display heading introduces the whole complex. No restaurant-only wording or Grill Bar mark remains on the shared home.
- **Layout:** four equal cards in a 2 × 2 grid, all visible above navigation at 320 × 640. Restaurant booking/banquet actions moved inside its own direction. The preserved header now stays visible while scrolling, with profile and own close control. Native forms retain back/profile/close controls without overlap at 320 px; chat has its own close control.
- **Color:** previous ivory/forest and dark forest/sage tokens are retained. The official SUNPARK complex logo uses its original colored light and white dark variants.
- **Images:** original photographs from the source site; first hotel image is the bright room `IMG_9324.png`. Gallery photos are inert elements, without anchor, click handler or source-site fallback. Arrows and swipe remain functional. Existing Phosphor icons are retained.
- **Copy:** descriptions are available directly in the application and bot. External registration buttons, source/footer copy and links to source/pricing pages are removed. Service actions use telephone links; restaurant menu, table booking, banquet and chat stay internal. The season of the wake tariff remains visible for accuracy.

Validation passed: 57 Python tests; full workflow regression suite and service suite at 320/390/820 px, both themes; no page errors or horizontal overflow. Tests cover inert photo clicks with no new browser tab/openLink call, phone-only service links, restaurant entry points, correct hotel cover, four visible home cards, fullscreen request and close, plus old-client and `UNSUPPORTED` fallback. The Telegram SDK is mocked, so these are API integration checks rather than a physical-phone claim. Per Telegram's official API documentation, fullscreen is available from Bot API 8.0 and can be unsupported by the client; such clients retain their native bar. User authorization to publish without physical-device testing remains recorded in `SERVICES.md`.

No unresolved P0/P1/P2 visual findings. One test-harness route callback initially bound Playwright's request object over the intended client mode; corrected the callback and re-ran old/unsupported scenarios successfully. This was a test setup issue, not a production-client finding.

## Service extension — 12 November 2026

final result: passed

This is a scoped extension of the previously selected visual system. There is no separate supplied mock of the new service pages, so this review checks preservation of the selected design and the quality of the extension; it does not claim a pixel clone of an unavailable service-page mock.

Evidence opened and compared together:

- [Existing home against updated home, same 390 × 844 viewport and state](artifacts/services-home-comparison.png). The top-level home composition is preserved; the three new cards follow the existing restaurant actions.
- [Three service screens, light theme](artifacts/services-sections-comparison.png) and [dark theme](artifacts/services-sections-dark-comparison.png). Each source is captured at 390 × 844 CSS pixels, deviceScaleFactor 1. The SDK mock's native controls are excluded from the app-owned design.
- [Home service cards](artifacts/services-home-list-light-390.png) and [room tariffs](artifacts/services-hotel-prices-light-390.png), examined at native size for wrapping, price alignment and labels.
- The real wake, wave and hotel photographs were opened separately and checked against their use in the rendered interface. Their source galleries and tariff sources are listed in `SERVICES.md`.

Initial P2 findings and fixes: square website thumbnails cropped the surfer's head in the wide gallery; the first composition put booking/call actions below the first mobile viewport. Gallery JPEGs now use the small original full-composition files, header spacing is tighter, and the price summary and actions precede the longer description. Revised captures show the subject, tariff summary, booking and telephone clearly at 390 px. Room PNGs use the site's smaller published variants. Home thumbnails were captured after actual image loading.

Required surfaces: **Typography** retains the existing Manrope controls, weights and price numerals; the Cormorant home hero is unchanged. **Layout** retains 26/20 px gutters, 48 px gallery controls, existing tabs/dividers/buttons and persistent navigation; price rows wrap without horizontal overflow at 320/390/820 px. **Colors** use existing ivory/forest and dark forest/sage tokens in both themes. **Assets** are the actual site photographs, original logo and existing Phosphor icons. **Copy** distinguishes roubles from the menu's kopecks, per-person sessions from individual sessions, the summer 2026 wake tariff, equipment charges and the hotel's two source phone numbers. No availability or booking confirmation is invented.

No unresolved P0/P1/P2 visual findings. Publication validation is separate: automated Chromium and mocked Telegram cannot establish a physical iOS/Android Telegram pass. On 12 November 2026 the user explicitly authorized publishing now without the real-device check requested by the supplied `telegram-webapps` skill. This authorization permits release; it does not establish a physical-device test pass.

Validation: 57 Python tests passed; service and existing workflow browser suites passed at 320/390/820 px and both themes. Source images load from the exact CSP-allowed website host; photo arrows, tab navigation, return state, telephone links and `openLink` work. The complete SDK mock is loaded only by tests. The shared browser could not initialize (`the gaas-browser node_repl sandbox cannot be disabled`); the evidence above comes from real headless Chromium against the local fixture server.

## Findings and revisions

- **P1, booking footer:** the initial calendar/time composition put the primary action behind bottom navigation. Added a sticky footer above navigation and corrected calendar/header spacing. Verified action visibility at 320, 390 and 820 px, including a reduced-height conversation viewport.
- **P2, conversation density:** repeated metadata and a separate timestamp line made the conversation heavier than the reference. Replaced the header with a compact request summary, grouped messages by date, put timestamps alongside message content and removed empty-toolbar spacing. Re-captured and compared the revised conversation.
- **P2, navigation and reading state:** returning through a form or polling chat could reset context. Added retained request values, per-conversation message drafts, stale-response guards, unchanged-message DOM preservation and scroll anchoring. Real browser polling verified that an incoming message preserves the reading position and offers a jump button.
- **P2, active time typography:** only the regular display face was available. Bundled an official Cormorant Garamond 600 numeral subset; active wheel numbers now use a real semibold face. Re-captured both themes at all three widths.

No unresolved P0/P1/P2 findings. Remaining small differences are listed below as intentional data/interaction constraints rather than pixel-equivalent claims.

## Exact visual targets and evidence

The user retained the selected third SUNPARK direction, asked for native Mini App adaptation, and specified scrolling hours/minutes, future calendar dates, a familiar conversation and complete administrative screens. These are scoped revisions of the selected direction, not a replacement visual system.

- Booking reference: `/workspace/generated_images/exec-8038acd1-3bdb-418d-a6b3-ee08bfe5f3ba.png`.
- Conversation reference: `/workspace/generated_images/exec-a3b4a55e-30cd-4d83-8930-a9b5ce277707.png`.
- [Booking comparison](artifacts/compare-booking-v2-final.webp), [wheel/footer detail](artifacts/compare-booking-v2-detail.webp).
- [Conversation comparison](artifacts/compare-chat-v2-final.webp), [header/message detail](artifacts/compare-chat-v2-detail.webp).

The actual source images and rendered implementation were opened and inspected, then combined side by side. Sources are normalized from 852 × 1844 to 390 × 844; browser viewport is 390 × 844 CSS pixels at deviceScaleFactor 1. Full comparison canvas is 780 × 872 with a 28 px label strip. No phone or browser chrome is included.

Matched booking state: November 2026, today 10 November, Saturday 14 November selected, 19:30, first of three steps. Matched conversation fixture: booking №24, 14 November at 19:30, four guests, the same two message bodies, 14:20/14:22 timestamps and a PDF at 14:23. All data is isolated test data, not a production booking.

## Required fidelity surfaces

- **Fonts/typography:** Cormorant Garamond editorial headings and time values; Manrope interface and body text. Real 600 numeral weight is bundled. Body/form text is 16–17 px, metadata is smaller, headings retain the approved hierarchy. Checked wrapping, number alignment, selected states and focus indicators.
- **Spacing/layout:** compact centered brand header on workflow screens, seven-column calendar, independent wheel columns, a clear primary action and persistent navigation. Conversation header, summary, message sides, dates and composer follow the revised target. Forms and lists use grouping/dividers instead of Telegram message dumps.
- **Colors/tokens:** retained warm ivory/forest light palette and approved forest/ivory/sage dark palette. All controls, fields, dialogs, conversation bubbles and Telegram panels follow automatic theme changes. Semantic error colors remain legible in both themes.
- **Image quality/assets:** original supplied SUNPARK logo and existing ImageGen foliage are retained. New workflow screens require no new raster illustrations. Icons are official Phosphor assets of the same family, including PDF/photo attachments. Fonts and assets are locally bundled.
- **Copy/content:** visible controls use application-specific Russian labels, Moscow booking time, honest availability/confirmation language, preserved drafts and inline field errors. The application never infers booking confirmation from the native message-status field.

Intentional/P3 differences: real wheel neighbors are 29/31 around minute 30 (the generated reference repeated 00); the current day remains identifiable and selectable for future times; a replied conversation displays its actual response status instead of pretending a booking is confirmed. PDF size is omitted when historical Telegram data does not contain it. Calendar tap rows and message spacing are slightly roomier than the generated image for practical use. No additional P3 iteration is required for handoff.

## Functional validation

- **52 Python tests passed:** complete booking submission and replay protection, Russian phone validation before writes, automatic Telegram identity, event limits, manual registration beyond the self-registration limit, duplicates, event edit version conflicts, past-event edits, manager CRUD/protected admins, Unicode Russian search, ticket pagination, guest cancellation, ownership checks and media permissions.
- Chromium at **320, 390 and 820 px**, both themes, no unexpected console errors or horizontal overflow. [Browser results](artifacts/browser-results.json).
- Full booking through actual calendar/wheel controls, return to previous steps without losing contact data, review and submission; own conversation and staff claim/reply/note; full template sheet; event creation using calendar/time dialogs, registration toggle, manual addition and deletion; manager add/rename/delete; address/contact links.
- A **390 × 500**-style reduced-height viewport check (also at the other tested widths) keeps the composer above navigation. This simulates keyboard-sized space; it is not a physical-phone claim.
- A rejected company registration (HTTP 409, insufficient capacity) scrolls its error into view above navigation without dropping the entered values.
- Long-chat polling preserves scroll position and exposes a jump-to-new control. Older-history pagination is covered by API integration tests.
- Cart/price variant/quantity/removal/persistence, all bar categories and deep-scrolled fixed dish modal remain covered by browser checks.
- Actual Pyodide executed the upload method with native Blob/FormData and mocked Telegram, including byte content, multipart fields, opaque upload token and temporary-message deletion.

No real guest messages, admin broadcasts or production fixture bookings were created during testing.

## Environment and handoff scope

Existing Python Worker, D1 records and hosting are retained. Access remains admin-only through `/admin → Разработка → SUNPARK · Mini App`. Native bot handlers remain compatible.

The managed environment exposes no shared desktop/browser control. Browser evidence was produced by real Chromium against a loopback fixture server. It does not claim a shared Desktop window or physical iOS/Android Telegram clients were tested. The user-requested production preview is the existing bot, not a separate Sites deployment.
