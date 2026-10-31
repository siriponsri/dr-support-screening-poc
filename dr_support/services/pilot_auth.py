"""Sign-in for the physician UX pilot (owner request 2026-10-31).

Users live in one private JSON file on the workstation (``DR_SUPPORT_AUTH_FILE``),
outside Git and the case store. Passwords are stored only as salted PBKDF2-SHA256
hashes; no password, hash or session token is ever returned, logged or sent to
the browser except the session cookie itself (HttpOnly, SameSite=Strict).

When the variable is not set the app behaves exactly as before (no sign-in).
This is local sign-in for one app; it is not the per-user Model API identity.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from hmac import compare_digest
import json
import os
from pathlib import Path
import re
import secrets
import threading
import time

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

COOKIE = "dr_session"
ROLES = {"admin", "user"}
USERNAME = re.compile(r"[a-z0-9_.-]{3,40}")
ITERATIONS = 310_000
SESSION_SECONDS = 12 * 3600
MIN_PASSWORD = 4   # Absolute floor (the operator's own setup command); the app policy is stricter.
# Sign-in policy the administrator can change, each within safe bounds.
DEFAULT_POLICY = {"min_length": 8, "letters_and_numbers": True, "first_sign_in_change": True,
                  "max_failures": 5, "lockout_minutes": 5, "idle_minutes": 30}
POLICY_BOUNDS = {"min_length": (6, 64), "max_failures": (3, 10), "lockout_minutes": (1, 60),
                 "idle_minutes": (5, 480)}


def password_problems(password: str, policy: dict) -> list[str]:
    """Plain reasons a password does not meet the policy; empty when it does."""
    problems = []
    if len(password) < policy["min_length"]:
        problems.append(f"at least {policy['min_length']} characters")
    if policy["letters_and_numbers"] and not (re.search(r"[A-Za-z]", password) and re.search(r"[0-9]", password)):
        problems.append("both letters and numbers")
    return problems


class AuthError(Exception):
    """Plain wording for the sign-in page; never says which part was wrong."""


def _hash(password: str, salt: bytes, iterations: int = ITERATIONS) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations).hex()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Session:
    username: str
    role: str
    must_change: bool
    expires: float
    short_password: bool = False


class UserStore:
    """The private user file. Writes are atomic; the file keeps hashes only."""

    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()

    def _load(self) -> dict:
        if not self.path.is_file():
            return {"schema": "dr-pilot-users.v1", "users": {}}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")
        os.replace(temporary, self.path)

    def policy(self) -> dict:
        with self.lock:
            stored = self._load().get("policy") or {}
        return {**DEFAULT_POLICY, **{key: stored[key] for key in DEFAULT_POLICY if key in stored}}

    def set_policy(self, values: dict) -> dict:
        policy = self.policy()
        for key, value in (values or {}).items():
            if key not in DEFAULT_POLICY:
                raise AuthError("Unknown policy setting.")
            if isinstance(DEFAULT_POLICY[key], bool):
                if type(value) is not bool:
                    raise AuthError("Use on or off for this setting.")
            else:
                low, high = POLICY_BOUNDS[key]
                if type(value) is not int or not low <= value <= high:
                    raise AuthError(f"Choose a number from {low} to {high}.")
            policy[key] = value
        with self.lock:
            data = self._load()
            data["policy"] = policy
            self._save(data)
        return policy

    def set_user(self, username: str, password: str, *, role: str, must_change: bool,
                 enforce_policy: bool = True) -> None:
        if not USERNAME.fullmatch(username or ""):
            raise AuthError("Use 3 to 40 lowercase letters, digits, dot, dash or underscore for the username.")
        if role not in ROLES:
            raise AuthError("Unknown role.")
        if not isinstance(password, str) or len(password) < MIN_PASSWORD:
            raise AuthError(f"The password needs at least {MIN_PASSWORD} characters.")
        problems = password_problems(password, self.policy())
        if enforce_policy and problems:
            raise AuthError("The password needs " + " and ".join(problems) + ".")
        salt = secrets.token_bytes(16)
        with self.lock:
            data = self._load()
            previous = data["users"].get(username, {})
            data["users"][username] = {"role": role, "salt": salt.hex(), "hash": _hash(password, salt),
                                       "iterations": ITERATIONS, "must_change": must_change, "disabled": False,
                                       "short_password": bool(problems),
                                       "created_utc": previous.get("created_utc", _now()), "updated_utc": _now()}
            self._save(data)

    def set_disabled(self, username: str, disabled: bool) -> None:
        with self.lock:
            data = self._load()
            if username not in data["users"]:
                raise AuthError("No such user.")
            data["users"][username]["disabled"] = disabled
            data["users"][username]["updated_utc"] = _now()
            self._save(data)

    def verify(self, username: str, password: str) -> dict | None:
        with self.lock:
            entry = self._load()["users"].get(username or "")
        if entry is None or entry.get("disabled"):
            _hash(password or "", b"\0" * 16)   # Same work whether or not the user exists.
            return None
        expected = _hash(password or "", bytes.fromhex(entry["salt"]), entry.get("iterations", ITERATIONS))
        return entry if compare_digest(expected, entry["hash"]) else None

    def list_users(self) -> list[dict]:
        with self.lock:
            users = self._load()["users"]
        return [{"username": name, "role": entry["role"], "disabled": entry.get("disabled", False),
                 "must_change": entry.get("must_change", False), "updated_utc": entry.get("updated_utc")}
                for name, entry in sorted(users.items())]

    def admin_count(self) -> int:
        return sum(1 for user in self.list_users() if user["role"] == "admin" and not user["disabled"])


class Authenticator:
    """Sessions in memory (a restart signs everyone out) and a per-username lockout."""

    def __init__(self, store: UserStore, *, clock=time.time):
        self.store, self.clock = store, clock
        self.sessions: dict[str, Session] = {}
        self.last_seen: dict[str, float] = {}
        self.failures: dict[str, list[float]] = {}
        self.lock = threading.RLock()

    def login(self, username: str, password: str) -> tuple[str, Session]:
        username = (username or "").strip().lower()
        now = self.clock()
        policy = self.store.policy()
        window = policy["lockout_minutes"] * 60
        with self.lock:
            recent = [moment for moment in self.failures.get(username, []) if now - moment < window]
            self.failures[username] = recent
            if len(recent) >= policy["max_failures"]:
                minutes = policy["lockout_minutes"]
                raise AuthError(f"Too many attempts. Wait {minutes} minute{'s' if minutes != 1 else ''} and try again.")
        entry = self.store.verify(username, password)
        with self.lock:
            if entry is None:
                self.failures[username].append(now)
                raise AuthError("The username or password is not correct.")
            self.failures.pop(username, None)
            token = secrets.token_urlsafe(32)
            session = Session(username, entry["role"], bool(entry.get("must_change")), now + SESSION_SECONDS,
                              bool(entry.get("short_password")))
            self.sessions[token] = session
            self.last_seen[token] = now
            return token, session

    def session(self, token: str | None) -> Session | None:
        if not token:
            return None
        now = self.clock()
        idle = self.store.policy()["idle_minutes"] * 60
        with self.lock:
            session = self.sessions.get(token)
            if session is None or session.expires < now or now - self.last_seen.get(token, now) > idle:
                self.sessions.pop(token, None)
                self.last_seen.pop(token, None)
                return None
            self.last_seen[token] = now
            return session

    def logout(self, token: str | None) -> None:
        with self.lock:
            self.sessions.pop(token or "", None)

    def change_password(self, token: str, current: str, new: str) -> Session:
        session = self.session(token)
        if session is None or self.store.verify(session.username, current) is None:
            raise AuthError("The current password is not correct.")
        if current == new:
            raise AuthError("Choose a password different from the current one.")
        self.store.set_user(session.username, new, role=session.role, must_change=False)
        with self.lock:
            updated = Session(session.username, session.role, False, session.expires, False)
            self.sessions[token] = updated
            return updated

    def end_sessions_of(self, username: str) -> None:
        with self.lock:
            for token in [token for token, session in self.sessions.items() if session.username == username]:
                self.sessions.pop(token)


OPEN_PATHS = ("/v1/auth/", "/health")


def install_pilot_auth(app, auth_file):
    """Require a signed-in session for every API route except sign-in itself and health."""
    store = UserStore(auth_file)
    auth = Authenticator(store)
    app.state.pilot_auth = auth

    @app.middleware("http")
    async def require_session(request: Request, call_next):
        path = request.url.path
        if path.startswith("/v1/") and not path.startswith(OPEN_PATHS):
            session = auth.session(request.cookies.get(COOKIE))
            if session is None:
                return JSONResponse({"detail": "Please sign in."}, status_code=401)
            if session.must_change and not path.startswith("/v1/auth/"):
                return JSONResponse({"detail": "Please change your password first."}, status_code=403)
            request.state.user = session
        return await call_next(request)

    def current(request: Request) -> Session:
        session = auth.session(request.cookies.get(COOKIE))
        if session is None:
            raise HTTPException(401, "Please sign in.")
        return session

    def public(session: Session) -> dict:
        return {"username": session.username, "role": session.role, "must_change": session.must_change,
                "short_password": session.short_password}

    @app.get("/v1/auth/me")
    def me(request: Request):
        return public(current(request))

    @app.post("/v1/auth/login")
    def login(body: dict):
        try:
            token, session = auth.login(str(body.get("username", "")), str(body.get("password", "")))
        except AuthError as error:
            raise HTTPException(401, str(error)) from None
        response = JSONResponse(public(session))
        response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True, samesite="strict", path="/")
        return response

    @app.post("/v1/auth/logout")
    def logout(request: Request):
        auth.logout(request.cookies.get(COOKIE))
        response = JSONResponse({"signed_out": True})
        response.delete_cookie(COOKIE, path="/")
        return response

    @app.post("/v1/auth/password")
    def change_password(request: Request, body: dict):
        current(request)
        try:
            session = auth.change_password(request.cookies.get(COOKIE), str(body.get("current_password", "")),
                                           str(body.get("new_password", "")))
        except AuthError as error:
            raise HTTPException(400, str(error)) from None
        return public(session)

    def admin(request: Request) -> Session:
        session = current(request)
        if session.role != "admin":
            raise HTTPException(403, "Only an administrator can do this.")
        return session

    @app.get("/v1/admin/users")
    def list_users(request: Request):
        admin(request)
        return {"users": store.list_users()}

    @app.post("/v1/admin/users")
    def save_user(request: Request, body: dict):
        acting = admin(request)
        username = str(body.get("username", "")).strip().lower()
        try:
            if "disabled" in body:
                if username == acting.username and body["disabled"]:
                    raise AuthError("You cannot disable your own account.")
                store.set_disabled(username, bool(body["disabled"]))
                if body["disabled"]:
                    auth.end_sessions_of(username)
            else:
                # New user or password reset: by policy, the person chooses their own at the next sign-in.
                store.set_user(username, str(body.get("password", "")), role=str(body.get("role", "user")),
                               must_change=store.policy()["first_sign_in_change"])
                auth.end_sessions_of(username)
        except AuthError as error:
            raise HTTPException(400, str(error)) from None
        return {"users": store.list_users()}

    @app.get("/v1/admin/policy")
    def get_policy(request: Request):
        admin(request)
        return {"policy": store.policy(), "bounds": POLICY_BOUNDS}

    @app.post("/v1/admin/policy")
    def save_policy(request: Request, body: dict):
        admin(request)
        try:
            return {"policy": store.set_policy(body), "bounds": POLICY_BOUNDS}
        except AuthError as error:
            raise HTTPException(400, str(error)) from None

    @app.get("/v1/auth/policy")
    def password_rules():
        policy = store.policy()
        return {key: policy[key] for key in ("min_length", "letters_and_numbers")}

    from .pilot_admin import install_pilot_admin
    install_pilot_admin(app, admin)
    return auth


def main(argv=None):
    """Operator setup on the workstation: create or reset one account. The password is typed, never echoed."""
    import argparse
    import getpass
    import sys
    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("command", choices=["set-user"])
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--role", choices=sorted(ROLES), default="user")
    parser.add_argument("--must-change", action="store_true")
    args = parser.parse_args(argv)
    password = sys.stdin.readline().rstrip(chr(13) + chr(10)) if not sys.stdin.isatty() else getpass.getpass("Password: ")
    try:
        # Operator setup on the workstation may set any password of at least 4 characters; the app flags it.
        UserStore(args.file).set_user(args.username, password, role=args.role, must_change=args.must_change,
                                      enforce_policy=False)
    except AuthError as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps({"saved": args.username, "role": args.role}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
