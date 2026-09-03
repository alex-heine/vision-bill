# Vision-Bill: Multi-User Authentication — Implementation Plan

**Stack:** FastAPI + raw asyncpg (no ORM) · SvelteKit SPA (adapter-static, served same-origin by FastAPI) · Argon2id via `argon2-cffi` · HMAC-signed stateless session cookie.

## Locked decisions
- Multi-user accounts (username + password), **Argon2id** package defaults (`m=64MiB, t=3, p=4`).
- **Pepper always on:** effective pepper = `AUTH__PEPPER` if set, else `AUTH__SECRET_KEY`. Hash = `argon2id(hmac_sha256(pepper, password))`.
- **Stateless HMAC session cookie** (HttpOnly, `SameSite=Lax`, 14-day max-age). No sessions table.
- **Per-row `user_id` scoping** on `receipts` + `images`; a non-admin only sees/edits their own.
- **Admin "see-all"** = `user.is_admin AND AUTH__ADMIN_CAN_SEE_ALL` (off by default).
- **First admin** bootstrapped from env on startup (idempotent) + legacy orphan rows backfilled to that admin.
- **Benchmarks admin-only.** Public endpoints: `/auth/*`, `/system/ui-config`.

> Each Part below is independently completable and verifiable. Prereqs list what it builds on.

---

## Part 1 — Dependency + DB schema
**Goal:** Add the hashing lib and create the auth schema. Backward-compatible: new `user_id` columns are nullable, so the app still boots unchanged.

**Files:** `pyproject.toml`, `alembic/versions/0003_add_users.py`

**Steps**
1. Add `argon2-cffi` to `dependencies`; run `make setup` (uv sync → refresh `uv.lock`).
2. Migration `0003` (`down_revision = "0002"`, hand-written `op.execute` like `0001`/`0002`):
   - `CREATE TABLE users (id SERIAL PK, username VARCHAR(100) NOT NULL UNIQUE, hashed_password TEXT NOT NULL, is_admin BOOLEAN NOT NULL DEFAULT FALSE, created_at TIMESTAMPTZ DEFAULT now())`.
   - `ALTER TABLE receipts ADD COLUMN user_id INT REFERENCES users(id) ON DELETE CASCADE;` + index on `user_id`.
   - `ALTER TABLE images ADD COLUMN user_id INT REFERENCES users(id) ON DELETE CASCADE;` + index on `user_id`.
   - `downgrade()`: drop indexes → drop columns → drop table.
3. `make migrate`.

**Done when:** `uv run python -c "import argon2"` succeeds; `make migrate` succeeds; `users` table exists and `receipts`/`images` have a nullable `user_id`; existing app still boots.

---

## Part 2 — Config + security helpers (pure, DB-free)
**Goal:** Settings plus self-contained crypto/token helpers, unit-tested without a database.

**Files:** `src/vision_bill/config.py`, `src/vision_bill/security/__init__.py`, `security/password.py`, `security/session.py`, `tests/test_security.py`

**Steps**
1. `config.py` — add `AuthSettings(BaseModel)`:
   - `secret_key: str`, `session_cookie_name: str = "vb_session"`, `session_max_age_seconds: int = 1_209_600`, `session_secure: bool = False`
   - `bootstrap_username: str | None = None`, `bootstrap_password: str | None = None`
   - `allow_registration: bool = True`, `admin_can_see_all: bool = False`, `pepper: str | None = None`
   - Add `auth: AuthSettings` to `Settings`.
2. `password.py` — `PasswordHasher(type=Type.ID, memory_cost=65536, time_cost=3, parallelism=4)`; `hash_password`, `verify_password` (pepper = `settings.auth.pepper or settings.auth.secret_key`; pre-hash `hmac_sha256(pepper, password)` when pepper present, else hash the password directly; catch `argon2.exceptions.VerifyMismatchError` → `False`); `needs_rehash`.
3. `session.py` — `create_token(user_id, max_age, secret) -> str` = `"{user_id}.{exp}.{hmac_sha256(secret, user_id.exp)}"`; `decode_token(token, secret) -> int | None` (constant-time compare; `None` on bad sig / expired / malformed).

**Done when:** `tests/test_security.py` covers hash/verify round-trip, wrong-password `False`, pepper path, token sign/decode, tampered token → `None`, expired token → `None`; `make test` green for these.

---

## Part 3 — User data layer + auth dependencies
**Goal:** `UserDB` provider, `User` model, and the two FastAPI dependencies.

**Files:** `src/vision_bill/security/models.py`, `security/dependencies.py`, `provider/db/user_db.py`, `api/helper/helper.py` (getter)

**Steps**
1. `models.py` — `User(BaseModel)`: `id, username, is_admin, can_see_all` (`can_see_all` = resolved effective privilege).
2. `user_db.py` — `UserDB` (pool pattern mirroring `ReceiptDB`): `create_user(username, hashed, is_admin)`, `get_user_by_username`, `get_user_by_id`, `count_users`, `set_owner_of_orphan_rows(user_id)`.
3. `dependencies.py` — `get_current_user` (read cookie → `decode_token` → load `User` via `UserDB` → set `can_see_all = is_admin and settings.auth.admin_can_see_all`; raise `401` on any failure) and `require_admin` (raise `403` when `not user.can_see_all`). Add a `get_user_db(request)` helper in `helper.py`.

**Prereqs:** Parts 1–2.

**Done when:** unit test: `create_user` → `get_user_by_username` → `verify_password` round-trip; the dependency resolves a valid cookie to the right user; ruff + mypy strict clean.

---

## Part 4 — Auth API + service wiring + bootstrap
**Goal:** The `/api/v1/auth` endpoints, wire `UserDB` into the app, and first-boot admin bootstrap + legacy backfill.

**Files:** `api/auth.py`, `service/receipt_service.py`, `main.py`

**Steps**
1. `api/auth.py`:
   - `POST /register` `{username,password}` → 201 + cookie; `409` taken; `403` if registration disabled.
   - `POST /login` → 200 + cookie; `401` bad creds.
   - `POST /logout` → clear cookie.
   - `GET /me` → `User` or `401`.
2. Wire `UserDB` into `ReceiptService` (init/destroy/property) and set `app.state.user_db` in `main.py`.
3. `main.py` lifespan (idempotent, after `init_db`): if `count_users() == 0` and `bootstrap_*` set → create admin; then `set_owner_of_orphan_rows(admin_id)`.
4. Mount the auth router at `/api/v1/auth`.

**Prereqs:** Parts 1–3.

**Done when:** TestClient: register → cookie set → `/me` 200; duplicate → 409; login ok / bad → 401; logout clears; bootstrap creates exactly one admin on an empty DB and is a no-op on the next boot.

---

## Part 5 — Protect routes
**Goal:** Enforce auth on all data routes; expose the registration flag to the SPA.

**Files:** `api/receipts.py`, `api/images.py`, `api/tags.py`, `api/system/llm.py`, `api/benchmarks.py`, `api/system/main.py`

**Steps**
1. Add `current_user: User = Depends(get_current_user)` to handlers + `dependencies=[Depends(get_current_user)]` on the receipts / images / tags / llm routers (FastAPI caches the dependency per request).
2. `benchmarks.py` → `Depends(require_admin)`.
3. `api/system/main.py` `/ui-config` → add `registration_open: settings.auth.allow_registration` to the response.

**Prereqs:** Part 4.

**Done when:** unauthenticated `/receipts`, `/images`, `/tags`, `/llm/models` → 401; with a valid cookie → 200; `/benchmarks` → 403 for non-admin, 200 for an admin; `/ui-config` returns `registration_open`.

---

## Part 6 — Per-user data scoping
**Goal:** Each user only sees/edits their own receipts & images; an admin sees all only when the global flag is enabled.

**Files:** `model/db/receipt.py`, `model/db/image.py`, `provider/db/receipt_db.py`, `provider/db/image_db.py`, `service/receipt_service.py`, `api/images.py`, `service/analysis_scheduler.py`

**Steps**
1. Add `user_id` to `ReceiptRow` and `ImageRow`.
2. `ReceiptDB`: `persist_receipt(..., user_id)`; `list_receipts` / `get_receipt_by_id` / `get_receipt_with_details` / `update_receipt` / `verify_receipt` / `delete_receipt` all take `user_id, can_see_all` — when `can_see_all` is false, append `AND user_id=$n` (other users' rows → `None` → 404).
3. `ImageDB`: `store_image(..., user_id)`; `get_image_by_id` / `list_images` take `user_id, can_see_all`. **`list_pending_images` stays unscoped** (background queue).
4. Thread `user_id` / `can_see_all` through `ReceiptService` methods.
5. `images.py` upload → pass `current_user.id` to `store_image` / `persist_receipt`; `analysis_scheduler._analyze_one` → `persist_receipt(..., user_id=image.user_id)` (owner travels with the queued image).

**Prereqs:** Parts 4–5.

**Done when:** `tests/test_scoping.py`: user A cannot GET/PUT/DELETE/verify user B's receipt or image; admin with `admin_can_see_all=true` can, admin with `false` cannot; the background worker tags a new receipt with the image's owner.

---

## Part 7 — Frontend
**Goal:** Login page, client-side guard, session handling. Image `<img>` previews keep working because the cookie is sent automatically on same-origin requests.

**Files:** `frontend/src/lib/api/client.ts`, `frontend/src/lib/auth.ts`, `frontend/src/routes/login/+page.svelte`, `frontend/src/routes/+layout.svelte`, `frontend/src/lib/types.ts`

**Steps**
1. `client.ts`: add `me() / login() / register() / logout()`; explicit `credentials: 'same-origin'`; global `401` handler → clear session + `goto('/login')`. Add `User` + `registration_open` types.
2. `lib/auth.ts`: session store (`User | null | 'loading'`) populated from `api.me()` on app start.
3. `routes/login/+page.svelte`: login form + conditional register (shown when `registration_open`).
4. `+layout.svelte`: guard — loading state → `goto('/login')` when logged out → app chrome when in; make the queue `listImages` query `enabled` only when authenticated; add username + **Sign out** to the header.
5. Rebuild: `npm run build` in `frontend/` (→ `src/vision_bill/static`).

**Prereqs:** Parts 4–5.

**Done when:** `npm run check` (svelte-check) + `npm run build` succeed; manual: logged-out → redirected to `/login`; after login → app loads; sign-out → `/login`.

---

## Part 8 — Tests, verify, env docs
**Goal:** Full integration, tooling green, operator documentation.

**Files:** `tests/*`, `frontend/src/lib/*.test.ts`, `.env`, `.env.example` (if present)

**Steps**
1. Frontend `vitest` for `auth.ts` (me → session mapping, 401 redirect).
2. Run `make lint` (ruff + mypy strict) and `make test`; fix everything.
3. Document env: `AUTH__SECRET_KEY` (required), optional `AUTH__PEPPER`, `AUTH__FIRST_USERNAME` / `AUTH__FIRST_PASSWORD`, `AUTH__ALLOW_REGISTRATION`, `AUTH__ADMIN_CAN_SEE_ALL`, `AUTH__SESSION_SECURE` in `.env` / `.env.example`.

**Prereqs:** Parts 1–7.

**Done when:** `make lint` and `make test` fully green; end-to-end: app boots, a user registers/logs in, and data is isolated per user (admin override honored).
