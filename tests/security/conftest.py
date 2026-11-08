"""Fixtures communes : application minimale (routeur d'authentification seul), base Mongo remplacée par des doubles."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest
from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import rate_limit
from app.core.deps import get_current_user

DEMO_ORG_ID = "66aaaaaaaaaaaaaaaaaaaaaa"
OTHER_ORG_ID = "66bbbbbbbbbbbbbbbbbbbbbb"


class FakeCollection:
    def __init__(self, docs: List[dict]):
        self.docs = docs

    async def update_one(self, query: dict, update: dict) -> None:
        self.updates = getattr(self, "updates", []) + [(query, update)]

    async def find_one(self, query: dict) -> Optional[dict]:
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in query.items()):
                return doc
        return None


class FakeDb:
    def __init__(self):
        self.collections: Dict[str, FakeCollection] = {
            "organizations": FakeCollection(
                [{"_id": ObjectId(DEMO_ORG_ID), "code": "MIZNAS_TEST"}, {"_id": ObjectId(OTHER_ORG_ID), "code": "BANQUE_B"}]
            )
        }

    def __getitem__(self, name: str) -> FakeCollection:
        return self.collections.setdefault(name, FakeCollection([]))


@pytest.fixture(autouse=True)
def _limiter_state(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "1")
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "0")
    monkeypatch.delenv("DYNO", raising=False)
    rate_limit.limiter.reset()
    rate_limit.login_guard.reset()
    yield
    rate_limit.limiter.reset()
    rate_limit.login_guard.reset()


@pytest.fixture
def created(monkeypatch) -> List[Any]:
    """Liste des demandes réellement transmises à create_user (après assainissement par la politique)."""
    import app.core.db as core_db
    import app.routers.auth as auth_router

    sink: List[Any] = []

    async def fake_create_user(user_in):
        sink.append(user_in)
        return {
            "id": "1" * 24,
            "email": user_in.email,
            "full_name": user_in.full_name,
            "organization_id": user_in.organization_id,
            "role": user_in.role,
            "is_active": True,
        }

    db = FakeDb()
    monkeypatch.setattr(core_db, "get_database", lambda: db)
    monkeypatch.setattr(auth_router, "get_database", lambda: db)
    monkeypatch.setattr(auth_router, "create_user", fake_create_user)
    return sink


@pytest.fixture
def make_client(created):
    from app.routers.auth import router

    def _make(current_user: Optional[dict] = None) -> TestClient:
        """current_user=None : appel anonyme (la vraie dépendance OAuth2 répond 401). Sinon utilisateur connecté simulé,
        les vraies dépendances de rôle (get_superadmin) s'appliquent."""
        app = FastAPI()
        app.include_router(router)
        if current_user is not None:
            app.dependency_overrides[get_current_user] = lambda: current_user
        return TestClient(app)

    return _make


def payload(**overrides) -> dict:
    data = {"email": "nouveau@example.com", "full_name": "Utilisateur Test", "password": "Secret-123456"}  # gitleaks:allow (valeur factice de test)
    data.update(overrides)
    return data


SUPERADMIN = {"id": "9" * 24, "role": "superadmin", "organization_id": None, "is_active": True}
ORG_ADMIN = {"id": "8" * 24, "role": "admin", "organization_id": OTHER_ORG_ID, "is_active": True}
PLAIN_USER = {"id": "7" * 24, "role": "user", "organization_id": DEMO_ORG_ID, "is_active": True}
