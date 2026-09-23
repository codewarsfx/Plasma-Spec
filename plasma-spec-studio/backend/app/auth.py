"""Request-scoped auth + storage-backend selection.

Two modes, chosen by ``PLASMA_SPEC_STORAGE_BACKEND`` (default ``local``):

- ``local`` (default): no auth required. Every route works exactly as it
  did before Supabase support existed -- a single implicit local user,
  backed by the local SQLite ``LocalStore``. This is what the existing
  pytest suite runs against, and what a solo researcher gets with zero
  Supabase setup.
- ``supabase``: every route requires a valid ``Authorization: Bearer
  <supabase-access-token>`` header. The token is verified locally (no round
  trip to Supabase Auth for every request) against the project's public
  JWKS (Settings -> API -> JWT Keys -> "JWT Signing Keys") -- Supabase
  projects now default to asymmetric ES256 signing keys rather than a
  shared HS256 secret, so this only needs the project's already-public
  ``SUPABASE_URL``, not a secret. Projects that haven't migrated off the
  legacy shared secret (or tokens issued just before a migration, until
  they expire) fall back to HS256 against ``SUPABASE_JWT_SECRET`` if it's
  set. Either way the verified token is used to build a ``SupabaseStore``
  that acts as that user for the rest of the request, so Postgres
  Row-Level-Security is the actual enforcement boundary.

``Depends(authenticated)`` is the single dependency routes need; it both
authenticates the caller and makes the right ``Store`` ambient for
everything the route calls into (see ``app.services.backends.base``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import AsyncIterator

import jwt
from fastapi import Header, HTTPException, Query
from jwt import PyJWKClientError

from app.services.backends.base import use_store
from app.services.backends.local_store import LocalStore
from app.services.backends.supabase_store import SupabaseStore


STORAGE_BACKEND = os.environ.get("PLASMA_SPEC_STORAGE_BACKEND", "local").strip().lower()
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
# Optional: only needed for a project still on (or mid-migration off of) the
# legacy shared-secret signing method -- see _verify_supabase_jwt below.
SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "")

_LOCAL_USER_ID = "local"

_jwks_client: jwt.PyJWKClient | None = None


def _jwks_client_for(supabase_url: str) -> jwt.PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = jwt.PyJWKClient(f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json")
    return _jwks_client


@dataclass(frozen=True, slots=True)
class AuthedUser:
    id: str
    email: str | None
    token: str | None
    backend: str


def _verify_supabase_jwt(token: str) -> dict:
    if not SUPABASE_URL:
        raise HTTPException(
            status_code=500,
            detail="PLASMA_SPEC_STORAGE_BACKEND=supabase but SUPABASE_URL is not set",
        )
    try:
        signing_key = _jwks_client_for(SUPABASE_URL).get_signing_key_from_jwt(token)
        return jwt.decode(token, signing_key.key, algorithms=["ES256", "RS256"], audience="authenticated")
    except PyJWKClientError:
        # No matching key in the JWKS -- likely a token signed with the
        # legacy shared secret rather than the project's asymmetric keys.
        if not SUPABASE_JWT_SECRET:
            raise HTTPException(
                status_code=401,
                detail=(
                    "auth token isn't signed by this project's JWKS and no "
                    "SUPABASE_JWT_SECRET fallback is configured"
                ),
            ) from None
        try:
            return jwt.decode(token, SUPABASE_JWT_SECRET, algorithms=["HS256"], audience="authenticated")
        except jwt.PyJWTError as exc:
            raise HTTPException(status_code=401, detail=f"invalid auth token: {exc}") from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"invalid auth token: {exc}") from exc


async def authenticated(
    authorization: str | None = Header(default=None),
    # EventSource (used for the batch SSE stream) can't set custom headers,
    # so batchStreamUrl() in the frontend passes the access token as a query
    # param instead. Every other request goes through lib/api.ts's shared
    # fetch wrapper and uses the header.
    token: str | None = Query(default=None),
) -> AsyncIterator[AuthedUser]:
    if STORAGE_BACKEND == "local":
        user = AuthedUser(id=_LOCAL_USER_ID, email=None, token=None, backend="local")
        with use_store(LocalStore()):
            yield user
        return

    if STORAGE_BACKEND != "supabase":
        raise HTTPException(
            status_code=500,
            detail=f"unknown PLASMA_SPEC_STORAGE_BACKEND: {STORAGE_BACKEND!r} (expected 'local' or 'supabase')",
        )

    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="missing bearer token")

    claims = _verify_supabase_jwt(token)
    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="auth token missing 'sub' claim")

    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise HTTPException(
            status_code=500,
            detail="PLASMA_SPEC_STORAGE_BACKEND=supabase but SUPABASE_URL/SUPABASE_ANON_KEY are not set",
        )

    user = AuthedUser(id=user_id, email=claims.get("email"), token=token, backend="supabase")
    store = SupabaseStore(SUPABASE_URL, SUPABASE_ANON_KEY, token, user_id)
    with use_store(store):
        yield user
