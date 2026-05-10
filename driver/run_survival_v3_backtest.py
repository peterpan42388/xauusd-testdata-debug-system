"""v3 baseline replay.

Tag: research-replay/baseline-v3-self
Meaning: v3 is treated as the baseline reference logic itself (no external round result file).
"""

import math
import pandas as pd
from pathlib import Path
import argparse

FILE = Path('/Users/leo/Menu/py_workspace/gold/TestData/XAUUSDM5-5.1-5.xlsx')
SHEET = 'XAUUSDM5'

Bollinger_Period = 20
Bollinger_Deviation = 2.0
EMA_Fast = 5
EMA_Slow = 20
Trend_Big_Bars = 50
Trend_Mid_Bars = 25
Trend_Small_Bars = 10
ATR_Period = 14
Risk_Per_Trade = 0.01
Struct_Relaxed_Mode = False
POINT = 1e-5

MOMENTUM_STRONG_CONTINUE = 0
MOMENTUM_WEAK_CONTINUE = 1
MOMENTUM_REVERSAL = 2
MOMENTUM_UNCLEAR = 3

BOLLING_NORMAL_EXPAND = 0
BOLLING_NORMAL_CONTRACT = 1
BOLLING_CLIFF_UP = 2
BOLLING_CLIFF_DOWN = 3

LINE_STATUS_SMOOTH = 0
LINE_STATUS_SHAKY = 1

LINE_CODE_UP = 0
LINE_CODE_DOWN = 1

DIR_DOWN = -1
DIR_FLAT = 0
DIR_UP = 1


def parse_data(path: Path):
    path = Path(path)

    def _normalize_from_parts(parts_df: pd.DataFrame):
        rows = []
        for row in parts_df.itertuples(index=False):
            vals = [str(x).strip() for x in row]
            if len(vals) < 6:
                continue
            dt, o, h, l, c, v = vals[:6]
            try:
                rows.append((pd.to_datetime(dt), float(o), float(h), float(l), float(c), float(v)))
            except Exception:
                continue
        out = pd.DataFrame(rows, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        out.sort_values('time', inplace=True)
        out.reset_index(drop=True, inplace=True)
        return out

    if path.suffix.lower() == '.csv':
        # MT5 CSV 常见为 UTF-16LE 无表头，兼容 UTF-8/带表头
        raw = None
        for enc in ('utf-16', 'utf-8-sig', 'utf-8'):
            try:
                raw = pd.read_csv(path, header=None, encoding=enc)
                break
            except Exception:
                raw = None
        if raw is None:
            raise RuntimeError(f'无法读取CSV: {path}')

        # 1列时按逗号切分；多列时直接取前6列
        if raw.shape[1] == 1:
            col = raw.iloc[:, 0].astype(str)
            parts = col.str.split(',', expand=True)
            return _normalize_from_parts(parts.iloc[:, :6])

        # 若第一行为表头字符串（如 <DATE>,<TIME> ...），跳过
        first = [str(x).strip().lower() for x in raw.iloc[0].tolist()[:2]]
        if any('date' in x or 'time' in x for x in first):
            raw = raw.iloc[1:].reset_index(drop=True)
        return _normalize_from_parts(raw.iloc[:, :6])

    # Excel 兼容旧格式（单列逗号串）
    raw = pd.read_excel(path, sheet_name=SHEET, header=None)
    col = raw.iloc[:, 0].astype(str)
    parts = col.str.split(',', expand=True)
    return _normalize_from_parts(parts.iloc[:, :6])


def indicators(df: pd.DataFrame):
    c = df['close']
    df['ema5'] = c.ewm(span=EMA_Fast, adjust=False).mean()
    df['ema20'] = c.ewm(span=EMA_Slow, adjust=False).mean()

    mid = c.rolling(Bollinger_Period).mean()
    std = c.rolling(Bollinger_Period).std(ddof=0)
    df['mid'] = mid
    df['up'] = mid + Bollinger_Deviation * std
    df['down'] = mid - Bollinger_Deviation * std

    prev_close = c.shift(1)
    tr = pd.concat([
        (df['high'] - df['low']).abs(),
        (df['high'] - prev_close).abs(),
        (df['low'] - prev_close).abs(),
    ], axis=1).max(axis=1)
    df['atr'] = tr.rolling(ATR_Period).mean()

    return df


def sign_dir(x: float):
    if x > 0: return DIR_UP
    if x < 0: return DIR_DOWN
    return DIR_FLAT


def to_deg(rad):
    return rad * 180.0 / math.pi


def compute_trend(close, idx, bars):
    y = close[idx-1] - close[idx-bars]
    x = bars * POINT * 10.0
    angle = to_deg(math.atan2(y, x))
    return sign_dir(y), angle


def compute_line_status(close, idx):
    n = Trend_Small_Bars
    # 与EA一致: 取最近10根已收盘K线，每3条均值形成折线
    # 对应 bars idx-n .. idx-1
    vals = close[idx-n:idx]
    ma3 = []
    for i in range(n-2):
        ma3.append((vals[i] + vals[i+1] + vals[i+2]) / 3.0)

    over30 = 0
    max_abs = 0.0
    for j in range(len(ma3)-1):
        dy = ma3[j+1] - ma3[j]
        dx = POINT * 10.0
        a = abs(to_deg(math.atan2(dy, dx)))
        if a > 30.0:
            over30 += 1
        max_abs = max(max_abs, a)

    line_status = LINE_STATUS_SHAKY if over30 >= 2 else LINE_STATUS_SMOOTH
    return line_status, max_abs


def compute_bolling_status(up, mid, down, idx):
    width_now = up[idx-1] - down[idx-1]
    width_prev = up[idx-2] - down[idx-2]
    width_delta = width_now - width_prev
    mid_delta = mid[idx-1] - mid[idx-2]
    angle = to_deg(math.atan2(mid_delta, width_delta if width_delta != 0 else 1e-7))

    expand_right = width_delta > 0
    expand_left = width_delta < 0

    if expand_right and angle > 90.0:
        status = BOLLING_CLIFF_UP
    elif expand_left and angle < -90.0:
        status = BOLLING_CLIFF_DOWN
    else:
        status = BOLLING_NORMAL_EXPAND if width_delta >= 0 else BOLLING_NORMAL_CONTRACT
    return status, angle


def detect_struct_up(open_, high, low, close, up, idx):
    l, m, r = idx-3, idx-2, idx-1
    k_line_top_m = high[m]
    k_line_top_l = high[l]
    k_line_top_r = high[r]
    k_line_price_down_r = min(open_[r], close[r])
    k_line_bottom_r = low[r]
    c1 = k_line_top_m > up[m]
    c2 = k_line_top_m > k_line_top_l and k_line_top_m > k_line_top_r
    c3_strict = k_line_price_down_r < low[l]
    c3_relaxed = k_line_bottom_r < low[l]
    c3 = c3_strict or (Struct_Relaxed_Mode and c3_relaxed)
    return c1 and c2 and c3


def detect_struct_down(open_, high, low, close, down, idx):
    l, m, r = idx-3, idx-2, idx-1
    k_line_bottom_m = low[m]
    k_line_bottom_l = low[l]
    k_line_bottom_r = low[r]
    k_line_price_up_r = max(open_[r], close[r])
    k_line_top_r = high[r]
    k_line_price_up_m = max(open_[m], close[m])
    c1 = k_line_bottom_m < down[m]
    c2 = k_line_bottom_m < k_line_bottom_l and k_line_bottom_m < k_line_bottom_r
    c3_strict = k_line_price_up_r > high[m]
    c3_relaxed = (k_line_top_r > high[m]) or (k_line_price_up_r > k_line_price_up_m)
    c3 = c3_strict or (Struct_Relaxed_Mode and c3_relaxed)
    return c1 and c2 and c3


def detect_cross(ema5, ema20, idx):
    xgold = ema5[idx-2] <= ema20[idx-2] and ema5[idx-1] > ema20[idx-1]
    xdead = ema5[idx-2] >= ema20[idx-2] and ema5[idx-1] < ema20[idx-1]
    return xgold, xdead


def detect_struct_x_gold(xgold, ema5, ema20, mid, idx):
    if not xgold:
        return False
    cross = (ema5[idx-1] + ema20[idx-1]) / 2.0
    return cross > mid[idx-1]


def detect_struct_x_dead(xdead, ema5, ema20, mid, idx):
    if not xdead:
        return False
    cross = (ema5[idx-1] + ema20[idx-1]) / 2.0
    return cross < mid[idx-1]


def compute_momentum(big_dir, mid_dir, small_dir, bolling_status, line_status):
    up = sum([big_dir == DIR_UP, mid_dir == DIR_UP, small_dir == DIR_UP])
    down = sum([big_dir == DIR_DOWN, mid_dir == DIR_DOWN, small_dir == DIR_DOWN])
    same = max(up, down)

    all_up = big_dir == mid_dir == small_dir == DIR_UP
    all_down = big_dir == mid_dir == small_dir == DIR_DOWN
    boll_match_up = bolling_status in (BOLLING_CLIFF_UP, BOLLING_NORMAL_EXPAND)
    boll_match_down = bolling_status in (BOLLING_CLIFF_DOWN, BOLLING_NORMAL_EXPAND)

    if ((all_up and boll_match_up and line_status == LINE_STATUS_SMOOTH) or
        (all_down and boll_match_down and line_status == LINE_STATUS_SMOOTH)):
        return MOMENTUM_STRONG_CONTINUE
    if same >= 2:
        return MOMENTUM_WEAK_CONTINUE
    if (big_dir == DIR_UP and small_dir == DIR_DOWN) or (big_dir == DIR_DOWN and small_dir == DIR_UP):
        return MOMENTUM_REVERSAL
    return MOMENTUM_UNCLEAR


def dynamic_mult(momentum, line_status, bolling_status):
    if momentum == MOMENTUM_STRONG_CONTINUE:
        sl, tp = 1.5, 4.0
    elif momentum == MOMENTUM_WEAK_CONTINUE:
        sl, tp = 1.9, 4.75
    elif momentum == MOMENTUM_REVERSAL:
        sl, tp = 2.5, 6.25
    else:
        sl, tp = 2.2, 5.5

    if line_status == LINE_STATUS_SHAKY:
        sl = min(2.5, sl + 0.2)
    if bolling_status in (BOLLING_CLIFF_UP, BOLLING_CLIFF_DOWN):
        sl = max(1.5, sl - 0.1)
    tp = max(tp, sl * 2.5)
    return sl, tp


def run_backtest(df):
    balance = 1000.0
    peak = balance
    max_dd = 0.0

    pos = None  # dict
    trades = []
    signal_counts = {'up':0, 'down':0, 'xgold':0, 'xdead':0}
    gate_pass = {'short':0, 'long':0}

    arr = {k: df[k].values for k in ['open','high','low','close','ema5','ema20','up','mid','down','atr']}
    times = df['time'].values

    start = max(60, Trend_Big_Bars + 2)
    for idx in range(start, len(df)):
        # 指标可用性
        if any(pd.isna(arr[k][idx-1]) for k in ['ema5','ema20','up','mid','down','atr']):
            continue

        atr = arr['atr'][idx-1]
        if not (atr and atr > 0):
            continue

        big_dir, big_ang = compute_trend(arr['close'], idx, Trend_Big_Bars)
        mid_dir, mid_ang = compute_trend(arr['close'], idx, Trend_Mid_Bars)
        small_dir, small_ang = compute_trend(arr['close'], idx, Trend_Small_Bars)

        line_code = LINE_CODE_UP if small_dir == DIR_UP else (LINE_CODE_DOWN if small_dir == DIR_DOWN else None)
        line_status, _ = compute_line_status(arr['close'], idx)
        boll_status, boll_ang = compute_bolling_status(arr['up'], arr['mid'], arr['down'], idx)
        xgold, xdead = detect_cross(arr['ema5'], arr['ema20'], idx)

        sup = detect_struct_up(arr['open'], arr['high'], arr['low'], arr['close'], arr['up'], idx)
        sdown = detect_struct_down(arr['open'], arr['high'], arr['low'], arr['close'], arr['down'], idx)
        sxg = detect_struct_x_gold(xgold, arr['ema5'], arr['ema20'], arr['mid'], idx)
        sxd = detect_struct_x_dead(xdead, arr['ema5'], arr['ema20'], arr['mid'], idx)

        signal_counts['up'] += int(sup)
        signal_counts['down'] += int(sdown)
        signal_counts['xgold'] += int(sxg)
        signal_counts['xdead'] += int(sxd)

        momentum = compute_momentum(big_dir, mid_dir, small_dir, boll_status, line_status)

        # 持仓管理（按bar开盘价执行）
        entry_px = arr['open'][idx]
        if pos is not None:
            close_reason = None
            exit_px = entry_px

            if pos['side'] == 'short':
                if xgold:
                    close_reason = 'xgold'
                elif momentum in (MOMENTUM_REVERSAL, MOMENTUM_UNCLEAR):
                    close_reason = 'momentum'

                # 先检查SL/TP触发（使用上一根K线high/low）
                hi = arr['high'][idx-1]
                lo = arr['low'][idx-1]
                if hi >= pos['sl']:
                    close_reason = 'sl'
                    exit_px = pos['sl']
                elif lo <= pos['tp']:
                    close_reason = 'tp'
                    exit_px = pos['tp']
            else:
                if xdead:
                    close_reason = 'xdead'
                elif momentum in (MOMENTUM_REVERSAL, MOMENTUM_UNCLEAR):
                    close_reason = 'momentum'

                hi = arr['high'][idx-1]
                lo = arr['low'][idx-1]
                if lo <= pos['sl']:
                    close_reason = 'sl'
                    exit_px = pos['sl']
                elif hi >= pos['tp']:
                    close_reason = 'tp'
                    exit_px = pos['tp']

            if close_reason is not None:
                if pos['side'] == 'short':
                    pnl = (pos['entry'] - exit_px) * pos['units']
                else:
                    pnl = (exit_px - pos['entry']) * pos['units']
                balance += pnl
                trades.append({
                    'entry_time': pos['time'], 'exit_time': times[idx], 'side': pos['side'],
                    'entry': pos['entry'], 'exit': exit_px, 'pnl': pnl, 'reason': close_reason,
                })
                pos = None
                peak = max(peak, balance)
                dd = (peak - balance) / peak if peak > 0 else 0
                max_dd = max(max_dd, dd)
                continue

            # strong continue 跟踪
            if momentum == MOMENTUM_STRONG_CONTINUE:
                slm, tpm = dynamic_mult(momentum, line_status, boll_status)
                if pos['side'] == 'short':
                    cand_sl = arr['open'][idx] + atr * slm
                    cand_tp = arr['open'][idx] - atr * tpm
                    if cand_sl < pos['sl']:
                        pos['sl'] = cand_sl
                    if cand_tp < pos['tp']:
                        pos['tp'] = cand_tp
                else:
                    cand_sl = arr['open'][idx] - atr * slm
                    cand_tp = arr['open'][idx] + atr * tpm
                    if cand_sl > pos['sl']:
                        pos['sl'] = cand_sl
                    if cand_tp > pos['tp']:
                        pos['tp'] = cand_tp

            continue

        # 准入
        cliff_up_combo = (boll_status == BOLLING_CLIFF_UP and sup and sxd)
        cliff_down_combo = (boll_status == BOLLING_CLIFF_DOWN and sdown and sxg)

        if line_code == LINE_CODE_UP and (sup or sxd or cliff_up_combo):
            gate_pass['short'] += 1
            slm, tpm = dynamic_mult(momentum, line_status, boll_status)
            stop_dist = atr * slm
            take_dist = atr * tpm
            risk_money = balance * Risk_Per_Trade
            units = risk_money / stop_dist if stop_dist > 0 else 0
            if units > 0:
                pos = {
                    'side': 'short', 'entry': entry_px, 'sl': entry_px + stop_dist,
                    'tp': entry_px - take_dist, 'units': units, 'time': times[idx]
                }
            continue

        if line_code == LINE_CODE_DOWN and (sdown or sxg or cliff_down_combo):
            gate_pass['long'] += 1
            slm, tpm = dynamic_mult(momentum, line_status, boll_status)
            stop_dist = atr * slm
            take_dist = atr * tpm
            risk_money = balance * Risk_Per_Trade
            units = risk_money / stop_dist if stop_dist > 0 else 0
            if units > 0:
                pos = {
                    'side': 'long', 'entry': entry_px, 'sl': entry_px - stop_dist,
                    'tp': entry_px + take_dist, 'units': units, 'time': times[idx]
                }
            continue

    # 最后一笔按最后收盘平仓
    if pos is not None:
        exit_px = arr['close'][-1]
        pnl = (pos['entry'] - exit_px) * pos['units'] if pos['side']=='short' else (exit_px - pos['entry']) * pos['units']
        balance += pnl
        trades.append({'entry_time': pos['time'], 'exit_time': times[-1], 'side': pos['side'], 'entry': pos['entry'], 'exit': exit_px, 'pnl': pnl, 'reason': 'final'})

    wins = sum(1 for t in trades if t['pnl'] > 0)
    losses = sum(1 for t in trades if t['pnl'] < 0)
    win_rate = wins / len(trades) * 100 if trades else 0

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
    }


def main():
    ap = argparse.ArgumentParser(description='Run Survival_v3 backtest (research-replay baseline-v3-self)')
    ap.add_argument('--file', type=str, default=str(FILE), help='input file path (.xlsx/.csv)')
    args = ap.parse_args()

    src = Path(args.file)
    df = parse_data(src)
    df = indicators(df)
    result = run_backtest(df)

    print('=== Backtest Summary (Survival_v3 logic / offline replay) ===')
    print(f"Source  : {src}")
    print(f"Data bars: {result['bars']}")
    print(f"Range   : {result['start']} -> {result['end']}")
    print(f"Signals : STRUCT_UP={result['signals']['up']}, STRUCT_DOWN={result['signals']['down']}, STRUCT_X_GOLD={result['signals']['xgold']}, STRUCT_X_DEAD={result['signals']['xdead']}")
    print(f"Gate pass attempts: short={result['gate_pass']['short']}, long={result['gate_pass']['long']}")
    print(f"Trades  : {len(result['trades'])}")
    print(f"Win/Loss: {result['wins']}/{result['losses']} ({result['win_rate']:.2f}%)")
    print(f"Net PnL : {result['net_pnl']:.2f}")
    print(f"Final Bal: {result['final_balance']:.2f}")
    print(f"Max DD  : {result['max_dd_pct']:.2f}%")

    print('\n=== Last 10 Trades ===')
    for t in result['trades'][-10:]:
        print(f"{t['entry_time']} -> {t['exit_time']} | {t['side']:5s} | entry={t['entry']:.2f} exit={t['exit']:.2f} pnl={t['pnl']:.2f} reason={t['reason']}")


if __name__ == '__main__':
    main()
