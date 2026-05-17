from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path
import json
from datetime import datetime
from uuid import uuid4
from collections import defaultdict
import re
import sys
import importlib.util
try:
    import pandas as pd
except Exception as e:
    print("[FATAL] Python dependency import failed: pandas/numpy")
    print("[FATAL] 原因:", repr(e))
    print("[FATAL] Windows 修复建议:")
    print("  1) 删除旧虚拟环境: rmdir /s /q .venv")
    print("  2) 使用 64 位 Python 3.12 重建: py -3.12 -m venv .venv")
    print("  3) 激活后升级打包工具: python -m pip install -U pip setuptools wheel")
    print("  4) 重新安装依赖: pip install --no-cache-dir numpy==2.2.6 pandas==2.2.3")
    print("  5) 启动服务: cd debug_system && python server.py")
    sys.exit(1)

BASE = Path(__file__).resolve().parent
WEB_DIR = BASE / 'web'
DATA_FILE = BASE / 'data' / 'ohlc.json'
TRADES_FILE = BASE / 'data' / 'trades.json'
LOG_FILE = BASE / 'logs' / 'comments.jsonl'
CURRENT_DATASET_FILE = BASE / 'data' / 'current_dataset.json'
CURRENT_ENGINE_FILE = BASE / 'data' / 'current_engine.json'
DATA_ROOT = BASE.parent
DRIVER_DIR = DATA_ROOT / 'driver'
BOLLINGER_DEVIATION = 2.0
COMMON_PARAMS_FILE = DRIVER_DIR / 'config' / 'common_params.json'
DEFAULT_COMMON_PARAMS = {
    'daily_max_loss_pct': 0.08,
    'per_trade_max_loss_pct': 0.08,
    'daily_max_consecutive_losses': 3,
}
EXPLICIT_ENGINE_BACKTEST_MAP = {
    'kline_plan01_ea.mq5': 'run_plan01_backtest.py',
    'kline_plan02_ea.mq5': 'run_plan02_backtest.py',
    'kline_plan02_ea_a.mq5': 'run_plan02_backtest.py',
    'kline_plan02_ea_b.mq5': 'run_plan02_backtest.py',
    'kline_base.mq5': 'run_plan02_backtest.py',
}

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
if not LOG_FILE.exists():
    LOG_FILE.touch()


def ensure_common_params():
    COMMON_PARAMS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not COMMON_PARAMS_FILE.exists():
        COMMON_PARAMS_FILE.write_text(json.dumps(DEFAULT_COMMON_PARAMS, ensure_ascii=False, indent=2), encoding='utf-8')


def read_common_params():
    ensure_common_params()
    cfg = read_json(COMMON_PARAMS_FILE, {}) or {}
    out = dict(DEFAULT_COMMON_PARAMS)
    out.update(cfg)
    try:
        out['daily_max_loss_pct'] = max(0.0, float(out.get('daily_max_loss_pct', DEFAULT_COMMON_PARAMS['daily_max_loss_pct'])))
    except Exception:
        out['daily_max_loss_pct'] = DEFAULT_COMMON_PARAMS['daily_max_loss_pct']
    try:
        out['per_trade_max_loss_pct'] = max(0.0, float(out.get('per_trade_max_loss_pct', DEFAULT_COMMON_PARAMS['per_trade_max_loss_pct'])))
    except Exception:
        out['per_trade_max_loss_pct'] = DEFAULT_COMMON_PARAMS['per_trade_max_loss_pct']
    try:
        out['daily_max_consecutive_losses'] = max(0, int(out.get('daily_max_consecutive_losses', DEFAULT_COMMON_PARAMS['daily_max_consecutive_losses'])))
    except Exception:
        out['daily_max_consecutive_losses'] = DEFAULT_COMMON_PARAMS['daily_max_consecutive_losses']
    return out


def write_common_params(payload: dict):
    cur = read_common_params()
    if 'daily_max_loss_pct' in payload:
        try:
            cur['daily_max_loss_pct'] = max(0.0, float(payload.get('daily_max_loss_pct')))
        except Exception:
            pass
    if 'per_trade_max_loss_pct' in payload:
        try:
            cur['per_trade_max_loss_pct'] = max(0.0, float(payload.get('per_trade_max_loss_pct')))
        except Exception:
            pass
    if 'daily_max_consecutive_losses' in payload:
        try:
            cur['daily_max_consecutive_losses'] = max(0, int(payload.get('daily_max_consecutive_losses')))
        except Exception:
            pass
    COMMON_PARAMS_FILE.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding='utf-8')
    return cur


def apply_common_limits_to_result(res: dict, common_params: dict):
    initial_balance = 1000.0
    daily_limit = initial_balance * float(common_params.get('daily_max_loss_pct', 0.0) or 0.0)
    per_trade_limit = initial_balance * float(common_params.get('per_trade_max_loss_pct', 0.0) or 0.0)
    consec_limit = int(common_params.get('daily_max_consecutive_losses', 0) or 0)
    if daily_limit <= 0 and per_trade_limit <= 0 and consec_limit <= 0:
        return res

    filtered = []
    day_pnl = defaultdict(float)
    day_consec_loss = defaultdict(int)
    blocked_days = set()
    blocked_count = 0
    blocked_by_rule = {'daily_max_loss': 0, 'per_trade_max_loss': 0, 'daily_consecutive_losses': 0}
    for t in res.get('trades', []):
        exit_dt = pd.to_datetime(t.get('exit_time'))
        day_key = exit_dt.strftime('%Y-%m-%d')
        if day_key in blocked_days:
            blocked_count += 1
            continue
        pnl = float(t.get('pnl', 0.0))
        filtered.append(t)
        day_pnl[day_key] += pnl
        if pnl < 0:
            day_consec_loss[day_key] += 1
        else:
            day_consec_loss[day_key] = 0

        if per_trade_limit > 0 and pnl <= -per_trade_limit:
            blocked_days.add(day_key)
            blocked_by_rule['per_trade_max_loss'] += 1
            continue
        if daily_limit > 0 and day_pnl[day_key] <= -daily_limit:
            blocked_days.add(day_key)
            blocked_by_rule['daily_max_loss'] += 1
            continue
        if consec_limit > 0 and day_consec_loss[day_key] >= consec_limit:
            blocked_days.add(day_key)
            blocked_by_rule['daily_consecutive_losses'] += 1
            continue

    res['trades'] = filtered
    res['blocked_by_daily_loss'] = blocked_count
    res['blocked_by_rule'] = blocked_by_rule
    return res


def read_json(path: Path, fallback):
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return fallback


def read_comments():
    items = []
    with LOG_FILE.open('r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return items


def append_comment(obj):
    with LOG_FILE.open('a', encoding='utf-8') as f:
        f.write(json.dumps(obj, ensure_ascii=False) + '\n')


def _engine_stem_from_name(file_name: str):
    stem = Path(str(file_name or 'unknown_engine')).stem.strip() or 'unknown_engine'
    stem = re.sub(r'[^A-Za-z0-9_-]+', '_', stem)
    return stem


def _next_comment_seq(out_dir: Path) -> int:
    max_seq = 0
    for p in out_dir.glob('comments_*.jsonl'):
        m = re.match(r'^comments_(\d+)\.jsonl$', p.name)
        if not m:
            continue
        try:
            max_seq = max(max_seq, int(m.group(1)))
        except Exception:
            pass
    return max_seq + 1


def archive_temp_comments(engine_file: str | None = None):
    items = read_comments()
    if len(items) == 0:
        return {'count': 0, 'items': [], 'archive_file': None, 'engine_name': _engine_stem_from_name(engine_file or '')}

    if not engine_file:
        eng = current_engine_meta() or {}
        engine_file = str(eng.get('file') or '')
    engine_name = _engine_stem_from_name(engine_file)
    out_dir = BASE / 'logs' / engine_name
    out_dir.mkdir(parents=True, exist_ok=True)
    seq = _next_comment_seq(out_dir)
    out_name = f"comments_{seq:04d}.jsonl"
    out_path = out_dir / out_name
    with out_path.open('w', encoding='utf-8') as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + '\n')

    LOG_FILE.write_text('', encoding='utf-8')
    return {
        'count': len(items),
        'items': items,
        'archive_file': str(out_path),
        'engine_name': engine_name,
    }


def list_engine_files():
    if not DRIVER_DIR.exists():
        return []
    mq5 = sorted([p.name for p in DRIVER_DIR.glob('*.mq5')])
    py_backtests = sorted([p.name for p in DRIVER_DIR.glob('run_*_backtest.py')])
    # 优先展示/使用mq5；若仓库不带mq5，回退到py backtest引擎
    return mq5 if mq5 else py_backtests


def preferred_default_engine():
    preferred = DRIVER_DIR / 'XAUUSD_Survival_v7.mq5'
    if preferred.exists():
        return preferred
    preferred_py = DRIVER_DIR / 'run_survival_v7_backtest.py'
    if preferred_py.exists():
        return preferred_py
    files = list_engine_files()
    if not files:
        return None
    return DRIVER_DIR / files[0]


def current_engine_meta():
    m = read_json(CURRENT_ENGINE_FILE, None)
    engines = list_engine_files()
    if m and m.get('file') in engines:
        return m

    default_engine = preferred_default_engine()
    if default_engine is None:
        return {'file': None, 'path': None}

    obj = {'file': default_engine.name, 'path': str(default_engine)}
    CURRENT_ENGINE_FILE.write_text(json.dumps(obj, ensure_ascii=False), encoding='utf-8')
    return obj


def set_current_engine(file_name: str):
    engines = list_engine_files()
    if file_name not in engines:
        raise ValueError(f'engine file not found: {file_name}')
    p = DRIVER_DIR / file_name
    obj = {'file': file_name, 'path': str(p)}
    CURRENT_ENGINE_FILE.write_text(json.dumps(obj, ensure_ascii=False), encoding='utf-8')
    return obj


def infer_bucket_from_file_name(name: str):
    if name.startswith('Year_'):
        return 'year'
    if name.startswith('Month_'):
        return 'month'
    if name.startswith('Week_'):
        return 'week'
    if name.startswith('Day_'):
        return 'day'
    return None


def resolve_engine_backtest_module(engine_file_name: str):
    """
    根据当前引擎文件，优先加载同名回测脚本:
    - XAUUSD_Survival_v7.mq5 -> run_survival_v7_backtest.py
    若不存在则回退到 run_survival_v3_backtest.py
    """
    candidates = []
    mapping_rule = 'fallback'
    engine_key = (engine_file_name or '').strip().lower()
    explicit_script = EXPLICIT_ENGINE_BACKTEST_MAP.get(engine_key)
    # Plan02 系列引擎统一映射到 run_plan02_backtest.py，避免误落到 survival fallback
    if explicit_script is None and engine_key.startswith('kline_plan02_ea'):
        explicit_script = 'run_plan02_backtest.py'

    if explicit_script:
        mapping_rule = 'explicit_map'
        candidates.extend([DRIVER_DIR / explicit_script, DATA_ROOT / explicit_script])

    if engine_file_name.endswith('.py'):
        candidates.extend([DRIVER_DIR / engine_file_name, DATA_ROOT / engine_file_name])
    else:
        stem = Path(engine_file_name).stem
        lower_stem = stem.lower()
        # v10 orchestrator special mapping
        if 'orchestrator_v10_localtest' in lower_stem:
            candidates.extend([
                DRIVER_DIR / 'run_v10_localtest_backtest.py',
                DATA_ROOT / 'run_v10_localtest_backtest.py',
                DRIVER_DIR / 'run_orchestrator_v10_backtest.py',
                DATA_ROOT / 'run_orchestrator_v10_backtest.py',
            ])
        elif 'orchestrator_v10' in lower_stem:
            candidates.extend([
                DRIVER_DIR / 'run_orchestrator_v10_backtest.py',
                DATA_ROOT / 'run_orchestrator_v10_backtest.py',
            ])
        candidate_name = stem.replace('XAUUSD_Survival', 'run_survival').lower() + '_backtest.py'
        candidates.extend([DRIVER_DIR / candidate_name, DATA_ROOT / candidate_name])

    candidates.extend([
        DRIVER_DIR / 'run_survival_v7_backtest.py',
        DATA_ROOT / 'run_survival_v7_backtest.py',
        DRIVER_DIR / 'run_survival_v3_backtest.py',
        DATA_ROOT / 'run_survival_v3_backtest.py',
    ])

    existing = [p for p in candidates if p.exists()]
    if not existing:
        raise FileNotFoundError('No backtest module found in driver/TestData.')

    # Ensure driver/data roots are importable for backtest modules that import each other,
    # e.g. run_survival_v5_backtest -> import run_survival_v7_backtest as base
    for _p in (str(DRIVER_DIR), str(DATA_ROOT)):
        if _p not in sys.path:
            sys.path.insert(0, _p)

    errs = []
    for module_path in existing:
        try:
            spec = importlib.util.spec_from_file_location(f'backtest_{module_path.stem}', str(module_path))
            if spec is None or spec.loader is None:
                raise RuntimeError(f'Failed to load backtest module: {module_path}')
            mod = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = mod
            spec.loader.exec_module(mod)
            for fn in ('parse_data', 'indicators', 'run_backtest'):
                if not hasattr(mod, fn):
                    raise RuntimeError(f'Backtest module missing "{fn}": {module_path}')
            effective_rule = mapping_rule
            if explicit_script:
                effective_rule = 'explicit_map' if module_path.name.lower() == explicit_script.lower() else 'fallback'
            return mod, module_path, effective_rule
        except Exception as e:
            errs.append(f'{module_path}: {e}')
            continue
    raise RuntimeError('Failed to load any backtest module. ' + ' | '.join(errs))


def load_parser_module():
    eng = current_engine_meta() or {}
    eng_name = str(eng.get('file') or '')
    if eng_name:
        mod, _, _ = resolve_engine_backtest_module(eng_name)
        return mod

    # hard fallback
    for fallback in ('run_survival_v7_backtest.py', 'run_survival_v3_backtest.py'):
        p = DRIVER_DIR / fallback
        if p.exists():
            spec = importlib.util.spec_from_file_location(f'backtest_{p.stem}', str(p))
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = mod
                spec.loader.exec_module(mod)
                if hasattr(mod, 'parse_data'):
                    return mod
    raise RuntimeError('No parser module found in driver.')


def dataset_dirs():
    return {
        'year': DATA_ROOT / 'Year',
        'month': DATA_ROOT / 'Month',
        'week': DATA_ROOT / 'Week',
        'day': DATA_ROOT / 'Day',
    }


def list_files(folder: Path, prefix: str):
    if not folder.exists():
        return []
    return sorted([p.name for p in folder.glob(f'{prefix}_*.csv')])


def ensure_day_files():
    day_dir = DATA_ROOT / 'Day'
    day_dir.mkdir(parents=True, exist_ok=True)
    has_any = any(day_dir.glob('Day_*.csv'))
    if has_any:
        return

    src = DATA_ROOT / 'XAUUSDM5-all.csv'
    if not src.exists():
        return

    parser_mod = load_parser_module()
    df = parser_mod.parse_data(src)
    if df.empty:
        return
    df['date_only'] = df['time'].dt.strftime('%Y-%m-%d')
    dates = sorted(df['date_only'].unique())
    for i, d in enumerate(dates, start=1):
        part = df[df['date_only'] == d].copy()
        out = day_dir / f'Day_{i:03d}_{d}.csv'
        out_df = part[['time', 'open', 'high', 'low', 'close', 'volume']].copy()
        out_df['time'] = out_df['time'].dt.strftime('%Y-%m-%d %H:%M:%S')
        out_df.to_csv(out, index=False, encoding='utf-8-sig')


def get_dataset_catalog():
    ensure_day_files()
    d = dataset_dirs()
    return {
        'year': list_files(d['year'], 'Year'),
        'month': list_files(d['month'], 'Month'),
        'week': list_files(d['week'], 'Week'),
        'day': list_files(d['day'], 'Day'),
    }


def current_dataset_meta():
    m = read_json(CURRENT_DATASET_FILE, None)
    if m:
        return m
    data = read_json(DATA_FILE, {})
    src = str(data.get('source_file') or '')
    return {'bucket': None, 'file': Path(src).name if src else None, 'source_file': src}


def set_current_dataset_meta(bucket: str, file_name: str, source_file: str):
    CURRENT_DATASET_FILE.write_text(
        json.dumps({'bucket': bucket, 'file': file_name, 'source_file': source_file}, ensure_ascii=False),
        encoding='utf-8'
    )


def resolve_current_dataset_selection():
    """
    优先使用 current_dataset.json；缺失时从 ohlc.json source_file 反推。
    """
    cur = current_dataset_meta()
    bucket = (cur.get('bucket') or '').lower() if isinstance(cur, dict) else ''
    file_name = (cur.get('file') or '').strip() if isinstance(cur, dict) else ''
    if bucket and file_name:
        return bucket, file_name

    data = read_json(DATA_FILE, {}) or {}
    src_file = Path(str(data.get('source_file') or '')).name
    if src_file:
        b = infer_bucket_from_file_name(src_file)
        if b:
            return b, src_file
    return None, None


def resolve_dataset_source(bucket: str, file_name: str):
    cat = get_dataset_catalog()
    bucket = str(bucket).lower()
    if bucket not in cat:
        raise ValueError(f'invalid bucket: {bucket}')
    if file_name not in cat[bucket]:
        raise ValueError(f'file not found in bucket={bucket}: {file_name}')
    folder = dataset_dirs()[bucket]
    src = folder / file_name
    if not src.exists():
        raise FileNotFoundError(f'source not found: {src}')
    return src


def resolve_existing_dataset_selection():
    """
    返回一个当前可用的数据选择 (bucket, file)。
    若current_dataset已失效，则自动回退到可用文件（优先week）。
    """
    b, f = resolve_current_dataset_selection()
    if b and f:
        try:
            resolve_dataset_source(b, f)
            return b, f
        except Exception:
            pass

    cat = get_dataset_catalog()
    prefer_order = ['week', 'day', 'month', 'year']
    for bucket in prefer_order:
        files = cat.get(bucket, [])
        if files:
            return bucket, files[-1]
    return None, None


def build_ohlc_payload(df: pd.DataFrame, source_file: Path, engine_file: str, engine_module_path: Path, build_id: str):
    generated_at = datetime.now().isoformat(timespec='milliseconds')
    rows = []
    def _pick(row, a: str, b: str | None = None):
        if a in row.index:
            return row[a]
        if b and b in row.index:
            return row[b]
        raise KeyError(a)

    for _, r in df.iterrows():
        bb_mid = _pick(r, 'mid', 'bb_mid')
        bb_up = _pick(r, 'up', 'bb_up')
        bb_down = _pick(r, 'down', 'bb_down')
        rows.append({
            'time': r['time'].strftime('%Y-%m-%dT%H:%M:%S'),
            'open': float(r['open']),
            'high': float(r['high']),
            'low': float(r['low']),
            'close': float(r['close']),
            'volume': float(r['volume']),
            'spread': float(r.get('spread', 0.0)),
            'ema5': (None if pd.isna(r['ema5']) else float(r['ema5'])),
            'ema20': (None if pd.isna(r['ema20']) else float(r['ema20'])),
            'bb_mid': (None if pd.isna(bb_mid) else float(bb_mid)),
            'bb_up': (None if pd.isna(bb_up) else float(bb_up)),
            'bb_down': (None if pd.isna(bb_down) else float(bb_down)),
        })

    return {
        'symbol': 'XAUUSD',
        'timeframe': 'M5',
        'build_id': build_id,
        'bollinger_deviation': BOLLINGER_DEVIATION,
        'source_file': str(source_file),
        'engine_file': engine_file,
        'engine_module': str(engine_module_path),
        'generated_at': generated_at,
        'filter_start': None,
        'count': len(rows),
        'rows': rows,
    }


def build_trades_payload(
    df: pd.DataFrame,
    source_file: Path,
    engine_file: str,
    engine_module_path: Path,
    mapping_rule: str,
    run_backtest_func,
    build_id: str,
    common_params: dict,
):
    generated_at = datetime.now().isoformat(timespec='milliseconds')
    try:
        res = run_backtest_func(df, common_params)
    except TypeError:
        res = run_backtest_func(df)
    # KLine_* 引擎默认不做公共风控裁剪，避免与策略定义产生偏移
    is_kline_engine = str(engine_file or '').lower().startswith('kline_')
    force_apply_for_kline = bool(common_params.get('apply_common_limits_for_kline', False))
    common_limits_applied = (not is_kline_engine) or force_apply_for_kline
    if common_limits_applied:
        res = apply_common_limits_to_result(res, common_params)

    trades = []
    for i, t in enumerate(res.get('trades', [])):
        entry_price_raw = t.get('entry_price', t.get('entry'))
        exit_price_raw = t.get('exit_price', t.get('exit'))
        if entry_price_raw is None or exit_price_raw is None:
            raise RuntimeError(f'trade missing entry/exit price fields: {t}')
        trades.append({
            'id': i + 1,
            'entry_time': pd.to_datetime(t['entry_time']).strftime('%Y-%m-%dT%H:%M:%S'),
            'exit_time': pd.to_datetime(t['exit_time']).strftime('%Y-%m-%dT%H:%M:%S'),
            'side': t['side'],
            'entry_price': float(entry_price_raw),
            'exit_price': float(exit_price_raw),
            'pnl': float(t['pnl']),
            'reason': str(t['reason']),
        })

    summary_src = res.get('summary', {}) if isinstance(res.get('summary'), dict) else {}
    bars_val = res.get('bars', summary_src.get('bars', len(df)))
    if bars_val is None:
        bars_val = len(df)
    start_val = res.get('start', summary_src.get('start'))
    if start_val is None and not df.empty and 'time' in df.columns:
        start_val = df.iloc[0]['time']
    end_val = res.get('end', summary_src.get('end'))
    if end_val is None and not df.empty and 'time' in df.columns:
        end_val = df.iloc[-1]['time']
    signals_val = res.get('signals', summary_src.get('signals', {}))
    gate_pass_val = res.get('gate_pass', summary_src.get('gate_pass', {}))
    blocked_by_daily_loss_val = res.get('blocked_by_daily_loss', summary_src.get('blocked_by_daily_loss', 0))

    wins = sum(1 for t in trades if float(t['pnl']) > 0)
    losses = len(trades) - wins
    net_pnl = sum(float(t['pnl']) for t in trades)
    win_rate = (wins / len(trades) * 100.0) if trades else 0.0
    initial_balance = 1000.0
    running = initial_balance
    peak = running
    max_dd_pct = 0.0
    for t in trades:
        running += float(t['pnl'])
        peak = max(peak, running)
        if peak > 0:
            dd = (peak - running) / peak * 100.0
            max_dd_pct = max(max_dd_pct, dd)
    final_balance = initial_balance + net_pnl

    trade_pnl_list = []
    day_map = defaultdict(lambda: {'date': '', 'trades': 0, 'wins': 0, 'losses': 0, 'net_pnl': 0.0})
    for t in trades:
        exit_dt = pd.to_datetime(t['exit_time'])
        day_key = exit_dt.strftime('%Y-%m-%d')
        pnl = float(t['pnl'])
        trade_pnl_list.append({
            'id': int(t['id']),
            'date': day_key,
            'entry_time': t['entry_time'],
            'exit_time': t['exit_time'],
            'side': t['side'],
            'pnl': pnl,
            'reason': t['reason'],
        })
        row = day_map[day_key]
        row['date'] = day_key
        row['trades'] += 1
        row['wins'] += (1 if pnl > 0 else 0)
        row['losses'] += (1 if pnl <= 0 else 0)
        row['net_pnl'] += pnl

    daily_pnl_list = []
    balance = initial_balance
    for day_key in sorted(day_map.keys()):
        row = day_map[day_key]
        balance += row['net_pnl']
        daily_pnl_list.append({
            'date': row['date'],
            'trades': int(row['trades']),
            'wins': int(row['wins']),
            'losses': int(row['losses']),
            'net_pnl': float(row['net_pnl']),
            'balance': float(balance),
        })

    return {
        'summary': {
            'build_id': build_id,
            'bars': int(bars_val),
            'start': str(start_val),
            'end': str(end_val),
            'source_file': str(source_file),
            'engine_file': engine_file,
            'engine_module': str(engine_module_path),
            'mapping_rule': mapping_rule,
            'common_limits_applied': bool(common_limits_applied),
            'generated_at': generated_at,
            'filter_start': None,
            'signals': signals_val,
            'gate_pass': gate_pass_val,
            'trades': len(trades),
            'wins': int(wins),
            'losses': int(losses),
            'win_rate': float(win_rate),
            'net_pnl': float(net_pnl),
            'final_balance': float(final_balance),
            'max_dd_pct': float(max_dd_pct),
            'blocked_by_daily_loss': int(blocked_by_daily_loss_val),
            'common_params': common_params,
        },
        'trades': trades,
        'trade_pnl_list': trade_pnl_list,
        'daily_pnl_list': daily_pnl_list,
    }


def rebuild_dataset(bucket: str, file_name: str, engine_file_name: str | None = None):
    engine_name = engine_file_name or str((current_engine_meta() or {}).get('file') or '')
    if not engine_name:
        raise RuntimeError('No engine selected.')
    engine_mod, engine_module_path, mapping_rule = resolve_engine_backtest_module(engine_name)
    common_params = read_common_params()

    build_id = uuid4().hex[:12]
    src = resolve_dataset_source(bucket, file_name)
    df = engine_mod.parse_data(src)
    if df.empty:
        raise RuntimeError(f'empty source: {src}')
    df = engine_mod.indicators(df)
    # 指标列兼容：支持 mid/up/down 与 bb_mid/bb_up/bb_down 双命名。
    if 'mid' not in df.columns and 'bb_mid' in df.columns:
        df['mid'] = df['bb_mid']
    if 'up' not in df.columns and 'bb_up' in df.columns:
        df['up'] = df['bb_up']
    if 'down' not in df.columns and 'bb_down' in df.columns:
        df['down'] = df['bb_down']
    if 'bb_mid' not in df.columns and 'mid' in df.columns:
        df['bb_mid'] = df['mid']
    if 'bb_up' not in df.columns and 'up' in df.columns:
        df['bb_up'] = df['up']
    if 'bb_down' not in df.columns and 'down' in df.columns:
        df['bb_down'] = df['down']
    df['spread'] = 0.0

    ohlc_payload = build_ohlc_payload(df, src, engine_name, engine_module_path, build_id)
    trades_payload = build_trades_payload(
        df, src, engine_name, engine_module_path, mapping_rule, engine_mod.run_backtest, build_id, common_params
    )

    DATA_FILE.write_text(json.dumps(ohlc_payload, ensure_ascii=False), encoding='utf-8')
    TRADES_FILE.write_text(json.dumps(trades_payload, ensure_ascii=False), encoding='utf-8')
    set_current_dataset_meta(bucket, file_name, str(src))

    return {
        'bucket': bucket,
        'file': file_name,
        'engine': engine_name,
        'source_file': str(src),
        'build_id': build_id,
        'bars': ohlc_payload['count'],
        'trades': trades_payload['summary']['trades'],
    }


def build_comment_item(payload):
    now = datetime.now().isoformat(timespec='seconds')
    mode = str(payload.get('mode', 'bar'))

    base = {
        'id': uuid4().hex,
        'created_at': now,
        'mode': mode,
        'kind': str(payload.get('kind', 'obs')),
        'tag': str(payload.get('tag', '')),
        'comment': str(payload.get('comment', '')).strip(),
    }

    if not base['comment']:
        raise ValueError('comment is empty')

    if mode == 'range':
        required = ['start_time', 'end_time', 'start_index', 'end_index', 'price']
        miss = [k for k in required if k not in payload]
        if miss:
            raise ValueError(f'missing fields: {miss}')

        base.update({
            'start_time': str(payload['start_time']),
            'end_time': str(payload['end_time']),
            'start_index': int(payload['start_index']),
            'end_index': int(payload['end_index']),
            'price': float(payload['price']),
            # 兼容查询/显示
            'bar_time': str(payload.get('bar_time', payload['start_time'])),
            'bar_index': int(payload.get('bar_index', payload['start_index'])),
        })
    else:
        required = ['bar_time', 'bar_index', 'price']
        miss = [k for k in required if k not in payload]
        if miss:
            raise ValueError(f'missing fields: {miss}')

        base.update({
            'bar_time': str(payload['bar_time']),
            'bar_index': int(payload['bar_index']),
            'price': float(payload['price']),
        })

    return base


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def _json(self, payload, code=200):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _text(self, txt, code=200, ctype='text/plain; charset=utf-8'):
        body = txt.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self):
        length = int(self.headers.get('Content-Length', '0'))
        body = self.rfile.read(length).decode('utf-8')
        return json.loads(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/api/health':
            return self._json({'ok': True, 'time': datetime.now().isoformat()})

        if path == '/api/engines':
            return self._json({
                'ok': True,
                'catalog': list_engine_files(),
                'current': current_engine_meta(),
                'driver_dir': str(DRIVER_DIR),
            })

        if path == '/api/common-params':
            cfg = read_common_params()
            return self._json({
                'ok': True,
                'file': str(COMMON_PARAMS_FILE),
                'params': cfg,
            })

        if path == '/api/datasets':
            cat = get_dataset_catalog()
            cur = current_dataset_meta()
            return self._json({'ok': True, 'catalog': cat, 'current': cur})

        if path == '/api/ohlc':
            data = read_json(DATA_FILE, None)
            if data is None:
                return self._json({'ok': False, 'error': 'ohlc.json not found'}, 404)
            return self._json({'ok': True, 'data': data})

        if path == '/api/trades':
            data = read_json(TRADES_FILE, {'summary': {}, 'trades': []})
            return self._json({'ok': True, 'data': data})

        if path == '/api/comments':
            items = read_comments()
            qs = parse_qs(parsed.query)
            time_filter = qs.get('time', [None])[0]
            if time_filter:
                items = [x for x in items if x.get('bar_time') == time_filter or x.get('start_time') == time_filter]
            return self._json({'ok': True, 'count': len(items), 'items': items})

        if path == '/api/comments.csv':
            items = read_comments()
            headers = [
                'id', 'created_at', 'mode', 'bar_time', 'bar_index', 'start_time', 'end_time',
                'start_index', 'end_index', 'price', 'kind', 'tag', 'comment'
            ]
            lines = [','.join(headers)]
            for it in items:
                row = []
                for h in headers:
                    v = str(it.get(h, '')).replace('"', '""')
                    row.append(f'"{v}"')
                lines.append(','.join(row))
            return self._text('\n'.join(lines), 200, 'text/csv; charset=utf-8')

        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/api/comments':
            try:
                payload = self._read_json_body()
                item = build_comment_item(payload)
            except Exception as e:
                return self._json({'ok': False, 'error': f'bad request: {e}'}, 400)

            append_comment(item)
            return self._json({'ok': True, 'item': item}, 201)

        if path == '/api/comments/batch':
            try:
                payload = self._read_json_body()
                items = payload.get('items', [])
                if not isinstance(items, list) or len(items) == 0:
                    raise ValueError('items must be non-empty list')

                built = []
                for raw in items:
                    built.append(build_comment_item(raw))
            except Exception as e:
                return self._json({'ok': False, 'error': f'bad request: {e}'}, 400)

            for it in built:
                append_comment(it)

            return self._json({'ok': True, 'count': len(built), 'items': built}, 201)

        if path == '/api/comments/clear':
            try:
                LOG_FILE.write_text('', encoding='utf-8')
            except Exception as e:
                return self._json({'ok': False, 'error': f'clear failed: {e}'}, 500)
            return self._json({'ok': True, 'count': 0}, 200)

        if path == '/api/comments/submit':
            try:
                payload = self._read_json_body() if int(self.headers.get('Content-Length', '0')) > 0 else {}
                engine_file = str(payload.get('engine_file', '')).strip() if isinstance(payload, dict) else ''
                result = archive_temp_comments(engine_file=engine_file or None)
            except Exception as e:
                return self._json({'ok': False, 'error': f'submit failed: {e}'}, 500)
            return self._json({'ok': True, **result}, 200)

        if path == '/api/engines/select':
            try:
                payload = self._read_json_body()
                file_name = str(payload.get('file', '')).strip()
                if not file_name:
                    raise ValueError('file is required')
                meta = set_current_engine(file_name)
                bucket, ds_file = resolve_existing_dataset_selection()
                rebuilt = None
                if bucket and ds_file:
                    rebuilt = rebuild_dataset(bucket, ds_file, file_name)
            except Exception as e:
                return self._json({'ok': False, 'error': f'bad request: {e}'}, 400)
            return self._json({'ok': True, 'meta': meta, 'rebuilt': rebuilt}, 200)

        if path == '/api/datasets/select':
            try:
                payload = self._read_json_body()
                bucket = str(payload.get('bucket', '')).lower().strip()
                file_name = str(payload.get('file', '')).strip()
                if not bucket or not file_name:
                    raise ValueError('bucket and file are required')
                meta = rebuild_dataset(bucket, file_name)
            except Exception as e:
                return self._json({'ok': False, 'error': f'bad request: {e}'}, 400)
            return self._json({'ok': True, 'meta': meta}, 200)

        if path == '/api/common-params':
            try:
                payload = self._read_json_body()
                params = payload.get('params') if isinstance(payload, dict) else None
                if not isinstance(params, dict):
                    raise ValueError('params must be object')
                cfg = write_common_params(params)
            except Exception as e:
                return self._json({'ok': False, 'error': f'bad request: {e}'}, 400)
            return self._json({'ok': True, 'file': str(COMMON_PARAMS_FILE), 'params': cfg}, 200)

        return self._json({'ok': False, 'error': 'not found'}, 404)


if __name__ == '__main__':
    ensure_common_params()
    host, port = '127.0.0.1', 8765
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f'K-line debug system running at http://{host}:{port}')
    print(f'Data  : {DATA_FILE}')
    print(f'Trades: {TRADES_FILE}')
    print(f'Log   : {LOG_FILE}')
    httpd.serve_forever()
