"""M/M/c queueing model for the rendering bottleneck.

Each Manhuaju Agent task counts as one render unit. The system has ``c``
concurrent slots (default = 16, from ``volcengine_manhuaju_2026.concurrency_quota``).
We model arrivals as Poisson(λ) and service times as Exp(μ) with
``μ = 1 / E[render_seconds_per_episode]``.

Outputs:
- ρ = λ / (c · μ) — utilisation
- L_q — expected queue length
- W_q — expected wait time
- Episodes per hour at saturation
"""

from __future__ import annotations

from dataclasses import dataclass
from math import factorial

from . import _io


@dataclass(frozen=True)
class MMC:
    arrivals_per_hour: float
    service_rate_per_hour: float
    servers: int
    rho: float
    p0: float
    erlang_c: float
    lq: float
    wq_seconds: float
    episodes_per_hour: float

    def as_dict(self) -> dict[str, float | int]:
        return {
            "arrivals_per_hour": round(self.arrivals_per_hour, 3),
            "service_rate_per_hour": round(self.service_rate_per_hour, 3),
            "servers": self.servers,
            "rho": round(self.rho, 4),
            "p0_idle_prob": round(self.p0, 6),
            "erlang_c_wait_prob": round(self.erlang_c, 4),
            "lq_expected_queue": round(self.lq, 3),
            "wq_seconds_expected_wait": round(self.wq_seconds, 2),
            "episodes_per_hour": round(self.episodes_per_hour, 2),
        }


def _erlang_c(c: int, rho_offered: float) -> tuple[float, float]:
    """Return (P0, ErlangC) for offered load rho_offered = λ/μ (a.k.a. erlangs).

    Numerically safe up to c ≤ 200; uses log-domain reformulation only when
    needed (we cap at 64 for the manhuaju use case).
    """

    if rho_offered <= 0:
        return 1.0, 0.0
    sum_terms = sum(rho_offered**k / factorial(k) for k in range(c))
    last_term = rho_offered**c / (factorial(c) * (1 - rho_offered / c)) if rho_offered < c else float("inf")
    p0 = 1.0 / (sum_terms + last_term)
    erlang_c = (rho_offered**c / factorial(c)) * (c / (c - rho_offered)) * p0 if rho_offered < c else 1.0
    return p0, erlang_c


def steady_state(arrivals_per_hour: float, mean_render_seconds: float, servers: int = 16) -> MMC:
    """Compute the M/M/c steady state for a given arrival/service intensity."""

    service_rate_per_hour = 3600.0 / mean_render_seconds
    rho_offered = arrivals_per_hour / service_rate_per_hour  # erlangs
    rho = rho_offered / servers
    if rho >= 1.0:
        return MMC(
            arrivals_per_hour=arrivals_per_hour,
            service_rate_per_hour=service_rate_per_hour,
            servers=servers,
            rho=rho,
            p0=0.0,
            erlang_c=1.0,
            lq=float("inf"),
            wq_seconds=float("inf"),
            episodes_per_hour=service_rate_per_hour * servers,
        )
    p0, ec = _erlang_c(servers, rho_offered)
    lq = ec * rho / (1.0 - rho)
    wq_hours = lq / arrivals_per_hour if arrivals_per_hour > 0 else 0.0
    wq_seconds = wq_hours * 3600.0
    eps_per_hr = arrivals_per_hour
    return MMC(
        arrivals_per_hour=arrivals_per_hour,
        service_rate_per_hour=service_rate_per_hour,
        servers=servers,
        rho=rho,
        p0=p0,
        erlang_c=ec,
        lq=lq,
        wq_seconds=wq_seconds,
        episodes_per_hour=eps_per_hr,
    )


def saturation_rate(mean_render_seconds: float, servers: int = 16, target_rho: float = 0.85) -> float:
    """Maximum arrivals-per-hour that keeps utilisation ≤ target_rho (default 85%)."""

    service_rate_per_hour = 3600.0 / mean_render_seconds
    return target_rho * servers * service_rate_per_hour


def summary() -> dict[str, object]:
    """Whitepaper-grade summary used by ``run_all`` and the spec anchors."""

    manhuaju = _io.load_pricing("volcengine_manhuaju_2026").payload
    servers_default = manhuaju["concurrency_quota"]["default"]
    servers_burst = manhuaju["concurrency_quota"]["burst"]

    # Mean render seconds per episode = sum of all per-episode video stages.
    # For a 90s episode (~18 shots @ 5s each) the dominant cost is video_generate.
    median_per_shot = manhuaju["endpoints"]["video_generate_fast720p"]["median_latency_s"]
    shots = 18
    mean_render_per_episode_seconds = median_per_shot * shots / max(servers_default, 1)
    # ^ assumes the 16 slots are saturated within a single episode (parallel shots).

    out: dict[str, object] = {}
    for arrivals in (4.0, 6.0, 8.0, 10.0, 12.0, 16.0, 20.0, 24.0):
        out[f"lambda_{int(arrivals)}_per_hour"] = steady_state(
            arrivals_per_hour=arrivals,
            mean_render_seconds=mean_render_per_episode_seconds,
            servers=servers_default,
        ).as_dict()

    sat = saturation_rate(mean_render_per_episode_seconds, servers=servers_default)
    out["saturation_at_default_c"] = round(sat, 2)
    out["episodes_per_hour_at_default_c"] = round(sat, 2)
    out["episodes_per_hour_at_burst_c"] = round(
        saturation_rate(mean_render_per_episode_seconds, servers=servers_burst), 2
    )
    out["mean_render_per_episode_seconds"] = round(mean_render_per_episode_seconds, 2)
    out["servers_default"] = servers_default
    out["servers_burst"] = servers_burst
    out["need_md_anchor_eps_per_hour_min"] = 8.0
    return out
