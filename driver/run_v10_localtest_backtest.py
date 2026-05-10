#!/usr/bin/env python3
from __future__ import annotations

"""Offline backtest adapter for XAUUSD_Survival_Orchestrator_v10_localtest.mq5.

This script mirrors the MQ5-local routing layer and does not call the local
HTTP scheduler API. The API server is for forward/simulated chart execution;
this file is for historical TestData batch validation.
"""

import argparse
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TESTDATA_DIR = ROOT / 'TestData'
DRIVER_DIR = TESTDATA_DIR / 'driver'

if str(DRIVER_DIR) not in sys.path:
    sys.path.insert(0, str(DRIVER_DIR))

def _load_base():
    # Prefer legacy full-feature v7 adapter used by orchestrator logic.
    candidates = [
        ROOT.parent / 'TestData' / 'driver' / 'run_survival_v7_backtest.py',
        DRIVER_DIR / 'run_survival_v7_backtest.py',
        ROOT / 'driver' / 'run_survival_v7_backtest.py',
    ]
    for p in candidates:
        if p.exists():
            spec = importlib.util.spec_from_file_location('orchestrator_v10_localtest_base', str(p))
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return mod
    raise FileNotFoundError('run_survival_v7_backtest.py not found for orchestrator base')


base = _load_base()


FILE = TESTDATA_DIR / 'Week' / 'Week_06_20260504_20260510.csv'

parse_data = base.parse_data
indicators = base.indicators

REGIME_NEUTRAL = 0
REGIME_AI_CHIP = 1
REGIME_GEO_OIL = 2
REGIME_DEF_USD = 3

PLAN_OBSERVE_ONLY = 0
PLAN_STRUCT_V4 = 1
PLAN_CONSERVATIVE_V5 = 2
PLAN_ADVANCED_V6 = 3
PLAN_FUSION_V7 = 4
PLAN_PYRAMID_TREND_V8_SAFE = 5
PLAN_PROFIT_V91_P1 = 6
PLAN_BALANCED_V91_P2 = 7
PLAN_PROFIT_V91_P3 = 8

CIRCUIT_NORMAL = 0
CIRCUIT_REDUCE = 1
CIRCUIT_FREEZE = 2

PLAN_NAMES = {
    PLAN_OBSERVE_ONLY: 'OBSERVE_ONLY',
    PLAN_STRUCT_V4: 'v4',
    PLAN_CONSERVATIVE_V5: 'v5',
    PLAN_ADVANCED_V6: 'v6',
    PLAN_FUSION_V7: 'v7',
    PLAN_PYRAMID_TREND_V8_SAFE: 'v8_safe',
    PLAN_PROFIT_V91_P1: 'v91_P1',
    PLAN_BALANCED_V91_P2: 'v91_P2',
    PLAN_PROFIT_V91_P3: 'v91_P3',
}

PLAN_NAME_TO_ID = {v: k for k, v in PLAN_NAMES.items()}
PLAN_NAME_TO_ID.update({
    'auto': -1,
    'AUTO': -1,
    'observe': PLAN_OBSERVE_ONLY,
    'v8': PLAN_PYRAMID_TREND_V8_SAFE,
    'P1': PLAN_PROFIT_V91_P1,
    'P2': PLAN_BALANCED_V91_P2,
    'P3': PLAN_PROFIT_V91_P3,
})

PLAN_PARAMS = {
    PLAN_STRUCT_V4: {
        'risk_mult': 0.65,
        'max_hold_bars': 73,
        'fusion_gate': False,
        'advanced_gate': False,
        'regime_gate': False,
    },
    PLAN_CONSERVATIVE_V5: {
        'risk_mult': 0.50,
        'max_hold_bars': 73,
        'fusion_gate': False,
        'advanced_gate': False,
        'regime_gate': False,
    },
    PLAN_ADVANCED_V6: {
        'risk_mult': 0.80,
        'max_hold_bars': 107,
        'fusion_gate': False,
        'advanced_gate': True,
        'regime_gate': False,
    },
    PLAN_FUSION_V7: {
        'risk_mult': 1.00,
        'max_hold_bars': 73,
        'fusion_gate': True,
        'advanced_gate': False,
        'regime_gate': False,
        'fusion_long_th': 1.1486930794579135,
        'fusion_short_th': 1.16052699635634,
    },
    PLAN_PYRAMID_TREND_V8_SAFE: {
        'risk_mult': 1.15,
        'max_hold_bars': 123,
        'fusion_gate': True,
        'advanced_gate': False,
        'regime_gate': False,
        'fusion_long_th': 1.3294839619284293,
        'fusion_short_th': 1.3294839619284293,
    },
    PLAN_PROFIT_V91_P1: {
        'max_hold_bars': 73,
        'fusion_gate': True,
        'advanced_gate': False,
        'regime_gate': True,
        'fusion_long_th': 1.10,
        'fusion_short_th': 1.10,
        'confirm_bars': 1,
        'ai_mult': 1.15,
        'geo_mult': 1.15,
        'def_mult': 0.90,
        'neu_mult': 1.20,
        'atr_pct_geo': 0.0018,
        'boll_geo_angle': 100.0,
        'ai_trend_power': 52.0,
    },
    PLAN_BALANCED_V91_P2: {
        'max_hold_bars': 96,
        'fusion_gate': True,
        'advanced_gate': False,
        'regime_gate': True,
        'fusion_long_th': 1.10,
        'fusion_short_th': 1.10,
        'confirm_bars': 1,
        'ai_mult': 1.20,
        'geo_mult': 1.00,
        'def_mult': 0.65,
        'neu_mult': 1.10,
        'atr_pct_geo': 0.0018,
        'boll_geo_angle': 100.0,
        'ai_trend_power': 48.0,
    },
    PLAN_PROFIT_V91_P3: {
        'max_hold_bars': 55,
        'fusion_gate': True,
        'advanced_gate': False,
        'regime_gate': True,
        'fusion_long_th': 1.10,
        'fusion_short_th': 1.10,
        'confirm_bars': 1,
        'ai_mult': 1.25,
        'geo_mult': 1.20,
        'def_mult': 0.55,
        'neu_mult': 1.10,
        'atr_pct_geo': 0.0018,
        'boll_geo_angle': 140.0,
        'ai_trend_power': 52.0,
    },
}


def _apply_base_profile():
    base.Struct_Relaxed_Mode = False
    base.Enable_Stats_Gate = False
    base.Allow_Struct_Up = True
    base.Allow_Struct_Down = True
    base.Allow_Struct_XGold = True
    base.Allow_Struct_XDead = True
    base.Require_Big_Trend_Align = False
    base.Block_Cliff_Down_Entry = False
    base.Use_Dynamic_Risk_Scale = True
    base.Enable_Trend_Tp_Recalc = True
    base.Enable_Weak_Momentum_Trail = True
    base.Tp_Recalc_Trigger_Atr = 0.80
    base.Tp_Expand_Factor = 1.3913402871157283
    base.Trail_Lock_Atr = 1.090217833327329
    base.Enable_Advanced_Gate = False
    base.Enable_Fusion_Gate = True


def plan_name(plan_id: int) -> str:
    return PLAN_NAMES.get(plan_id, 'UNKNOWN')


def _plan_params(plan_id: int) -> dict:
    return PLAN_PARAMS.get(plan_id, PLAN_PARAMS[PLAN_BALANCED_V91_P2])


def _regime_risk_multiplier(regime: int, plan_id: int) -> float:
    p = _plan_params(plan_id)
    if plan_id in (PLAN_STRUCT_V4, PLAN_CONSERVATIVE_V5, PLAN_ADVANCED_V6, PLAN_FUSION_V7, PLAN_PYRAMID_TREND_V8_SAFE):
        return float(p.get('risk_mult', 1.0))
    if regime == REGIME_AI_CHIP:
        return float(p['ai_mult'])
    if regime == REGIME_GEO_OIL:
        return float(p['geo_mult'])
    if regime == REGIME_DEF_USD:
        return float(p['def_mult'])
    return float(p['neu_mult'])


def _detect_factor_regime_local(atr_now, close_now, big_angle, mid_angle, line_status, momentum, boll_status, boll_angle, plan_id):
    if (not atr_now) or atr_now <= 0 or close_now <= 0:
        return REGIME_NEUTRAL

    p = _plan_params(plan_id)
    atr_pct = atr_now / close_now
    trend_power = abs(big_angle) + abs(mid_angle)
    atr_pct_geo = float(p.get('atr_pct_geo', 0.0020))
    boll_geo_angle = float(p.get('boll_geo_angle', 120.0))
    ai_trend_power = float(p.get('ai_trend_power', 44.0))

    ai_chip = (
        trend_power >= ai_trend_power
        and line_status == base.LINE_STATUS_SMOOTH
        and momentum in (base.MOMENTUM_STRONG_CONTINUE, base.MOMENTUM_WEAK_CONTINUE)
        and boll_status != base.BOLLING_NORMAL_CONTRACT
    )

    geo_oil = (
        abs(boll_angle) >= boll_geo_angle
        and boll_status in (base.BOLLING_CLIFF_UP, base.BOLLING_CLIFF_DOWN)
        and atr_pct >= atr_pct_geo
    )

    def_usd = (
        (line_status == base.LINE_STATUS_SHAKY and momentum in (base.MOMENTUM_REVERSAL, base.MOMENTUM_UNCLEAR))
        or (boll_status == base.BOLLING_NORMAL_CONTRACT and atr_pct < atr_pct_geo * 0.90)
    )

    if geo_oil:
        return REGIME_GEO_OIL
    if ai_chip:
        return REGIME_AI_CHIP
    if def_usd:
        return REGIME_DEF_USD
    return REGIME_NEUTRAL


def _allow_entry_by_regime(is_short, struct_type, regime, line_status, momentum, plan_id):
    if not _plan_params(plan_id).get('regime_gate', False):
        return True
    if regime == REGIME_DEF_USD:
        if is_short:
            return False
        if struct_type in (0, 3):
            return False
        if line_status == base.LINE_STATUS_SHAKY and momentum != base.MOMENTUM_STRONG_CONTINUE:
            return False
    if regime == REGIME_GEO_OIL and momentum == base.MOMENTUM_UNCLEAR:
        return False
    return True


def _is_high_vol_trend(atr_now, close_now, big_ang, mid_ang, line_status, momentum):
    if atr_now <= 0 or close_now <= 0:
        return False
    atr_pct = atr_now / close_now
    trend_power = abs(big_ang) + abs(mid_ang)
    return (
        atr_pct >= 0.0018
        and trend_power >= 48.0
        and line_status == base.LINE_STATUS_SMOOTH
        and momentum in (base.MOMENTUM_STRONG_CONTINUE, base.MOMENTUM_WEAK_CONTINUE)
    )


def _is_low_signal_chop(atr_now, close_now, boll_angle, boll_status, line_status):
    if atr_now <= 0 or close_now <= 0:
        return False
    atr_pct = atr_now / close_now
    return (
        atr_pct <= 0.0014
        and abs(boll_angle) <= 80.0
        and (boll_status == base.BOLLING_NORMAL_CONTRACT or line_status == base.LINE_STATUS_SHAKY)
    )


def _route_base_plan(override: int, allow_v8: bool, atr_now, close_now, big_ang, mid_ang, line_status, momentum, boll_status, boll_angle, regime):
    if 0 <= override <= 8:
        return override
    if _is_low_signal_chop(atr_now, close_now, boll_angle, boll_status, line_status):
        return PLAN_STRUCT_V4
    if allow_v8 and _is_high_vol_trend(atr_now, close_now, big_ang, mid_ang, line_status, momentum):
        return PLAN_PYRAMID_TREND_V8_SAFE
    if regime == REGIME_AI_CHIP:
        return PLAN_FUSION_V7
    if regime == REGIME_GEO_OIL:
        return PLAN_BALANCED_V91_P2
    if regime == REGIME_DEF_USD:
        return PLAN_PROFIT_V91_P1
    return PLAN_CONSERVATIVE_V5


def _allow_entry_by_advanced(plan_id, is_short, arr, idx, boll_ang):
    if not _plan_params(plan_id).get('advanced_gate', False):
        return True
    return base.allow_entry_by_advanced_gate(
        is_short, arr['open'], arr['high'], arr['low'], arr['close'], arr['ema5'], arr['ema20'], arr['up'], arr['down'], idx, boll_ang
    )


def _allow_entry_by_fusion(plan_id, is_short, arr, idx, boll_ang):
    p = _plan_params(plan_id)
    if not p.get('fusion_gate', False):
        return True

    old_gate = base.Enable_Fusion_Gate
    old_long = base.Fusion_Long_Threshold
    old_short = base.Fusion_Short_Threshold
    try:
        base.Enable_Fusion_Gate = True
        base.Fusion_Long_Threshold = float(p.get('fusion_long_th', 1.10))
        base.Fusion_Short_Threshold = float(p.get('fusion_short_th', 1.10))
        return base.allow_entry_by_fusion_gate(
            is_short, arr['open'], arr['high'], arr['low'], arr['close'], arr['ema5'], arr['ema20'], arr['up'], arr['down'], idx, boll_ang
        )
    finally:
        base.Enable_Fusion_Gate = old_gate
        base.Fusion_Long_Threshold = old_long
        base.Fusion_Short_Threshold = old_short


def run_backtest(df, plan_override=-1, allow_v8=True):
    _apply_base_profile()

    balance = 1000.0
    peak = balance
    max_dd = 0.0
    consecutive_losses = 0
    circuit_state = CIRCUIT_NORMAL

    pos = None
    trades = []
    signal_counts = {'up': 0, 'down': 0, 'xgold': 0, 'xdead': 0}
    gate_pass = {'short': 0, 'long': 0}
    plan_counts = {}
    base_plan_counts = {}
    circuit_counts = {}

    arr = {k: df[k].values for k in ['open', 'high', 'low', 'close', 'ema5', 'ema20', 'up', 'mid', 'down', 'atr']}
    times = df['time'].values

    factor_regime = REGIME_NEUTRAL
    factor_regime_pending = REGIME_NEUTRAL
    factor_regime_pending_count = 0
    active_plan = PLAN_BALANCED_V91_P2

    start = max(60, base.Trend_Big_Bars + 10)
    for idx in range(start, len(df)):
        if any(base.pd.isna(arr[k][idx - 1]) for k in ['ema5', 'ema20', 'up', 'mid', 'down', 'atr']):
            continue
        if idx < 12:
            continue

        atr_now = arr['atr'][idx - 1]
        if not (atr_now and atr_now > 0):
            continue

        big_dir, big_ang = base.compute_trend(arr['close'], idx, base.Trend_Big_Bars)
        mid_dir, mid_ang = base.compute_trend(arr['close'], idx, base.Trend_Mid_Bars)
        small_dir, _small_ang = base.compute_trend(arr['close'], idx, base.Trend_Small_Bars)

        line_code = base.LINE_CODE_UP if small_dir == base.DIR_UP else (base.LINE_CODE_DOWN if small_dir == base.DIR_DOWN else None)
        line_status, _shaky = base.compute_line_status(arr['close'], idx)
        boll_status, boll_ang = base.compute_bolling_status(arr['up'], arr['mid'], arr['down'], idx)
        momentum = base.compute_momentum(big_dir, mid_dir, small_dir, boll_status, line_status)

        close_prev = arr['close'][idx - 1]
        target_regime = _detect_factor_regime_local(
            atr_now, close_prev, big_ang, mid_ang, line_status, momentum, boll_status, boll_ang, active_plan
        )
        if target_regime == factor_regime:
            factor_regime_pending = target_regime
            factor_regime_pending_count = 0
        else:
            if target_regime == factor_regime_pending:
                factor_regime_pending_count += 1
            else:
                factor_regime_pending = target_regime
                factor_regime_pending_count = 1
            if factor_regime_pending_count >= max(1, int(_plan_params(active_plan).get('confirm_bars', 1))):
                factor_regime = target_regime
                factor_regime_pending_count = 0

        base_plan = _route_base_plan(
            plan_override, allow_v8, atr_now, close_prev, big_ang, mid_ang, line_status, momentum, boll_status, boll_ang, factor_regime
        )

        dd_pct = ((peak - balance) / peak * 100.0) if peak > 0 else 0.0
        if dd_pct >= 12.0:
            circuit_state = CIRCUIT_FREEZE
            active_plan = PLAN_OBSERVE_ONLY
        elif dd_pct >= 9.0 or consecutive_losses >= 3:
            circuit_state = CIRCUIT_REDUCE
            active_plan = PLAN_CONSERVATIVE_V5
        else:
            circuit_state = CIRCUIT_NORMAL
            active_plan = base_plan

        plan_counts[plan_name(active_plan)] = plan_counts.get(plan_name(active_plan), 0) + 1
        base_plan_counts[plan_name(base_plan)] = base_plan_counts.get(plan_name(base_plan), 0) + 1
        circuit_counts[str(circuit_state)] = circuit_counts.get(str(circuit_state), 0) + 1

        xgold, xdead = base.detect_cross(arr['ema5'], arr['ema20'], idx)
        sup = base.detect_struct_up(arr['open'], arr['high'], arr['low'], arr['close'], arr['up'], idx)
        sdown = base.detect_struct_down(arr['open'], arr['high'], arr['low'], arr['close'], arr['down'], idx)
        sxg = base.detect_struct_x_gold(xgold, arr['ema5'], arr['ema20'], arr['mid'], idx)
        sxd = base.detect_struct_x_dead(xdead, arr['ema5'], arr['ema20'], arr['mid'], idx)

        signal_counts['up'] += int(sup)
        signal_counts['down'] += int(sdown)
        signal_counts['xgold'] += int(sxg)
        signal_counts['xdead'] += int(sxd)

        entry_px = arr['open'][idx]
        if pos is not None:
            pos['held_bars'] += 1

            close_reason = None
            exit_px = entry_px
            hi = arr['high'][idx - 1]
            lo = arr['low'][idx - 1]

            if pos['side'] == 'short':
                if hi >= pos['sl']:
                    close_reason = 'sl'
                    exit_px = pos['sl']
                elif lo <= pos['tp']:
                    close_reason = 'tp'
                    exit_px = pos['tp']
            else:
                if lo <= pos['sl']:
                    close_reason = 'sl'
                    exit_px = pos['sl']
                elif hi >= pos['tp']:
                    close_reason = 'tp'
                    exit_px = pos['tp']

            max_hold = int(_plan_params(pos.get('plan_id', active_plan)).get('max_hold_bars', 73))
            if close_reason is None:
                if max_hold > 0 and pos['held_bars'] >= max_hold:
                    close_reason = 'max_hold'
                elif pos['side'] == 'short' and xgold:
                    close_reason = 'xgold'
                elif pos['side'] == 'long' and xdead:
                    close_reason = 'xdead'
                elif momentum in (base.MOMENTUM_REVERSAL, base.MOMENTUM_UNCLEAR):
                    close_reason = 'momentum'

            if close_reason is not None:
                pnl = (pos['entry'] - exit_px) * pos['units'] if pos['side'] == 'short' else (exit_px - pos['entry']) * pos['units']
                balance += pnl
                consecutive_losses = consecutive_losses + 1 if pnl < 0 else 0
                trades.append({
                    'entry_time': pos['time'],
                    'exit_time': times[idx],
                    'side': pos['side'],
                    'entry': pos['entry'],
                    'exit': exit_px,
                    'pnl': pnl,
                    'reason': close_reason,
                    'plan': pos['plan'],
                })
                pos = None
                peak = max(peak, balance)
                dd = (peak - balance) / peak if peak > 0 else 0
                max_dd = max(max_dd, dd)
                continue

            pos = base.maybe_trail_position(pos, pos['side'], entry_px, atr_now, momentum, line_status, boll_status, big_dir)
            continue

        if active_plan == PLAN_OBSERVE_ONLY:
            continue

        cliff_up_combo = (boll_status == base.BOLLING_CLIFF_UP and sup and sxd)
        cliff_down_combo = (boll_status == base.BOLLING_CLIFF_DOWN and sdown and sxg)

        if line_code == base.LINE_CODE_UP:
            short_by_struct_up = sup or cliff_up_combo
            short_by_xdead = (not short_by_struct_up) and sxd
            struct_type = 0 if short_by_struct_up else 3
            if short_by_struct_up or short_by_xdead:
                pass_stats = base.allow_entry_by_stats(True, struct_type, big_dir, boll_status)
                pass_adv = _allow_entry_by_advanced(active_plan, True, arr, idx, boll_ang)
                pass_fusion = _allow_entry_by_fusion(active_plan, True, arr, idx, boll_ang)
                pass_regime = _allow_entry_by_regime(True, struct_type, factor_regime, line_status, momentum, active_plan)
                if pass_stats and pass_adv and pass_fusion and pass_regime:
                    gate_pass['short'] += 1
                    slm, tpm = base.dynamic_mult(momentum, line_status, boll_status)
                    stop_dist = atr_now * slm
                    take_dist = atr_now * tpm
                    risk_scale = base.get_risk_scale(momentum, line_status, boll_status)
                    risk_scale *= max(0.10, _regime_risk_multiplier(factor_regime, active_plan))
                    if circuit_state == CIRCUIT_REDUCE:
                        risk_scale *= 0.50
                    risk_scale = max(base.Risk_Scale_Min * 0.5, min(1.8, risk_scale))
                    risk_money = balance * base.Risk_Per_Trade * max(0.0, risk_scale)
                    units = risk_money / stop_dist if stop_dist > 0 else 0
                    if units > 0:
                        pos = {
                            'side': 'short',
                            'entry': entry_px,
                            'sl': entry_px + stop_dist,
                            'tp': entry_px - take_dist,
                            'units': units,
                            'time': times[idx],
                            'held_bars': 0,
                            'plan': plan_name(active_plan),
                            'plan_id': active_plan,
                        }
                continue

        if line_code == base.LINE_CODE_DOWN:
            long_by_struct_down = sdown or cliff_down_combo
            long_by_xgold = (not long_by_struct_down) and sxg
            struct_type = 1 if long_by_struct_down else 2
            if long_by_struct_down or long_by_xgold:
                pass_stats = base.allow_entry_by_stats(False, struct_type, big_dir, boll_status)
                pass_adv = _allow_entry_by_advanced(active_plan, False, arr, idx, boll_ang)
                pass_fusion = _allow_entry_by_fusion(active_plan, False, arr, idx, boll_ang)
                pass_regime = _allow_entry_by_regime(False, struct_type, factor_regime, line_status, momentum, active_plan)
                if pass_stats and pass_adv and pass_fusion and pass_regime:
                    gate_pass['long'] += 1
                    slm, tpm = base.dynamic_mult(momentum, line_status, boll_status)
                    stop_dist = atr_now * slm
                    take_dist = atr_now * tpm
                    risk_scale = base.get_risk_scale(momentum, line_status, boll_status)
                    risk_scale *= max(0.10, _regime_risk_multiplier(factor_regime, active_plan))
                    if circuit_state == CIRCUIT_REDUCE:
                        risk_scale *= 0.50
                    risk_scale = max(base.Risk_Scale_Min * 0.5, min(1.8, risk_scale))
                    risk_money = balance * base.Risk_Per_Trade * max(0.0, risk_scale)
                    units = risk_money / stop_dist if stop_dist > 0 else 0
                    if units > 0:
                        pos = {
                            'side': 'long',
                            'entry': entry_px,
                            'sl': entry_px - stop_dist,
                            'tp': entry_px + take_dist,
                            'units': units,
                            'time': times[idx],
                            'held_bars': 0,
                            'plan': plan_name(active_plan),
                            'plan_id': active_plan,
                        }
                continue

    if pos is not None:
        exit_px = arr['close'][-1]
        pnl = (pos['entry'] - exit_px) * pos['units'] if pos['side'] == 'short' else (exit_px - pos['entry']) * pos['units']
        balance += pnl
        trades.append({
            'entry_time': pos['time'],
            'exit_time': times[-1],
            'side': pos['side'],
            'entry': pos['entry'],
            'exit': exit_px,
            'pnl': pnl,
            'reason': 'final',
            'plan': pos['plan'],
        })

    wins = sum(1 for t in trades if t['pnl'] > 0)
    losses = sum(1 for t in trades if t['pnl'] < 0)
    gross_profit = sum(t['pnl'] for t in trades if t['pnl'] > 0)
    gross_loss = -sum(t['pnl'] for t in trades if t['pnl'] < 0)
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
    win_rate = wins / len(trades) * 100 if trades else 0.0
    plan_trade_counts = {}
    for t in trades:
        plan_trade_counts[t['plan']] = plan_trade_counts.get(t['plan'], 0) + 1

    return {
        'bars': len(df),
        'start': str(df['time'].iloc[0]),
        'end': str(df['time'].iloc[-1]),
        'signals': signal_counts,
        'gate_pass': gate_pass,
        'trades': trades,
        'wins': wins,
        'losses': losses,
        'win_rate': win_rate,
        'final_balance': balance,
        'net_pnl': balance - 1000.0,
        'max_dd_pct': max_dd * 100,
        'profit_factor': profit_factor,
        'plan_bar_counts': plan_counts,
        'base_plan_bar_counts': base_plan_counts,
        'plan_trade_counts': plan_trade_counts,
        'circuit_counts': circuit_counts,
    }


def _collect_files(mode: str):
    if mode == 'year':
        return sorted((TESTDATA_DIR / 'Year').glob('*.csv'))
    if mode == 'month':
        return sorted((TESTDATA_DIR / 'Month').glob('*.csv'))
    if mode == 'week':
        return sorted((TESTDATA_DIR / 'Week').glob('*.csv'))
    if mode == 'year_month':
        return sorted((TESTDATA_DIR / 'Year').glob('*.csv')) + sorted((TESTDATA_DIR / 'Month').glob('*.csv'))
    if mode == 'all':
        return (
            sorted((TESTDATA_DIR / 'Year').glob('*.csv'))
            + sorted((TESTDATA_DIR / 'Month').glob('*.csv'))
            + sorted((TESTDATA_DIR / 'Week').glob('*.csv'))
        )
    return []


def _run_batch(files, plan_override, allow_v8):
    rows = []
    for fp in files:
        df = indicators(parse_data(fp))
        rs = run_backtest(df, plan_override=plan_override, allow_v8=allow_v8)
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
            'plan_bar_counts': json.dumps(rs['plan_bar_counts'], ensure_ascii=False),
            'plan_trade_counts': json.dumps(rs['plan_trade_counts'], ensure_ascii=False),
            'circuit_counts': json.dumps(rs['circuit_counts'], ensure_ascii=False),
        })
    return rows


def _parse_plan_override(value: str) -> int:
    if value is None:
        return -1
    try:
        return int(value)
    except ValueError:
        pass
    if value not in PLAN_NAME_TO_ID:
        raise argparse.ArgumentTypeError(f'unknown plan override: {value}')
    return int(PLAN_NAME_TO_ID[value])


def main():
    ap = argparse.ArgumentParser(description='Run XAUUSD_Survival_Orchestrator_v10 offline backtest')
    ap.add_argument('--file', type=str, default=str(FILE), help='single input file path (.xlsx/.csv)')
    ap.add_argument('--plan-override', type=_parse_plan_override, default=-1, help='-1/auto or one of v4,v5,v6,v7,v8,v91_P1,v91_P2,v91_P3')
    ap.add_argument('--disable-v8', action='store_true', help='disable v8_safe routing in auto mode')
    ap.add_argument('--batch', type=str, default='single', choices=['single', 'year', 'month', 'week', 'year_month', 'all'], help='batch mode')
    ap.add_argument('--out-dir', type=str, default=str(Path(__file__).resolve().parent), help='output folder for batch csv/json')
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    allow_v8 = not args.disable_v8

    if args.batch == 'single':
        src = Path(args.file)
        df = indicators(parse_data(src))
        result = run_backtest(df, plan_override=args.plan_override, allow_v8=allow_v8)
        print('=== Backtest Summary (Orchestrator_v10 / offline replay) ===')
        print(f'Source      : {src}')
        print(f'PlanOverride: {args.plan_override} ({plan_name(args.plan_override) if args.plan_override >= 0 else "AUTO"})')
        print(f'Data bars   : {result["bars"]}')
        print(f'Range       : {result["start"]} -> {result["end"]}')
        print(f'Trades      : {len(result["trades"])}')
        print(f'Win/Loss    : {result["wins"]}/{result["losses"]} ({result["win_rate"]:.2f}%)')
        print(f'Net PnL     : {result["net_pnl"]:.2f}')
        print(f'Final Bal   : {result["final_balance"]:.2f}')
        print(f'Max DD      : {result["max_dd_pct"]:.2f}%')
        print(f'ProfitFactor: {result["profit_factor"]:.4f}')
        print(f'Plan bars   : {json.dumps(result["plan_bar_counts"], ensure_ascii=False)}')
        print(f'Plan trades : {json.dumps(result["plan_trade_counts"], ensure_ascii=False)}')
        print(f'Circuit     : {json.dumps(result["circuit_counts"], ensure_ascii=False)}')
        return

    files = _collect_files(args.batch)
    rows = _run_batch(files, args.plan_override, allow_v8)
    df_out = base.pd.DataFrame(rows)

    plan_label = 'auto' if args.plan_override < 0 else plan_name(args.plan_override)
    csv_path = out_dir / f'v10_localtest_backtest_{plan_label}_{args.batch}.csv'
    json_path = out_dir / f'v10_localtest_backtest_{plan_label}_{args.batch}_summary.json'
    df_out.to_csv(csv_path, index=False, encoding='utf-8-sig')

    summary = {
        'plan_override': args.plan_override,
        'plan_label': plan_label,
        'batch': args.batch,
        'files': len(rows),
        'mean_final_balance': float(df_out['final_balance'].mean()) if len(df_out) else 0.0,
        'mean_net_pnl': float(df_out['net_pnl'].mean()) if len(df_out) else 0.0,
        'mean_win_rate': float(df_out['win_rate'].mean()) if len(df_out) else 0.0,
        'mean_max_dd_pct': float(df_out['max_dd_pct'].mean()) if len(df_out) else 0.0,
        'mean_profit_factor': float(df_out['profit_factor'].mean()) if len(df_out) else 0.0,
    }
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')

    print(f'Batch mode   : {args.batch}')
    print(f'PlanOverride : {plan_label}')
    print(f'Files        : {len(rows)}')
    print(f'Output CSV   : {csv_path}')
    print(f'Output JSON  : {json_path}')
    print(f'Mean Balance : {summary["mean_final_balance"]:.2f}')
    print(f'Mean NetPnL  : {summary["mean_net_pnl"]:.2f}')
    print(f'Mean WinRate : {summary["mean_win_rate"]:.2f}%')
    print(f'Mean MaxDD   : {summary["mean_max_dd_pct"]:.2f}%')
    print(f'Mean PF      : {summary["mean_profit_factor"]:.4f}')


if __name__ == '__main__':
    main()
