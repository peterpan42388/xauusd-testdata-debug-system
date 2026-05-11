from __future__ import annotations

"""Survival v8 backtest (完整内嵌版, 稳定趋势加仓)."""

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import numpy as np

import run_survival_v7_backtest as core

BASE_DIR = Path(__file__).resolve().parents[1]
FILE = BASE_DIR / 'Week' / 'Week_06_20260504_20260510.csv'

parse_data = core.parse_data
indicators = core.indicators


@dataclass
class V8Params:
    # fusion
    w3: float = 2.5508174962852266
    w4: float = 1.3736761786027831
    w5: float = 1.4936677551934587
    th_long: float = 2.5170650850193304
    th_short: float = 1.3294839619284293
    # exits
    sl_atr: float = 1.0973260356991068
    tp_atr: float = 7.90013935887591
    max_hold: int = 123
    tp_expand_factor: float = 1.3073819614591737
    sl_lock_factor: float = 0.7975841355348746
    trail_factor: float = 2.6887302789262204
    # pyramid
    init_risk_pct: float = 0.9762550057653149
    max_total_risk_pct: float = 1.6044065173174662
    max_layers: int = 2
    add_step_atr: float = 1.8652204404523134
    add_risk_frac1: float = 0.25535609858844627
    add_risk_decay: float = 0.7580829266348091
    add_cooldown: int = 5
    # stable gate
    stable_window: int = 16
    stable_dir_ratio: float = 0.7852094999885092
    stable_bb_angle_min: float = 113.03959493055385
    stable_spread_slope_min: float = 0.2583031962702827
    stable_curv_cap: float = 0.23420146781728782
    stable_ypos_long_min: float = 0.5363484010189243
    stable_ypos_short_max: float = 0.5156967658949874


def open_units(balance: float, risk_pct: float, entry: float, sl: float) -> float:
    dist = abs(entry - sl)
    if dist <= 1e-9:
        return 0.0
    return (balance * risk_pct / 100.0) / dist


def simulate(d, p: V8Params, enable_pyramid: bool = True, collect_details: bool = False) -> Dict:
    bal = 1000.0
    peak = bal
    max_dd = 0.0
    pos = None
    trades = []
    signals = {'long': 0, 'short': 0}
    add_events: List[Dict] = []

    for i in range(50, len(d)):
        atr = float(d['atr'].iloc[i - 1])
        if not np.isfinite(atr) or atr <= 0:
            continue

        op = float(d['open'].iloc[i])
        sig, _ = core.fusion_signal(d, i, p)

        big_trend = np.sign(float(d['close'].iloc[i - 1] - d['close'].iloc[max(0, i - 51)]))
        slope = float(d['ema_spread_slope'].iloc[i - 1])

        if pos is not None:
            pos['hold'] += 1
            hi = float(d['high'].iloc[i - 1])
            lo = float(d['low'].iloc[i - 1])
            reason = None
            ep = op

            if enable_pyramid and pos['layers'] < p.max_layers and (i - pos['last_add_i']) >= p.add_cooldown:
                favorable = (op - pos['last_add_price']) if pos['side'] == 'long' else (pos['last_add_price'] - op)
                need = atr * p.add_step_atr
                stable_ok = core.stable_for_add(d, i, p, pos['side'])
                if favorable >= need and stable_ok:
                    layer_idx = pos['layers'] + 1
                    add_risk = p.init_risk_pct * p.add_risk_frac1 * (p.add_risk_decay ** (layer_idx - 1))
                    if pos['risk_used'] + add_risk <= p.max_total_risk_pct:
                        add_units = open_units(bal, add_risk, op, pos['sl'])
                        if add_units > 0:
                            total_units = pos['units'] + add_units
                            pos['entry'] = (pos['entry'] * pos['units'] + op * add_units) / total_units
                            pos['units'] = total_units
                            pos['layers'] += 1
                            pos['risk_used'] += add_risk
                            pos['last_add_price'] = op
                            pos['last_add_i'] = i
                            if pos['side'] == 'long':
                                pos['tp'] = max(pos['tp'], pos['entry'] + atr * p.tp_atr)
                            else:
                                pos['tp'] = min(pos['tp'], pos['entry'] - atr * p.tp_atr)
                            add_events.append({
                                'time': str(d['time'].iloc[i]),
                                'side': pos['side'],
                                'layer': int(pos['layers']),
                                'add_risk_pct': float(add_risk),
                                'price': float(op),
                                'label': core.add_structure_label(d, i, pos['side'])
                            })

            if pos['side'] == 'long':
                if lo <= pos['sl']:
                    reason = 'sl'; ep = pos['sl']
                else:
                    tp_hit = hi >= pos['tp']
                    continue_trend = (big_trend > 0 and slope > 0 and core.stable_for_add(d, i, p, 'long'))
                    if tp_hit and continue_trend:
                        pos['tp'] = max(pos['tp'], op + atr * (p.tp_atr * p.tp_expand_factor))
                        pos['sl'] = max(pos['sl'], op - atr * p.sl_lock_factor)
                    elif tp_hit:
                        reason = 'tp'; ep = pos['tp']
                if reason is None:
                    pos['sl'] = max(pos['sl'], op - atr * p.trail_factor)
                if reason is None and sig == -1:
                    reason = 'flip'; ep = op
            else:
                if hi >= pos['sl']:
                    reason = 'sl'; ep = pos['sl']
                else:
                    tp_hit = lo <= pos['tp']
                    continue_trend = (big_trend < 0 and slope < 0 and core.stable_for_add(d, i, p, 'short'))
                    if tp_hit and continue_trend:
                        pos['tp'] = min(pos['tp'], op - atr * (p.tp_atr * p.tp_expand_factor))
                        pos['sl'] = min(pos['sl'], op + atr * p.sl_lock_factor)
                    elif tp_hit:
                        reason = 'tp'; ep = pos['tp']
                if reason is None:
                    pos['sl'] = min(pos['sl'], op + atr * p.trail_factor)
                if reason is None and sig == 1:
                    reason = 'flip'; ep = op

            if reason is None and pos['hold'] >= p.max_hold:
                reason = 'timeout'; ep = op

            if reason is not None:
                pnl = (ep - pos['entry']) * pos['units'] if pos['side'] == 'long' else (pos['entry'] - ep) * pos['units']
                bal += pnl
                peak = max(peak, bal)
                dd = (peak - bal) / peak if peak > 0 else 0.0
                max_dd = max(max_dd, dd)
                trades.append({
                    'entry_time': str(pos['time']),
                    'exit_time': str(d['time'].iloc[i]),
                    'side': pos['side'],
                    'entry': float(pos['entry']),
                    'exit': float(ep),
                    'pnl': float(pnl),
                    'reason': reason,
                    'layers': int(pos['layers']),
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

        units = open_units(bal, p.init_risk_pct, op, sl)
        if units <= 0:
            continue

        pos = {
            'side': side,
            'entry': op,
            'sl': sl,
            'tp': tp,
            'units': units,
            'time': d['time'].iloc[i],
            'hold': 0,
            'layers': 1,
            'risk_used': p.init_risk_pct,
            'last_add_price': op,
            'last_add_i': i,
        }

    if pos is not None:
        ep = float(d['close'].iloc[-1])
        pnl = (ep - pos['entry']) * pos['units'] if pos['side'] == 'long' else (pos['entry'] - ep) * pos['units']
        bal += pnl
        trades.append({
            'entry_time': str(pos['time']),
            'exit_time': str(d['time'].iloc[-1]),
            'side': pos['side'],
            'entry': float(pos['entry']),
            'exit': float(ep),
            'pnl': float(pnl),
            'reason': 'final',
            'layers': int(pos['layers']),
        })

    wins = sum(1 for t in trades if t['pnl'] > 0)
    losses = sum(1 for t in trades if t['pnl'] < 0)
    gp = sum(t['pnl'] for t in trades if t['pnl'] > 0)
    gl = -sum(t['pnl'] for t in trades if t['pnl'] < 0)
    pf = gp / gl if gl > 1e-9 else 999.0

    layers_gt1 = [t for t in trades if t.get('layers', 1) > 1]
    out = {
        'bars': int(len(d)),
        'start': str(d['time'].iloc[0]),
        'end': str(d['time'].iloc[-1]),
        'signals': signals,
        'gate_pass': {'short': 0, 'long': 0},
        'trades': trades if collect_details else trades,
        'wins': int(wins),
        'losses': int(losses),
        'win_rate': float(wins / len(trades) * 100.0) if trades else 0.0,
        'net_pnl': float(bal - 1000.0),
        'final_balance': float(bal),
        'max_dd_pct': float(max_dd * 100.0),
        'profit_factor': float(pf),
        'add_count': int(len(add_events)),
        'multi_layer_trades': int(len(layers_gt1)),
        'multi_layer_ratio_pct': float((len(layers_gt1) / len(trades) * 100.0) if trades else 0.0),
    }
    if collect_details:
        out['trades_detail'] = trades
        out['add_events'] = add_events
    return out


def run_backtest(df):
    p = V8Params()
    rs = simulate(df, p, enable_pyramid=True, collect_details=True)
    return {
        'bars': rs['bars'],
        'start': rs['start'],
        'end': rs['end'],
        'signals': rs['signals'],
        'gate_pass': rs.get('gate_pass', {'short': 0, 'long': 0}),
        'trades': rs.get('trades_detail', rs['trades']),
        'wins': rs['wins'],
        'losses': rs['losses'],
        'win_rate': rs['win_rate'],
        'net_pnl': rs['net_pnl'],
        'final_balance': rs['final_balance'],
        'max_dd_pct': rs['max_dd_pct'],
        'profit_factor': rs['profit_factor'],
        'add_count': rs['add_count'],
        'multi_layer_trades': rs['multi_layer_trades'],
        'multi_layer_ratio_pct': rs['multi_layer_ratio_pct'],
    }


def main():
    ap = argparse.ArgumentParser(description='Run Survival_v8 backtest (embedded)')
    ap.add_argument('--file', type=str, default=str(FILE), help='single input file path (.xlsx/.csv)')
    args = ap.parse_args()

    df = indicators(parse_data(Path(args.file)))
    rs = run_backtest(df)
    print('=== Backtest Summary (Survival_v8 embedded) ===')
    print(f'Source      : {args.file}')
    print(f'Trades      : {len(rs["trades"])}')
    print(f'Win/Loss    : {rs["wins"]}/{rs["losses"]} ({rs["win_rate"]:.2f}%)')
    print(f'Net PnL     : {rs["net_pnl"]:.2f}')
    print(f'Final Bal   : {rs["final_balance"]:.2f}')
    print(f'Max DD      : {rs["max_dd_pct"]:.2f}%')
    print(f'ProfitFactor: {rs["profit_factor"]:.4f}')


if __name__ == '__main__':
    main()
