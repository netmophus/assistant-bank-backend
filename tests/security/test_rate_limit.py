"""Limitation de débit : mécanisme, détermination de l'IP, protection de la connexion, comportement des agences."""

from __future__ import annotations

import pytest
from starlette.requests import Request

from app.core import rate_limit
from app.core.rate_limit import SlidingWindowLimiter, client_ip, trusted_proxy_hops
from tests.security.conftest import OTHER_ORG_ID, SUPERADMIN, payload

pytestmark = pytest.mark.security

PASSWORD = "Secret-123456"  # gitleaks:allow (valeur factice de test)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(rate_limit.login_guard, "_clock", c)
    monkeypatch.setattr(rate_limit.limiter, "_clock", c)
    return c


def make_request(forwarded=None, peer="203.0.113.9"):
    headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded is not None else []
    scope = {"type": "http", "headers": headers, "client": (peer, 5555) if peer else None}
    return Request(scope)


# --- mécanisme de fenêtre -------------------------------------------------------------------------------------------------
def test_window_blocks_after_limit_and_reports_retry_after():
    now = [0.0]
    limiter = SlidingWindowLimiter(clock=lambda: now[0])
    assert [limiter.hit("k", 3, 60)[0] for _ in range(3)] == [True, True, True]
    allowed, retry = limiter.hit("k", 3, 60)
    assert not allowed and 1 <= retry <= 60


def test_window_slides_and_keys_are_independent():
    now = [0.0]
    limiter = SlidingWindowLimiter(clock=lambda: now[0])
    for _ in range(3):
        limiter.hit("a", 3, 60)
    assert limiter.hit("b", 3, 60)[0]
    now[0] = 61
    assert limiter.hit("a", 3, 60)[0]


def test_disabled_flag_turns_every_limit_off(monkeypatch, clock):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "0")
    for _ in range(500):
        rate_limit.enforce("x", "ip", 1, 60)
        rate_limit.login_guard.record_failure("1.1.1.1", "a@example.com")
    rate_limit.login_guard.check("1.1.1.1", "a@example.com")


def test_env_override_of_a_named_limit(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_DEMO_X", "2/60")
    rate_limit.enforce("demo_x", "ip", 100, 60)
    rate_limit.enforce("demo_x", "ip", 100, 60)
    with pytest.raises(Exception) as info:
        rate_limit.enforce("demo_x", "ip", 100, 60)
    assert info.value.status_code == 429
    monkeypatch.setenv("RATE_LIMIT_DEMO_Y", "garbage")
    for _ in range(5):
        rate_limit.enforce("demo_y", "ip", 100, 60)  # surcharge illisible : valeur par défaut


def test_429_is_uniform_and_carries_retry_after():
    with pytest.raises(Exception) as first:
        for _ in range(3):
            rate_limit.enforce("u", "ip", 1, 60)
    err = first.value
    assert err.status_code == 429 and err.detail == "Trop de tentatives. Réessayez plus tard."
    assert err.headers["Retry-After"].isdigit() and int(err.headers["Retry-After"]) >= 1


# --- adresse IP du client / en-têtes de proxy -----------------------------------------------------------------------------
def test_forwarded_header_is_ignored_without_trusted_proxy():
    assert client_ip(make_request("6.6.6.6, 7.7.7.7", peer="203.0.113.9")) == "203.0.113.9"


def test_forwarded_header_uses_the_hop_added_by_our_proxy(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "1")
    assert client_ip(make_request("6.6.6.6, 198.51.100.4")) == "198.51.100.4"  # le début est falsifiable, la fin non


def test_forged_leading_entries_cannot_change_the_identity(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "1")
    ids = {client_ip(make_request(f"10.0.0.{i}, 198.51.100.4")) for i in range(50)}
    assert ids == {"198.51.100.4"}


def test_two_trusted_hops_for_a_cdn_in_front(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "2")
    assert client_ip(make_request("9.9.9.9, 198.51.100.4, 172.16.0.1")) == "198.51.100.4"


def test_ip_is_unknown_when_the_proxy_header_is_missing_short_or_garbage(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "1")
    assert client_ip(make_request(None)) == "unknown"
    assert client_ip(make_request("")) == "unknown"
    assert client_ip(make_request("not-an-ip")) == "unknown"
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "2")
    assert client_ip(make_request("198.51.100.4")) == "unknown"


def test_ip_is_unknown_without_peer_and_without_proxy():
    assert client_ip(make_request(None, peer=None)) == "unknown"


def test_ipv6_clients_are_grouped_by_64_and_mapped_ipv4_is_unwrapped(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "1")
    a = client_ip(make_request("2001:db8:1:2:aaaa::1"))
    b = client_ip(make_request("2001:db8:1:2:bbbb::9"))
    assert a == b and client_ip(make_request("::ffff:198.51.100.4")) == "198.51.100.4"


def test_heroku_dyno_enables_one_trusted_hop_by_default(monkeypatch):
    monkeypatch.delenv("TRUSTED_PROXY_HOPS", raising=False)
    monkeypatch.setenv("DYNO", "web.1")
    assert trusted_proxy_hops() == 1
    monkeypatch.delenv("DYNO")
    assert trusted_proxy_hops() == 0
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "abc")
    assert trusted_proxy_hops() == 0  # valeur illisible : ne rien croire


# --- connexion --------------------------------------------------------------------------------------------------------------
@pytest.fixture
def login(make_client, monkeypatch, clock):
    """login(email, password, ip) ; comptes de test : tous avec le même mot de passe."""
    import app.routers.auth as auth_router

    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "1")
    monkeypatch.setenv("RATE_LIMIT_LOGIN_IP", "100000/60")  # isole la logique d'échecs du plafond de requêtes

    async def authenticate_user(email, password):
        if password != PASSWORD:
            return None
        return {"_id": "1" * 24, "email": email, "role": "user", "organization_id": OTHER_ORG_ID}

    async def license_ok(org_id):
        return {"active": True}

    monkeypatch.setattr(auth_router, "authenticate_user", authenticate_user)
    monkeypatch.setattr(auth_router, "get_active_license_for_org", license_ok)
    client = make_client()

    def _login(email="agent@example.com", password=PASSWORD, ip="198.51.100.10"):
        return client.post(
            "/auth/login", json={"email": email, "password": password}, headers={"X-Forwarded-For": f"1.2.3.4, {ip}"}
        )

    return _login


def test_many_colleagues_behind_one_ip_can_all_log_in_repeatedly(login):
    for round_ in range(3):
        for i in range(40):
            assert login(f"agent{i}@example.com").status_code == 200, (round_, i)


def test_successful_logins_never_consume_quota(login):
    for _ in range(200):
        assert login().status_code == 200


def test_a_few_typos_are_free_then_lock_is_temporary_and_progressive(login, clock):
    for _ in range(5):
        assert login(password="bad").status_code == 401
    assert login(password="bad").status_code == 401  # 6e échec : déclenche le verrou
    locked = login()  # même le bon mot de passe est refusé pendant le verrou
    assert locked.status_code == 429 and 1 <= int(locked.headers["Retry-After"]) <= 30
    clock.advance(31)
    assert login(password="bad").status_code == 401  # nouvel échec : verrou doublé (60 s)
    clock.advance(31)
    assert login().status_code == 429
    clock.advance(30)
    assert login().status_code == 200


def test_lock_is_capped(login, clock):
    for _ in range(40):
        login(password="bad")
        clock.advance(2000)  # chaque tentative hors verrou (et hors délai de remise à zéro)
    clock.advance(0)
    for _ in range(8):
        login(password="bad")
    locked = login()
    assert locked.status_code == 429 and int(locked.headers["Retry-After"]) <= 900


def test_one_users_lock_does_not_block_a_colleague_on_the_same_ip(login):
    for _ in range(8):
        login("clumsy@example.com", password="bad")
    assert login("clumsy@example.com").status_code == 429
    assert login("colleague@example.com").status_code == 200


def test_a_third_party_cannot_lock_the_victim_from_another_address(login):
    for _ in range(12):
        login("victim@example.com", password="bad", ip="203.0.113.66")  # l'attaquant
    assert login("victim@example.com", ip="203.0.113.66").status_code == 429
    assert login("victim@example.com", ip="198.51.100.10").status_code == 200  # la victime, depuis son agence


def test_distributed_attack_on_one_account_spares_known_addresses_only(login, clock):
    assert login("victim@example.com", ip="198.51.100.10").status_code == 200  # adresse connue de ce compte
    for i in range(30):
        login("victim@example.com", password="bad", ip=f"203.0.113.{i + 1}")
    assert login("victim@example.com", ip="198.51.100.10").status_code == 200  # connue : passe
    blocked = login("victim@example.com", ip="198.51.100.77")  # inconnue : refusée pendant l'attaque
    assert blocked.status_code == 429 and blocked.json()["detail"] == "Trop de tentatives. Réessayez plus tard."
    assert login("other@example.com", ip="198.51.100.77").status_code == 200  # les autres comptes ne sont pas touchés
    clock.advance(901)
    assert login("victim@example.com", ip="198.51.100.77").status_code == 200  # fin de la période


def test_ip_failure_ceiling_applies_per_address(login, monkeypatch):
    monkeypatch.setenv("LOGIN_IP_FAIL_LIMIT", "10")
    for i in range(10):
        assert login(f"user{i}@example.com", password="bad", ip="203.0.113.50").status_code == 401
    assert login("fresh@example.com", ip="203.0.113.50").status_code == 429
    assert login("fresh@example.com", ip="203.0.113.51").status_code == 200


def test_counters_are_reset_after_the_period(login, clock):
    for _ in range(5):
        assert login(password="bad").status_code == 401
    clock.advance(901)
    for _ in range(5):
        assert login(password="bad").status_code == 401  # pas de verrou : compteur remis à zéro


def test_success_resets_the_pair_state(login):
    for _ in range(4):
        login(password="bad")
    assert login().status_code == 200
    for _ in range(4):
        assert login(password="bad").status_code == 401
    assert login().status_code == 200


def test_forged_proxy_headers_do_not_evade_the_lock(login):
    for _ in range(8):
        login(password="bad", ip="203.0.113.70")
    from_forger = login(ip="203.0.113.70")  # seul le début de l'en-tête change à chaque appel de l'assistant
    assert from_forger.status_code == 429


def test_proxy_header_is_ignored_when_no_proxy_is_trusted(make_client, monkeypatch, login):
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "0")  # tous les appels du test partagent l'adresse du pair
    for _ in range(8):
        login(password="bad", ip="203.0.113.1")
    assert login(ip="203.0.113.2").status_code == 429  # l'en-tête est ignoré : même identité


def test_unknown_address_still_works_and_is_limited_per_account(make_client, monkeypatch, login):
    import app.routers.auth as auth_router

    client = make_client()
    for _ in range(8):
        client.post("/auth/login", json={"email": "agent@example.com", "password": "bad"})  # pas d'en-tête : « unknown »
    assert client.post("/auth/login", json={"email": "agent@example.com", "password": PASSWORD}).status_code == 429
    assert client.post("/auth/login", json={"email": "autre@example.com", "password": PASSWORD}).status_code == 200


def test_restart_loses_in_memory_state_documented_limit(login):
    for _ in range(8):
        login(password="bad")
    assert login().status_code == 429
    rate_limit.login_guard.reset()  # équivaut à un redémarrage de dyno
    assert login().status_code == 200


def test_memory_stays_bounded_under_a_flood_of_distinct_accounts(login, monkeypatch):
    monkeypatch.setattr(rate_limit, "_MAX_KEYS", 50)
    for i in range(300):
        login(f"flood{i}@example.com", password="bad", ip=f"203.0.113.{i % 200 + 1}")
    guard = rate_limit.login_guard
    assert len(guard._account_failures) <= 50 and len(guard._pairs) <= 50
    assert login("legit@example.com").status_code == 200


# --- autres routes --------------------------------------------------------------------------------------------------------
def test_register_is_rate_limited_for_the_superadmin_route(make_client, created, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_REGISTER", "3/600")
    client = make_client(current_user=SUPERADMIN)
    codes = [
        client.post("/auth/register", json=payload(email=f"u{i}@example.com", organization_id=OTHER_ORG_ID)).status_code
        for i in range(5)
    ]
    assert codes == [200, 200, 200, 429, 429]


SENSITIVE_ROUTES = {
    "/auth/register", "/auth/register-demo", "/auth/verify-otp", "/auth/resend-otp",
    "/auth/login", "/auth/forgot-password", "/auth/reset-password",
}


def test_every_sensitive_public_route_declares_a_rate_limit():
    from app.routers.auth import router

    limited = {
        route.path
        for route in router.routes
        if any(getattr(dep.dependency, "__qualname__", "").startswith("rate_limit.<locals>") for dep in route.dependencies)
    }
    assert SENSITIVE_ROUTES <= limited, SENSITIVE_ROUTES - limited
