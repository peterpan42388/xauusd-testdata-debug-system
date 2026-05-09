from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path
import json
from datetime import datetime
from uuid import uuid4
import sys
import importlib.util
import pandas as pd

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

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
if not LOG_FILE.exists():
    LOG_FILE.touch()


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


def list_engine_files():
    if not DRIVER_DIR.exists():
        return []
    mq5 = sorted([p.name for p in DRIVER_DIR.glob('*.mq5')])
    py_backtests = sorted([p.name for p in DRIVER_DIR.glob('run_survival_v*_backtest.py')])
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
    if engine_file_name.endswith('.py'):
        candidates.extend([DRIVER_DIR / engine_file_name, DATA_ROOT / engine_file_name])
    else:
        stem = Path(engine_file_name).stem
        candidate_name = stem.replace('XAUUSD_Survival', 'run_survival').lower() + '_backtest.py'
        candidates.extend([DRIVER_DIR / candidate_name, DATA_ROOT / candidate_name])

    candidates.extend([
        DRIVER_DIR / 'run_survival_v7_backtest.py',
        DATA_ROOT / 'run_survival_v7_backtest.py',
        DRIVER_DIR / 'run_survival_v3_backtest.py',
        DATA_ROOT / 'run_survival_v3_backtest.py',
    ])

    module_path = None
    for p in candidates:
        if p.exists():
            module_path = p
            break
    if module_path is None:
        raise FileNotFoundError('No backtest module found in driver/TestData.')

    spec = importlib.util.spec_from_file_location(f'backtest_{module_path.stem}', str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Failed to load backtest module: {module_path}')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for fn in ('parse_data', 'indicators', 'run_backtest'):
        if not hasattr(mod, fn):
            raise RuntimeError(f'Backtest module missing "{fn}": {module_path}')
    return mod, module_path


def load_parser_module():
    eng = current_engine_meta() or {}
    eng_name = str(eng.get('file') or '')
    if eng_name:
        mod, _ = resolve_engine_backtest_module(eng_name)
        return mod

    # hard fallback
    for fallback in ('run_survival_v7_backtest.py', 'run_survival_v3_backtest.py'):
        p = DRIVER_DIR / fallback
        if p.exists():
            spec = importlib.util.spec_from_file_location(f'backtest_{p.stem}', str(p))
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
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


def build_ohlc_payload(df: pd.DataFrame, source_file: Path, engine_file: str, engine_module_path: Path):
    generated_at = datetime.now().isoformat(timespec='milliseconds')
    rows = []
    for _, r in df.iterrows():
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
            'bb_mid': (None if pd.isna(r['mid']) else float(r['mid'])),
            'bb_up': (None if pd.isna(r['up']) else float(r['up'])),
            'bb_down': (None if pd.isna(r['down']) else float(r['down'])),
        })

    return {
        'symbol': 'XAUUSD',
        'timeframe': 'M5',
        'bollinger_deviation': BOLLINGER_DEVIATION,
        'source_file': str(source_file),
        'engine_file': engine_file,
        'engine_module': str(engine_module_path),
        'generated_at': generated_at,
        'filter_start': None,
        'count': len(rows),
        'rows': rows,
    }


def build_trades_payload(df: pd.DataFrame, source_file: Path, engine_file: str, engine_module_path: Path, run_backtest_func):
    generated_at = datetime.now().isoformat(timespec='milliseconds')
    res = run_backtest_func(df)
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

    return {
        'summary': {
            'bars': int(res['bars']),
            'start': str(res['start']),
            'end': str(res['end']),
            'source_file': str(source_file),
            'engine_file': engine_file,
            'engine_module': str(engine_module_path),
            'generated_at': generated_at,
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


def rebuild_dataset(bucket: str, file_name: str, engine_file_name: str | None = None):
    engine_name = engine_file_name or str((current_engine_meta() or {}).get('file') or '')
    if not engine_name:
        raise RuntimeError('No engine selected.')
    engine_mod, engine_module_path = resolve_engine_backtest_module(engine_name)

    src = resolve_dataset_source(bucket, file_name)
    df = engine_mod.parse_data(src)
    if df.empty:
        raise RuntimeError(f'empty source: {src}')
    df = engine_mod.indicators(df)
    df['spread'] = 0.0

    ohlc_payload = build_ohlc_payload(df, src, engine_name, engine_module_path)
    trades_payload = build_trades_payload(df, src, engine_name, engine_module_path, engine_mod.run_backtest)

    DATA_FILE.write_text(json.dumps(ohlc_payload, ensure_ascii=False), encoding='utf-8')
    TRADES_FILE.write_text(json.dumps(trades_payload, ensure_ascii=False), encoding='utf-8')
    set_current_dataset_meta(bucket, file_name, str(src))

    return {
        'bucket': bucket,
        'file': file_name,
        'engine': engine_name,
        'source_file': str(src),
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

        if path == '/api/engines/select':
            try:
                payload = self._read_json_body()
                file_name = str(payload.get('file', '')).strip()
                if not file_name:
                    raise ValueError('file is required')
                meta = set_current_engine(file_name)
                bucket, ds_file = resolve_current_dataset_selection()
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

        return self._json({'ok': False, 'error': 'not found'}, 404)


if __name__ == '__main__':
    host, port = '127.0.0.1', 8765
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f'K-line debug system running at http://{host}:{port}')
    print(f'Data  : {DATA_FILE}')
    print(f'Trades: {TRADES_FILE}')
    print(f'Log   : {LOG_FILE}')
    httpd.serve_forever()
