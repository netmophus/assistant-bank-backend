"""POST /auth/register est réservée au superadmin ; l'inscription publique est /auth/register-demo (OTP)."""

from __future__ import annotations

import asyncio

import pytest
from bson import ObjectId

from tests.security.conftest import (
    DEMO_ORG_ID,
    ORG_ADMIN,
    OTHER_ORG_ID,
    PLAIN_USER,
    SUPERADMIN,
    payload,
)

pytestmark = pytest.mark.security


# --- Refus sans authentification ou sans le rôle superadmin ------------------------------------------------------------
@pytest.mark.parametrize(
    "extra",
    [
        {},
        {"role": "user"},
        {"role": "admin", "organization_id": OTHER_ORG_ID},
        {"role": "superadmin"},
        {"organization_id": DEMO_ORG_ID},
        {"role": "Admin", "organization_id": OTHER_ORG_ID},
    ],
)
def test_anonymous_calls_are_refused_with_401(make_client, created, extra):
    response = make_client().post("/auth/register", json=payload(**extra))
    assert response.status_code == 401, response.text
    assert created == []


def test_invalid_or_garbage_token_is_refused(make_client, created):
    for header in ("Bearer jeton.invalide.xyz", "Bearer ", "Basic abc", "Bearer null"):
        response = make_client().post(
            "/auth/register",
            json=payload(role="admin", organization_id=OTHER_ORG_ID),
            headers={"Authorization": header},
        )
        assert response.status_code == 401, header
    assert created == []


@pytest.mark.parametrize("caller", [ORG_ADMIN, PLAIN_USER], ids=["org_admin", "plain_user"])
@pytest.mark.parametrize(
    "extra",
    [{}, {"role": "admin", "organization_id": OTHER_ORG_ID}, {"role": "user", "organization_id": OTHER_ORG_ID}, {"role": "superadmin"}],
)
def test_authenticated_non_superadmin_is_refused_with_403(make_client, created, caller, extra):
    response = make_client(current_user=caller).post("/auth/register", json=payload(**extra))
    assert response.status_code == 403, response.text
    assert created == []


# --- Ce que le superadmin peut faire ------------------------------------------------------------------------------------
def test_superadmin_creates_organization_admin_like_the_admin_screen(make_client, created):
    """Reproduit l'appel de app/admin/dashboard/page.tsx : role=admin + organization_id."""
    response = make_client(current_user=SUPERADMIN).post(
        "/auth/register", json=payload(role="admin", organization_id=OTHER_ORG_ID)
    )
    assert response.status_code == 200, response.text
    assert created[0].role == "admin" and created[0].organization_id == OTHER_ORG_ID


def test_superadmin_creates_plain_user_and_default_role_is_user(make_client, created):
    client = make_client(current_user=SUPERADMIN)
    assert client.post("/auth/register", json=payload(role="user", organization_id=OTHER_ORG_ID)).status_code == 200
    assert client.post("/auth/register", json=payload(email="b@example.com", organization_id=OTHER_ORG_ID)).status_code == 200
    assert [u.role for u in created] == ["user", "user"]


def test_register_response_contract_is_unchanged(make_client):
    body = make_client(current_user=SUPERADMIN).post(
        "/auth/register", json=payload(role="admin", organization_id=OTHER_ORG_ID)
    ).json()
    assert {"id", "email", "full_name", "role"} <= set(body)


def test_role_is_normalised_server_side(make_client, created):
    response = make_client(current_user=SUPERADMIN).post(
        "/auth/register", json=payload(role=" ADMIN ", organization_id=OTHER_ORG_ID)
    )
    assert response.status_code == 200 and created[0].role == "admin"


@pytest.mark.parametrize("role", ["superadmin", "SuperAdmin", " superadmin "])
def test_nobody_can_create_a_superadmin_not_even_a_superadmin(make_client, created, role):
    response = make_client(current_user=SUPERADMIN).post(
        "/auth/register", json=payload(role=role, organization_id=OTHER_ORG_ID)
    )
    assert response.status_code == 403 and created == []


@pytest.mark.parametrize("role", ["root", "gestionnaire_stock", "agent_stock_drh", "owner"])
def test_unknown_or_stock_roles_are_refused_on_this_route(make_client, created, role):
    response = make_client(current_user=SUPERADMIN).post(
        "/auth/register", json=payload(role=role, organization_id=OTHER_ORG_ID)
    )
    assert response.status_code == 403 and created == []


def test_organization_is_required(make_client, created):
    for role in ("admin", "user"):
        assert make_client(current_user=SUPERADMIN).post("/auth/register", json=payload(role=role)).status_code == 400
    assert created == []


@pytest.mark.parametrize("organization_id", [str(ObjectId()), "not-an-id", "' || 1=1", "../x", "{'$ne': null}"])
def test_invalid_or_unknown_organization_is_refused(make_client, created, organization_id):
    response = make_client(current_user=SUPERADMIN).post(
        "/auth/register", json=payload(role="admin", organization_id=organization_id)
    )
    assert response.status_code == 400 and created == []


def test_extra_privilege_fields_are_never_forwarded(make_client, created):
    response = make_client(current_user=SUPERADMIN).post(
        "/auth/register",
        json=payload(
            role="user", organization_id=OTHER_ORG_ID, is_active=False, is_superadmin=True, is_admin=True,
            permissions=["*"], tab_permissions={"all": True}, is_demo=False,
        ),
    )
    assert response.status_code == 200
    assert set(created[0].model_dump()) <= {
        "email", "full_name", "password", "organization_id", "department_id", "service_id", "role", "role_departement"
    }


# --- Permissions après création -----------------------------------------------------------------------------------------
def test_account_created_by_superadmin_as_user_has_no_administrative_access(make_client, created):
    from fastapi import HTTPException

    from app.core.deps import get_org_admin, get_superadmin

    make_client(current_user=SUPERADMIN).post("/auth/register", json=payload(role="user", organization_id=OTHER_ORG_ID))
    new_user = {"id": "1" * 24, "role": created[0].role, "organization_id": created[0].organization_id}
    for dependency in (get_superadmin, get_org_admin):
        with pytest.raises(HTTPException) as info:
            asyncio.run(dependency(new_user))
        assert info.value.status_code == 403


@pytest.mark.parametrize(
    "method, path, body",
    [
        ("get", "/auth/users", None),
        ("put", "/auth/users/" + "1" * 24, {"role": "superadmin"}),
        ("post", "/auth/users/org", payload(organization_id=DEMO_ORG_ID)),
        ("put", "/auth/users/org/" + "1" * 24, {"is_active": False}),
    ],
)
def test_administration_routes_reject_a_plain_user(make_client, method, path, body):
    client = make_client(current_user=PLAIN_USER)
    response = getattr(client, method)(path, **({"json": body} if body is not None else {}))
    assert response.status_code == 403


def test_org_admin_creation_route_stays_in_its_own_perimeter(make_client):
    """/auth/users/org reste la voie des administrateurs d'organisation : ni admin, ni autre organisation."""
    client = make_client(current_user=ORG_ADMIN)
    assert client.post("/auth/users/org", json=payload(organization_id=DEMO_ORG_ID, role="admin")).status_code == 403
