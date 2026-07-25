# AgroWise — Rules

Guardrails for anyone (human or AI) working on this codebase. Companion to [PRD.md](PRD.md) (what & why) and [ARCHITECTURE.md](ARCHITECTURE.md) (how it's built). Rules below reference the original invention disclosure form where a rule exists specifically to protect the claimed novelty.

---

## 1. Core pipeline & scoring

**Do**
- Keep `analysis_engine.py` as the single source of truth for validate → filter → score → classify → recommend → alert. Any scoring/threshold change belongs there first.
- Keep the 6 parameter weights (`PARAMS[*]["w"]`) summing to exactly 1.0 — `analysis_engine.py`'s own self-test asserts this; run `python analysis_engine.py` after touching weights.
- Preserve the **combined-threshold BARREN rule** (N, P, K sub-scores all < 35 → forced BARREN regardless of aggregate score) as a hard override in `classify()`, not folded into the weighted average. This is the invention disclosure's core novelty claim (§3.1) — diluting it into the score would remove the very thing that makes barren-but-not-obviously-so land detectable.
- Keep all intelligence server-side. The ESP32 firmware only reads sensors and POSTs raw JSON — it must never gain scoring/classification/recommendation logic. This is deliberate (README/ARCHITECTURE): it keeps firmware small and lets scoring be fixed without re-flashing hardware.
- When the web dashboard's client-side fallback engine needs a change, mirror it in `analysis_engine.py` too (and vice versa). They must agree — the fallback exists only for when the backend is unreachable, not as a second implementation to diverge from.
- Keep any "previous reading" lookup (EMA noise filtering, BARREN-transition alert detection) scoped by `device_id` — `database.get_latest(device_id=...)`, not the unscoped global-latest. With multiple physical ESP32 units posting to one backend, "previous" must mean that same device's previous reading; blending across devices produces meaningless filtered values and false/missed alert transitions.

**Avoid**
- Don't add a new "raw value only" display mode — the entire point of this system (per PRD problem statement) is replacing raw dumps with an interpretable score + recommendation. Prior art already does raw display; that's what we're differentiated against.
- Don't let recommendations become vague ("apply more fertilizer"). Every recommendation must carry a concrete, dosed action (kg/acre, mm/acre, etc.) — that specificity is the product's advisory value per PRD §5.3.
- Don't silently change classification thresholds (80/50) or the barren sub-score cutoff (35) without updating `analysis_engine.py`'s self-test, the client-side mirror in both frontends, and the README scoring-methodology table together. These three are known to fall out of sync if only one is touched.

---

## 2. Security

**Do**
- Require `X-API-Key` on every `/api/*` route, including `GET` endpoints like `/api/health` and `/api/summary` — they reveal farm-level data and are not exempt.
- Compare API keys with `hmac.compare_digest`, never `==` (timing-attack safe comparison is already in place — keep it that way for any future auth code).
- Keep CORS same-origin by default. Cross-origin access is opt-in only, via `AGROWISE_ALLOWED_ORIGINS` — never fall back to a wildcard `CORS(app)` for convenience.
- Keep rate limits in place, especially the tight 5/min on `DELETE /api/readings` (it's irreversibly destructive — wipes the entire dataset).
- Keep `.api_key`, `agrowise.db`, and `.venv` gitignored. Never commit a real API key, even a "just for testing" one, into a tracked file.
- When adding a new backend route, thread the API key through *all* callers: `simulator.py` (`--api-key`), `firmware/AgroWise_ESP32.ino` (`API_KEY` constant), and both frontends' `X-API-Key`/`authHeaders()` helpers. A route that's protected server-side but not called with the key by every client is a silent breakage, not a security win.

**Avoid**
- Don't loosen the security headers (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`) or the `before_request` API-key hook to "make testing easier." Test with the real key (`cat backend/.api_key` or the printed startup banner) instead.
- Don't reintroduce `debug=True` on `app.run()` — it exposes stack traces and an interactive debugger to anyone who can reach the port.
- Don't assume plain HTTP is "fine forever." It's a documented, deliberate tradeoff (see README § Security) because the ESP32's `HTTPClient` doesn't do TLS well — it is not an oversight to silently "fix" by adding `ssl_context='adhoc'` without also updating firmware, simulator, and both frontends' backend-URL handling, and without telling the user about self-signed cert warnings.

---

## 3. Frontend conventions

**Do**
- Keep both `web-dashboard/index.html` and `mobile-app/index.html` as single self-contained files (inline CSS/JS, CDN `<script>` tags for the few external libs). No bundler, no npm dependency tree, no build step — the whole project must stay runnable via `pip install -r requirements.txt && python server.py` alone.
- Reuse existing CSS custom properties (`--sage`, `--shadow`, `--line`, etc.) and existing utility classes (`.card`, `.action-btn`, `.tile`) rather than inventing parallel one-off styles for new UI.
- When adding new dynamically-rendered elements (recommendations, alerts, table rows), give them the same classes the delegated tilt/interaction JS already selects on (`.card, .stat, .reco, ...` in web-dashboard; `.card, .tile, .stat, .reco, .btn, nav button` in mobile-app) so new content picks up the existing depth/press animations automatically — don't hand-roll a separate hover/press system per component.
- Check for duplicate `id` attributes before adding new elements (`grep -o 'id="[a-zA-Z0-9_]*"' index.html | sort | uniq -c | sort -rn`) — both files rely on unique IDs for `$('id')` lookups.
- Keep the dashboard's offline/local-mode fallback working. Any change to how the app fetches from the backend must still degrade gracefully to local scoring + `localStorage` persistence when the backend is unreachable.
- If you touch anything covered by `design.md` (colors, fonts, shadows, card style) and it's still marked **LOCKED**, stop and get explicit confirmation before changing it — see the design-lock rule below.

**Avoid**
- Don't introduce a JS framework (React/Vue/etc.) or a build pipeline for either frontend's actual source. That's a deliberate simplicity tradeoff (ARCHITECTURE §8), not an oversight. The root `package.json`/`node_modules`/`ios/`/`android/` that now exist are an intentional, narrow exception — they're purely Capacitor's native-wrapping layer (`deploy/NATIVE_WRAPPING.md`), never touch `mobile-app/index.html`'s actual source, and the app still runs with zero Node tooling via `python server.py`. Don't let that exception creep into "well there's already a package.json, let's add a bundler" for the frontends themselves.
- Don't add per-element event listeners for hover/tilt/press effects — the existing delegated `pointermove`/`pointerdown` listeners on `document` already cover dynamically-created elements by class selector; per-element listeners would need manual re-wiring after every re-render and are redundant.
- Don't attach real click/tilt behavior to elements that aren't meant to feel interactive (e.g. plain informational text) just because they share a class with interactive cards — check what a class is actually used for before reusing it.
- **The visual design is locked (`design.md` § "Status: LOCKED").** The color palette, typography (Inter, both apps), shadow/elevation scale, and card/chip style were matched to an explicit reference design the project owner provided and finalized on request. Don't restyle, retheme, "modernize," or drift these values in response to a vague ask ("make it nicer," "clean up the UI") — that requires an explicit new instruction to change the *locked design itself*, not just a feature request that happens to touch a styled component. Ordinary feature work (new pages, new buttons, new data) should keep reusing the locked tokens (§ above), not reinterpret them. Brand text ("AgroWise") is part of this too, now unified across both apps (`design.md` §9) — a request to rename it is a small, explicit, easy-to-apply change, but still confirm scope first if it's ambiguous whether it should also touch `README.md`/`PRD.md`/`manifest.json`.

---

## 4. Backend conventions

**Do**
- Keep `server.py` (HTTP/auth/routing), `analysis_engine.py` (pure computation, no I/O), and `database.py` (the only file that touches SQL) separated as they are. A new feature that mixes SQL into `analysis_engine.py`, or scoring logic into `server.py`, breaks the layering that makes the engine independently testable.
- Use parameterized queries (`?` placeholders) for all SQL — already the pattern in `database.py`; never string-format values into a query.
- Validate all six parameters server-side against their physical sensor clamp ranges before they enter the pipeline (`analysis_engine.validate()`). Don't trust firmware, simulator, or manual-entry input to already be sane.
- Run `python analysis_engine.py` (self-test suite) after any pipeline change, **and** `pytest` (from `backend/`, with `requirements-dev.txt` installed) after any change to `server.py`/`database.py`/`analysis_engine.py` — the 32-test suite in `tests/` covers auth (401s), rate limiting (429s), the ingest pipeline, and the DB layer. Both checks are wired into `.github/workflows/ci.yml`; run them locally before considering a backend change done, don't wait for CI to catch it.

**Avoid**
- Don't add new persistent state outside SQLite (no separate config files, no in-memory-only state that matters across requests) without a good reason — the single-SQLite-file model is what keeps setup to "no external services required."
- Don't make `simulator.py` or the firmware depend on internal backend modules. They are separate HTTP clients by design and must only ever talk to the REST API, never `import` backend code directly.

---

## 5. Documentation

**Do**
- Keep `README.md` (setup/run/API reference), `PRD.md` (what/why/who), and `ARCHITECTURE.md` (how) each in their lane — don't duplicate content wholesale between them; cross-reference instead.
- Update all three together when a change affects more than one: e.g. a new `/api/*` route needs a README table row, possibly a PRD feature bullet, and an ARCHITECTURE data-flow update if it changes the pipeline.
- Ground documentation in the actual repository state, not just the original invention disclosure aspirations — PRD.md and ARCHITECTURE.md were deliberately written to reflect what's really implemented (e.g. "Prototype Status" honestly separates working software from pending hardware integration).

**Avoid**
- Don't let docs claim capabilities that aren't implemented (e.g. actuator control / automated irrigation triggering — explicitly out of scope per PRD §7) just because the invention disclosure mentions them as a possibility.
- Don't remove the invention disclosure's stated limitations (§7.1/7.2 — sensor accuracy in saline/waterlogged/rocky soil, calibration drift, no power/network resilience) from PRD.md when updating it. They're load-bearing for setting correct user expectations, not boilerplate.

---

## 6. Known environment quirks (don't "fix" these by breaking things)

- macOS often has port 5000 occupied by AirPlay Receiver/ControlCenter. This is a local environment issue, not a bug in `server.py` — don't hardcode a different default port to work around one machine's config; document the AirPlay toggle instead (already in README/troubleshooting).
- `flask-limiter`'s in-memory storage backend (the default, `AGROWISE_RATELIMIT_STORAGE` unset) is fine for local dev's single process. This is now configurable, not fixed — see § 7 for when to actually switch it.

---

## 7. Deployment / production (`deploy/`)

**Do**
- Keep `AGROWISE_RATELIMIT_STORAGE=redis://...` set whenever gunicorn runs with more than one worker (`docker-compose.yml` already wires this). Each worker holds its own in-memory counter otherwise, so a client bouncing between workers gets a multiple of the intended rate limit — this silently weakens the 5/min DELETE protection specifically, which is the one that matters most.
- Keep `AGROWISE_BEHIND_PROXY=1` (→ `ProxyFix`) set whenever the app actually sits behind nginx/any reverse proxy. Without it every request appears to originate from the proxy's own IP, and per-client rate limiting stops working — this isn't optional or cosmetic.
- Keep `.env` (real secrets) out of git — `.env.example` is the committed template; `.gitignore` already excludes `.env` itself.
- Treat the required-variable guard in `docker-compose.yml` (`${AGROWISE_API_KEY:?...}`) as intentional — it's there so the stack refuses to start with no auth configured, not a bug to relax.

**Avoid**
- Don't let the native-wrapping layer (`ios/`, `android/`, `package.json`) become a second place product logic lives. It exists solely to package `mobile-app/index.html` for app stores (`deploy/NATIVE_WRAPPING.md`) — any real feature work still happens in `mobile-app/index.html` and reaches the native shells via `npx cap sync`, never by editing generated native files directly (the cleartext-traffic config in `AndroidManifest.xml`/`Info.plist` is the one deliberate exception, since Capacitor doesn't regenerate those from `capacitor.config.json` on sync).
- Don't assume this session's Docker-build/Xcode-build verification generalizes to "verified working end-to-end" — the sandbox here couldn't reach GitHub (blocked Swift Package Manager resolution) or install Python packages inside a running container (network-namespaced), so `docker build` and a full Xcode compile were not actually completed here, only validated up to those specific external-network walls. Don't claim more than that was tested.
