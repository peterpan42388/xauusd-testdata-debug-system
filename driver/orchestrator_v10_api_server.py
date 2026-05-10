#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


PLAN_OBSERVE_ONLY = 0
PLAN_STRUCT_V4 = 1
PLAN_CONSERVATIVE_V5 = 2
PLAN_ADVANCED_V6 = 3
PLAN_FUSION_V7 = 4
PLAN_PYRAMID_TREND_V8_SAFE = 5
PLAN_PROFIT_V91_P1 = 6
PLAN_BALANCED_V91_P2 = 7
PLAN_PROFIT_V91_P3 = 8

REGIME_NEUTRAL = 0
REGIME_AI_CHIP = 1
REGIME_GEO_OIL = 2
REGIME_DEF_USD = 3

CIRCUIT_NORMAL = 0
CIRCUIT_REDUCE = 1
CIRCUIT_FREEZE = 2

BOLLING_NORMAL_EXPAND = 0
BOLLING_NORMAL_CONTRACT = 1
BOLLING_CLIFF_UP = 2
BOLLING_CLIFF_DOWN = 3

LINE_STATUS_SMOOTH = 0
LINE_STATUS_SHAKY = 1

MOMENTUM_STRONG_CONTINUE = 0
MOMENTUM_WEAK_CONTINUE = 1
MOMENTUM_REVERSAL = 2
MOMENTUM_UNCLEAR = 3


PLAN_NAMES = {
    PLAN_OBSERVE_ONLY: "OBSERVE_ONLY",
    PLAN_STRUCT_V4: "v4",
    PLAN_CONSERVATIVE_V5: "v5",
    PLAN_ADVANCED_V6: "v6",
    PLAN_FUSION_V7: "v7",
    PLAN_PYRAMID_TREND_V8_SAFE: "v8_safe",
    PLAN_PROFIT_V91_P1: "v91_P1",
    PLAN_BALANCED_V91_P2: "v91_P2",
    PLAN_PROFIT_V91_P3: "v91_P3",
}


@dataclass(frozen=True)
class SchedulerConfig:
    high_vol_atr_pct: float = 0.0018
    high_vol_trend_power: float = 48.0
    low_signal_atr_pct: float = 0.0014
    low_signal_boll_angle: float = 80.0
    geo_atr_pct: float = 0.0018
    geo_boll_angle: float = 100.0
    ai_trend_power: float = 48.0
    dd_reduce_pct: float = 9.0
    dd_freeze_pct: float = 12.0
    loss_reduce_count: int = 3
    allow_v8_safe: bool = True


def _one(qs: dict[str, list[str]], key: str, default: str = "") -> str:
    values = qs.get(key)
    if not values:
        return default
    return values[0]


def _float(qs: dict[str, list[str]], key: str, default: float = 0.0) -> float:
    try:
        return float(_one(qs, key, str(default)))
    except ValueError:
        return default


def _int(qs: dict[str, list[str]], key: str, default: int = 0) -> int:
    try:
        return int(float(_one(qs, key, str(default))))
    except ValueError:
        return default


def infer_factor_regime(qs: dict[str, list[str]], cfg: SchedulerConfig) -> int:
    given = _int(qs, "factor_regime", -1)
    if given in (REGIME_AI_CHIP, REGIME_GEO_OIL, REGIME_DEF_USD):
        return given

    atr_pct = _float(qs, "atr_pct")
    trend_power = _float(qs, "trend_power")
    boll_angle = abs(_float(qs, "boll_angle"))
    boll_status = _int(qs, "boll_status", BOLLING_NORMAL_CONTRACT)
    line_status = _int(qs, "line_status", LINE_STATUS_SHAKY)
    momentum = _int(qs, "momentum", MOMENTUM_UNCLEAR)

    geo = (
        atr_pct >= cfg.geo_atr_pct
        and boll_angle >= cfg.geo_boll_angle
        and boll_status in (BOLLING_CLIFF_UP, BOLLING_CLIFF_DOWN)
    )
    ai = (
        trend_power >= cfg.ai_trend_power
        and line_status == LINE_STATUS_SMOOTH
        and momentum in (MOMENTUM_STRONG_CONTINUE, MOMENTUM_WEAK_CONTINUE)
        and boll_status != BOLLING_NORMAL_CONTRACT
    )
    defensive = (
        (line_status == LINE_STATUS_SHAKY and momentum in (MOMENTUM_REVERSAL, MOMENTUM_UNCLEAR))
        or (boll_status == BOLLING_NORMAL_CONTRACT and atr_pct < cfg.geo_atr_pct * 0.90)
    )

    if geo:
        return REGIME_GEO_OIL
    if ai:
        return REGIME_AI_CHIP
    if defensive:
        return REGIME_DEF_USD
    return REGIME_NEUTRAL


def route_plan(qs: dict[str, list[str]], cfg: SchedulerConfig) -> dict[str, Any]:
    circuit_state = _int(qs, "circuit_state", CIRCUIT_NORMAL)
    dd_pct = _float(qs, "dd_pct")
    loss_streak = _int(qs, "loss_streak")

    if circuit_state == CIRCUIT_FREEZE or dd_pct >= cfg.dd_freeze_pct:
        return decision(PLAN_OBSERVE_ONLY, "circuit_freeze")
    if circuit_state == CIRCUIT_REDUCE or dd_pct >= cfg.dd_reduce_pct or loss_streak >= cfg.loss_reduce_count:
        return decision(PLAN_CONSERVATIVE_V5, "circuit_reduce")

    atr_pct = _float(qs, "atr_pct")
    trend_power = _float(qs, "trend_power")
    boll_angle = abs(_float(qs, "boll_angle"))
    boll_status = _int(qs, "boll_status", BOLLING_NORMAL_CONTRACT)
    line_status = _int(qs, "line_status", LINE_STATUS_SHAKY)
    momentum = _int(qs, "momentum", MOMENTUM_UNCLEAR)
    regime = infer_factor_regime(qs, cfg)

    low_signal_chop = (
        atr_pct <= cfg.low_signal_atr_pct
        and boll_angle <= cfg.low_signal_boll_angle
        and (boll_status == BOLLING_NORMAL_CONTRACT or line_status == LINE_STATUS_SHAKY)
    )
    if low_signal_chop:
        return decision(PLAN_STRUCT_V4, "low_signal_chop", regime)

    high_vol_trend = (
        cfg.allow_v8_safe
        and atr_pct >= cfg.high_vol_atr_pct
        and trend_power >= cfg.high_vol_trend_power
        and line_status == LINE_STATUS_SMOOTH
        and momentum in (MOMENTUM_STRONG_CONTINUE, MOMENTUM_WEAK_CONTINUE)
    )
    if high_vol_trend:
        return decision(PLAN_PYRAMID_TREND_V8_SAFE, "high_vol_trend", regime)

    if regime == REGIME_AI_CHIP:
        return decision(PLAN_FUSION_V7, "ai_chip_regime", regime)
    if regime == REGIME_GEO_OIL:
        return decision(PLAN_BALANCED_V91_P2, "geo_oil_regime", regime)
    if regime == REGIME_DEF_USD:
        return decision(PLAN_PROFIT_V91_P1, "def_usd_regime", regime)

    return decision(PLAN_CONSERVATIVE_V5, "neutral_fallback", regime)


def decision(plan: int, reason: str, regime: int = REGIME_NEUTRAL) -> dict[str, Any]:
    return {
        "plan": plan,
        "plan_name": PLAN_NAMES.get(plan, "UNKNOWN"),
        "reason": reason,
        "regime": regime,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


class SchedulerHandler(BaseHTTPRequestHandler):
    cfg = SchedulerConfig()
    access_log: Path | None = None

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send({"ok": True, "service": "orchestrator_v10_api"})
            return
        if parsed.path != "/route":
            self._send({"ok": False, "error": "not_found"}, status=404)
            return

        qs = parse_qs(parsed.query)
        payload = route_plan(qs, self.cfg)
        payload["ok"] = True
        payload["symbol"] = _one(qs, "symbol")
        payload["period"] = _int(qs, "period")
        self._append_log(qs, payload)
        self._send(payload)

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _send(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _append_log(self, qs: dict[str, list[str]], payload: dict[str, Any]) -> None:
        if self.access_log is None:
            return
        row = {
            "time": datetime.now(timezone.utc).isoformat(),
            "symbol": _one(qs, "symbol"),
            "period": _one(qs, "period"),
            "bar_time": _one(qs, "bar_time"),
            "atr_pct": _one(qs, "atr_pct"),
            "trend_power": _one(qs, "trend_power"),
            "boll_angle": _one(qs, "boll_angle"),
            "boll_status": _one(qs, "boll_status"),
            "line_status": _one(qs, "line_status"),
            "momentum": _one(qs, "momentum"),
            "factor_regime": _one(qs, "factor_regime"),
            "dd_pct": _one(qs, "dd_pct"),
            "loss_streak": _one(qs, "loss_streak"),
            "plan": payload["plan"],
            "plan_name": payload["plan_name"],
            "reason": payload["reason"],
        }
        with self.access_log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local scheduler API for XAUUSD_Survival_Orchestrator_v10.mq5")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--log", default="scheduler_access.jsonl")
    parser.add_argument("--disable-v8", action="store_true")
    parser.add_argument("--high-vol-atr-pct", type=float, default=0.0018)
    parser.add_argument("--high-vol-trend-power", type=float, default=48.0)
    parser.add_argument("--low-signal-atr-pct", type=float, default=0.0014)
    parser.add_argument("--low-signal-boll-angle", type=float, default=80.0)
    parser.add_argument("--geo-atr-pct", type=float, default=0.0018)
    parser.add_argument("--geo-boll-angle", type=float, default=100.0)
    parser.add_argument("--ai-trend-power", type=float, default=48.0)
    parser.add_argument("--dd-reduce-pct", type=float, default=9.0)
    parser.add_argument("--dd-freeze-pct", type=float, default=12.0)
    parser.add_argument("--loss-reduce-count", type=int, default=3)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = SchedulerConfig(
        high_vol_atr_pct=args.high_vol_atr_pct,
        high_vol_trend_power=args.high_vol_trend_power,
        low_signal_atr_pct=args.low_signal_atr_pct,
        low_signal_boll_angle=args.low_signal_boll_angle,
        geo_atr_pct=args.geo_atr_pct,
        geo_boll_angle=args.geo_boll_angle,
        ai_trend_power=args.ai_trend_power,
        dd_reduce_pct=args.dd_reduce_pct,
        dd_freeze_pct=args.dd_freeze_pct,
        loss_reduce_count=args.loss_reduce_count,
        allow_v8_safe=not args.disable_v8,
    )
    SchedulerHandler.cfg = cfg
    SchedulerHandler.access_log = Path(args.log).resolve() if args.log else None
    server = ThreadingHTTPServer((args.host, args.port), SchedulerHandler)
    print(f"orchestrator_v10_api listening on http://{args.host}:{args.port}")
    print(f"access log: {SchedulerHandler.access_log}")
    print(f"MT5 WebRequest allow-list URL: http://127.0.0.1:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
