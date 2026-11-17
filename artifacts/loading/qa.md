# SunPark loading-state QA

Scope: restore the owner-selected original botanical image inside the existing responsive header; add loading motion to the current Mini App. The forest/ivory palette, Cormorant/Manrope type and supplied Phosphor assets remain the visual reference.

Inspected rendered bootstrap and section-loading screenshots at 393 px in dark/light themes. Branded startup, wave motion, skeleton spacing and navigation remain readable. The restored image is the exact original asset; the header grid contains its element and separates it from both text lines.

Chromium and WebKit loading suites passed at 280×653, 393×853 and 844×390, including reduced motion, real delayed bootstrap/section/photo requests, initial and section retries, failed checkout button restoration, stale navigation responses, image failure recovery and background chat refresh without content replacement. CSS animations are present while waiting and absent under reduced-motion preferences. No browser JavaScript errors.

The existing 14-profile responsive suites pass in both engines, covering the restored header, forms, menu, calendar, time drums, QR and chat. The core concept flow and preserved legacy shell pass. The 88 Python tests pass; server code is unchanged.

No physical Telegram device or live payment was exercised. The Product Design shared browser tool is not exposed here; these are this repository's headless browser checks of the actual UI, not a separate prototype handoff.

Result: repository UI checks passed.
