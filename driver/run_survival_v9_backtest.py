from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import pandas as pd

import run_survival_v3_backtest as io_base

ROOT = Path('/Users/leo/Menu/py_workspace/gold')
TESTDATA_DIR = ROOT / 'TestData'
FILE = TESTDATA_DIR / 'Week' / 'Week_06_20260504_20260510.csv'
ROUND8_PY = ROOT / 'SelfUpgrade' / '08 v8加仓研究' / 'round8_pyramiding_research.py'
ROUND8_RESULT = ROOT / 'SelfUpgrade' / '08 v8加仓研究' / 'result_round8.json'
ROUND9_PY = ROOT / 'SelfUpgrade' / '09 回撤约束型加仓优化' / 'round9_dd_constrained_pyramid.py'
ROUND9_RESULT = ROOT / 'SelfUpgrade' / '09 回撤约束型加仓优化' / 'result_round9.json'

parse_data = io_base.parse_data


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f'cannot load module: {path}')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_round8 = _load_module(ROUND8_PY, 'round8_research_mod')
_round9 = _load_module(ROUND9_PY, 'round9_research_mod')


def indicators(df: pd.DataFrame) -> pd.DataFrame:
    return _round8.indicators(df)


def _load_cfg():
    r8 = json.loads(ROUND8_RESULT.read_text(encoding='utf-8'))
    r9 = json.loads(ROUND9_RESULT.read_text(encoding='utf-8'))
    pbase = _round8.V8Params(**r8['best_params'])
    ddp = _round9.DDParams(**r9['dd_params'])
    return pbase, ddp


def run_backtest(df: pd.DataFrame):
    pbase, ddp = _load_cfg()
    rs = _round9.simulate_dd(df, _round8, pbase, ddp, enable_pyramid=True, collect_details=True)
    trades = rs.get('trades_detail', [])
    return {
        'bars': rs['bars'],
        'start': rs['start'],
        'end': rs['end'],
        'signals': rs['signals'],
        'gate_pass': {'short': 0, 'long': 0},
        'trades': trades,
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


def _collect_files(mode: str):
    if mode == 'year':
        return sorted((TESTDATA_DIR / 'Year').glob('*.csv'))
    if mode == 'month':
        return sorted((TESTDATA_DIR / 'Month').glob('*.csv'))
    if mode == 'year_month':
        return sorted((TESTDATA_DIR / 'Year').glob('*.csv')) + sorted((TESTDATA_DIR / 'Month').glob('*.csv'))
    return []


def main():
    ap = argparse.ArgumentParser(description='Run Survival_v9 research-replay backtest (/09 回撤约束加仓口径)')
    ap.add_argument('--file', type=str, default=str(FILE), help='single input file path (.xlsx/.csv)')
    ap.add_argument('--batch', type=str, default='single', choices=['single', 'year', 'month', 'year_month'])
    ap.add_argument('--out-dir', type=str, default=str(Path(__file__).resolve().parent))
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.batch == 'single':
        df = indicators(parse_data(Path(args.file)))
        rs = run_backtest(df)
        print('=== Backtest Summary (Survival_v9 / Round9 research replay) ===')
        print(f'Source      : {args.file}')
        print(f'Trades      : {len(rs["trades"])}')
        print(f'Win/Loss    : {rs["wins"]}/{rs["losses"]} ({rs["win_rate"]:.2f}%)')
        print(f'Net PnL     : {rs["net_pnl"]:.2f}')
        print(f'Final Bal   : {rs["final_balance"]:.2f}')
        print(f'Max DD      : {rs["max_dd_pct"]:.2f}%')
        print(f'ProfitFactor: {rs["profit_factor"]:.4f}')
        print(f'Add Count   : {rs["add_count"]}')
        print(f'MultiLayer  : {rs["multi_layer_trades"]} ({rs["multi_layer_ratio_pct"]:.2f}%)')
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
            'add_count': rs['add_count'],
            'multi_layer_trades': rs['multi_layer_trades'],
            'multi_layer_ratio_pct': rs['multi_layer_ratio_pct'],
        })

    out = pd.DataFrame(rows)
    csv_path = out_dir / f'v9_backtest_{args.batch}.csv'
    json_path = out_dir / f'v9_backtest_{args.batch}_summary.json'
    out.to_csv(csv_path, index=False, encoding='utf-8-sig')
    summary = {
        'batch': args.batch,
        'files': len(rows),
        'mean_final_balance': float(out['final_balance'].mean()) if len(out) else 0.0,
        'mean_net_pnl': float(out['net_pnl'].mean()) if len(out) else 0.0,
        'mean_win_rate': float(out['win_rate'].mean()) if len(out) else 0.0,
        'mean_max_dd_pct': float(out['max_dd_pct'].mean()) if len(out) else 0.0,
        'mean_profit_factor': float(out['profit_factor'].mean()) if len(out) else 0.0,
        'mean_add_count': float(out['add_count'].mean()) if len(out) else 0.0,
        'mean_multi_layer_ratio_pct': float(out['multi_layer_ratio_pct'].mean()) if len(out) else 0.0,
    }
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Output CSV   : {csv_path}')
    print(f'Output JSON  : {json_path}')


if __name__ == '__main__':
    main()
