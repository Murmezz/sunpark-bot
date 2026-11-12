# SUNPARK Mini App — Product Design QA

final result: passed

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
