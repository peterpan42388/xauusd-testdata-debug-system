from pathlib import Path
import json
import pandas as pd
import sys

sys.path.append('/Users/leo/Menu/py_workspace/gold/TestData')
from run_survival_v3_backtest import parse_data, indicators  # type: ignore

BASE = Path('/Users/leo/Menu/py_workspace/gold/TestData')
SRC = BASE / 'Week' / 'Week_06_20260504_20260510.csv'
OUT = BASE / 'debug_system' / 'data' / 'ohlc.json'
BOLLINGER_DEVIATION = 2.0

df = parse_data(SRC)
if len(df) == 0:
    raise RuntimeError(f'No rows in source file: {SRC}')
df = indicators(df)
df['bb_mid'] = df['mid']
df['bb_up'] = df['up']
df['bb_down'] = df['down']

# CSV没有spread，调试系统统一补0
df['spread'] = 0.0

out_rows = []
for _, r in df.iterrows():
    out_rows.append({
        'time': r['time'].strftime('%Y-%m-%dT%H:%M:%S'),
        'open': float(r['open']),
        'high': float(r['high']),
        'low': float(r['low']),
        'close': float(r['close']),
        'volume': float(r['volume']),
        'spread': float(r['spread']),
        'ema5': (None if pd.isna(r['ema5']) else float(r['ema5'])),
        'ema20': (None if pd.isna(r['ema20']) else float(r['ema20'])),
        'bb_mid': (None if pd.isna(r['bb_mid']) else float(r['bb_mid'])),
        'bb_up': (None if pd.isna(r['bb_up']) else float(r['bb_up'])),
        'bb_down': (None if pd.isna(r['bb_down']) else float(r['bb_down'])),
    })

payload = {
    'symbol': 'XAUUSD',
    'timeframe': 'M5',
    'bollinger_deviation': BOLLINGER_DEVIATION,
    'source_file': str(SRC),
    'filter_start': None,
    'count': len(out_rows),
    'rows': out_rows,
}

OUT.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
if len(out_rows) == 0:
    raise RuntimeError(f'No rows generated from source={SRC}')
print(f'Wrote {len(out_rows)} rows (source={SRC.name}) -> {OUT}')
