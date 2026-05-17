from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FILE = WORKSPACE_ROOT / "TestData_publish_repo" / "Day" / "Day_367_2026-05-07.csv"


@dataclass
class Corner:
    valid: bool
    direct: int  # 1=solo_up, 0=solo_down
    time: pd.Timestamp
    right_index: int
    top: float
    shadow: float


@dataclass
class Position:
    side: int  # 1=long, -1=short
    entry_time: pd.Timestamp
    entry_price: float
    sl_price: float
    tp_top: float
    tp_shadow: float
    reason: str
    tp_armed: bool = False
    exit_on_next_intersection: bool = False


@dataclass
class GroupInterval:
    level: int
    num: int
    updown: int
    status: int


@dataclass
class KlineGroup:
    level: int
    intervals: list[GroupInterval]
    last_status: int


@dataclass
class IntersectionSignal:
    bar_index: int
    bar_time: pd.Timestamp
    is_cross: bool
    direction: int
    jump: float
    ratio: float
    mid_ang: float
    prev3_ang: float
    right_ang: float
    hit_a: int
    hit_b: int
    score: float
    label: str


# A: 总体准确率优先（偏保守）
INTERSECTION_A = {
    "jump": 0.3255687278146456,
    "ratio": 0.9465324936293601,
    "mid": 0.24172376871004736,
    "prev3": 19.112973733671282,
    "right": 1.7242402553514056,
}

# B: 有效交叉识别优先（偏积极）
INTERSECTION_B = {
    "jump": 0.17649558336450857,
    "ratio": 0.9465324936293601,
    "mid": -2.4906003864080986,
    "prev3": 11.203353539286086,
    "right": 1.7242402553514056,
}


def load_ohlc(path: Path) -> pd.DataFrame:
    raw = None
    for enc in ("utf-16", "utf-8-sig", "utf-8"):
        try:
            raw = pd.read_csv(path, header=None, encoding=enc)
            break
        except Exception:
            raw = None
    if raw is None:
        raise RuntimeError(f"cannot read csv: {path}")

    if raw.shape[1] == 1:
        raw = raw.iloc[:, 0].astype(str).str.split(",", expand=True)

    rows = []
    for row in raw.itertuples(index=False):
        vals = [str(x).strip() for x in row]
        if len(vals) < 6:
            continue
        try:
            try:
                t = pd.to_datetime(vals[0], format="%Y.%m.%d %H:%M")
            except Exception:
                t = pd.to_datetime(vals[0])
            o = float(vals[1])
            h = float(vals[2])
            l = float(vals[3])
            c = float(vals[4])
            v = float(vals[5])
            rows.append((t, o, h, l, c, v))
        except Exception:
            continue

    df = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"])
    df.sort_values("time", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def _classify_k_site(high_p: float, low_p: float, close_p: float, b_up: float, b_mid: float, b_low: float) -> str:
    if pd.isna(b_up) or pd.isna(b_mid) or pd.isna(b_low):
        return "mid"
    if high_p > b_up:
        return "up_over"
    if low_p < b_low:
        return "down_over"
    if low_p <= b_mid <= high_p:
        return "mid"
    if close_p >= b_mid:
        return "up"
    return "down"


def _segment_status(seg: pd.DataFrame) -> tuple[int, int]:
    if seg.empty:
        return 0, 3
    start_c = float(seg.iloc[0]["close"])
    end_c = float(seg.iloc[-1]["close"])
    updown = 1 if end_c > start_c else (-1 if end_c < start_c else 0)
    amp = float(seg["high"].max() - seg["low"].min())
    drift = abs(end_c - start_c)
    if drift == 0:
        status = 4 if amp > 0 else 3
    else:
        status = 4 if (amp / drift) >= 3.0 else (1 if updown > 0 else (2 if updown < 0 else 3))
    return updown, status


def build_kline_group(df: pd.DataFrame, end_idx: int, level: int) -> Optional[KlineGroup]:
    bars = {1: 9, 2: 27, 3: 81, 4: 288}.get(level)
    if bars is None:
        return None
    start = end_idx - bars + 1
    if start < 0:
        return None
    window = df.iloc[start : end_idx + 1]
    seg = bars // 3
    intervals: list[GroupInterval] = []
    for num in range(3):
        s0 = num * seg
        s1 = s0 + seg
        part = window.iloc[s0:s1]
        updown, status = _segment_status(part)
        intervals.append(GroupInterval(level=level, num=num, updown=updown, status=status))
    return KlineGroup(level=level, intervals=intervals, last_status=intervals[0].status)


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["ma5"] = out["close"].rolling(5).mean()
    out["ma20"] = out["close"].rolling(20).mean()
    out["ema5"] = out["close"].ewm(span=5, adjust=False).mean()
    out["ema20"] = out["close"].ewm(span=20, adjust=False).mean()
    out["ema_diff"] = out["ema5"] - out["ema20"]
    out["mid"] = out["close"].rolling(20).mean()
    std20 = out["close"].rolling(20).std(ddof=0)
    out["up"] = out["mid"] + 2.0 * std20
    out["down"] = out["mid"] - 2.0 * std20
    out["bb_mid"] = out["mid"]
    out["bb_up"] = out["up"]
    out["bb_down"] = out["down"]
    out["b_up"] = out["up"]
    out["b_mid"] = out["mid"]
    out["b_low"] = out["down"]

    prev_close = out["close"].shift(1)
    tr = pd.concat(
        [
            (out["high"] - out["low"]).abs(),
            (out["high"] - prev_close).abs(),
            (out["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    out["atr14"] = tr.rolling(14).mean()

    out["updown"] = (out["close"] > out["open"]).astype(int) - (out["close"] < out["open"]).astype(int)
    out["k_height_a"] = out["high"] - out["low"]
    out["k_height_b"] = (out["close"] - out["open"]).abs()
    out["k_weight"] = out["k_height_b"] / out["k_height_a"].replace(0.0, pd.NA)
    out["k_weight"] = out["k_weight"].fillna(0.0)

    prev8_min = out["k_height_b"].rolling(8, min_periods=1).min().shift(1)
    out["k_multiple"] = out["k_height_b"] / prev8_min.replace(0.0, pd.NA)
    out["k_multiple"] = out["k_multiple"].fillna(1.0)

    # comments_0003 对齐：intersection 使用 EMA5/EMA20 反转定义
    out["intersection"] = ((out["ema_diff"] * out["ema_diff"].shift(1)) < 0).astype(int)
    out["intersection"] = out["intersection"].fillna(0).astype(int)

    atr_safe = out["atr14"].replace(0.0, pd.NA)
    out["angle_mid3"] = (((out["b_mid"] - out["b_mid"].shift(2)) / 2.0) / atr_safe).apply(
        lambda x: pd.NA if pd.isna(x) else math.degrees(math.atan(float(x)))
    )
    out["angle_up3"] = (((out["b_up"] - out["b_up"].shift(2)) / 2.0) / atr_safe).apply(
        lambda x: pd.NA if pd.isna(x) else math.degrees(math.atan(float(x)))
    )
    out["angle_down3"] = (((out["b_low"] - out["b_low"].shift(2)) / 2.0) / atr_safe).apply(
        lambda x: pd.NA if pd.isna(x) else math.degrees(math.atan(float(x)))
    )
    out["angle_right3"] = (out["angle_up3"] - out["angle_down3"]).abs()
    out["angle_close3"] = (((out["close"] - out["close"].shift(3)) / 3.0) / atr_safe).apply(
        lambda x: pd.NA if pd.isna(x) else math.degrees(math.atan(float(x)))
    )

    out["k_site"] = [
        _classify_k_site(h, l, c, u, m, d)
        for h, l, c, u, m, d in zip(
            out["high"], out["low"], out["close"], out["b_up"], out["b_mid"], out["b_low"], strict=False
        )
    ]
    return out


def parse_data(path: Path) -> pd.DataFrame:
    return load_ohlc(Path(path))


def indicators(df: pd.DataFrame) -> pd.DataFrame:
    return add_indicators(df)


def detect_corner(df: pd.DataFrame, i: int, tol: float) -> Optional[Corner]:
    # Sequence: left=i-2, right=i-1, m=i
    left = i - 2
    right = i - 1
    if left < 0:
        return None

    open_l = float(df.at[left, "open"])
    close_l = float(df.at[left, "close"])
    high_l = float(df.at[left, "high"])
    low_l = float(df.at[left, "low"])

    open_r = float(df.at[right, "open"])
    close_r = float(df.at[right, "close"])
    high_r = float(df.at[right, "high"])
    low_r = float(df.at[right, "low"])

    if abs(close_l - open_r) > tol:
        return None

    left_bull = close_l > open_l
    left_bear = close_l < open_l
    right_bull = close_r > open_r
    right_bear = close_r < open_r

    top = close_l
    ctime = pd.Timestamp(df.at[right, "time"])

    if left_bull and right_bear:
        return Corner(True, 1, ctime, right, top, max(high_l, high_r))
    if left_bear and right_bull:
        return Corner(True, 0, ctime, right, top, min(low_l, low_r))
    return None


def candle_direction(o: float, c: float) -> int:
    if c > o:
        return 1
    if c < o:
        return -1
    return 0


def in_tp_zone(side: int, close_price: float, tp_top: float, tp_shadow: float) -> bool:
    zone_low = min(tp_top, tp_shadow)
    zone_high = max(tp_top, tp_shadow)
    if side > 0:
        return close_price >= zone_low
    return close_price <= zone_high


def warmup_ok(day_counter: int, warmup_bars: int) -> bool:
    return day_counter >= warmup_bars


def next_day_counter(prev_time: Optional[pd.Timestamp], cur_time: pd.Timestamp, prev_counter: int) -> int:
    if prev_time is None or prev_time.date() != cur_time.date():
        prev_counter = 0

    if cur_time.hour == 1 and cur_time.minute == 0:
        return 1
    if prev_counter > 0:
        return prev_counter + 1
    return 0


def day_anchor_time(cur_time: pd.Timestamp, hour: int = 3, minute: int = 0) -> pd.Timestamp:
    return pd.Timestamp(cur_time.year, cur_time.month, cur_time.day, hour, minute, 0)


def _intersection_hit(sig: IntersectionSignal, threshold: dict[str, float]) -> int:
    cond = (
        sig.jump >= float(threshold["jump"])
        and sig.ratio <= float(threshold["ratio"])
        and sig.mid_ang >= float(threshold["mid"])
        and sig.prev3_ang >= float(threshold["prev3"])
        and sig.right_ang >= float(threshold["right"])
    )
    return 1 if cond else 0


def build_intersection_signal(
    df: pd.DataFrame,
    i: int,
    weight_a: float,
    weight_b: float,
) -> IntersectionSignal:
    is_cross = bool(int(df.at[i, "intersection"]) == 1)
    ema_diff = float(df.at[i, "ema_diff"]) if "ema_diff" in df.columns else 0.0
    direction = 1 if ema_diff > 0 else (-1 if ema_diff < 0 else 0)

    atr = float(df.at[i, "atr14"]) if "atr14" in df.columns and pd.notna(df.at[i, "atr14"]) else float("nan")
    if i <= 0 or (not pd.notna(atr)) or atr <= 0:
        jump = 0.0
    else:
        prev_diff = float(df.at[i - 1, "ema_diff"])
        jump = abs(ema_diff - prev_diff) / atr

    b_up = float(df.at[i, "b_up"]) if pd.notna(df.at[i, "b_up"]) else 0.0
    b_low = float(df.at[i, "b_low"]) if pd.notna(df.at[i, "b_low"]) else 0.0
    ema5 = float(df.at[i, "ema5"]) if pd.notna(df.at[i, "ema5"]) else 0.0
    ema20 = float(df.at[i, "ema20"]) if pd.notna(df.at[i, "ema20"]) else 0.0
    if direction > 0:
        denom = max(1e-9, b_up - ema20)
        ratio = (b_up - ema5) / denom
    elif direction < 0:
        denom = max(1e-9, ema20 - b_low)
        ratio = (ema5 - b_low) / denom
    else:
        ratio = 1.0

    angle_mid3 = float(df.at[i, "angle_mid3"]) if "angle_mid3" in df.columns and pd.notna(df.at[i, "angle_mid3"]) else 0.0
    angle_close3 = float(df.at[i, "angle_close3"]) if "angle_close3" in df.columns and pd.notna(df.at[i, "angle_close3"]) else 0.0
    angle_right3 = float(df.at[i, "angle_right3"]) if "angle_right3" in df.columns and pd.notna(df.at[i, "angle_right3"]) else 0.0

    signed_mid = direction * angle_mid3
    signed_prev3 = direction * angle_close3

    sig = IntersectionSignal(
        bar_index=i,
        bar_time=pd.Timestamp(df.at[i, "time"]),
        is_cross=is_cross,
        direction=direction,
        jump=float(jump),
        ratio=float(ratio),
        mid_ang=float(signed_mid),
        prev3_ang=float(signed_prev3),
        right_ang=float(angle_right3),
        hit_a=0,
        hit_b=0,
        score=0.0,
        label="micro",
    )

    if is_cross:
        sig.hit_a = _intersection_hit(sig, INTERSECTION_A)
        sig.hit_b = _intersection_hit(sig, INTERSECTION_B)
        total_w = max(1e-9, weight_a + weight_b)
        sig.score = (weight_a * sig.hit_a + weight_b * sig.hit_b) / total_w
        sig.label = "major" if sig.score >= 0.5 else "micro"
    return sig


def run_backtest(
    df: pd.DataFrame,
    tol_price: float = 0.10,
    warmup_bars: int = 24,
    initial_balance: float = 1000.0,
    min_top_gap: float = 1.0,
    max_opposite_gap_bars: int = 12,
    entry_ratio_threshold: float = 2.0,
    state_reset_time: Optional[pd.Timestamp] = None,
    breakout_buffer: float = 1.0,
    immediate_reentry_buffer: float = 2.0,
    intersection_weight_a: float = 0.5,
    intersection_weight_b: float = 0.5,
) -> dict:
    solo_up: Optional[Corner] = None
    solo_down: Optional[Corner] = None
    pos: Optional[Position] = None
    trades: list[dict] = []
    solo_timeline: list[dict] = []
    intersection_timeline: list[dict] = []

    balance = initial_balance
    prev_time: Optional[pd.Timestamp] = None
    day_counter = 0
    reset_done = False
    strategy_started = False
    last_intersection_exit_index: Optional[int] = None
    last_entry_pair_time: Optional[pd.Timestamp] = None
    last_groups: dict[int, Optional[KlineGroup]] = {1: None, 2: None, 3: None, 4: None}
    for i in range(len(df)):
        t = pd.Timestamp(df.at[i, "time"])
        o = float(df.at[i, "open"])
        h = float(df.at[i, "high"])
        l = float(df.at[i, "low"])
        c = float(df.at[i, "close"])
        m_updown = int(df.at[i, "updown"]) if "updown" in df.columns else candle_direction(o, c)

        for lv in (1, 2, 3, 4):
            last_groups[lv] = build_kline_group(df, i, lv)

        day_counter = next_day_counter(prev_time, t, day_counter)
        prev_time = t

        if state_reset_time is not None and (not reset_done) and t >= state_reset_time:
            solo_up = None
            solo_down = None
            pos = None
            reset_done = True

        # 1) 先更新 corner 记录（评论要求：持续记录最新 solo_up / solo_down）。
        corner: Optional[Corner] = detect_corner(df, i, tol_price) if i >= 2 else None
        solo_up_updated = False
        solo_down_updated = False
        if corner is not None:
            if corner.direct == 1:
                solo_up = corner
                solo_up_updated = True
            else:
                solo_down = corner
                solo_down_updated = True

        solo_timeline.append(
            {
                "bar_index": i,
                "bar_time": t.isoformat(),
                "has_corner": int(corner is not None),
                "corner_direct": (corner.direct if corner is not None else None),
                "corner_right_index": (corner.right_index if corner is not None else None),
                "corner_right_time": (corner.time.isoformat() if corner is not None else None),
                "corner_top": (corner.top if corner is not None else None),
                "corner_shadow": (corner.shadow if corner is not None else None),
                "solo_up_updated": int(solo_up_updated),
                "solo_down_updated": int(solo_down_updated),
                "solo_up_right_index": (solo_up.right_index if solo_up is not None else None),
                "solo_up_time": (solo_up.time.isoformat() if solo_up is not None else None),
                "solo_up_top": (solo_up.top if solo_up is not None else None),
                "solo_up_shadow": (solo_up.shadow if solo_up is not None else None),
                "solo_down_right_index": (solo_down.right_index if solo_down is not None else None),
                "solo_down_time": (solo_down.time.isoformat() if solo_down is not None else None),
                "solo_down_top": (solo_down.top if solo_down is not None else None),
                "solo_down_shadow": (solo_down.shadow if solo_down is not None else None),
            }
        )

        ix = build_intersection_signal(df, i, float(intersection_weight_a), float(intersection_weight_b))
        intersection_timeline.append(
            {
                "bar_index": ix.bar_index,
                "bar_time": ix.bar_time.isoformat(),
                "is_cross": int(ix.is_cross),
                "direction": ix.direction,
                "jump": ix.jump,
                "ratio": ix.ratio,
                "mid_ang": ix.mid_ang,
                "prev3_ang": ix.prev3_ang,
                "right_ang": ix.right_ang,
                "hit_a": ix.hit_a,
                "hit_b": ix.hit_b,
                "score": ix.score,
                "label": ix.label,
            }
        )

        anchor_0300 = day_anchor_time(t, 3, 0)

        # 2) 持仓管理：止损强制；止盈按A版本规则执行。
        if pos is not None:
            exit_price = None
            reason = ""

            if pos.side > 0 and l <= pos.sl_price:
                exit_price = pos.sl_price
                reason = "sl"
            elif pos.side < 0 and h >= pos.sl_price:
                exit_price = pos.sl_price
                reason = "sl"

            if exit_price is None:
                # 条件2入场：固定止盈价，买多 close>tp；买空 close<tp。
                if pos.reason.startswith("a_cond2_"):
                    if pos.side > 0 and c > pos.tp_top:
                        exit_price = c
                        reason = "tp_level"
                    elif pos.side < 0 and c < pos.tp_top:
                        exit_price = c
                        reason = "tp_level"
                # 条件3入场：下一次 intersection 平仓。
                elif pos.reason.startswith("a_cond3_") and int(df.at[i, "intersection"]) == 1:
                    exit_price = c
                    reason = "tp_intersection"

            if exit_price is not None:
                pnl = (exit_price - pos.entry_price) * pos.side
                balance += pnl
                trades.append(
                    {
                        "entry_time": pos.entry_time.isoformat(),
                        "exit_time": t.isoformat(),
                        "side": "long" if pos.side > 0 else "short",
                        "entry_price": pos.entry_price,
                        "exit_price": exit_price,
                        "sl_price": pos.sl_price,
                        "tp_top": pos.tp_top,
                        "tp_shadow": pos.tp_shadow,
                        "pnl": pnl,
                        "reason": reason,
                        "signal": pos.reason,
                    }
                )
                pos = None

        # 3) 入场：仅在“最新solo后的下一根K线”判断条件链。
        if pos is not None:
            continue
        if not warmup_ok(day_counter, warmup_bars):
            continue
        # 评论规则：03:00 前只观察，不参与入场。
        if t < anchor_0300:
            continue
        if solo_up is None or solo_down is None:
            continue
        latest_is_up = solo_up.time >= solo_down.time
        latest = solo_up if latest_is_up else solo_down
        if latest.time < anchor_0300:
            continue
        if i != latest.right_index + 1:
            continue

        # 条件1：方向和最新solo反弹方向一致。
        if latest_is_up and m_updown >= 0:
            continue
        if (not latest_is_up) and m_updown <= 0:
            continue

        # 条件3优先：若成立则直接走“下一个intersection平仓”。
        side = 0
        sl = 0.0
        tp_level = 0.0
        signal = ""
        if latest_is_up:
            if c < solo_down.shadow:
                side = -1
                sl = solo_up.top
                signal = "a_cond3_short"
        else:
            if c > solo_up.shadow:
                side = 1
                sl = solo_down.top
                signal = "a_cond3_long"

        # 条件3不成立，再判断条件2（倍数阈值）
        if side == 0:
            d_up = abs(o - solo_up.shadow)
            d_down = abs(o - solo_down.shadow)
            if latest_is_up:
                ratio = d_down / max(1e-9, d_up)
            else:
                ratio = d_up / max(1e-9, d_down)
            if ratio >= entry_ratio_threshold:
                side = -1 if latest_is_up else 1
                sl = solo_up.top if latest_is_up else solo_down.top
                tp_level = solo_down.top if latest_is_up else solo_up.top
                signal = "a_cond2_short" if latest_is_up else "a_cond2_long"

        if side == 0:
            continue

        pos = Position(
            side=side,
            entry_time=t,
            entry_price=c,
            sl_price=sl,
            tp_top=tp_level,
            tp_shadow=tp_level,
            reason=signal,
            exit_on_next_intersection=signal.startswith("a_cond3_"),
        )
        strategy_started = True

    # If one position remains, close on last close as backtest tail handling.
    if pos is not None and len(df) > 0:
        t_last = pd.Timestamp(df.iloc[-1]["time"])
        c_last = float(df.iloc[-1]["close"])
        pnl = (c_last - pos.entry_price) * pos.side
        balance += pnl
        trades.append(
            {
                "entry_time": pos.entry_time.isoformat(),
                "exit_time": t_last.isoformat(),
                "side": "long" if pos.side > 0 else "short",
                "entry_price": pos.entry_price,
                "exit_price": c_last,
                "sl_price": pos.sl_price,
                "tp_top": pos.tp_top,
                "tp_shadow": pos.tp_shadow,
                "pnl": pnl,
                "reason": "end_of_data",
                "signal": pos.reason,
            }
        )

    wins = sum(1 for t in trades if t["pnl"] > 0)
    losses = sum(1 for t in trades if t["pnl"] <= 0)
    gross_profit = sum(t["pnl"] for t in trades if t["pnl"] > 0)
    gross_loss_abs = -sum(t["pnl"] for t in trades if t["pnl"] < 0)
    net_pnl = sum(t["pnl"] for t in trades)
    trade_count = len(trades)

    summary = {
        "bars": int(len(df)),
        "trades": trade_count,
        "wins": wins,
        "losses": losses,
        "win_rate": (wins / trade_count * 100.0) if trade_count else 0.0,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss_abs,
        "profit_factor": (gross_profit / gross_loss_abs) if gross_loss_abs > 0 else 999.0,
        "net_pnl": net_pnl,
        "initial_balance": initial_balance,
        "final_balance": balance,
        "warmup_bars_after_0100": warmup_bars,
        "corner_equal_tolerance_price": tol_price,
        "min_top_gap": min_top_gap,
        "max_opposite_gap_bars": max_opposite_gap_bars,
        "entry_ratio_threshold": entry_ratio_threshold,
        "breakout_buffer": breakout_buffer,
        "immediate_reentry_buffer": immediate_reentry_buffer,
        "intersection_weight_a": intersection_weight_a,
        "intersection_weight_b": intersection_weight_b,
        "intersection_major_count": int(sum(1 for x in intersection_timeline if x["is_cross"] == 1 and x["label"] == "major")),
        "intersection_micro_count": int(sum(1 for x in intersection_timeline if x["is_cross"] == 1 and x["label"] == "micro")),
        "structure_enabled": True,
        "group_last_status": {
            "level1": (last_groups[1].last_status if last_groups[1] is not None else None),
            "level2": (last_groups[2].last_status if last_groups[2] is not None else None),
            "level3": (last_groups[3].last_status if last_groups[3] is not None else None),
            "level4": (last_groups[4].last_status if last_groups[4] is not None else None),
        },
        "state_reset_time": (state_reset_time.isoformat() if state_reset_time is not None else None),
    }
    return {
        "summary": summary,
        "trades": trades,
        "solo_timeline": solo_timeline,
        "intersection_timeline": intersection_timeline,
    }


def write_trades_csv(path: Path, trades: list[dict]) -> None:
    fields = [
        "entry_time",
        "exit_time",
        "side",
        "entry_price",
        "exit_price",
        "sl_price",
        "tp_top",
        "tp_shadow",
        "pnl",
        "reason",
        "signal",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in trades:
            w.writerow(row)


def write_solo_timeline_csv(path: Path, timeline: list[dict]) -> None:
    fields = [
        "bar_index",
        "bar_time",
        "has_corner",
        "corner_direct",
        "corner_right_index",
        "corner_right_time",
        "corner_top",
        "corner_shadow",
        "solo_up_updated",
        "solo_down_updated",
        "solo_up_right_index",
        "solo_up_time",
        "solo_up_top",
        "solo_up_shadow",
        "solo_down_right_index",
        "solo_down_time",
        "solo_down_top",
        "solo_down_shadow",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in timeline:
            w.writerow(row)


def write_intersection_timeline_csv(path: Path, timeline: list[dict]) -> None:
    fields = [
        "bar_index",
        "bar_time",
        "is_cross",
        "direction",
        "jump",
        "ratio",
        "mid_ang",
        "prev3_ang",
        "right_ang",
        "hit_a",
        "hit_b",
        "score",
        "label",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in timeline:
            w.writerow(row)


def main() -> None:
    ap = argparse.ArgumentParser(description="Plan02 signal-layer backtest")
    ap.add_argument("--file", type=str, default=str(DEFAULT_FILE))
    ap.add_argument("--out-trades", type=str, default="")
    ap.add_argument("--out-summary", type=str, default="")
    ap.add_argument("--out-solo", type=str, default="")
    ap.add_argument("--out-intersection", type=str, default="")
    ap.add_argument("--warmup-bars", type=int, default=24)
    ap.add_argument("--tol-price", type=float, default=0.10)
    ap.add_argument("--initial-balance", type=float, default=1000.0)
    ap.add_argument("--min-top-gap", type=float, default=1.0)
    ap.add_argument("--max-opposite-gap-bars", type=int, default=12)
    ap.add_argument("--entry-ratio-threshold", type=float, default=2.0)
    ap.add_argument("--state-reset-time", type=str, default="")
    ap.add_argument("--breakout-buffer", type=float, default=1.0)
    ap.add_argument("--immediate-reentry-buffer", type=float, default=2.0)
    ap.add_argument("--intersection-weight-a", type=float, default=0.5)
    ap.add_argument("--intersection-weight-b", type=float, default=0.5)
    args = ap.parse_args()

    fp = Path(args.file)
    out_trades = Path(args.out_trades) if args.out_trades else Path(__file__).resolve().parent / "plan02_backtest_day367_trades.csv"
    out_summary = Path(args.out_summary) if args.out_summary else Path(__file__).resolve().parent / "plan02_backtest_day367_summary.json"
    out_solo = Path(args.out_solo) if args.out_solo else Path(__file__).resolve().parent / "plan02_backtest_day367_solo_timeline.csv"
    out_intersection = Path(args.out_intersection) if args.out_intersection else Path(__file__).resolve().parent / "plan02_backtest_day367_intersection_timeline.csv"

    df = add_indicators(load_ohlc(fp))
    reset_time = pd.to_datetime(args.state_reset_time) if args.state_reset_time else None

    res = run_backtest(
        df,
        tol_price=float(args.tol_price),
        warmup_bars=int(args.warmup_bars),
        initial_balance=float(args.initial_balance),
        min_top_gap=float(args.min_top_gap),
        max_opposite_gap_bars=int(args.max_opposite_gap_bars),
        entry_ratio_threshold=float(args.entry_ratio_threshold),
        state_reset_time=reset_time,
        breakout_buffer=float(args.breakout_buffer),
        immediate_reentry_buffer=float(args.immediate_reentry_buffer),
        intersection_weight_a=float(args.intersection_weight_a),
        intersection_weight_b=float(args.intersection_weight_b),
    )

    write_trades_csv(out_trades, res["trades"])
    write_solo_timeline_csv(out_solo, res.get("solo_timeline", []))
    write_intersection_timeline_csv(out_intersection, res.get("intersection_timeline", []))
    out_summary.write_text(json.dumps(res["summary"], ensure_ascii=False, indent=2), encoding="utf-8")

    s = res["summary"]
    print("=== Plan02 Backtest ===")
    print(f"bars={s['bars']} trades={s['trades']} wins={s['wins']} losses={s['losses']}")
    print(f"win_rate={s['win_rate']:.2f}% pf={s['profit_factor']:.4f} net={s['net_pnl']:.2f}")
    print(f"final_balance={s['final_balance']:.2f}")
    print(f"trades_csv={out_trades}")
    print(f"summary_json={out_summary}")
    print(f"solo_timeline_csv={out_solo}")
    print(f"intersection_timeline_csv={out_intersection}")


if __name__ == "__main__":
    main()
