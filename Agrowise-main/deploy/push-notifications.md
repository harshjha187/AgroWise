# Push Notifications — Integration Plan

Goal: when a critical alert fires (e.g. land flips to BARREN, per `analysis_engine.build_alerts()`), notify the user even if the app isn't open. Two genuinely different paths — read the first section before picking one, since they have very different account requirements.

---

## The two paths, and which needs what

| | Web Push (VAPID) | Native Push (FCM / APNs) |
|---|---|---|
| Works on | Any browser tab, and installed PWAs on Android + iOS 16.4+ | Only after native-wrapping (`deploy/NATIVE_WRAPPING.md`) |
| Requires an account? | **No** — VAPID keys are self-generated, no registration with anyone | **Yes** — a Firebase project (free) for Android/FCM, and an Apple Developer Program membership ($99/yr) for iOS/APNs |
| Requires native wrapping? | No — works with the PWA as-is | Yes |
| Delivery reliability | Good on Android; iOS Safari's web push is real but historically less consistent than native APNs | Best — this is what real production apps use |

**Practical read:** Web Push is the only one of these two I can actually build right now without you creating anything — it's genuinely account-free. Native push needs the same accounts as the App Store/Play Store submission (`deploy/STORE_LISTING.md`), so it naturally happens *after* you decide to native-wrap and enroll in those programs. This file documents both; only Web Push is "ready to build on request" today.

---

## Path A: Web Push (buildable now, not yet built)

This is intentionally left as a documented plan rather than shipped code, for two reasons: (1) it needs a new DB table, new API routes, frontend permission UX, and a service worker change — a real feature worth its own focused pass, not a rushed addition on top of everything else in this session; (2) browsers require a "secure context" for the Push API — `localhost` is exempted (so it's testable in local dev), but the LAN-IP testing pattern used throughout this project (`http://192.168.x.x:5001`) is **not** a secure context, so it can't be verified from a phone on the same WiFi until the backend is actually deployed behind HTTPS (`deploy/DEPLOY.md`). Building it before that deployment exists means shipping something untestable in the project's normal dev loop.

### What it would take

1. **Generate a VAPID keypair once** (self-generated, no account):
   ```bash
   pip install pywebpush py-vapid
   vapid --gen  # writes private_key.pem / public_key.pem
   ```
2. **Backend (`server.py` / `database.py`):**
   - New table `push_subscriptions (id, endpoint, p256dh, auth, created_at)`.
   - `POST /api/push/subscribe` — accepts the browser's `PushSubscription` JSON, stores it (behind the existing `X-API-Key` auth).
   - In `ingest_reading()`, after `db.insert_alerts(...)`: for any alert with `level == "critical"`, loop stored subscriptions and call `pywebpush.webpush(subscription_info, data=json.dumps({...}), vapid_private_key=..., vapid_claims={"sub": "mailto:you@example.com"})`. Wrap in try/except per-subscription — a dead/expired subscription shouldn't break the request.
3. **Frontend (both apps' `index.html`):**
   - A "Enable notifications" button (Settings/Setup page) that calls `Notification.requestPermission()`, then `navigator.serviceWorker.ready`, then `registration.pushManager.subscribe({userVisibleOnly: true, applicationServerKey: VAPID_PUBLIC_KEY})`, then POSTs the resulting subscription object to `/api/push/subscribe`.
   - Note: **the web dashboard has no service worker today** (only `mobile-app/sw.js` exists) — Web Push requires one, so the dashboard would need a minimal service worker added first if you want push there too.
4. **Service worker (`mobile-app/sw.js`):** add a `push` event listener that calls `self.registration.showNotification(title, {body, icon})`.

None of this is wired up yet. If you want it built, say so explicitly and confirm you're fine testing it only after HTTPS deployment (or accept Chrome-desktop-via-localhost as the dev-loop substitute).

---

## Path B: Native Push (FCM + APNs)

Only relevant once native-wrapped (`deploy/NATIVE_WRAPPING.md`) and enrolled in both developer programs.

1. **Firebase (Android/FCM):** create a free Firebase project → add the Android app (package name from `capacitor.config.json`) → download `google-services.json` into the wrapped Android project → add `@capacitor/push-notifications` plugin → Firebase gives you a server key to send from your backend.
2. **APNs (iOS):** requires the paid Apple Developer Program → create an APNs Auth Key (`.p8` file) in the Apple Developer portal → same `@capacitor/push-notifications` plugin handles registration on the client side → backend sends via APNs HTTP/2 API using that key (or via Firebase Cloud Messaging, which can relay to APNs too, unifying both platforms behind one backend integration).
3. **Backend integration point:** same as Path A — after `db.insert_alerts()` in `server.py`, for critical alerts, call out to FCM's send API (which can target both Android and, via APNs relay, iOS devices) instead of `pywebpush`. The device-token storage table replaces the web-push subscription table (`device_tokens (id, platform, token, created_at)`), registered via the Capacitor plugin's `addListener('registration', ...)` callback POSTing the token to a new `/api/push/register-device` route.

This path is naturally gated on you completing the App Store/Play Store account setup anyway, so there's no way to build ahead of that.

---

## Recommendation

If you want a working "critical alert while the app is closed" experience soonest, and are willing to deploy behind HTTPS first (`deploy/DEPLOY.md`), **Web Push is the faster, account-free path** — ask for it explicitly once the domain/TLS setup from `DEPLOY.md` is live, and it can be built and actually tested end-to-end at that point.
