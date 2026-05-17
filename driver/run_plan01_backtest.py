from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_FILE = BASE_DIR / "XAUUSDM5-test.csv"


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


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["ma5"] = out["close"].rolling(5).mean()
    out["ma20"] = out["close"].rolling(20).mean()
    out["ema5"] = out["close"].ewm(span=5, adjust=False).mean()
    out["ema20"] = out["close"].ewm(span=20, adjust=False).mean()
    out["mid"] = out["close"].rolling(20).mean()
    std20 = out["close"].rolling(20).std(ddof=0)
    out["up"] = out["mid"] + 2.0 * std20
    out["down"] = out["mid"] - 2.0 * std20
    out["bb_mid"] = out["mid"]
    out["bb_up"] = out["up"]
    out["bb_down"] = out["down"]
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


def run_backtest(
    df: pd.DataFrame,
    tol_price: float = 0.10,
    warmup_bars: int = 20,
    initial_balance: float = 1000.0,
    min_top_gap: float = 1.0,
    max_opposite_gap_bars: int = 12,
    entry_ratio_threshold: float = 0.5,
    state_reset_time: Optional[pd.Timestamp] = None,
) -> dict:
    solo_up: Optional[Corner] = None
    solo_down: Optional[Corner] = None
    pos: Optional[Position] = None
    trades: list[dict] = []

    balance = initial_balance
    prev_time: Optional[pd.Timestamp] = None
    day_counter = 0
    reset_done = False
    for i in range(len(df)):
        t = pd.Timestamp(df.at[i, "time"])
        o = float(df.at[i, "open"])
        h = float(df.at[i, "high"])
        l = float(df.at[i, "low"])
        c = float(df.at[i, "close"])

        day_counter = next_day_counter(prev_time, t, day_counter)
        prev_time = t

        if state_reset_time is not None and (not reset_done) and t >= state_reset_time:
            solo_up = None
            solo_down = None
            pos = None
            reset_done = True

        corner: Optional[Corner] = detect_corner(df, i, tol_price) if i >= 2 else None

        # 1) Manage open position by SL and TP-reversal-only (no long-wick logic in Plan01).
        if pos is not None:
            exit_price = None
            reason = ""

            if pos.side > 0 and l <= pos.sl_price:
                exit_price = pos.sl_price
                reason = "sl"
            elif pos.side < 0 and h >= pos.sl_price:
                exit_price = pos.sl_price
                reason = "sl"

            if exit_price is None and in_tp_zone(pos.side, c, pos.tp_top, pos.tp_shadow):
                pos.tp_armed = True

            if exit_price is None and pos.tp_armed:
                if candle_direction(o, c) == -pos.side:
                    exit_price = c
                    reason = "tp_reversal_candle"

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

        # 2) Detect latest corner and update solo corner.
        if corner is None:
            continue

        if corner.direct == 1:
            solo_up = corner
        else:
            solo_down = corner

        # 3) Entry only when no position and warmup finished (corner main flow).
        if pos is not None:
            continue
        if not warmup_ok(day_counter, warmup_bars):
            continue
        if solo_up is None or solo_down is None:
            continue
        if abs(solo_up.top - solo_down.top) < min_top_gap:
            continue

        side = 0
        signal = ""
        tp_ref: Optional[Corner] = None
        sl = None
        m_dir = candle_direction(o, c)

        if corner.direct == 1:
            if (corner.right_index - solo_down.right_index) > max_opposite_gap_bars:
                continue
            if (c < corner.shadow) and (m_dir < 0):
                side = -1
                signal = "solo_up_dir_short"
                tp_ref = solo_down
                sl = corner.top
        else:
            if (corner.right_index - solo_up.right_index) > max_opposite_gap_bars:
                continue
            if (c > corner.shadow) and (m_dir > 0):
                side = 1
                signal = "solo_down_dir_long"
                tp_ref = solo_up
                sl = corner.top

        if side == 0 or tp_ref is None or sl is None:
            continue

        if side > 0 and sl >= c:
            continue
        if side < 0 and sl <= c:
            continue

        pos = Position(
            side=side,
            entry_time=t,
            entry_price=c,
            sl_price=sl,
            tp_top=tp_ref.top,
            tp_shadow=tp_ref.shadow,
            reason=signal,
        )

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
        "state_reset_time": (state_reset_time.isoformat() if state_reset_time is not None else None),
    }
    return {"summary": summary, "trades": trades}


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


def main() -> None:
    ap = argparse.ArgumentParser(description="Plan01 corner strategy backtest")
    ap.add_argument("--file", type=str, default=str(DEFAULT_FILE))
    ap.add_argument("--out-trades", type=str, default="")
    ap.add_argument("--out-summary", type=str, default="")
    ap.add_argument("--warmup-bars", type=int, default=20)
    ap.add_argument("--tol-price", type=float, default=0.10)
    ap.add_argument("--initial-balance", type=float, default=1000.0)
    ap.add_argument("--min-top-gap", type=float, default=1.0)
    ap.add_argument("--max-opposite-gap-bars", type=int, default=12)
    ap.add_argument("--entry-ratio-threshold", type=float, default=0.5)
    ap.add_argument("--state-reset-time", type=str, default="")
    args = ap.parse_args()

    fp = Path(args.file)
    out_trades = Path(args.out_trades) if args.out_trades else Path(__file__).resolve().parent / "plan01_backtest_trades.csv"
    out_summary = Path(args.out_summary) if args.out_summary else Path(__file__).resolve().parent / "plan01_backtest_summary.json"

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
    )

    write_trades_csv(out_trades, res["trades"])
    out_summary.write_text(json.dumps(res["summary"], ensure_ascii=False, indent=2), encoding="utf-8")

    s = res["summary"]
    print("=== Plan01 Backtest ===")
    print(f"bars={s['bars']} trades={s['trades']} wins={s['wins']} losses={s['losses']}")
    print(f"win_rate={s['win_rate']:.2f}% pf={s['profit_factor']:.4f} net={s['net_pnl']:.2f}")
    print(f"final_balance={s['final_balance']:.2f}")
    print(f"trades_csv={out_trades}")
    print(f"summary_json={out_summary}")


if __name__ == "__main__":
    main()
