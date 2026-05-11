from __future__ import annotations

"""Survival v6 backtest (完整内嵌版, round3 口径)."""

import argparse
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

import run_survival_v3_backtest as io_base

BASE_DIR = Path(__file__).resolve().parents[1]
FILE = BASE_DIR / 'Week' / 'Week_06_20260504_20260510.csv'

parse_data = io_base.parse_data


@dataclass
class Params:
    boll_angle_long: float = 137.57306588636873
    boll_angle_short: float = -113.85017350164195
    y_low: float = 0.33376156641703826
    y_high: float = 0.6381725610417532
    ema5_ang_long: float = -6.137710738148822
    ema20_ang_long: float = -16.64108941367931
    ema5_ang_short: float = -0.6753561077494844
    ema20_ang_short: float = -14.426729554730186
    spread_slope_long: float = -0.3804665364165669
    spread_slope_short: float = 0.01812893459247469
    k5_body_long: float = -1.299998392609744
    k5_body_short: float = -0.6270584772456646
    k5_shadow_cap: float = 0.3774413112492591
    sl_atr: float = 1.0973260356991068
    tp_atr: float = 7.90013935887591
    max_hold: int = 123


def indicators(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    c = d['close']
    d['ema5'] = c.ewm(span=5, adjust=False).mean()
    d['ema20'] = c.ewm(span=20, adjust=False).mean()

    mid = c.rolling(20).mean()
    std = c.rolling(20).std(ddof=0)
    d['bb_mid'] = mid
    d['bb_up'] = mid + 2.0 * std
    d['bb_down'] = mid - 2.0 * std
    d['bb_width'] = d['bb_up'] - d['bb_down']

    prev = c.shift(1)
    tr = pd.concat([
        (d['high'] - d['low']).abs(),
        (d['high'] - prev).abs(),
        (d['low'] - prev).abs(),
    ], axis=1).max(axis=1)
    d['atr'] = tr.rolling(14).mean()

    d['bb_mid_delta'] = d['bb_mid'].diff()
    d['bb_width_delta'] = d['bb_width'].diff()
    d['bb_angle'] = np.degrees(np.arctan2(d['bb_mid_delta'], d['bb_width_delta'].replace(0, 1e-9)))

    width = d['bb_width'].replace(0, np.nan)
    d['y_pos'] = (d['close'] - d['bb_down']) / width

    d['ema_spread'] = d['ema5'] - d['ema20']
    d['ema_spread_slope'] = d['ema_spread'].diff()
    return d


def _angle(series: np.ndarray) -> float:
    if len(series) < 2:
        return 0.0
    y = float(series[-1] - series[0])
    x = float(len(series) - 1)
    return float(math.degrees(math.atan2(y, x)))


def _k5_features(o: np.ndarray, h: np.ndarray, l: np.ndarray, c: np.ndarray):
    body = np.abs(c - o)
    upper = h - np.maximum(o, c)
    lower = np.minimum(o, c) - l
    rng = np.maximum(1e-9, h - l)
    body_score = float((c[-1] - c[0]) / max(1e-9, np.mean(rng)))
    shadow_ratio = float(np.mean((upper + lower) / rng))
    up_count = int(np.sum(np.diff(c) > 0))
    down_count = int(np.sum(np.diff(c) < 0))
    return body_score, shadow_ratio, up_count, down_count


def signal(d: pd.DataFrame, i: int, p: Params) -> int:
    if i < 30:
        return 0

    bb_angle = float(d['bb_angle'].iloc[i - 1])
    y_pos = float(d['y_pos'].iloc[i - 1])
    spread_slope = float(d['ema_spread_slope'].iloc[i - 1])

    ema5_ang = _angle(d['ema5'].iloc[i - 6:i].to_numpy())
    ema20_ang = _angle(d['ema20'].iloc[i - 10:i].to_numpy())

    o = d['open'].iloc[i - 5:i].to_numpy()
    h = d['high'].iloc[i - 5:i].to_numpy()
    l = d['low'].iloc[i - 5:i].to_numpy()
    c = d['close'].iloc[i - 5:i].to_numpy()
    body_score, shadow_ratio, up_count, down_count = _k5_features(o, h, l, c)

    long_cond = (
        bb_angle >= p.boll_angle_long
        and y_pos >= p.y_low and y_pos <= p.y_high
        and ema5_ang >= p.ema5_ang_long
        and ema20_ang >= p.ema20_ang_long
        and spread_slope >= p.spread_slope_long
        and body_score >= p.k5_body_long
        and shadow_ratio <= p.k5_shadow_cap
        and up_count >= 3
    )

    short_cond = (
        bb_angle <= p.boll_angle_short
        and y_pos <= (1.0 - p.y_low) and y_pos >= (1.0 - p.y_high)
        and ema5_ang <= p.ema5_ang_short
        and ema20_ang <= p.ema20_ang_short
        and spread_slope <= p.spread_slope_short
        and body_score <= p.k5_body_short
        and shadow_ratio <= p.k5_shadow_cap
        and down_count >= 3
    )

    if long_cond and not short_cond:
        return 1
    if short_cond and not long_cond:
        return -1
    return 0


def run_backtest(df: pd.DataFrame):
    p = Params()

    balance = 1000.0
    peak = balance
    max_dd = 0.0

    pos = None
    trades = []
    signals = {'long': 0, 'short': 0}

    for i in range(35, len(df)):
        atr = float(df['atr'].iloc[i - 1])
        if not np.isfinite(atr) or atr <= 0:
            continue

        op = float(df['open'].iloc[i])
        sig = signal(df, i, p)

        if pos is not None:
            pos['hold'] += 1
            hi = float(df['high'].iloc[i - 1])
            lo = float(df['low'].iloc[i - 1])

            reason = None
            ep = op

            if pos['side'] == 'long':
                if lo <= pos['sl']:
                    reason, ep = 'sl', pos['sl']
                elif hi >= pos['tp']:
                    reason, ep = 'tp', pos['tp']
                elif sig == -1:
                    reason, ep = 'flip', op
            else:
                if hi >= pos['sl']:
                    reason, ep = 'sl', pos['sl']
                elif lo <= pos['tp']:
                    reason, ep = 'tp', pos['tp']
                elif sig == 1:
                    reason, ep = 'flip', op

            if reason is None and pos['hold'] >= p.max_hold:
                reason, ep = 'timeout', op

            if reason is not None:
                pnl = (ep - pos['entry']) * pos['units'] if pos['side'] == 'long' else (pos['entry'] - ep) * pos['units']
                balance += pnl
                peak = max(peak, balance)
                dd = (peak - balance) / peak if peak > 0 else 0.0
                max_dd = max(max_dd, dd)
                trades.append({
                    'entry_time': str(pos['time']),
                    'exit_time': str(df['time'].iloc[i]),
                    'side': pos['side'],
                    'entry': float(pos['entry']),
                    'exit': float(ep),
                    'pnl': float(pnl),
                    'reason': reason,
                })
                pos = None

            if pos is not None:
                continue

        if sig == 0:
            continue

        if sig == 1:
            signals['long'] += 1
            sl = op - atr * p.sl_atr
            tp = op + atr * p.tp_atr
            side = 'long'
        else:
            signals['short'] += 1
            sl = op + atr * p.sl_atr
            tp = op - atr * p.tp_atr
            side = 'short'

        risk_money = balance * 0.01
        dist = abs(op - sl)
        units = risk_money / dist if dist > 1e-9 else 0.0
        if units <= 0:
            continue

        pos = {
            'side': side,
            'entry': op,
            'sl': sl,
            'tp': tp,
            'units': units,
            'time': df['time'].iloc[i],
            'hold': 0,
        }

    if pos is not None:
        ep = float(df['close'].iloc[-1])
        pnl = (ep - pos['entry']) * pos['units'] if pos['side'] == 'long' else (pos['entry'] - ep) * pos['units']
        balance += pnl
        trades.append({
            'entry_time': str(pos['time']),
            'exit_time': str(df['time'].iloc[-1]),
            'side': pos['side'],
            'entry': float(pos['entry']),
            'exit': float(ep),
            'pnl': float(pnl),
            'reason': 'final',
        })

    wins = sum(1 for t in trades if t['pnl'] > 0)
    losses = sum(1 for t in trades if t['pnl'] < 0)
    gp = sum(t['pnl'] for t in trades if t['pnl'] > 0)
    gl = -sum(t['pnl'] for t in trades if t['pnl'] < 0)
    pf = gp / gl if gl > 1e-9 else (999.0 if gp > 0 else 0.0)

    return {
        'bars': int(len(df)),
        'start': str(df['time'].iloc[0]),
        'end': str(df['time'].iloc[-1]),
        'signals': signals,
        'gate_pass': {'short': 0, 'long': 0},
        'trades': trades,
        'wins': int(wins),
        'losses': int(losses),
        'win_rate': float(wins / len(trades) * 100.0) if trades else 0.0,
        'net_pnl': float(balance - 1000.0),
        'final_balance': float(balance),
        'max_dd_pct': float(max_dd * 100.0),
        'profit_factor': float(pf),
    }


def main():
    ap = argparse.ArgumentParser(description='Run Survival_v6 backtest (embedded round3)')
    ap.add_argument('--file', type=str, default=str(FILE), help='single input file path (.xlsx/.csv)')
    args = ap.parse_args()

    df = indicators(parse_data(Path(args.file)))
    rs = run_backtest(df)
    print('=== Backtest Summary (Survival_v6 embedded round3) ===')
    print(f'Source      : {args.file}')
    print(f'Trades      : {len(rs["trades"])}')
    print(f'Win/Loss    : {rs["wins"]}/{rs["losses"]} ({rs["win_rate"]:.2f}%)')
    print(f'Net PnL     : {rs["net_pnl"]:.2f}')
    print(f'Final Bal   : {rs["final_balance"]:.2f}')
    print(f'Max DD      : {rs["max_dd_pct"]:.2f}%')


if __name__ == '__main__':
    main()
