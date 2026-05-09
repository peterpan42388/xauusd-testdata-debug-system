import math
import argparse
from pathlib import Path

import pandas as pd

FILE = Path('/Users/leo/Menu/py_workspace/gold/TestData/Week/Week_06_20260504_20260510.csv')
SHEET = 'XAUUSDM5'

# ---------- Core constants (aligned with XAUUSD_Survival_v7.mq5) ----------
Bollinger_Period = 20
Bollinger_Deviation = 2.0
EMA_Fast = 5
EMA_Slow = 20
Trend_Big_Bars = 50
Trend_Mid_Bars = 25
Trend_Small_Bars = 10
ATR_Period = 14
Risk_Per_Trade = 0.01
POINT = 1e-5

# v7 execution defaults
Struct_Relaxed_Mode = False
Enable_Stats_Gate = False
Allow_Struct_Up = True
Allow_Struct_Down = True
Allow_Struct_XGold = True
Allow_Struct_XDead = True
Require_Big_Trend_Align = False
Block_Cliff_Down_Entry = False
Max_Hold_Bars = 73

Use_Dynamic_Risk_Scale = True
Risk_Scale_Strong = 1.00
Risk_Scale_Weak = 0.75
Risk_Scale_Other = 0.55
Risk_Scale_Shaky_Factor = 0.80
Risk_Scale_Contract_Factor = 0.80
Risk_Scale_Min = 0.35

Enable_Trend_Tp_Recalc = True
Enable_Weak_Momentum_Trail = True
Tp_Recalc_Trigger_Atr = 0.80
Tp_Expand_Factor = 1.3913402871157283
Trail_Lock_Atr = 1.090217833327329

Enable_Advanced_Gate = False
Adv_Boll_Angle_Long_Min = 100.0
Adv_Boll_Angle_Short_Max = -109.0
Adv_YPos_Low = 0.23
Adv_YPos_High = 0.81
Adv_Ema5_Long_Min_Deg = 13.9
Adv_Ema20_Long_Min_Deg = 14.1
Adv_Ema5_Short_Max_Deg = -13.5
Adv_Ema20_Short_Max_Deg = -3.4
Adv_Shadow_Cap = 0.84
Adv_Body_Long_Min = 0.37
Adv_Body_Short_Max = -1.75

Enable_Fusion_Gate = True
Fusion_W3 = 1.8878837900777607
Fusion_W4 = 1.119812645681353
Fusion_W5 = 1.3057083219978902
Fusion_Long_Threshold = 1.1486930794579135
Fusion_Short_Threshold = 1.16052699635634

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

# Round4 states / Round5 edges (from v7 mq5)
FUSION_LONG_STATES = {
    'A_DN|Y_HIGH|E_BEAR_DECEL|K5_MIX', 'A_DN|Y_HIGH|E_BEAR_DECEL|K5_UP',
    'A_DN|Y_LOW|E_BEAR_ACCEL|K5_UP', 'A_DN|Y_LOW|E_BEAR_DECEL|K5_MIX',
    'A_DN|Y_LOW|E_BEAR_DECEL|K5_UP', 'A_DN|Y_MID|E_BEAR_DECEL|K5_UP',
    'A_FLAT|Y_HIGH|E_BULL_DECEL|K5_DN', 'A_FLAT|Y_HIGH|E_BULL_DECEL|K5_MIX',
    'A_FLAT|Y_LOW|E_BEAR_ACCEL|K5_MIX', 'A_FLAT|Y_LOW|E_BEAR_ACCEL|K5_UP',
    'A_FLAT|Y_LOW|E_BEAR_DECEL|K5_DN', 'A_FLAT|Y_MID|E_BEAR_ACCEL|K5_DN',
    'A_FLAT|Y_MID|E_BULL_ACCEL|K5_MIX', 'A_UP|Y_LOW|E_BEAR_DECEL|K5_MIX',
    'A_UP|Y_LOW|E_BULL_DECEL|K5_DN', 'A_UP|Y_LOW|E_BULL_DECEL|K5_MIX',
    'A_UP|Y_MID|E_BEAR_DECEL|K5_DN',
}

FUSION_SHORT_STATES = {
    'A_DN|Y_HIGH|E_BULL_ACCEL|K5_MIX', 'A_DN|Y_MID|E_BULL_ACCEL|K5_MIX',
    'A_DN|Y_MID|E_BULL_DECEL|K5_DN', 'A_DN|Y_MID|E_BULL_DECEL|K5_MIX',
    'A_DN|Y_MID|E_BULL_DECEL|K5_UP', 'A_FLAT|Y_HIGH|E_BEAR_DECEL|K5_UP',
    'A_FLAT|Y_LOW|E_BULL_DECEL|K5_DN', 'A_FLAT|Y_LOW|E_BULL_DECEL|K5_MIX',
    'A_FLAT|Y_MID|E_BEAR_ACCEL|K5_MIX', 'A_FLAT|Y_MID|E_BEAR_DECEL|K5_UP',
    'A_FLAT|Y_MID|E_BULL_DECEL|K5_MIX', 'A_UP|Y_HIGH|E_BULL_ACCEL|K5_DN',
    'A_UP|Y_MID|E_BEAR_ACCEL|K5_MIX', 'A_UP|Y_MID|E_BULL_ACCEL|K5_DN',
    'A_UP|Y_MID|E_BULL_DECEL|K5_UP',
}

FUSION_LONG_EDGES = {
    'DLNAKUP->DLNAKDN', 'DLNAKUP->DLNAKUP', 'DLNAKUP->DMNAKUP',
    'DLNBKUP->DLNBKDN', 'DMNAKUP->DLNBKUP', 'DMNAKUP->DMNBKDN',
    'DMNAKUP->FLNBKUP', 'FHPAKDN->FHPAKDN', 'FHPAKUP->UMPBKUP',
    'FHPBKDN->FHPAKUP', 'FHPBKDN->FHPBKUP', 'FLNAKDN->FMNAKUP',
    'FLNBKDN->DMNAKUP', 'FLNBKUP->FLNBKDN', 'FLNBKUP->FLNBKUP',
    'FMPBKDN->FMPBKDN', 'UHPAKUP->UMPBKDN', 'UHPBKUP->FHPAKUP',
    'UMPBKDN->FLNBKDN', 'UMPBKDN->UHPAKUP',
}

FUSION_SHORT_EDGES = {
    'DHNAKUP->DHPAKUP', 'DLNBKDN->DMNAKDN', 'DMNAKDN->DLNBKDN',
    'DMNAKDN->DMNAKDN', 'DMNAKDN->DMNAKUP', 'DMNAKDN->DMNBKDN',
    'DMNAKUP->DHNAKUP', 'DMNAKUP->DMPAKUP', 'DMNBKDN->DMNAKDN',
    'FHPAKDN->FHPAKUP', 'FHPAKUP->UHPBKDN', 'FHPBKDN->UMPBKDN',
    'FLNAKDN->DLNAKUP', 'FLNAKUP->FMNAKUP', 'FLNBKDN->DLNAKDN',
    'FLNBKUP->FLNAKUP', 'FMPBKDN->UMPBKDN', 'UHPAKUP->UHPAKUP',
    'UHPAKUP->UHPBKDN', 'UHPAKUP->UMPBKUP', 'UHPBKUP->UHPBKUP',
    'ULNBKDN->FLNBKDN', 'UMNAKUP->UMNAKUP', 'UMPAKUP->UHPAKUP',
    'UMPBKDN->ULNBKDN', 'UMPBKDN->UMNBKDN', 'UMPBKDN->UMPBKDN',
    'UMPBKUP->UMPBKDN', 'UMPBKUP->UMPBKUP',
}


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
        raw = None
        for enc in ('utf-16', 'utf-8-sig', 'utf-8'):
            try:
                raw = pd.read_csv(path, header=None, encoding=enc)
                break
            except Exception:
                raw = None
        if raw is None:
            raise RuntimeError(f'无法读取CSV: {path}')

        if raw.shape[1] == 1:
            col = raw.iloc[:, 0].astype(str)
            parts = col.str.split(',', expand=True)
            return _normalize_from_parts(parts.iloc[:, :6])

        first = [str(x).strip().lower() for x in raw.iloc[0].tolist()[:2]]
        if any('date' in x or 'time' in x for x in first):
            raw = raw.iloc[1:].reset_index(drop=True)
        return _normalize_from_parts(raw.iloc[:, :6])

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


def to_deg(rad):
    return rad * 180.0 / math.pi


def sign_dir(x: float):
    if x > 0:
        return DIR_UP
    if x < 0:
        return DIR_DOWN
    return DIR_FLAT


def compute_trend(close, idx, bars):
    y = close[idx - 1] - close[idx - bars]
    x = bars * POINT * 10.0
    angle = to_deg(math.atan2(y, x))
    return sign_dir(y), angle


def compute_series_angle(arr, idx, from_shift, to_shift):
    if from_shift <= to_shift:
        return 0.0
    y = arr[idx - to_shift] - arr[idx - from_shift]
    x = float(from_shift - to_shift)
    return to_deg(math.atan2(y, x))


def compute_line_status(close, idx):
    vals = close[idx - Trend_Small_Bars:idx]
    ma3 = []
    for i in range(Trend_Small_Bars - 2):
        ma3.append((vals[i] + vals[i + 1] + vals[i + 2]) / 3.0)

    over30 = 0
    max_abs = 0.0
    for j in range(len(ma3) - 1):
        dy = ma3[j + 1] - ma3[j]
        dx = POINT * 10.0
        a = abs(to_deg(math.atan2(dy, dx)))
        if a > 30.0:
            over30 += 1
        max_abs = max(max_abs, a)

    line_status = LINE_STATUS_SHAKY if over30 >= 2 else LINE_STATUS_SMOOTH
    shaky_level = 0
    if line_status == LINE_STATUS_SHAKY:
        if max_abs > 60.0:
            shaky_level = 2
        elif max_abs > 45.0:
            shaky_level = 1
    return line_status, shaky_level


def compute_bolling_status(up, mid, down, idx):
    width_now = up[idx - 1] - down[idx - 1]
    width_prev = up[idx - 2] - down[idx - 2]
    width_delta = width_now - width_prev
    mid_delta = mid[idx - 1] - mid[idx - 2]
    angle = to_deg(math.atan2(mid_delta, width_delta if width_delta != 0 else 1e-7))

    if width_delta > 0 and angle > 90.0:
        status = BOLLING_CLIFF_UP
    elif width_delta < 0 and angle < -90.0:
        status = BOLLING_CLIFF_DOWN
    else:
        status = BOLLING_NORMAL_EXPAND if width_delta >= 0 else BOLLING_NORMAL_CONTRACT
    return status, angle


def detect_cross(ema5, ema20, idx):
    xgold = ema5[idx - 2] <= ema20[idx - 2] and ema5[idx - 1] > ema20[idx - 1]
    xdead = ema5[idx - 2] >= ema20[idx - 2] and ema5[idx - 1] < ema20[idx - 1]
    return xgold, xdead


def detect_struct_up(open_, high, low, close, up, idx):
    l, m, r = idx - 3, idx - 2, idx - 1
    c1 = high[m] > up[m]
    c2 = high[m] > high[l] and high[m] > high[r]
    c3_strict = min(open_[r], close[r]) < low[l]
    c3_relaxed = low[r] < low[l]
    c3 = c3_strict or (Struct_Relaxed_Mode and c3_relaxed)
    return c1 and c2 and c3


def detect_struct_down(open_, high, low, close, down, idx):
    l, m, r = idx - 3, idx - 2, idx - 1
    c1 = low[m] < down[m]
    c2 = low[m] < low[l] and low[m] < low[r]
    c3_strict = max(open_[r], close[r]) > high[m]
    c3_relaxed = (high[r] > high[m]) or (max(open_[r], close[r]) > max(open_[m], close[m]))
    c3 = c3_strict or (Struct_Relaxed_Mode and c3_relaxed)
    return c1 and c2 and c3


def detect_struct_x_gold(xgold, ema5, ema20, mid, idx):
    if not xgold:
        return False
    return (ema5[idx - 1] + ema20[idx - 1]) / 2.0 > mid[idx - 1]


def detect_struct_x_dead(xdead, ema5, ema20, mid, idx):
    if not xdead:
        return False
    return (ema5[idx - 1] + ema20[idx - 1]) / 2.0 < mid[idx - 1]


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


def get_risk_scale(momentum, line_status, bolling_status):
    if not Use_Dynamic_Risk_Scale:
        return 1.0

    r = Risk_Scale_Other
    if momentum == MOMENTUM_STRONG_CONTINUE:
        r = Risk_Scale_Strong
    elif momentum == MOMENTUM_WEAK_CONTINUE:
        r = Risk_Scale_Weak

    if line_status == LINE_STATUS_SHAKY:
        r *= Risk_Scale_Shaky_Factor
    if bolling_status == BOLLING_NORMAL_CONTRACT:
        r *= Risk_Scale_Contract_Factor

    r = max(Risk_Scale_Min, min(1.0, r))
    return r


def allow_entry_by_stats(is_short, struct_type, big_dir, bolling_status):
    if not Enable_Stats_Gate:
        return True

    if Block_Cliff_Down_Entry and bolling_status == BOLLING_CLIFF_DOWN:
        return False

    if struct_type == 0 and not Allow_Struct_Up:
        return False
    if struct_type == 1 and not Allow_Struct_Down:
        return False
    if struct_type == 2 and not Allow_Struct_XGold:
        return False
    if struct_type == 3 and not Allow_Struct_XDead:
        return False

    if Require_Big_Trend_Align:
        if is_short and big_dir != DIR_DOWN:
            return False
        if (not is_short) and big_dir != DIR_UP:
            return False

    return True


def build_state4(close, open_, high, low, ema5, ema20, up, down, idx, shift):
    if shift < 1:
        return ''
    i = idx - shift
    ip = idx - (shift + 1)

    width = up[i] - down[i]
    if width <= POINT:
        return ''

    width_prev = up[ip] - down[ip]
    width_delta = width - width_prev
    mid_now = (up[i] + down[i]) * 0.5
    mid_prev = (up[ip] + down[ip]) * 0.5
    ang = to_deg(math.atan2(mid_now - mid_prev, width_delta if width_delta != 0 else 1e-7))
    y_pos = (close[i] - down[i]) / width

    spread = ema5[i] - ema20[i]
    spread_prev = ema5[ip] - ema20[ip]
    slope = spread - spread_prev

    a = 'A_FLAT'
    if ang > 95.0:
        a = 'A_UP'
    elif ang < -95.0:
        a = 'A_DN'

    y = 'Y_MID'
    if y_pos < 0.33:
        y = 'Y_LOW'
    elif y_pos > 0.66:
        y = 'Y_HIGH'

    e = 'E_BEAR_DECEL'
    if spread > 0.0 and slope > 0.0:
        e = 'E_BULL_ACCEL'
    elif spread > 0.0 and slope <= 0.0:
        e = 'E_BULL_DECEL'
    elif spread <= 0.0 and slope < 0.0:
        e = 'E_BEAR_ACCEL'

    up_count, down_count = 0, 0
    for s in range(shift + 4, shift, -1):
        newer = idx - (s - 1)
        older = idx - s
        if close[newer] > close[older]:
            up_count += 1
        elif close[newer] < close[older]:
            down_count += 1

    k = 'K5_MIX'
    if up_count >= 3:
        k = 'K5_UP'
    elif down_count >= 3:
        k = 'K5_DN'

    return f'{a}|{y}|{e}|{k}'


def build_node5(close, open_, high, low, ema5, ema20, up, down, idx, shift):
    i = idx - shift
    ip = idx - (shift + 1)

    width = up[i] - down[i]
    if width <= POINT:
        return ''

    width_prev = up[ip] - down[ip]
    width_delta = width - width_prev
    mid_now = (up[i] + down[i]) * 0.5
    mid_prev = (up[ip] + down[ip]) * 0.5
    ang = to_deg(math.atan2(mid_now - mid_prev, width_delta if width_delta != 0 else 1e-7))
    y_pos = (close[i] - down[i]) / width

    spread = ema5[i] - ema20[i]
    spread_prev = ema5[ip] - ema20[ip]
    slope = spread - spread_prev

    a = 'U' if ang > 95.0 else ('D' if ang < -95.0 else 'F')
    y = 'L' if y_pos < 0.33 else ('H' if y_pos > 0.66 else 'M')
    e = 'P' if spread > 0.0 else 'N'
    s = 'A' if slope > 0.0 else 'B'

    up_count, down_count = 0, 0
    for t in range(shift + 3, shift, -1):
        newer = idx - (t - 1)
        older = idx - t
        if close[newer] > close[older]:
            up_count += 1
        elif close[newer] < close[older]:
            down_count += 1

    k = 'KUP' if up_count >= 2 else ('KDN' if down_count >= 2 else 'KM')
    return f'{a}{y}{e}{s}{k}'


def evaluate_round3_signal(is_short, open_, high, low, close, ema5, ema20, up, down, idx, bolling_angle, apply_switch):
    if apply_switch and not Enable_Advanced_Gate:
        return True

    width = up[idx - 1] - down[idx - 1]
    if width <= 0.0:
        return False

    y_pos = (close[idx - 1] - down[idx - 1]) / width
    ema5_ang = compute_series_angle(ema5, idx, 6, 1)
    ema20_ang = compute_series_angle(ema20, idx, 10, 1)

    body_move = close[idx - 1] - close[idx - 5]
    avg_range = 0.0
    shadow_ratio_sum = 0.0
    up_count, down_count = 0, 0

    for s in range(1, 6):
        i = idx - s
        o, c, h, l = open_[i], close[i], high[i], low[i]
        r = max(POINT, h - l)
        avg_range += r
        upper = h - max(o, c)
        lower_shadow = min(o, c) - l
        shadow_ratio_sum += (upper + lower_shadow) / r

        if s < 5:
            newer = idx - s
            older = idx - (s + 1)
            if close[newer] > close[older]:
                up_count += 1
            elif close[newer] < close[older]:
                down_count += 1

    avg_range /= 5.0
    body_score = body_move / max(POINT, avg_range)
    shadow_ratio = shadow_ratio_sum / 5.0
    if shadow_ratio > Adv_Shadow_Cap:
        return False

    if not is_short:
        return (
            bolling_angle >= Adv_Boll_Angle_Long_Min and
            y_pos >= Adv_YPos_Low and y_pos <= Adv_YPos_High and
            ema5_ang >= Adv_Ema5_Long_Min_Deg and
            ema20_ang >= Adv_Ema20_Long_Min_Deg and
            body_score >= Adv_Body_Long_Min and
            up_count >= 3
        )

    return (
        bolling_angle <= Adv_Boll_Angle_Short_Max and
        y_pos <= (1.0 - Adv_YPos_Low) and y_pos >= (1.0 - Adv_YPos_High) and
        ema5_ang <= Adv_Ema5_Short_Max_Deg and
        ema20_ang <= Adv_Ema20_Short_Max_Deg and
        body_score <= Adv_Body_Short_Max and
        down_count >= 3
    )


def allow_entry_by_advanced_gate(is_short, open_, high, low, close, ema5, ema20, up, down, idx, bolling_angle):
    return evaluate_round3_signal(is_short, open_, high, low, close, ema5, ema20, up, down, idx, bolling_angle, True)


def allow_entry_by_fusion_gate(is_short, open_, high, low, close, ema5, ema20, up, down, idx, bolling_angle):
    if not Enable_Fusion_Gate:
        return True

    s3_long = evaluate_round3_signal(False, open_, high, low, close, ema5, ema20, up, down, idx, bolling_angle, False)
    s3_short = evaluate_round3_signal(True, open_, high, low, close, ema5, ema20, up, down, idx, bolling_angle, False)

    state = build_state4(close, open_, high, low, ema5, ema20, up, down, idx, 1)
    s4_long = state in FUSION_LONG_STATES
    s4_short = state in FUSION_SHORT_STATES

    node_a = build_node5(close, open_, high, low, ema5, ema20, up, down, idx, 2)
    node_b = build_node5(close, open_, high, low, ema5, ema20, up, down, idx, 1)
    edge = f'{node_a}->{node_b}'
    s5_long = edge in FUSION_LONG_EDGES
    s5_short = edge in FUSION_SHORT_EDGES

    long_score = (Fusion_W3 if s3_long else 0.0) + (Fusion_W4 if s4_long else 0.0) + (Fusion_W5 if s5_long else 0.0)
    short_score = (Fusion_W3 if s3_short else 0.0) + (Fusion_W4 if s4_short else 0.0) + (Fusion_W5 if s5_short else 0.0)

    if not is_short:
        return long_score >= Fusion_Long_Threshold and long_score > short_score
    return short_score >= Fusion_Short_Threshold and short_score > long_score


def maybe_trail_position(pos, side, ref_price, atr, momentum, line_status, boll_status, big_dir):
    allow_trail = (momentum == MOMENTUM_STRONG_CONTINUE) or (
        Enable_Weak_Momentum_Trail and momentum == MOMENTUM_WEAK_CONTINUE
    )
    if not allow_trail:
        return pos

    sl_mult, tp_mult = dynamic_mult(momentum, line_status, boll_status)
    if side == 'long':
        cand_sl = ref_price - atr * sl_mult
        cand_tp = ref_price + atr * tp_mult
        if cand_sl > pos['sl']:
            pos['sl'] = cand_sl
        if cand_tp > pos['tp']:
            pos['tp'] = cand_tp

        if Enable_Trend_Tp_Recalc and pos['tp'] > 0.0:
            trigger_dist = atr * Tp_Recalc_Trigger_Atr
            if (pos['tp'] - ref_price) <= trigger_dist and big_dir == DIR_UP and momentum not in (MOMENTUM_REVERSAL, MOMENTUM_UNCLEAR):
                ext_tp = ref_price + atr * (tp_mult * Tp_Expand_Factor)
                lock_sl = ref_price - atr * Trail_Lock_Atr
                if ext_tp > pos['tp']:
                    pos['tp'] = ext_tp
                if lock_sl > pos['sl']:
                    pos['sl'] = lock_sl

    else:
        cand_sl = ref_price + atr * sl_mult
        cand_tp = ref_price - atr * tp_mult
        if cand_sl < pos['sl']:
            pos['sl'] = cand_sl
        if cand_tp < pos['tp']:
            pos['tp'] = cand_tp

        if Enable_Trend_Tp_Recalc and pos['tp'] > 0.0:
            trigger_dist = atr * Tp_Recalc_Trigger_Atr
            if (ref_price - pos['tp']) <= trigger_dist and big_dir == DIR_DOWN and momentum not in (MOMENTUM_REVERSAL, MOMENTUM_UNCLEAR):
                ext_tp = ref_price - atr * (tp_mult * Tp_Expand_Factor)
                lock_sl = ref_price + atr * Trail_Lock_Atr
                if ext_tp < pos['tp']:
                    pos['tp'] = ext_tp
                if lock_sl < pos['sl']:
                    pos['sl'] = lock_sl

    return pos


def run_backtest(df):
    balance = 1000.0
    peak = balance
    max_dd = 0.0

    pos = None
    trades = []
    signal_counts = {'up': 0, 'down': 0, 'xgold': 0, 'xdead': 0}
    gate_pass = {'short': 0, 'long': 0}

    arr = {k: df[k].values for k in ['open', 'high', 'low', 'close', 'ema5', 'ema20', 'up', 'mid', 'down', 'atr']}
    times = df['time'].values

    start = max(60, Trend_Big_Bars + 10)
    for idx in range(start, len(df)):
        # indicator / history availability
        if any(pd.isna(arr[k][idx - 1]) for k in ['ema5', 'ema20', 'up', 'mid', 'down', 'atr']):
            continue
        if idx < 12:
            continue

        atr_now = arr['atr'][idx - 1]
        if not (atr_now and atr_now > 0):
            continue

        big_dir, _big_ang = compute_trend(arr['close'], idx, Trend_Big_Bars)
        mid_dir, _mid_ang = compute_trend(arr['close'], idx, Trend_Mid_Bars)
        small_dir, _small_ang = compute_trend(arr['close'], idx, Trend_Small_Bars)

        line_code = LINE_CODE_UP if small_dir == DIR_UP else (LINE_CODE_DOWN if small_dir == DIR_DOWN else None)
        line_status, _shaky = compute_line_status(arr['close'], idx)
        boll_status, boll_ang = compute_bolling_status(arr['up'], arr['mid'], arr['down'], idx)
        momentum = compute_momentum(big_dir, mid_dir, small_dir, boll_status, line_status)

        xgold, xdead = detect_cross(arr['ema5'], arr['ema20'], idx)
        sup = detect_struct_up(arr['open'], arr['high'], arr['low'], arr['close'], arr['up'], idx)
        sdown = detect_struct_down(arr['open'], arr['high'], arr['low'], arr['close'], arr['down'], idx)
        sxg = detect_struct_x_gold(xgold, arr['ema5'], arr['ema20'], arr['mid'], idx)
        sxd = detect_struct_x_dead(xdead, arr['ema5'], arr['ema20'], arr['mid'], idx)

        signal_counts['up'] += int(sup)
        signal_counts['down'] += int(sdown)
        signal_counts['xgold'] += int(sxg)
        signal_counts['xdead'] += int(sxd)

        # manage open position
        entry_px = arr['open'][idx]
        if pos is not None:
            pos['held_bars'] += 1

            close_reason = None
            exit_px = entry_px

            # simulate intrabar sl/tp via previous bar range
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

            if close_reason is None:
                if Max_Hold_Bars > 0 and pos['held_bars'] >= Max_Hold_Bars:
                    close_reason = 'max_hold'
                elif pos['side'] == 'short' and xgold:
                    close_reason = 'xgold'
                elif pos['side'] == 'long' and xdead:
                    close_reason = 'xdead'
                elif momentum in (MOMENTUM_REVERSAL, MOMENTUM_UNCLEAR):
                    close_reason = 'momentum'

            if close_reason is not None:
                pnl = (pos['entry'] - exit_px) * pos['units'] if pos['side'] == 'short' else (exit_px - pos['entry']) * pos['units']
                balance += pnl
                trades.append({
                    'entry_time': pos['time'],
                    'exit_time': times[idx],
                    'side': pos['side'],
                    'entry': pos['entry'],
                    'exit': exit_px,
                    'pnl': pnl,
                    'reason': close_reason,
                })
                pos = None
                peak = max(peak, balance)
                dd = (peak - balance) / peak if peak > 0 else 0
                max_dd = max(max_dd, dd)
                continue

            pos = maybe_trail_position(pos, pos['side'], entry_px, atr_now, momentum, line_status, boll_status, big_dir)
            continue

        # flat -> entry gating
        cliff_up_combo = (boll_status == BOLLING_CLIFF_UP and sup and sxd)
        cliff_down_combo = (boll_status == BOLLING_CLIFF_DOWN and sdown and sxg)

        if line_code == LINE_CODE_UP:
            short_by_struct_up = sup or cliff_up_combo
            short_by_xdead = (not short_by_struct_up) and sxd
            struct_type = 0 if short_by_struct_up else 3

            if short_by_struct_up or short_by_xdead:
                pass_stats = allow_entry_by_stats(True, struct_type, big_dir, boll_status)
                pass_adv = allow_entry_by_advanced_gate(True, arr['open'], arr['high'], arr['low'], arr['close'], arr['ema5'], arr['ema20'], arr['up'], arr['down'], idx, boll_ang)
                pass_fusion = allow_entry_by_fusion_gate(True, arr['open'], arr['high'], arr['low'], arr['close'], arr['ema5'], arr['ema20'], arr['up'], arr['down'], idx, boll_ang)

                if pass_stats and pass_adv and pass_fusion:
                    gate_pass['short'] += 1
                    slm, tpm = dynamic_mult(momentum, line_status, boll_status)
                    stop_dist = atr_now * slm
                    take_dist = atr_now * tpm
                    risk_scale = get_risk_scale(momentum, line_status, boll_status)
                    risk_money = balance * Risk_Per_Trade * max(0.0, risk_scale)
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
                        }
                continue

        if line_code == LINE_CODE_DOWN:
            long_by_struct_down = sdown or cliff_down_combo
            long_by_xgold = (not long_by_struct_down) and sxg
            struct_type = 1 if long_by_struct_down else 2

            if long_by_struct_down or long_by_xgold:
                pass_stats = allow_entry_by_stats(False, struct_type, big_dir, boll_status)
                pass_adv = allow_entry_by_advanced_gate(False, arr['open'], arr['high'], arr['low'], arr['close'], arr['ema5'], arr['ema20'], arr['up'], arr['down'], idx, boll_ang)
                pass_fusion = allow_entry_by_fusion_gate(False, arr['open'], arr['high'], arr['low'], arr['close'], arr['ema5'], arr['ema20'], arr['up'], arr['down'], idx, boll_ang)

                if pass_stats and pass_adv and pass_fusion:
                    gate_pass['long'] += 1
                    slm, tpm = dynamic_mult(momentum, line_status, boll_status)
                    stop_dist = atr_now * slm
                    take_dist = atr_now * tpm
                    risk_scale = get_risk_scale(momentum, line_status, boll_status)
                    risk_money = balance * Risk_Per_Trade * max(0.0, risk_scale)
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
        })

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
    ap = argparse.ArgumentParser(description='Run Survival_v7 offline backtest')
    ap.add_argument('--file', type=str, default=str(FILE), help='input file path (.xlsx/.csv)')
    args = ap.parse_args()

    src = Path(args.file)
    df = parse_data(src)
    df = indicators(df)
    result = run_backtest(df)

    print('=== Backtest Summary (Survival_v7 logic / offline replay) ===')
    print(f'Source  : {src}')
    print(f'Data bars: {result["bars"]}')
    print(f'Range   : {result["start"]} -> {result["end"]}')
    print(
        'Signals : '
        f'STRUCT_UP={result["signals"]["up"]}, '
        f'STRUCT_DOWN={result["signals"]["down"]}, '
        f'STRUCT_X_GOLD={result["signals"]["xgold"]}, '
        f'STRUCT_X_DEAD={result["signals"]["xdead"]}'
    )
    print(f'Gate pass attempts: short={result["gate_pass"]["short"]}, long={result["gate_pass"]["long"]}')
    print(f'Trades  : {len(result["trades"])}')
    print(f'Win/Loss: {result["wins"]}/{result["losses"]} ({result["win_rate"]:.2f}%)')
    print(f'Net PnL : {result["net_pnl"]:.2f}')
    print(f'Final Bal: {result["final_balance"]:.2f}')
    print(f'Max DD  : {result["max_dd_pct"]:.2f}%')

    print('\n=== Last 10 Trades ===')
    for t in result['trades'][-10:]:
        print(
            f"{t['entry_time']} -> {t['exit_time']} | {t['side']:5s} | "
            f"entry={t['entry']:.2f} exit={t['exit']:.2f} pnl={t['pnl']:.2f} reason={t['reason']}"
        )


if __name__ == '__main__':
    main()
