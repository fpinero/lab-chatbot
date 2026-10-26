import hashlib
import secrets
from collections.abc import Callable
from datetime import UTC, datetime
from hmac import compare_digest
from ipaddress import ip_address, ip_network
from threading import BoundedSemaphore

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.auth.access import AccessVerifier
from app.auth.policy import DeclarativePolicy
from app.config import Settings
from app.models import AuthBucket, Owner, OwnerSession


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class AuthError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        self.status, self.code, self.message = status, code, message


class AuthService:
    def __init__(
        self,
        engine: Engine,
        settings: Settings,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.engine, self.settings, self.clock = engine, settings, clock
        self.policy = (
            DeclarativePolicy.load(settings.auth_policy_file) if settings.auth_policy_file else None
        )
        self.access = AccessVerifier(settings) if settings.auth_mode == "access" else None
        self.hasher = PasswordHasher()
        self.password_slots = BoundedSemaphore(2)

    def client_ip(self, request: Request) -> str:
        peer = request.client.host if request.client else "unknown"
        try:
            networks = [ip_network(value) for value in self.settings.trusted_proxy_networks]
            if not any(ip_address(peer) in network for network in networks):
                return peer
            chain = request.headers.get("x-forwarded-for", "").split(",")
            if len(chain) > 16:
                return peer
            for value in reversed(chain):
                if not any(ip_address(peer) in network for network in networks):
                    break
                peer = str(ip_address(value.strip()))
        except ValueError:
            return request.client.host if request.client else "unknown"
        return peer

    def verify_access(self, request: Request) -> None:
        if self.access and not self.access.verify(
            request.headers.get("cf-access-jwt-assertion", "")
        ):
            raise AuthError(401, "identity_required", "Verified owner identity is required.")

    def check_origin(self, request: Request, *, required: bool = False) -> None:
        origin = request.headers.get("origin")
        if (
            (required or origin is not None)
            and origin != self.settings.app_origin
            or request.headers.get("sec-fetch-site") == "cross-site"
        ):
            raise AuthError(403, "origin_rejected", "This request origin is not allowed.")

    def reserve_attempt(self, ip: str) -> list[str]:
        now = int(self.clock().timestamp())
        keys = [digest(f"ip:{ip}"), digest("global")]
        with Session(self.engine) as db:
            db.connection().exec_driver_sql("BEGIN IMMEDIATE")
            db.execute(delete(AuthBucket).where(AuthBucket.window_start <= now - 300))
            for key, limit in zip(keys, [5, 50], strict=True):
                bucket = db.get(AuthBucket, key)
                if bucket and bucket.attempts >= limit:
                    db.rollback()
                    raise AuthError(429, "login_throttled", "Too many attempts. Try again later.")
                if bucket:
                    bucket.attempts += 1
                else:
                    db.add(AuthBucket(key=key, window_start=now, attempts=1))
            db.commit()
        return keys

    def login(self, request: Request, password: str, code: str) -> tuple[str, OwnerSession]:
        self.check_origin(request, required=True)
        self.verify_access(request)
        keys = self.reserve_attempt(self.client_ip(request))
        valid = True
        if self.settings.auth_mode == "password":
            try:
                with self.password_slots:
                    valid = self.hasher.verify(
                        self.settings.auth_password_hash.get_secret_value(), password
                    )
            except VerificationError:
                valid = False
        if self.policy:
            valid = self.policy.verify(code, self.clock()) and valid
        if not valid:
            raise AuthError(401, "login_failed", "Sign-in failed. Check your credentials.")
        token = secrets.token_urlsafe(32)
        now = int(self.clock().timestamp())
        with Session(self.engine, expire_on_commit=False) as db:
            db.connection().exec_driver_sql("BEGIN IMMEDIATE")
            if not db.get(Owner, "primary"):
                db.add(Owner(id="primary", created_at=now))
                db.flush()
            old = request.cookies.get(self.settings.cookie_name)
            if old:
                db.execute(delete(OwnerSession).where(OwnerSession.token_hash == digest(old)))
            db.execute(delete(OwnerSession).where(OwnerSession.expires_at <= now))
            for key in keys:
                bucket = db.get(AuthBucket, key)
                if bucket:
                    bucket.attempts = max(0, bucket.attempts - 1)
            session = OwnerSession(
                token_hash=digest(token),
                owner_id="primary",
                csrf_token=secrets.token_urlsafe(32),
                created_at=now,
                last_seen=now,
                expires_at=now + self.settings.session_absolute_seconds,
            )
            db.add(session)
            db.commit()
        return token, session

    def authenticate(self, request: Request) -> OwnerSession:
        self.verify_access(request)
        self.check_origin(request)
        token = request.cookies.get(self.settings.cookie_name, "")
        now = int(self.clock().timestamp())
        with Session(self.engine, expire_on_commit=False) as db:
            session = db.get(OwnerSession, digest(token)) if token else None
            if (
                not session
                or now >= session.expires_at
                or now >= session.last_seen + self.settings.session_idle_seconds
            ):
                raise AuthError(401, "session_required", "Sign in to continue.")
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                self.check_origin(request, required=True)
                if not compare_digest(
                    request.headers.get("x-csrf-token", "").encode(), session.csrf_token.encode()
                ):
                    raise AuthError(403, "csrf_rejected", "Refresh your session and try again.")
            session.last_seen = now
            db.commit()
            return session

    def logout(self, session: OwnerSession) -> None:
        with Session(self.engine) as db:
            db.execute(delete(OwnerSession).where(OwnerSession.token_hash == session.token_hash))
            db.commit()

    def ready(self) -> bool:
        with Session(self.engine) as db:
            db.execute(select(Owner.id).limit(1))
        return self.settings.data_dir.is_dir()
