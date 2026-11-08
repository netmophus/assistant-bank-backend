"""Limitation de débit EN MÉMOIRE pour les routes d'authentification publiques.

LIMITE DE CONCEPTION (à lire) : tous les compteurs vivent dans la mémoire du processus.
* Ils sont perdus à chaque redémarrage de dyno (déploiement, cycle quotidien Heroku, crash) : un attaquant retrouve alors
  un quota neuf. Les verrouillages en cours sont levés.
* Ils ne sont pas partagés : avec N processus ou dynos, chaque processus a ses propres compteurs et la limite effective
  d'une IP (ou d'un compte) est multipliée par N (le routeur Heroku répartit au hasard). Le Procfile lance un seul
  processus uvicorn par dyno : N = nombre de dynos web.
* Ce n'est donc PAS une solution distribuée ; un stockage partagé (Redis, par exemple) reste à prévoir.

Conception de la connexion (``LoginGuard``) :
* seuls les ÉCHECS comptent ; une connexion réussie ne consomme aucun quota (et remet à zéro l'état du couple compte+IP) ;
* un seuil par adresse IP souple (agences : plusieurs collaborateurs derrière la même IP) ;
* un compteur par COUPLE (compte, IP) avec ralentissement progressif : après ``LOGIN_FREE_FAILURES`` échecs, verrou
  temporaire de ``LOGIN_LOCK_BASE_SECONDS`` secondes, doublé à chaque échec, plafonné à ``LOGIN_LOCK_MAX_SECONDS`` ;
  comme la clé contient l'IP, un tiers ne peut pas verrouiller l'utilisateur légitime depuis une autre adresse ;
* attaque répartie sur beaucoup d'IP contre un seul compte : au-delà de ``LOGIN_ACCOUNT_FAIL_LIMIT`` échecs en
  ``LOGIN_ACCOUNT_FAIL_WINDOW`` secondes, seules les IP jamais vues en succès pour ce compte sont refusées (429) ; les IP
  déjà connues (connexion réussie dans les ``LOGIN_KNOWN_IP_TTL`` secondes) continuent de passer.
* toutes les réponses de limitation sont des 429 identiques (même message, ``Retry-After`` en secondes), sans indiquer
  quelle règle a joué.

Variables d'environnement (valeurs par défaut sûres) :
  RATE_LIMIT_ENABLED        "0" désactive toute limitation (diagnostic d'urgence). Défaut : activée.
  TRUSTED_PROXY_HOPS        Nombre de proxys de confiance devant l'application. Défaut : 1 si DYNO est défini (Heroku),
                            sinon 0. À 0, X-Forwarded-For est ignoré. À n > 0, l'adresse retenue est le n-ième élément
                            en partant de la fin (ajouté par NOTRE proxy) ; les éléments précédents sont falsifiables.
                            Mettre 2 si un CDN (ex. Cloudflare) est placé devant le routeur Heroku.
  RATE_LIMIT_<NOM>          Surcharge "limite/fenêtre_en_secondes" d'une limite nommée (ex. RATE_LIMIT_REGISTER=10/600).
                            Noms : LOGIN_IP, REGISTER, REGISTER_DEMO, VERIFY_OTP_IP, VERIFY_OTP_EMAIL, RESEND_OTP_IP,
                            RESEND_OTP_EMAIL, FORGOT_PASSWORD_IP, FORGOT_PASSWORD_EMAIL, RESET_PASSWORD_IP.
  LOGIN_IP_FAIL_LIMIT=100  LOGIN_IP_FAIL_WINDOW=900          échecs tolérés par IP.
  LOGIN_FREE_FAILURES=5    LOGIN_FAIL_RESET=900              échecs gratuits par (compte, IP) ; remise à zéro après ce délai.
  LOGIN_LOCK_BASE_SECONDS=30  LOGIN_LOCK_MAX_SECONDS=900     ralentissement progressif.
  LOGIN_ACCOUNT_FAIL_LIMIT=30 LOGIN_ACCOUNT_FAIL_WINDOW=900  seuil d'attaque répartie sur un compte.
  LOGIN_KNOWN_IP_TTL=604800                                  durée de mémorisation d'une IP « connue ».
"""

from __future__ import annotations

import ipaddress
import math
import os
import time
from collections import OrderedDict, defaultdict, deque
from typing import Callable, Deque, Dict, Optional, Tuple

from fastapi import HTTPException, Request, status

_MAX_KEYS = 20_000
_MAX_KNOWN_IPS_PER_ACCOUNT = 20
_TOO_MANY = "Trop de tentatives. Réessayez plus tard."


def too_many_requests(retry_after: int) -> HTTPException:
    """Réponse 429 unique pour toutes les limitations."""
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=_TOO_MANY,
        headers={"Retry-After": str(max(1, int(retry_after)))},
    )


def _env_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, ""))
        return value if value > 0 else default
    except ValueError:
        return default


def _enabled() -> bool:
    return os.getenv("RATE_LIMIT_ENABLED", "1") != "0"


# --- fenêtre glissante -------------------------------------------------------------------------------------------------
class SlidingWindowLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)

    def hit(self, key: str, limit: int, window_seconds: int) -> Tuple[bool, int]:
        """Enregistre un appel. Retourne (autorisé, secondes avant nouvel essai)."""
        now = self._clock()
        if len(self._hits) > _MAX_KEYS:
            self._purge(now)
        events = self._hits[key]
        while events and now - events[0] >= window_seconds:
            events.popleft()
        if len(events) >= limit:
            return False, max(1, math.ceil(window_seconds - (now - events[0])))
        events.append(now)
        return True, 0

    def reset(self) -> None:
        self._hits.clear()

    def _purge(self, now: float) -> None:
        for key in [k for k, ev in self._hits.items() if not ev or now - ev[-1] > 3600]:
            del self._hits[key]


limiter = SlidingWindowLimiter()


def _resolve(name: str, limit: int, window: int) -> Tuple[int, int]:
    """Applique la surcharge RATE_LIMIT_<NOM>="limite/fenêtre" si elle est valide."""
    raw = os.getenv(f"RATE_LIMIT_{name.upper()}", "")
    try:
        a, b = raw.split("/")
        if int(a) > 0 and int(b) > 0:
            return int(a), int(b)
    except ValueError:
        pass
    return limit, window


def enforce(name: str, identity: str, limit: int, window_seconds: int) -> None:
    """Lève 429 si la limite nommée est dépassée pour cette identité."""
    if not _enabled():
        return
    limit, window_seconds = _resolve(name, limit, window_seconds)
    allowed, retry_after = limiter.hit(f"{name}:{identity}", limit, window_seconds)
    if not allowed:
        raise too_many_requests(retry_after)


def rate_limit(name: str, limit: int, window_seconds: int) -> Callable[[Request], None]:
    """Dépendance FastAPI : limite par adresse IP, sans modifier la signature ni le contrat de la route."""

    def dependency(request: Request) -> None:
        enforce(name, client_ip(request), limit, window_seconds)

    return dependency


def email_key(email: Optional[str]) -> str:
    return (email or "").strip().lower()[:254]


# --- adresse IP du client ------------------------------------------------------------------------------------------------
UNKNOWN_IP = "unknown"


def trusted_proxy_hops() -> int:
    raw = os.getenv("TRUSTED_PROXY_HOPS")
    if raw is not None:
        try:
            return max(0, int(raw))
        except ValueError:
            return 0  # valeur illisible : ne rien croire
    return 1 if os.getenv("DYNO") else 0


def _normalize_ip(value: str) -> Optional[str]:
    try:
        ip = ipaddress.ip_address(value.strip())
    except ValueError:
        return None
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped:
            return str(ip.ipv4_mapped)
        return str(ipaddress.ip_network(f"{ip}/64", strict=False).network_address)  # un client IPv6 contrôle tout son /64
    return str(ip)


def client_ip(request: Request) -> str:
    """Adresse du client, ou « unknown » si elle n'est pas déterminable de façon fiable.

    Sans proxy de confiance configuré, seule l'adresse du pair TCP est utilisée et X-Forwarded-For est ignoré.
    """
    hops = trusted_proxy_hops()
    if hops > 0:
        parts = [p for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
        if len(parts) >= hops:
            return _normalize_ip(parts[-hops]) or UNKNOWN_IP
        return UNKNOWN_IP  # en-tête absent ou trop court : le proxy n'a pas fait son travail, on ne devine pas
    peer = request.client.host if request.client else ""
    return _normalize_ip(peer) or UNKNOWN_IP


# --- connexion : échecs par IP et par compte -----------------------------------------------------------------------------
class _PairState:
    __slots__ = ("failures", "last_failure", "locked_until")

    def __init__(self) -> None:
        self.failures = 0
        self.last_failure = 0.0
        self.locked_until = 0.0


class LoginGuard:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._ip_failures: Dict[str, Deque[float]] = defaultdict(deque)
        self._account_failures: Dict[str, Deque[float]] = defaultdict(deque)
        self._pairs: Dict[Tuple[str, str], _PairState] = {}
        self._known: Dict[str, "OrderedDict[str, float]"] = {}

    def reset(self) -> None:
        self._ip_failures.clear()
        self._account_failures.clear()
        self._pairs.clear()
        self._known.clear()

    # configuration lue à chaque appel (modifiable par variable d'environnement sans redémarrage des tests)
    @staticmethod
    def _cfg() -> Dict[str, int]:
        return {
            "ip_limit": _env_int("LOGIN_IP_FAIL_LIMIT", 100),
            "ip_window": _env_int("LOGIN_IP_FAIL_WINDOW", 900),
            "free": _env_int("LOGIN_FREE_FAILURES", 5),
            "reset": _env_int("LOGIN_FAIL_RESET", 900),
            "base": _env_int("LOGIN_LOCK_BASE_SECONDS", 30),
            "max": _env_int("LOGIN_LOCK_MAX_SECONDS", 900),
            "acct_limit": _env_int("LOGIN_ACCOUNT_FAIL_LIMIT", 30),
            "acct_window": _env_int("LOGIN_ACCOUNT_FAIL_WINDOW", 900),
            "known_ttl": _env_int("LOGIN_KNOWN_IP_TTL", 604800),
        }

    @staticmethod
    def _trim(events: Deque[float], now: float, window: int) -> None:
        while events and now - events[0] >= window:
            events.popleft()

    def check(self, ip: str, account: str) -> None:
        """À appeler AVANT de vérifier le mot de passe. Lève 429 si la tentative doit être refusée."""
        if not _enabled():
            return
        c, now = self._cfg(), self._clock()
        self._maybe_purge(now, c)

        ip_events = self._ip_failures.get(ip)
        if ip_events is not None:
            self._trim(ip_events, now, c["ip_window"])
            if len(ip_events) >= c["ip_limit"]:
                raise too_many_requests(c["ip_window"] - (now - ip_events[0]))

        pair = self._pairs.get((account, ip))
        if pair is not None and now < pair.locked_until:
            raise too_many_requests(math.ceil(pair.locked_until - now))

        acct_events = self._account_failures.get(account)
        if acct_events is not None:
            self._trim(acct_events, now, c["acct_window"])
            if len(acct_events) >= c["acct_limit"] and not self._is_known(account, ip, now, c):
                raise too_many_requests(c["acct_window"] - (now - acct_events[0]))

    def record_failure(self, ip: str, account: str) -> None:
        if not _enabled():
            return
        c, now = self._cfg(), self._clock()
        self._ip_failures[ip].append(now)
        if len(self._account_failures) < _MAX_KEYS or account in self._account_failures:
            self._account_failures[account].append(now)
        pair = self._pairs.get((account, ip))
        if pair is None:
            if len(self._pairs) >= _MAX_KEYS:
                return
            pair = self._pairs[(account, ip)] = _PairState()
        if pair.failures and now - pair.last_failure > c["reset"]:
            pair.failures = 0
        pair.failures += 1
        pair.last_failure = now
        if pair.failures > c["free"]:
            excess = pair.failures - c["free"] - 1
            pair.locked_until = now + min(c["base"] * (2 ** min(excess, 20)), c["max"])

    def record_success(self, ip: str, account: str) -> None:
        """Mot de passe correct : aucun quota consommé, état du couple remis à zéro, IP mémorisée comme connue."""
        if not _enabled():
            return
        c, now = self._cfg(), self._clock()
        self._pairs.pop((account, ip), None)
        if account not in self._known and len(self._known) >= _MAX_KEYS:
            return
        ips = self._known.setdefault(account, OrderedDict())
        ips[ip] = now
        ips.move_to_end(ip)
        while len(ips) > _MAX_KNOWN_IPS_PER_ACCOUNT:
            ips.popitem(last=False)

    def _is_known(self, account: str, ip: str, now: float, c: Dict[str, int]) -> bool:
        seen = self._known.get(account, {}).get(ip)
        return seen is not None and now - seen < c["known_ttl"]

    def _maybe_purge(self, now: float, c: Dict[str, int]) -> None:
        total = len(self._ip_failures) + len(self._account_failures) + len(self._pairs)
        if total <= _MAX_KEYS:
            return
        for store, window in ((self._ip_failures, c["ip_window"]), (self._account_failures, c["acct_window"])):
            for key in [k for k, ev in store.items() if not ev or now - ev[-1] >= window]:
                del store[key]
        for key in [k for k, p in self._pairs.items() if now >= p.locked_until and now - p.last_failure > c["reset"]]:
            del self._pairs[key]


login_guard = LoginGuard()
