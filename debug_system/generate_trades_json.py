from pathlib import Path
import json
import sys
import pandas as pd

BASE = Path(__file__).resolve().parents[1]
DRIVER = BASE / 'driver'
sys.path.insert(0, str(DRIVER))
from run_survival_v3_backtest import parse_data, indicators, run_backtest  # type: ignore

OUT = BASE / 'debug_system' / 'data' / 'trades.json'
SRC = BASE / 'Week' / 'Week_06_20260504_20260510.csv'


def main():
    df = parse_data(SRC)
    if len(df) == 0:
        raise RuntimeError(f'No rows in source file: {SRC}')
    df = indicators(df)
    res = run_backtest(df)

    trades = []
    for i, t in enumerate(res['trades']):
        trades.append({
            'id': i + 1,
            'entry_time': pd.to_datetime(t['entry_time']).strftime('%Y-%m-%dT%H:%M:%S'),
            'exit_time': pd.to_datetime(t['exit_time']).strftime('%Y-%m-%dT%H:%M:%S'),
            'side': t['side'],
            'entry_price': float(t['entry']),
            'exit_price': float(t['exit']),
            'pnl': float(t['pnl']),
            'reason': str(t['reason']),
        })

    payload = {
        'summary': {
            'bars': int(res['bars']),
            'start': str(res['start']),
            'end': str(res['end']),
            'source_file': str(SRC),
            'filter_start': None,
            'signals': res['signals'],
            'gate_pass': res['gate_pass'],
            'trades': len(trades),
            'wins': int(res['wins']),
            'losses': int(res['losses']),
            'win_rate': float(res['win_rate']),
            'net_pnl': float(res['net_pnl']),
            'final_balance': float(res['final_balance']),
            'max_dd_pct': float(res['max_dd_pct']),
        },
        'trades': trades,
    }

    OUT.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    print(f'Wrote {len(trades)} trades (source={SRC.name}) -> {OUT}')


if __name__ == '__main__':
    main()
