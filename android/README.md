# Series 76 Assistant — Android client (Spec 5)

Native Kotlin + Jetpack Compose app, **single Gradle module** (`:app`),
Feature-First packages, MVVM + unidirectional data flow, type-safe Navigation
Compose, Retrofit/OkHttp, a Room read cache, DataStore for non-sensitive
settings, and Android-Keystore-backed storage. It is a pure consumer of the
backend (Spec 3) and renderer of the typed `content_blocks` (Spec 4).

> **Status (honest):** the owner built the app with Gradle on an API 35 emulator. The
> JVM unit/property suite passed (`BUILD SUCCESSFUL`) and the instrumented suite ran 3/3,
> including the end-to-end login against the host backend. Login, account isolation, the
> Debug screen and multi-turn context were checked by hand in the app. The last Android
> changes (offline-detection fix, "count" unit, Debug "returned data" and its JVM test)
> came after that run and have not been compiled since; the manual checks with real
> answers could not be repeated because the OpenRouter key expired. Accessibility and the
> F5-OFF offline scenarios were not executed.

## Build and run (Android Studio)

1. Install Android Studio (Ladybug or newer) with **JDK 17** and the Android
   SDK **API 35** platform; create an emulator (any API 26+ image).
2. *File → Open…* the `android/` directory. Studio uses the checked-in Gradle
   wrapper (Gradle 8.10.2; the wrapper JAR and the distribution are pinned by
   SHA-256 in `gradle/wrapper/`).
3. Start the backend on the host (see the repository root `README.md`), e.g.
   `docker compose up` in `backend/` — it listens on `http://localhost:8000`.
4. Run the `app` configuration on the emulator.

CLI equivalents (from `android/`): `./gradlew :app:assembleDebug`,
`./gradlew :app:testDebugUnitTest` (JVM unit + property tests),
`./gradlew :app:connectedDebugAndroidTest` (needs a running emulator).

### Host ↔ emulator networking

The emulator reaches the host's loopback at **`10.0.2.2`**. The default backend
URL is `http://10.0.2.2:8000/`, set in `gradle.properties`
(`series76.apiBaseUrl`) and compiled into `BuildConfig.API_BASE_URL`. To point
elsewhere, override `series76.apiBaseUrl` in `~/.gradle/gradle.properties`
(never put a secret there).

Cleartext HTTP is **disallowed globally** and permitted **only** for
`10.0.2.2` (`res/xml/network_security_config.xml`). Any other host must use
HTTPS.

## Demo accounts

The Compose `migrate` job pre-loads two test users from `DEMO_*` in `backend/.env`:
`user@example.com` / `demo-user-example-2026A!` (role `user`) and `dev@example.com` /
`demo-dev-example-2026A!` (role `developer`, sees the Debug screen). They are local demo
credentials. Registration in the app always creates role `user` — the app has no role
selector and never sends a role.

## Reaching the Developer Debug screen

1. Sign in with the `developer` account.
2. Open a conversation (*Conversations → a row*), send a message, wait for the
   answer.
3. Under an assistant message, tap **Debug trace**: turn states, model calls, and per
   tool its parameters and the data it returned. The entry appears only when
   `GET /api/auth/me` reports role `developer`; the backend re-checks role and
   ownership on every trace request and denies anything else identically.

## Architecture map

| Package | Role |
|---|---|
| `core/model` | `Response_Envelope` / `content_blocks` model + tolerant parser (unknown kind → text) |
| `core/render` | Pure `RenderMapper` (≤3 cards, dual selector, comparable-only bars + text alternatives, N/A explicit, top-1) and `UiText` (only UI strings are localized) |
| `core/turn` | `TurnState` (10 states), `JobState`, idempotency keys, polling policy (1→30 s, `Retry-After` 1–300 s) |
| `core/net` | `Spec3Api`, Retrofit/OkHttp implementation, single-flight refresh rotation; `Offline` ≠ HTTP error |
| `core/security` | AES-256-GCM `CipherBox`, Keystore master key, per-account wrapped data keys, encrypted tokens and drafts |
| `core/cache` | Payload-encrypted, per-account Room cache (no plaintext index) |
| `core/session` | `Account_Epoch` guard; logout / account switch purge |
| `core/offline` | Offline banner vs server error, Send gating, reconciliation |
| `feature/*` | Auth, Conversations, Chat (incl. `TypedBlockRenderer`), Debug — a pure *Store* per screen wrapped by a thin `ViewModel` |
| `navigation` | Typed routes (IDs only), launch routing, developer gate |

Invariants: the app **never parses a number from `answer` prose** — every
figure is read from a typed `FigureDTO` field (value string at stored
precision, unit, status, service, frequency, supply, evidence). Offline it
**never sends or queues**: Send is disabled, the encrypted draft is kept, and
nothing is sent automatically after reconnection.

## Tests

* `app/src/test/…` — JVM tests against an in-memory fake of the Spec 3 API:
  33 property tests (kotest-property, 100 cases each, tagged
  `Feature: android-app, Property N`), a traceability check, a secret /
  cleartext-policy scan, and a Robolectric Compose semantics test.
* `app/src/androidTest/…` — emulator suite: 2.0× font scale, cleartext policy,
  an opt-in end-to-end login against the host backend, and the F5-OFF offline
  checklist. **To be run; not asserted executed.**
