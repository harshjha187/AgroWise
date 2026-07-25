# App Store / Play Store — Listing Prep

Draft copy and the submission checklist for both stores. AgroWise Field is currently a PWA (installable via "Add to Home Screen") — to submit to the App Store or Play Store as a listed app (not just a web install), it needs native wrapping first (see `deploy/NATIVE_WRAPPING.md`). This file is the content/copy side; that file is the packaging side. Neither requires the other to be done first — write the listing whenever, wrap natively whenever, submit once both are ready.

---

## App identity

- **App name:** AgroWise Field
- **Subtitle / short description (30 chars, iOS):** IoT Soil Health Companion
- **Category:** Utilities (or Agriculture / Weather, if the store offers it — Apple has no dedicated Agriculture category; Google Play does have "Weather" and no Agriculture-specific one either, so Utilities or Productivity is the practical choice on both)
- **Bundle ID / package name (placeholder — pick a real reverse-domain identifier you control):** `com.yourorg.agrowise.field`

## Short description (Play Store — 80 chars max)

> Real-time soil health monitoring, land classification & recovery guidance.

## Full description

> AgroWise Field is the mobile companion to the AgroWise IoT Soil Health Analysis System. Connect it to your AgroWise backend (running on a laptop, home server, or your own hosted instance) to see live readings from your ESP32 soil sensor rig — Nitrogen, Phosphorus, Potassium, Soil Moisture, pH, and Temperature — updated automatically.
>
> AgroWise doesn't just show raw numbers. Every reading is scored into a single 0–100 Soil Health Score, classified as Fertile, Moderate, or Barren, and turned into a concrete recovery plan: which fertilizer to apply and how much, when to irrigate, and how to treat problem soil — not just "your nitrogen is low."
>
> Features:
> • Live soil health score and classification
> • Full reading history with trend sparkline
> • Manual reading entry (no hardware required to try it)
> • Offline-safe: readings taken without a connection are queued and synced automatically once you're back online
> • Dark mode
> • Works entirely with your own self-hosted backend — no AgroWise cloud account, no data leaves your network unless you choose to host it publicly
>
> Requires an AgroWise backend server (open source, see the project repository) running on your local network or a server you control.

## Keywords (Play Store / App Store keyword field)

`soil, agriculture, farming, IoT, sensor, NPK, moisture, pH, ESP32, precision agriculture, crop, fertilizer, irrigation`

## Screenshots checklist

Both stores require actual device screenshots, not mockups. Capture these once the app is wrapped and installed on a real or simulated device (this repo's `run` skill / the iOS Simulator + Android emulator sessions used earlier in this project are exactly the right tool for this):

- [ ] Home screen — live score gauge + classification badge, real (or simulated) data visible
- [ ] Recovery recommendations list
- [ ] History page with sparkline
- [ ] Add Reading (manual entry) page
- [ ] Setup page (blur/redact the API key field before capturing!)
- [ ] Dark mode variant of at least one screen

Apple requires specific sizes per device class (6.7", 6.5", 5.5" iPhone; 12.9" iPad if supporting tablets). Google Play requires at minimum 2 screenshots, JPEG/PNG, 16:9 or 9:16.

## App icon

Already have `mobile-app/icons/icon-192.png` and `icon-512.png` (used for the PWA manifest). Both stores need specific additional sizes/formats:
- **iOS:** 1024×1024 PNG, no alpha channel, no rounded corners (Apple applies the mask) — export a flat version from the same source art.
- **Android:** adaptive icon (foreground + background layers) at 512×512, plus the legacy 512×512 — Android Studio's Image Asset tool generates all densities from one source image.

## Privacy policy

**Required by both stores**, even for a simple utility app. See `deploy/PRIVACY_POLICY.md` — you'll need to host that content at a real, publicly reachable URL (e.g. a page on your own domain, or a free static host) and paste that URL into both stores' submission forms. A repo file alone isn't enough for the store review process — it has to be a live URL.

## Age rating / content rating questionnaires

Both stores ask a standard questionnaire (violence, gambling, user-generated content, data collection, etc.). AgroWise Field collects no personal data and has no user-generated content shared with other users — expect the lowest rating tier (4+ / Everyone) on both, assuming you answer the data-collection questions per `PRIVACY_POLICY.md`.

## Review-specific gotchas to plan for

- **Apple** will ask what happens with no backend configured — make sure the onboarding/"Explore in Demo Mode" or empty-state ("AWAITING DATA" / "connect to the AgroWise backend in Setup") is reachable and doesn't look broken, since reviewers won't have a real backend to point it at.
- **Apple** requires `NSAppTransportSecurity` exceptions to be justified if you allow plain-HTTP backend URLs (which this app does, by design, for LAN-only use) — see the cleartext-traffic notes in `deploy/NATIVE_WRAPPING.md`.
- **Google Play** requires a Data Safety form matching what's actually in `PRIVACY_POLICY.md` — keep them in sync if either changes.

## Submission checklist (do this once both listing copy and native wrapping are ready)

- [ ] Apple Developer Program enrollment ($99/year) — apple.com/developer
- [ ] Google Play Console account ($25 one-time) — play.google.com/console
- [ ] App Store Connect: create the app record, fill in this listing copy, upload screenshots + icon, attach the Xcode-built `.ipa` via Xcode Organizer or Transporter
- [ ] Play Console: create the app record, fill in this listing copy, upload screenshots + icon, upload the signed `.aab` from Android Studio
- [ ] Submit for review (Apple: typically 1–3 days; Google: hours to a few days)
