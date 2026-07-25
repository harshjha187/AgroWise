# AgroWise Field — Privacy Policy (draft)

**This is a draft you must review, adapt, and host at a real public URL before submitting to any app store — it is not legal advice, and it makes factual claims about the app that you should verify still hold true at submission time.** Replace the bracketed placeholders, then publish the final text on a page you control (a page on your own domain, or a free static host like GitHub Pages) and use that URL in your store listings.

*Last updated: [DATE]*

## Summary

AgroWise Field is a companion app for the AgroWise IoT Soil Health Analysis System. It connects to a backend server that **you** run and control (on your own computer, home network, or a server you host) — there is no AgroWise-operated cloud service, and the developer of this app does not receive, store, or have access to any data you collect or enter.

## What data the app handles

| Data | What it is | Where it goes |
|---|---|---|
| Soil sensor readings (N, P, K, moisture, pH, temperature) | Measurements from your ESP32 device or manually entered by you | Sent only to the backend URL you configure in Setup — never to any server operated by the app developer |
| Backend URL & API key | Connection details you enter in Setup, so the app knows where to send/fetch data | Stored only in the app's local storage on your device; never transmitted anywhere except to the backend URL you provided |
| Device identifiers, location, contacts, photos, etc. | **Not collected.** | N/A |

## Data collection questionnaire answers (for store Data Safety / App Privacy forms)

- Does the app collect personal data? **No** — it has no user accounts, no sign-in, no analytics SDK, and no identifiers are transmitted to any developer-operated server.
- Does the app share data with third parties? **No.**
- Is data encrypted in transit? **Depends on your backend setup** — if you deploy the backend behind HTTPS (see `deploy/DEPLOY.md`), yes; if you use it locally over plain HTTP on your own LAN (the default/documented setup for hardware use), no. Disclose this honestly based on how you've told users to deploy it.
- Does the app use tracking/advertising? **No.**

## Local storage

The app stores your backend URL, API key, and (if offline) a small queue of not-yet-synced readings in the browser/WebView's local storage on your device. This data never leaves your device except when the app sends it to the backend URL you configured.

## Children's privacy

This app is a technical utility for agricultural monitoring and is not directed at children. It does not knowingly collect data from children under 13 (or the relevant age threshold in your jurisdiction).

## Your responsibility as the operator

Because AgroWise Field talks to a backend **you** deploy, you are the data controller for whatever soil/farm data flows through your instance. If you deploy a public-facing backend (per `deploy/DEPLOY.md`) and allow others to use your app pointed at it, you may have additional obligations (e.g. GDPR if any of those users are in the EU) — this template does not cover that scenario; consult a lawyer if you intend to operate AgroWise as a multi-tenant service rather than a personal/single-farm tool.

## Changes to this policy

[Describe how you'll notify users of changes, e.g. "Updates will be posted at this same URL with a revised 'Last updated' date."]

## Contact

[Your contact email or method — required by both app stores.]
