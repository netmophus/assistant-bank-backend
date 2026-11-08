"""Parcours public mobile : /auth/register-demo (OTP e-mail) -> /auth/verify-otp -> /auth/login ; contrats de réponse."""

from __future__ import annotations

import pytest
from bson import ObjectId

from tests.security.conftest import DEMO_ORG_ID, OTHER_ORG_ID

pytestmark = pytest.mark.security

DEMO = {
    "email": "mobile@example.com", "password": "Secret-123456",  # gitleaks:allow (valeur factice de test)
    "first_name": "Aissa", "last_name": "Test", "phone_country_code": "+227", "phone_number": "90000000",
}


@pytest.fixture
def demo(monkeypatch, created):
    import app.models.user as user_model
    import app.routers.auth as auth_router

    state = {"created": [], "mails": []}
    doc = {
        "_id": ObjectId(), "email": DEMO["email"], "full_name": "Aissa Test", "role": "user", "is_demo": True,
        "email_verified": False, "organization_id": ObjectId(DEMO_ORG_ID), "is_active": True,
    }

    async def create_demo_user(data):
        state["created"].append(data)
        return doc

    async def create_otp(email):
        return "123456"

    async def send_email(to, subject, html):
        state["mails"].append(to)

    async def verify_otp(email, code):
        if code != "123456":
            raise auth_router.OtpVerificationError("INVALID_CODE", "Code incorrect.")

    async def get_user_by_email(email):
        return doc

    async def authenticate_user(email, password):
        return doc if password == DEMO["password"] else None

    monkeypatch.setattr(auth_router, "create_demo_user", create_demo_user)
    monkeypatch.setattr(auth_router, "create_or_replace_otp", create_otp)
    monkeypatch.setattr(auth_router, "send_email", send_email)
    monkeypatch.setattr(auth_router, "verify_otp", verify_otp)
    monkeypatch.setattr(auth_router, "authenticate_user", authenticate_user)
    monkeypatch.setattr(user_model, "get_user_by_email", get_user_by_email)
    state["doc"] = doc
    return state


def test_register_demo_is_public_sends_an_otp_and_keeps_its_contract(make_client, demo):
    response = make_client().post("/auth/register-demo", json=DEMO)
    assert response.status_code == 200, response.text
    assert set(response.json()) == {"success", "message", "email", "requires_otp_verification"}
    assert response.json()["requires_otp_verification"] is True
    assert demo["mails"] == [DEMO["email"]]


def test_register_demo_ignores_client_supplied_privileges(make_client, demo):
    response = make_client().post(
        "/auth/register-demo", json={**DEMO, "role": "admin", "organization_id": OTHER_ORG_ID, "is_superadmin": True}
    )
    assert response.status_code == 200
    submitted = demo["created"][0]
    assert not hasattr(submitted, "role") and not hasattr(submitted, "organization_id")


def test_unverified_demo_account_cannot_log_in_then_otp_unlocks_it(make_client, demo):
    client = make_client()
    blocked = client.post("/auth/login", json={"email": DEMO["email"], "password": DEMO["password"]})
    assert blocked.status_code == 403 and blocked.json()["detail"]["code"] == "EMAIL_NOT_VERIFIED"

    assert client.post("/auth/verify-otp", json={"email": DEMO["email"], "code": "000000"}).status_code == 400

    ok = client.post("/auth/verify-otp", json={"email": DEMO["email"], "code": "123456"})
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert {"access_token", "token_type", "user"} <= set(body) and body["token_type"] == "bearer"
    assert body["user"]["role"] == "user" and body["user"]["email_verified"] is True


def test_login_response_contract_for_a_verified_account(make_client, demo, monkeypatch):
    import app.routers.auth as auth_router

    demo["doc"]["email_verified"] = True

    async def license_ok(org_id):
        return {"active": True}

    monkeypatch.setattr(auth_router, "get_active_license_for_org", license_ok)
    response = make_client().post("/auth/login", json={"email": DEMO["email"], "password": DEMO["password"]})
    assert response.status_code == 200 and set(response.json()) == {"access_token", "token_type"}
