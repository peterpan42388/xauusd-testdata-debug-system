from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

import run_survival_v3_backtest as io_base

ROOT = Path('/Users/leo/Menu/py_workspace/gold')
TESTDATA_DIR = ROOT / 'TestData'
FILE = TESTDATA_DIR / 'Week' / 'Week_06_20260504_20260510.csv'
ROUND6_PY = ROOT / 'SelfUpgrade' / '06 成功信号融合最大化' / 'round6_fusion_max_research.py'
ROUND6_RESULT = ROOT / 'SelfUpgrade' / '06 成功信号融合最大化' / 'result_round6.json'

parse_data = io_base.parse_data


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f'cannot load module: {path}')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_round6 = _load_module(ROUND6_PY, 'round6_research_mod')


def indicators(df: pd.DataFrame) -> pd.DataFrame:
    return _round6.indicators(df)


def _load_cfg():
    obj = json.loads(ROUND6_RESULT.read_text(encoding='utf-8'))
    return _round6.FusionParams(**obj['best_params'])


def run_backtest(df: pd.DataFrame):
    p = _load_cfg()

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
        sig, comp = _round6.fusion_signal(df, i, p)

        big_trend = np.sign(float(df['close'].iloc[i - 1] - df['close'].iloc[max(0, i - 51)]))
        slope = float(df['ema_spread_slope'].iloc[i - 1])

        if pos is not None:
            pos['hold'] += 1
            hi = float(df['high'].iloc[i - 1])
            lo = float(df['low'].iloc[i - 1])
            reason = None
            ep = op

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
                    'long_score': float(comp.get('l', 0.0)),
                    'short_score': float(comp.get('s', 0.0)),
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
    ap = argparse.ArgumentParser(description='Run Survival_v7 research-replay backtest (/06 融合最大化口径)')
    ap.add_argument('--file', type=str, default=str(FILE), help='single input file path (.xlsx/.csv)')
    ap.add_argument('--batch', type=str, default='single', choices=['single', 'year', 'month', 'year_month'])
    ap.add_argument('--out-dir', type=str, default=str(Path(__file__).resolve().parent))
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.batch == 'single':
        df = indicators(parse_data(Path(args.file)))
        rs = run_backtest(df)
        print('=== Backtest Summary (Survival_v7 / Round6 research replay) ===')
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
    csv_path = out_dir / f'v7_backtest_{args.batch}.csv'
    json_path = out_dir / f'v7_backtest_{args.batch}_summary.json'
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
