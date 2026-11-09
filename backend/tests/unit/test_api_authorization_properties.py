"""Property tests for the authorization guard (Properties 10, 42, 43).

The ownership guard is pure given a resolved principal and a stored resource,
so these run without a database. Property 10's HTTP-level indistinguishability
(cross-user vs nonexistent yields the identical 404) is reinforced by an
integration test; here we assert the guard's decision logic, that no decryption
happens on a denied request (Property 42), and that no model/tool dispatch
happens on a denied request (Property 43).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from hypothesis import given
from hypothesis import strategies as st

from series76_api.application.authorization import authorize_ownership, resolve_owner_id
from series76_api.domain.errors import NotFoundError
from series76_api.domain.models import AuthenticatedPrincipal, UserRole


@dataclass(frozen=True)
class _Resource:
    owner_id: uuid.UUID


def _principal(user_id: uuid.UUID, role: UserRole) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        user_id=user_id, role=role, auth_session_id=uuid.uuid4()
    )


_roles = st.sampled_from(list(UserRole))


# Feature: backend-api-auth-jobs-crypto, Property 10: Ownership is
# session-authoritative and cross-user access is an indistinguishable 404.
@given(
    session_owner=st.uuids(),
    resource_owner=st.uuids(),
    role=_roles,
    body_owner=st.uuids(),
)
def test_property_10_ownership_session_authoritative_indistinguishable_404(
    session_owner: uuid.UUID,
    resource_owner: uuid.UUID,
    role: UserRole,
    body_owner: uuid.UUID,
) -> None:
    """Owner is resolved from the session; cross-user == nonexistent (same 404)."""

    principal = _principal(session_owner, role)

    # Owner id is always the session's, regardless of any supplied body owner.
    # ``resolve_owner_id`` takes only the principal, so ``body_owner`` cannot
    # influence it by construction.
    assert resolve_owner_id(principal) == session_owner

    if resource_owner == session_owner:
        resource = _Resource(owner_id=resource_owner)
        assert authorize_ownership(principal, resource) is resource
    else:
        # Cross-user (including a developer) is denied with NotFound...
        cross_exc = _capture_notfound(
            lambda: authorize_ownership(principal, _Resource(resource_owner))
        )
        # ...identically to a nonexistent resource.
        missing_exc = _capture_notfound(lambda: authorize_ownership(principal, None))
        assert cross_exc is not None and missing_exc is not None
        # Indistinguishable: same code, same (empty) details, no attributes.
        assert cross_exc.code == missing_exc.code
        assert cross_exc.details == missing_exc.details == {}
        assert str(cross_exc) == str(missing_exc)


def _capture_notfound(fn: object) -> NotFoundError | None:
    try:
        fn()  # type: ignore[operator]
    except NotFoundError as exc:
        return exc
    return None


class _SpyCrypto:
    """A crypto spy recording whether any decrypt happened."""

    def __init__(self) -> None:
        self.decrypt_calls = 0

    def decrypt(self, *_args: object, **_kwargs: object) -> bytes:
        self.decrypt_calls += 1
        return b""


class _SpyDispatcher:
    """A model/tool dispatcher spy recording whether any dispatch happened."""

    def __init__(self) -> None:
        self.dispatch_calls = 0

    def dispatch(self, *_args: object, **_kwargs: object) -> None:
        self.dispatch_calls += 1


def _guarded_read(
    principal: AuthenticatedPrincipal,
    resource: _Resource | None,
    crypto: _SpyCrypto,
) -> None:
    """A representative read path: authorize BEFORE any decryption."""

    authorize_ownership(principal, resource)  # raises on denial, before decrypt
    crypto.decrypt(b"title-ciphertext")


def _guarded_dispatch(
    principal: AuthenticatedPrincipal,
    resource: _Resource | None,
    dispatcher: _SpyDispatcher,
) -> None:
    """A representative action path: authorize BEFORE any model/tool dispatch."""

    authorize_ownership(principal, resource)  # raises on denial, before dispatch
    dispatcher.dispatch("agent-turn")


# Feature: backend-api-auth-jobs-crypto, Property 42: Authorization precedes
# decryption.
@given(session_owner=st.uuids(), resource_owner=st.uuids(), role=_roles)
def test_property_42_authorization_precedes_decryption(
    session_owner: uuid.UUID, resource_owner: uuid.UUID, role: UserRole
) -> None:
    """On a denied request no decryption is performed on the target resource."""

    principal = _principal(session_owner, role)
    crypto = _SpyCrypto()

    if resource_owner == session_owner:
        _guarded_read(principal, _Resource(resource_owner), crypto)
        assert crypto.decrypt_calls == 1  # allowed path decrypts exactly once
    else:
        denied = _capture_notfound(
            lambda: _guarded_read(principal, _Resource(resource_owner), crypto)
        )
        assert denied is not None
        assert crypto.decrypt_calls == 0  # denial -> NO decryption

    # A nonexistent resource is likewise denied before any decryption.
    crypto2 = _SpyCrypto()
    assert (
        _capture_notfound(lambda: _guarded_read(principal, None, crypto2)) is not None
    )
    assert crypto2.decrypt_calls == 0


# Feature: backend-api-auth-jobs-crypto, Property 43: Endpoint authorization
# precedes any model or tool dispatch.
@given(session_owner=st.uuids(), resource_owner=st.uuids(), role=_roles)
def test_property_43_authorization_precedes_dispatch(
    session_owner: uuid.UUID, resource_owner: uuid.UUID, role: UserRole
) -> None:
    """On a denied request no model is dispatched and no tool is invoked."""

    principal = _principal(session_owner, role)
    dispatcher = _SpyDispatcher()

    if resource_owner == session_owner:
        _guarded_dispatch(principal, _Resource(resource_owner), dispatcher)
        assert dispatcher.dispatch_calls == 1
    else:
        denied = _capture_notfound(
            lambda: _guarded_dispatch(principal, _Resource(resource_owner), dispatcher)
        )
        assert denied is not None
        assert dispatcher.dispatch_calls == 0

    dispatcher2 = _SpyDispatcher()
    assert (
        _capture_notfound(lambda: _guarded_dispatch(principal, None, dispatcher2))
        is not None
    )
    assert dispatcher2.dispatch_calls == 0
