from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

import run_survival_v3_backtest as io_base

TESTDATA_DIR = Path(__file__).resolve().parents[1]
FILE = TESTDATA_DIR / 'Week' / 'Week_06_20260504_20260510.csv'

parse_data = io_base.parse_data


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
    return d


def _state_of(d: pd.DataFrame, i: int) -> str:
    ang = float(d['bb_angle'].iloc[i])
    ypos = float(d['ypos'].iloc[i])
    spread = float(d['ema_spread'].iloc[i])
    slope = float(d['ema_spread_slope'].iloc[i])

    if ang > 95:
        a = 'A_UP'
    elif ang < -95:
        a = 'A_DN'
    else:
        a = 'A_FLAT'

    if ypos < 0.33:
        y = 'Y_LOW'
    elif ypos > 0.66:
        y = 'Y_HIGH'
    else:
        y = 'Y_MID'

    if spread > 0 and slope > 0:
        e = 'E_BULL_ACCEL'
    elif spread > 0 and slope <= 0:
        e = 'E_BULL_DECEL'
    elif spread <= 0 and slope < 0:
        e = 'E_BEAR_ACCEL'
    else:
        e = 'E_BEAR_DECEL'

    c = d['close'].iloc[i - 4:i + 1].to_numpy()
    up = int(np.sum(np.diff(c) > 0))
    dn = int(np.sum(np.diff(c) < 0))
    if up >= 3:
        k = 'K5_UP'
    elif dn >= 3:
        k = 'K5_DN'
    else:
        k = 'K5_MIX'

    return f'{a}|{y}|{e}|{k}'


def _load_round4_cfg():
    return {
        # Embedded from SelfUpgrade/04/result_round4.json
        'sl_atr': 1.2,
        'tp_atr': 5.0,
        'max_hold': 60,
        'long_states': {
            'A_DN|Y_HIGH|E_BEAR_DECEL|K5_MIX','A_DN|Y_HIGH|E_BEAR_DECEL|K5_UP','A_DN|Y_LOW|E_BEAR_ACCEL|K5_UP',
            'A_DN|Y_LOW|E_BEAR_DECEL|K5_MIX','A_DN|Y_LOW|E_BEAR_DECEL|K5_UP','A_DN|Y_MID|E_BEAR_DECEL|K5_UP',
            'A_FLAT|Y_HIGH|E_BULL_DECEL|K5_DN','A_FLAT|Y_HIGH|E_BULL_DECEL|K5_MIX','A_FLAT|Y_LOW|E_BEAR_ACCEL|K5_MIX',
            'A_FLAT|Y_LOW|E_BEAR_ACCEL|K5_UP','A_FLAT|Y_LOW|E_BEAR_DECEL|K5_DN','A_FLAT|Y_MID|E_BEAR_ACCEL|K5_DN',
            'A_FLAT|Y_MID|E_BULL_ACCEL|K5_MIX','A_UP|Y_LOW|E_BEAR_DECEL|K5_MIX','A_UP|Y_LOW|E_BULL_DECEL|K5_DN',
            'A_UP|Y_LOW|E_BULL_DECEL|K5_MIX','A_UP|Y_MID|E_BEAR_DECEL|K5_DN',
        },
        'short_states': {
            'A_DN|Y_HIGH|E_BULL_ACCEL|K5_MIX','A_DN|Y_MID|E_BULL_ACCEL|K5_MIX','A_DN|Y_MID|E_BULL_DECEL|K5_DN',
            'A_DN|Y_MID|E_BULL_DECEL|K5_MIX','A_DN|Y_MID|E_BULL_DECEL|K5_UP','A_FLAT|Y_HIGH|E_BEAR_DECEL|K5_UP',
            'A_FLAT|Y_LOW|E_BULL_DECEL|K5_DN','A_FLAT|Y_LOW|E_BULL_DECEL|K5_MIX','A_FLAT|Y_MID|E_BEAR_ACCEL|K5_MIX',
            'A_FLAT|Y_MID|E_BEAR_DECEL|K5_UP','A_FLAT|Y_MID|E_BULL_DECEL|K5_MIX','A_UP|Y_HIGH|E_BULL_ACCEL|K5_DN',
            'A_UP|Y_MID|E_BEAR_ACCEL|K5_MIX','A_UP|Y_MID|E_BULL_ACCEL|K5_DN','A_UP|Y_MID|E_BULL_DECEL|K5_UP',
        },
    }


def run_backtest(df: pd.DataFrame):
    cfg = _load_round4_cfg()

    bal = 1000.0
    peak = bal
    max_dd = 0.0
    pos = None
    trades = []
    signals = {'long': 0, 'short': 0}

    for i in range(35, len(df)):
        atr = float(df['atr'].iloc[i - 1])
        if not np.isfinite(atr) or atr <= 0:
            continue

        op = float(df['open'].iloc[i])
        st = _state_of(df, i - 1)
        sig = 1 if st in cfg['long_states'] else (-1 if st in cfg['short_states'] else 0)

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

            if reason is None and pos['hold'] >= cfg['max_hold']:
                reason, ep = 'timeout', op

            if reason is not None:
                pnl = (ep - pos['entry']) * pos['units'] if pos['side'] == 'long' else (pos['entry'] - ep) * pos['units']
                bal += pnl
                peak = max(peak, bal)
                dd = (peak - bal) / peak if peak > 0 else 0.0
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
            sl = op - atr * cfg['sl_atr']
            tp = op + atr * cfg['tp_atr']
            side = 'long'
        else:
            signals['short'] += 1
            sl = op + atr * cfg['sl_atr']
            tp = op - atr * cfg['tp_atr']
            side = 'short'

        dist = abs(op - sl)
        if dist <= 1e-12:
            continue
        units = (bal * 0.01) / dist
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
        bal += pnl
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


def _collect_files(mode: str):
    if mode == 'year':
        return sorted((TESTDATA_DIR / 'Year').glob('*.csv'))
    if mode == 'month':
        return sorted((TESTDATA_DIR / 'Month').glob('*.csv'))
    if mode == 'year_month':
        return sorted((TESTDATA_DIR / 'Year').glob('*.csv')) + sorted((TESTDATA_DIR / 'Month').glob('*.csv'))
    return []


def main():
    ap = argparse.ArgumentParser(description='Run Survival_v4 research-replay backtest (/04 状态EV口径)')
    ap.add_argument('--file', type=str, default=str(FILE), help='single input file path (.xlsx/.csv)')
    ap.add_argument('--batch', type=str, default='single', choices=['single', 'year', 'month', 'year_month'])
    ap.add_argument('--out-dir', type=str, default=str(Path(__file__).resolve().parent))
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.batch == 'single':
        df = indicators(parse_data(Path(args.file)))
        rs = run_backtest(df)
        print('=== Backtest Summary (Survival_v4 / Round4 research replay) ===')
        print(f'Source      : {args.file}')
        print(f'Trades      : {len(rs["trades"])}')
        print(f'Win/Loss    : {rs["wins"]}/{rs["losses"]} ({rs["win_rate"]:.2f}%)')
        print(f'Net PnL     : {rs["net_pnl"]:.2f}')
        print(f'Final Bal   : {rs["final_balance"]:.2f}')
        print(f'Max DD      : {rs["max_dd_pct"]:.2f}%')
        print(f'ProfitFactor: {rs["profit_factor"]:.4f}')
        return

    rows = []
    for fp in _collect_files(args.batch):
        df = indicators(parse_data(fp))
        rs = run_backtest(df)
        rows.append({
            'file': str(fp),
            'bars': rs['bars'],
            'start': rs['start'],
            'end': rs['end'],
            'trades': len(rs['trades']),
            'wins': rs['wins'],
            'losses': rs['losses'],
            'win_rate': rs['win_rate'],
            'net_pnl': rs['net_pnl'],
            'final_balance': rs['final_balance'],
            'max_dd_pct': rs['max_dd_pct'],
            'profit_factor': rs['profit_factor'],
        })

    out = pd.DataFrame(rows)
    csv_path = out_dir / f'v4_backtest_{args.batch}.csv'
    json_path = out_dir / f'v4_backtest_{args.batch}_summary.json'
    out.to_csv(csv_path, index=False, encoding='utf-8-sig')
    summary = {
        'batch': args.batch,
        'files': len(rows),
        'mean_final_balance': float(out['final_balance'].mean()) if len(out) else 0.0,
        'mean_net_pnl': float(out['net_pnl'].mean()) if len(out) else 0.0,
        'mean_win_rate': float(out['win_rate'].mean()) if len(out) else 0.0,
        'mean_max_dd_pct': float(out['max_dd_pct'].mean()) if len(out) else 0.0,
        'mean_profit_factor': float(out['profit_factor'].mean()) if len(out) else 0.0,
    }
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Output CSV   : {csv_path}')
    print(f'Output JSON  : {json_path}')


if __name__ == '__main__':
    main()
