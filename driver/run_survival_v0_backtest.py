from pathlib import Path
import argparse

import run_survival_v7_backtest as base

FILE = Path(__file__).resolve().parents[1] / 'Week' / 'Week_06_20260504_20260510.csv'

# Re-export parser/indicator so debug_system can load uniformly
parse_data = base.parse_data
indicators = base.indicators


def run_backtest(df, common_params=None):
    # v0: no entries, no exits, no strategy actions
    bars = int(len(df))
    start = str(df['time'].iloc[0]) if bars else ''
    end = str(df['time'].iloc[-1]) if bars else ''
    return {
        'bars': bars,
        'start': start,
        'end': end,
        'signals': {'long': 0, 'short': 0},
        'gate_pass': {'short': 0, 'long': 0},
        'trades': [],
        'wins': 0,
        'losses': 0,
        'win_rate': 0.0,
        'net_pnl': 0.0,
        'final_balance': 1000.0,
        'max_dd_pct': 0.0,
        'profit_factor': 0.0,
    }


def main():
    ap = argparse.ArgumentParser(description='Run Survival_v0 empty backtest')
    ap.add_argument('--file', type=str, default=str(FILE), help='input file path (.xlsx/.csv)')
    args = ap.parse_args()

    src = Path(args.file)
    df = parse_data(src)
    df = indicators(df)
    result = run_backtest(df)

    print('=== Backtest Summary (Survival_v0 empty engine) ===')
    print(f'Source   : {src}')
    print(f'Data bars: {result["bars"]}')
    print(f'Range    : {result["start"]} -> {result["end"]}')
    print(f'Trades   : {len(result["trades"])}')
    print(f'Net PnL  : {result["net_pnl"]:.2f}')
    print(f'Final Bal: {result["final_balance"]:.2f}')


if __name__ == '__main__':
    main()
