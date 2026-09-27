"""Who is asking: the three ways Kintsugi can know its user, and the per-user scoping of sessions.

    KIN_AUTH=none      (default) a personal server on a trusted network; everyone is the same anonymous user.
    KIN_AUTH=token     one shared access code (KIN_ACCESS_TOKEN): the UI asks for it once and keeps a signed cookie.
                       Fine for a private deployment shared by a few people; every session is visible to all of them.
    KIN_AUTH=easyauth  the platform signs people in before the request reaches us (Azure Container Apps / App Service
                       "Easy Auth" with Microsoft, GitHub or Google) and forwards the identity in X-MS-CLIENT-PRINCIPAL-*
                       headers. Sessions belong to the person who created them; KIN_ADMIN_USERS see everything.

The middleware resolves the user once per request and parks it in a context variable, so `current_user()` works
anywhere below (the session helpers use it to filter and to stamp `owner`). Nothing here stores passwords.
"""

from __future__ import annotations

import base64
import contextvars
import hashlib
import hmac
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

COOKIE = "kin_auth"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30

# paths that never need a user: liveness, the auth endpoints themselves, the published schemas (static documentation);
# the SPA shell and its assets are not under /api and are always served
PUBLIC_API = ("/api/health", "/api/auth/", "/api/schemas/")


@dataclass(frozen=True)
class User:
    id: str
    name: str
    provider: str = "none"
    admin: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "provider": self.provider, "admin": self.admin}


ANON = User(id="local", name="local", provider="none", admin=True)
SHARED = User(id="shared", name="shared workspace", provider="token", admin=True)

_current: contextvars.ContextVar[User | None] = contextvars.ContextVar("kin_user", default=None)


def mode() -> str:
    m = os.environ.get("KIN_AUTH", "none").strip().lower()
    return m if m in ("none", "token", "easyauth") else "none"


def current_user() -> User:
    """The user of the request being served; `ANON` outside a request (CLI, tests without the middleware)."""
    return _current.get() or ANON


def admins() -> set[str]:
    return {x.strip().lower() for x in os.environ.get("KIN_ADMIN_USERS", "").split(",") if x.strip()}


def _secret() -> bytes:
    return (os.environ.get("KIN_SECRET_KEY") or os.environ.get("KIN_ACCESS_TOKEN") or "kintsugi").encode("utf-8")


def cookie_value() -> str:
    """The signed value a valid access code earns; it never contains the code itself."""
    return hmac.new(_secret(), b"kintsugi-auth-v1", hashlib.sha256).hexdigest()


def _same(a: str, b: str) -> bool:
    """Constant-time equality that tolerates any unicode (compare_digest on str insists on ASCII)."""
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def check_token(token: str) -> bool:
    expected = os.environ.get("KIN_ACCESS_TOKEN", "")
    return bool(expected) and _same(token.strip(), expected)


# ---- login throttle (token mode) ------------------------------------------------------------------------------------
# A shared code is a password with no lockout; slow the guessing down without locking out the household after a typo.

FAILS_ALLOWED = 8          # wrong codes per client before a cool-off
FAIL_WINDOW_S = 600        # ...within this many seconds
COOL_OFF_S = 60            # then every attempt from that client waits this long
_fails: dict[str, list[float]] = {}


def client_key(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    ip = fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")
    return ip or "?"


def throttle_check(key: str) -> float:
    """Seconds the client must still wait before another login attempt is considered (0 = go ahead)."""
    now = time.time()
    hits = [t for t in _fails.get(key, []) if now - t < FAIL_WINDOW_S]
    _fails[key] = hits
    if len(hits) >= FAILS_ALLOWED:
        return max(0.0, COOL_OFF_S - (now - hits[-1]))
    return 0.0


def throttle_fail(key: str) -> None:
    _fails.setdefault(key, []).append(time.time())
    if len(_fails) > 10000:            # never let the map grow without bound
        _fails.clear()


def throttle_clear(key: str) -> None:
    _fails.pop(key, None)


def _bearer(request: Request) -> str | None:
    h = request.headers.get("authorization", "")
    if h.lower().startswith("bearer "):
        return h[7:].strip()
    return None


def _easyauth_user(request: Request) -> User | None:
    """Azure App Service / Container Apps authentication forwards the signed-in identity in these headers."""
    name = request.headers.get("x-ms-client-principal-name", "").strip()
    pid = request.headers.get("x-ms-client-principal-id", "").strip()
    idp = request.headers.get("x-ms-client-principal-idp", "").strip() or "easyauth"
    display = name
    raw = request.headers.get("x-ms-client-principal", "")
    if raw:
        try:
            doc = json.loads(base64.b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8"))
            for c in doc.get("claims", []):
                if c.get("typ") in ("name", "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name") and c.get("val"):
                    display = str(c["val"])
                if not name and c.get("typ") in ("preferred_username", "email", "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress"):
                    name = str(c.get("val", ""))
            idp = doc.get("auth_typ", idp) or idp
        except (ValueError, json.JSONDecodeError):
            pass
    uid = (name or pid).lower()
    if not uid:
        return None
    return User(id=uid, name=display or name or pid, provider=idp, admin=uid in admins())


def resolve(request: Request) -> User | None:
    m = mode()
    if m == "none":
        return ANON
    if m == "token":
        tok = _bearer(request)
        if tok is not None and check_token(tok):
            return SHARED
        if _same(request.cookies.get(COOKIE, ""), cookie_value()):
            return SHARED
        return None
    return _easyauth_user(request)


def describe(request: Request | None = None) -> dict[str, Any]:
    """What the UI needs to draw the gate: the mode, the user (if any) and where sign-in / sign-out live."""
    m = mode()
    u = current_user() if request is None else (resolve(request))
    out: dict[str, Any] = {"mode": m, "user": u.to_dict() if u else None}
    if m == "easyauth":
        provider = os.environ.get("KIN_EASYAUTH_PROVIDER", "aad")
        out["login_url"] = f"/.auth/login/{provider}?post_login_redirect_uri=/"
        out["logout_url"] = "/.auth/logout?post_logout_redirect_uri=/"
    elif m == "token":
        out["login_url"] = "/api/auth/login"
        out["logout_url"] = "/api/auth/logout"
    return out


def secure_cookie(request: Request) -> bool:
    if os.environ.get("KIN_COOKIE_SECURE", "").lower() in ("1", "true", "yes"):
        return True
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    return proto == "https"


# ---- per-client rate limit for the endpoints that cost CPU or money ------------------------------------------------
# KIN_RATE_PER_MIN (default 0 = off): how many heavy calls one client may make per minute. A public demo box wants
# something like 30; a personal server does not need it. Previews are exempt (they are latest-wins and cancel each other).

HEAVY = re.compile(r"^/api/sessions/(?:import$|[^/]+/(?:run|iterate|coupon|coupon/result|export|params|code|photos|intake|followup)$)")
_hits: dict[str, list[float]] = {}


def rate_per_min() -> int:
    try:
        return max(0, int(os.environ.get("KIN_RATE_PER_MIN", "0") or 0))
    except ValueError:
        return 0


def rate_check(key: str, limit: int) -> float:
    """Seconds until the client may call a heavy endpoint again (0 = now)."""
    now = time.time()
    hits = [t for t in _hits.get(key, []) if now - t < 60]
    if len(hits) >= limit:
        _hits[key] = hits
        return max(0.0, 60 - (now - hits[0]))
    hits.append(now)
    _hits[key] = hits
    if len(_hits) > 10000:
        _hits.clear()
    return 0.0


async def middleware(request: Request, call_next):
    """Resolve the user; refuse API calls without one (except the public paths); expose it to the handlers."""
    path = request.url.path
    try:
        user = resolve(request)
    except Exception:          # noqa: BLE001 — a malformed header or cookie is "not signed in", never a 500
        user = None
    needs_user = path.startswith("/api/") and not any(path.startswith(p) for p in PUBLIC_API)
    if needs_user and user is None:
        return JSONResponse({"detail": "sign in to use Kintsugi", "auth": describe(request)}, status_code=401)
    limit = rate_per_min()
    if limit and request.method in ("POST", "PUT") and HEAVY.match(path):
        wait = rate_check(client_key(request), limit)
        if wait > 0:
            return JSONResponse({"detail": f"slow down: {limit} of these calls per minute; try again in {int(wait) + 1} s"},
                                status_code=429, headers={"Retry-After": str(int(wait) + 1)})
    token = _current.set(user)
    try:
        return await call_next(request)
    finally:
        _current.reset(token)


def can_see(meta: dict[str, Any]) -> bool:
    """Per-user scoping: in easyauth mode a session belongs to its owner (admins see all); other modes share everything."""
    if mode() != "easyauth":
        return True
    u = current_user()
    if u.admin:
        return True
    owner = str(meta.get("owner") or "").lower()
    return owner == u.id


def owner_fields() -> dict[str, Any]:
    u = current_user()
    if mode() == "none":
        return {}
    return {"owner": u.id, "owner_name": u.name}
