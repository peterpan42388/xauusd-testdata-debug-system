from __future__ import annotations

"""Survival v7 backtest (self-contained).

已内嵌原 SelfUpgrade/06 依赖的关键参数与融合判定逻辑，
不再依赖仓库外部脚本/JSON。
"""

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

# Embedded from SelfUpgrade result_round3.json
R3P = {
    'boll_angle_long': 137.57306588636873,
    'boll_angle_short': -113.85017350164195,
    'y_low': 0.33376156641703826,
    'y_high': 0.6381725610417532,
    'ema5_ang_long': -6.137710738148822,
    'ema20_ang_long': -16.64108941367931,
    'ema5_ang_short': -0.6753561077494844,
    'ema20_ang_short': -14.426729554730186,
    'spread_slope_long': -0.3804665364165669,
    'spread_slope_short': 0.01812893459247469,
    'k5_body_long': -1.299998392609744,
    'k5_body_short': -0.6270584772456646,
    'k5_shadow_cap': 0.3774413112492591,
}

# Embedded from SelfUpgrade result_round4.json
R4_LONG = {
    'A_DN|Y_HIGH|E_BEAR_DECEL|K5_MIX','A_DN|Y_HIGH|E_BEAR_DECEL|K5_UP','A_DN|Y_LOW|E_BEAR_ACCEL|K5_UP',
    'A_DN|Y_LOW|E_BEAR_DECEL|K5_MIX','A_DN|Y_LOW|E_BEAR_DECEL|K5_UP','A_DN|Y_MID|E_BEAR_DECEL|K5_UP',
    'A_FLAT|Y_HIGH|E_BULL_DECEL|K5_DN','A_FLAT|Y_HIGH|E_BULL_DECEL|K5_MIX','A_FLAT|Y_LOW|E_BEAR_ACCEL|K5_MIX',
    'A_FLAT|Y_LOW|E_BEAR_ACCEL|K5_UP','A_FLAT|Y_LOW|E_BEAR_DECEL|K5_DN','A_FLAT|Y_MID|E_BEAR_ACCEL|K5_DN',
    'A_FLAT|Y_MID|E_BULL_ACCEL|K5_MIX','A_UP|Y_LOW|E_BEAR_DECEL|K5_MIX','A_UP|Y_LOW|E_BULL_DECEL|K5_DN',
    'A_UP|Y_LOW|E_BULL_DECEL|K5_MIX','A_UP|Y_MID|E_BEAR_DECEL|K5_DN',
}
R4_SHORT = {
    'A_DN|Y_HIGH|E_BULL_ACCEL|K5_MIX','A_DN|Y_MID|E_BULL_ACCEL|K5_MIX','A_DN|Y_MID|E_BULL_DECEL|K5_DN',
    'A_DN|Y_MID|E_BULL_DECEL|K5_MIX','A_DN|Y_MID|E_BULL_DECEL|K5_UP','A_FLAT|Y_HIGH|E_BEAR_DECEL|K5_UP',
    'A_FLAT|Y_LOW|E_BULL_DECEL|K5_DN','A_FLAT|Y_LOW|E_BULL_DECEL|K5_MIX','A_FLAT|Y_MID|E_BEAR_ACCEL|K5_MIX',
    'A_FLAT|Y_MID|E_BEAR_DECEL|K5_UP','A_FLAT|Y_MID|E_BULL_DECEL|K5_MIX','A_UP|Y_HIGH|E_BULL_ACCEL|K5_DN',
    'A_UP|Y_MID|E_BEAR_ACCEL|K5_MIX','A_UP|Y_MID|E_BULL_ACCEL|K5_DN','A_UP|Y_MID|E_BULL_DECEL|K5_UP',
}

# Embedded from SelfUpgrade result_round5.json
R5_LONG = {
    'DLNAKUP->DLNAKDN','DLNAKUP->DLNAKUP','DLNAKUP->DMNAKUP','DLNBKUP->DLNBKDN','DMNAKUP->DLNBKUP',
    'DMNAKUP->DMNBKDN','DMNAKUP->FLNBKUP','FHPAKDN->FHPAKDN','FHPAKUP->UMPBKUP','FHPBKDN->FHPAKUP',
    'FHPBKDN->FHPBKUP','FLNAKDN->FMNAKUP','FLNBKDN->DMNAKUP','FLNBKUP->FLNBKDN','FLNBKUP->FLNBKUP',
    'FMPBKDN->FMPBKDN','UHPAKUP->UMPBKDN','UHPBKUP->FHPAKUP','UMPBKDN->FLNBKDN','UMPBKDN->UHPAKUP',
}
R5_SHORT = {
    'DHNAKUP->DHPAKUP','DLNBKDN->DMNAKDN','DMNAKDN->DLNBKDN','DMNAKDN->DMNAKDN','DMNAKDN->DMNAKUP',
    'DMNAKDN->DMNBKDN','DMNAKUP->DHNAKUP','DMNAKUP->DMPAKUP','DMNBKDN->DMNAKDN','FHPAKDN->FHPAKUP',
    'FHPAKUP->UHPBKDN','FHPBKDN->UMPBKDN','FLNAKDN->DLNAKUP','FLNAKUP->FMNAKUP','FLNBKDN->DLNAKDN',
    'FLNBKUP->FLNAKUP','FMPBKDN->UMPBKDN','UHPAKUP->UHPAKUP','UHPAKUP->UHPBKDN','UHPAKUP->UMPBKUP',
    'UHPBKUP->UHPBKUP','ULNBKDN->FLNBKDN','UMNAKUP->UMNAKUP','UMPAKUP->UHPAKUP','UMPBKDN->ULNBKDN',
    'UMPBKDN->UMNBKDN','UMPBKDN->UMPBKDN','UMPBKUP->UMPBKDN','UMPBKUP->UMPBKUP',
}

# Embedded from SelfUpgrade result_round6.json
@dataclass
class FusionParams:
    w3: float = 1.8878837900777607
    w4: float = 1.119812645681353
    w5: float = 1.3057083219978902
    th_long: float = 1.1486930794579135
    th_short: float = 1.16052699635634
    sl_atr: float = 1.1072042572256844
    tp_atr: float = 4.1187717113174385
    max_hold: int = 73
    tp_expand_factor: float = 1.3913402871157283
    sl_lock_factor: float = 1.090217833327329
    trail_factor: float = 1.1343085980180683


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
    d['ypos'] = (d['close'] - d['bb_down']) / d['bb_width'].replace(0, np.nan)

    d['ema_spread'] = d['ema5'] - d['ema20']
    d['ema_spread_slope'] = d['ema_spread'].diff()
    # For v8/v9 stable-trend add-on gates
    d['ema20_slope_8'] = (d['ema20'] - d['ema20'].shift(8)) / 8.0
    d['ema20_curv'] = d['ema20'].diff().diff().abs()
    d['bb_mid_curv'] = d['bb_mid'].diff().diff().abs()
    sign_up = (d['ema20'].diff() > 0).astype(float)
    sign_dn = (d['ema20'].diff() < 0).astype(float)
    d['dir_up_ratio_12'] = sign_up.rolling(12).mean()
    d['dir_dn_ratio_12'] = sign_dn.rolling(12).mean()
    return d


def _ang(vals: np.ndarray) -> float:
    if len(vals) < 2:
        return 0.0
    return float(math.degrees(math.atan2(float(vals[-1] - vals[0]), float(len(vals) - 1))))


def _k5_features(o: np.ndarray, h: np.ndarray, l: np.ndarray, c: np.ndarray):
    upper = h - np.maximum(o, c)
    lower = np.minimum(o, c) - l
    rng = np.maximum(1e-9, h - l)
    shadow_ratio = float(np.mean((upper + lower) / rng))
    body_score = float((c[-1] - c[0]) / max(1e-9, np.mean(rng)))
    up_count = int(np.sum(np.diff(c) > 0))
    down_count = int(np.sum(np.diff(c) < 0))
    return body_score, shadow_ratio, up_count, down_count


def signal_round3(d: pd.DataFrame, i: int) -> int:
    if i < 30:
        return 0
    p = R3P
    bb_angle = float(d['bb_angle'].iloc[i - 1])
    ypos = float(d['ypos'].iloc[i - 1])
    spread_slope = float(d['ema_spread_slope'].iloc[i - 1])

    ema5_ang = _ang(d['ema5'].iloc[i - 6:i].to_numpy())
    ema20_ang = _ang(d['ema20'].iloc[i - 10:i].to_numpy())
    o = d['open'].iloc[i - 5:i].to_numpy(); h = d['high'].iloc[i - 5:i].to_numpy(); l = d['low'].iloc[i - 5:i].to_numpy(); c = d['close'].iloc[i - 5:i].to_numpy()
    body_score, shadow_ratio, up_count, down_count = _k5_features(o, h, l, c)

    long_cond = (
        bb_angle >= p['boll_angle_long'] and ypos >= p['y_low'] and ypos <= p['y_high'] and
        ema5_ang >= p['ema5_ang_long'] and ema20_ang >= p['ema20_ang_long'] and
        spread_slope >= p['spread_slope_long'] and body_score >= p['k5_body_long'] and
        shadow_ratio <= p['k5_shadow_cap'] and up_count >= 3
    )
    short_cond = (
        bb_angle <= p['boll_angle_short'] and ypos <= (1.0 - p['y_low']) and ypos >= (1.0 - p['y_high']) and
        ema5_ang <= p['ema5_ang_short'] and ema20_ang <= p['ema20_ang_short'] and
        spread_slope <= p['spread_slope_short'] and body_score <= p['k5_body_short'] and
        shadow_ratio <= p['k5_shadow_cap'] and down_count >= 3
    )
    if long_cond and not short_cond:
        return 1
    if short_cond and not long_cond:
        return -1
    return 0


def state4(d: pd.DataFrame, i: int) -> str:
    ang = float(d['bb_angle'].iloc[i]); ypos = float(d['ypos'].iloc[i])
    spread = float(d['ema_spread'].iloc[i]); slope = float(d['ema_spread_slope'].iloc[i])
    a = 'A_UP' if ang > 95 else ('A_DN' if ang < -95 else 'A_FLAT')
    y = 'Y_LOW' if ypos < 0.33 else ('Y_HIGH' if ypos > 0.66 else 'Y_MID')
    if spread > 0 and slope > 0: e = 'E_BULL_ACCEL'
    elif spread > 0 and slope <= 0: e = 'E_BULL_DECEL'
    elif spread <= 0 and slope < 0: e = 'E_BEAR_ACCEL'
    else: e = 'E_BEAR_DECEL'
    c = d['close'].iloc[i - 4:i + 1].to_numpy()
    up = int(np.sum(np.diff(c) > 0)); dn = int(np.sum(np.diff(c) < 0))
    k = 'K5_UP' if up >= 3 else ('K5_DN' if dn >= 3 else 'K5_MIX')
    return f'{a}|{y}|{e}|{k}'


def node5(d: pd.DataFrame, i: int) -> str:
    ang = float(d['bb_angle'].iloc[i]); ypos = float(d['ypos'].iloc[i])
    spread = float(d['ema_spread'].iloc[i]); slope = float(d['ema_spread_slope'].iloc[i])
    a = 'U' if ang > 95 else ('D' if ang < -95 else 'F')
    y = 'L' if ypos < 0.33 else ('H' if ypos > 0.66 else 'M')
    e = 'P' if spread > 0 else 'N'
    s = 'A' if slope > 0 else 'B'
    c = d['close'].iloc[i - 3:i + 1].to_numpy()
    k = 'KUP' if np.sum(np.diff(c) > 0) >= 2 else ('KDN' if np.sum(np.diff(c) < 0) >= 2 else 'KM')
    return f'{a}{y}{e}{s}{k}'


def fusion_signal(d: pd.DataFrame, i: int, p: FusionParams):
    s3 = signal_round3(d, i)
    st4 = state4(d, i - 1)
    s4 = 1 if st4 in R4_LONG else (-1 if st4 in R4_SHORT else 0)
    e5 = node5(d, i - 2) + '->' + node5(d, i - 1)
    s5 = 1 if e5 in R5_LONG else (-1 if e5 in R5_SHORT else 0)

    long_score = (p.w3 if s3 == 1 else 0.0) + (p.w4 if s4 == 1 else 0.0) + (p.w5 if s5 == 1 else 0.0)
    short_score = (p.w3 if s3 == -1 else 0.0) + (p.w4 if s4 == -1 else 0.0) + (p.w5 if s5 == -1 else 0.0)

    sig = 0
    if long_score >= p.th_long and long_score > short_score:
        sig = 1
    elif short_score >= p.th_short and short_score > long_score:
        sig = -1

    return sig, {'s3': s3, 's4': s4, 's5': s5, 'l': long_score, 's': short_score}


def add_structure_label(d: pd.DataFrame, i: int, side: str) -> str:
    ang = float(d['bb_angle'].iloc[i - 1])
    ypos = float(d['ypos'].iloc[i - 1])
    sp = float(d['ema_spread_slope'].iloc[i - 1])
    c1 = 'A_HI' if abs(ang) >= 120 else ('A_MD' if abs(ang) >= 95 else 'A_LO')
    c2 = 'Y_TOP' if ypos >= 0.7 else ('Y_MID' if ypos >= 0.3 else 'Y_BOT')
    c3 = 'SP_UP' if sp > 0 else 'SP_DN'
    return f'{side}|{c1}|{c2}|{c3}'


def stable_for_add(d: pd.DataFrame, i: int, p, side: str) -> bool:
    # p should provide stable_window/stable_dir_ratio/stable_bb_angle_min/stable_spread_slope_min/
    # stable_curv_cap/stable_ypos_long_min/stable_ypos_short_max
    if i < max(30, int(getattr(p, 'stable_window', 12)) + 5):
        return False

    atr = float(d['atr'].iloc[i - 1])
    if not np.isfinite(atr) or atr <= 0:
        return False

    bb_ang = float(d['bb_angle'].iloc[i - 1])
    spread_slope = float(d['ema_spread_slope'].iloc[i - 1])
    ypos = float(d['ypos'].iloc[i - 1])
    ema20_curv = float(d['ema20_curv'].iloc[i - 1])
    bb_curv = float(d['bb_mid_curv'].iloc[i - 1])

    w = int(getattr(p, 'stable_window', 12))
    seg = d['ema20'].iloc[i - w:i].to_numpy()
    if len(seg) < w:
        return False

    dif = np.diff(seg)
    up_ratio = float(np.mean(dif > 0))
    dn_ratio = float(np.mean(dif < 0))
    curv_norm = (ema20_curv + bb_curv) / max(1e-9, atr)

    stable_dir_ratio = float(getattr(p, 'stable_dir_ratio', 0.75))
    stable_bb_angle_min = float(getattr(p, 'stable_bb_angle_min', 95.0))
    stable_spread_slope_min = float(getattr(p, 'stable_spread_slope_min', 0.08))
    stable_curv_cap = float(getattr(p, 'stable_curv_cap', 0.18))
    stable_ypos_long_min = float(getattr(p, 'stable_ypos_long_min', 0.56))
    stable_ypos_short_max = float(getattr(p, 'stable_ypos_short_max', 0.44))

    if side == 'long':
        return (
            d['ema5'].iloc[i - 1] > d['ema20'].iloc[i - 1]
            and up_ratio >= stable_dir_ratio
            and bb_ang >= stable_bb_angle_min
            and spread_slope >= stable_spread_slope_min
            and curv_norm <= stable_curv_cap
            and ypos >= stable_ypos_long_min
        )

    return (
        d['ema5'].iloc[i - 1] < d['ema20'].iloc[i - 1]
        and dn_ratio >= stable_dir_ratio
        and bb_ang <= -stable_bb_angle_min
        and spread_slope <= -stable_spread_slope_min
        and curv_norm <= stable_curv_cap
        and ypos <= stable_ypos_short_max
    )


def run_backtest(df: pd.DataFrame):
    p = FusionParams()
    bal = 1000.0
    peak = bal
    max_dd = 0.0
    pos = None
    trades = []
    signals = {'long': 0, 'short': 0}

    for i in range(40, len(df)):
        atr = float(df['atr'].iloc[i - 1])
        if not np.isfinite(atr) or atr <= 0:
            continue

        op = float(df['open'].iloc[i])
        sig, comp = fusion_signal(df, i, p)
        big_trend = np.sign(float(df['close'].iloc[i - 1] - df['close'].iloc[max(0, i - 51)]))
        slope = float(df['ema_spread_slope'].iloc[i - 1])

        if pos is not None:
            pos['hold'] += 1
            hi = float(df['high'].iloc[i - 1]); lo = float(df['low'].iloc[i - 1])
            reason = None; ep = op

            if pos['side'] == 'long':
                if lo <= pos['sl']:
                    reason, ep = 'sl', pos['sl']
                else:
                    tp_hit = hi >= pos['tp']
                    cont = (big_trend > 0 and slope > 0)
                    if tp_hit and cont:
                        pos['tp'] = max(pos['tp'], op + atr * (p.tp_atr * p.tp_expand_factor))
                        pos['sl'] = max(pos['sl'], op - atr * p.sl_lock_factor)
                    elif tp_hit:
                        reason, ep = 'tp', pos['tp']
                if reason is None:
                    pos['sl'] = max(pos['sl'], op - atr * p.trail_factor)
                if reason is None and sig == -1:
                    reason, ep = 'flip', op
            else:
                if hi >= pos['sl']:
                    reason, ep = 'sl', pos['sl']
                else:
                    tp_hit = lo <= pos['tp']
                    cont = (big_trend < 0 and slope < 0)
                    if tp_hit and cont:
                        pos['tp'] = min(pos['tp'], op - atr * (p.tp_atr * p.tp_expand_factor))
                        pos['sl'] = min(pos['sl'], op + atr * p.sl_lock_factor)
                    elif tp_hit:
                        reason, ep = 'tp', pos['tp']
                if reason is None:
                    pos['sl'] = min(pos['sl'], op + atr * p.trail_factor)
                if reason is None and sig == 1:
                    reason, ep = 'flip', op

            if reason is None and pos['hold'] >= p.max_hold:
                reason, ep = 'timeout', op

            if reason is not None:
                pnl = (ep - pos['entry']) * pos['units'] if pos['side'] == 'long' else (pos['entry'] - ep) * pos['units']
                bal += pnl; peak = max(peak, bal)
                dd = (peak - bal) / peak if peak > 0 else 0.0
                max_dd = max(max_dd, dd)
                trades.append({
                    'entry_time': str(pos['time']), 'exit_time': str(df['time'].iloc[i]),
                    'side': pos['side'], 'entry': float(pos['entry']), 'exit': float(ep),
                    'pnl': float(pnl), 'reason': reason,
                    'long_score': float(comp.get('l', 0.0)), 'short_score': float(comp.get('s', 0.0)),
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

        dist = abs(op - sl)
        if dist <= 1e-12:
            continue
        units = (bal * 0.01) / dist
        if units <= 0:
            continue

        pos = {'side': side, 'entry': op, 'sl': sl, 'tp': tp, 'units': units, 'time': df['time'].iloc[i], 'hold': 0}

    if pos is not None:
        ep = float(df['close'].iloc[-1])
        pnl = (ep - pos['entry']) * pos['units'] if pos['side'] == 'long' else (pos['entry'] - ep) * pos['units']
        bal += pnl
        trades.append({
            'entry_time': str(pos['time']), 'exit_time': str(df['time'].iloc[-1]),
            'side': pos['side'], 'entry': float(pos['entry']), 'exit': float(ep), 'pnl': float(pnl), 'reason': 'final',
        })

    wins = sum(1 for t in trades if t['pnl'] > 0)
    losses = sum(1 for t in trades if t['pnl'] < 0)
    gp = sum(t['pnl'] for t in trades if t['pnl'] > 0)
    gl = -sum(t['pnl'] for t in trades if t['pnl'] < 0)
    pf = gp / gl if gl > 1e-12 else (999.0 if gp > 0 else 0.0)

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
        'net_pnl': float(bal - 1000.0),
        'final_balance': float(bal),
        'max_dd_pct': float(max_dd * 100.0),
        'profit_factor': float(pf),
    }


def main():
    ap = argparse.ArgumentParser(description='Run Survival_v7 backtest (self-contained fusion)')
    ap.add_argument('--file', type=str, default=str(FILE), help='single input file path (.xlsx/.csv)')
    args = ap.parse_args()

    df = indicators(parse_data(Path(args.file)))
    rs = run_backtest(df)
    print('=== Backtest Summary (Survival_v7 self-contained fusion) ===')
    print(f'Source      : {args.file}')
    print(f'Trades      : {len(rs["trades"])}')
    print(f'Win/Loss    : {rs["wins"]}/{rs["losses"]} ({rs["win_rate"]:.2f}%)')
    print(f'Net PnL     : {rs["net_pnl"]:.2f}')
    print(f'Final Bal   : {rs["final_balance"]:.2f}')
    print(f'Max DD      : {rs["max_dd_pct"]:.2f}%')
    print(f'ProfitFactor: {rs["profit_factor"]:.4f}')


if __name__ == '__main__':
    main()
