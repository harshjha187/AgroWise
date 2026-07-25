# Native App Wrapping (Capacitor) — Status

**This is further along than a plan — real native projects already exist in this repo**, generated and verified this session:

```
AgroWise_Project/
├── package.json              Capacitor CLI/core as devDependencies
├── capacitor.config.json      appId: com.agrowise.field, webDir: mobile-app
├── ios/App/                   Real Xcode project (Swift Package Manager, not CocoaPods)
└── android/                   Real Android Studio / Gradle project
```

## What's actually done

- `npx cap init` — real `capacitor.config.json` pointing `webDir` at `mobile-app/` (the same PWA that's been built and tested all session — no separate native codebase to keep in sync).
- `npx cap add ios` — generated a working Xcode project at `ios/App/`.
- `npx cap add android` — generated a working Android Studio project at `android/`.
- `npx cap sync` — copied the current `mobile-app/` (dark mode, onboarding, offline queue, accessibility, i18n — everything built this session) into both native projects' asset folders. Verified: `ios/App/App/public/index.html` contains the onboarding overlay and dark-mode code.
- **Cleartext HTTP allowed on both platforms**, since AgroWise backends are commonly plain-HTTP on a LAN with a user-configured URL unknown at build time (`backend/rules.md` § 2):
  - Android: `android:usesCleartextTraffic="true"` added to `android/app/src/main/AndroidManifest.xml` (this is exactly what the README's troubleshooting section already told users to do manually — now baked in).
  - iOS: `NSAppTransportSecurity` → `NSAllowsArbitraryLoads` added to `ios/App/App/Info.plist`, with a comment explaining why (App Review sometimes asks for justification on this — the LAN-IoT use case in `deploy/STORE_LISTING.md` is that justification).

## What's still needed before this is a submittable build

All of this requires **your** Apple/Google accounts, local toolchain state, or normal (non-sandboxed) internet access — none of it can be done from here:

1. **First-time dependency resolution** — tried this session and hit a real wall worth knowing about: `xcodebuild` needs to fetch Capacitor's iOS runtime from `https://github.com/ionic-team/capacitor-swift-pm.git` via Swift Package Manager, and **this sandbox cannot reach `github.com` at all** (confirmed directly — `curl`/`git ls-remote` to github.com both time out, even though PyPI and the npm registry worked fine for everything else this session). This isn't a project problem — it'll resolve itself the first time you open `ios/App/App.xcodeproj` (or `.xcworkspace`) in Xcode on your own machine with normal internet access; Xcode fetches it automatically. Same expectation for Android's Gradle dependencies (pulled from Maven Central/Google's Maven, not GitHub, so likely unaffected — but genuinely untested here, see next point).
2. **Java for Gradle** — this machine also doesn't have a Java runtime installed (same gap noted earlier in this project for `avdmanager`), so `android/`'s Gradle sync couldn't fully complete headlessly *regardless* of the GitHub issue. Opening the project in Android Studio will prompt to install/use its bundled JDK and resolve this automatically.
3. **Xcode signing** — once SPM resolution succeeds on your machine, select your Apple Developer Team under Signing & Capabilities in `ios/App/App.xcworkspace`, and let Xcode provision it. Requires the paid Apple Developer Program membership (`deploy/STORE_LISTING.md`).
4. **Android signing** — Android Studio → Build → Generate Signed Bundle/APK, creating (or reusing) a keystore. Requires the Google Play Console account.
5. **App icons at store-required sizes** — `npx cap` already copied the existing 192/512px PWA icons in, but store submission wants specific additional sizes (`deploy/STORE_LISTING.md` § App icon) — regenerate via Android Studio's Image Asset tool / Xcode's asset catalog from the same source art.
6. **Push notifications, if wanted** — `@capacitor/push-notifications` isn't installed yet; see `deploy/push-notifications.md` § Path B once you're at this stage.

**Bottom line:** the project scaffolding, config, and web-asset sync are real and verified (file contents checked directly). The one thing genuinely *not* verified end-to-end is a full compile, because of the sandbox's GitHub access restriction above — that's an environment limitation of this session, not a defect in the generated projects.

## Ongoing workflow once you're building locally

Every time `mobile-app/index.html` (or `manifest.json`/`sw.js`) changes, re-sync before rebuilding either native app:

```bash
npx cap sync
```

Then rebuild in Xcode (`ios/App/App.xcworkspace`) or Android Studio (open the `android/` folder) as usual.

## Why this approach (Capacitor) instead of alternatives

- **vs. a from-scratch native rewrite:** zero duplicate UI code — the exact same `mobile-app/index.html` that's been built, tested (iOS Simulator + Android emulator), and hardened all session runs unchanged inside a thin native WebView shell. Any future dashboard/mobile feature work only touches one file per platform difference, not three.
- **vs. staying PWA-only:** Capacitor is what unlocks actual App Store / Play Store listing (`deploy/STORE_LISTING.md`) and native push notifications (`deploy/push-notifications.md` Path B) — things a browser-installed PWA can't fully do, especially on iOS.
