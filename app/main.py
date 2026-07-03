from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from datetime import datetime
import shutil
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

from .config import ROOT, load_config, save_config, master_path
from .calc import generate
from .supabase_engine import (
    init_supabase_schema, db_status,
    sync_rates_from_excel, sync_status_from_excel, sync_client_from_excel,
    get_warehouses, get_rates_by_warehouse, get_all_rates,
    lookup_status, client_lists_db, client_lookup,
    save_case_db, list_cases_db, get_case_db,
)

app = FastAPI(title='AGL Closing System V18 Supabase')
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])

STATIC = ROOT / 'static'
EXPORTS = ROOT / 'exports'
RUNTIME_CACHE = ROOT / 'runtime_cache'
EXPORTS.mkdir(exist_ok=True)
RUNTIME_CACHE.mkdir(exist_ok=True)

STATE = {
    'warehouses': [],
    'rates_count': 0,
    'last_sync_at': '',
    'syncing': False,
    'errors': {},
    'snapshots': {},
}


def _safe_snapshot(kind: str, source_path: Path):
    source_path = Path(source_path)
    if not source_path.exists():
        raise FileNotFoundError(f'No existe archivo master: {source_path}')
    ext = source_path.suffix or '.xlsx'
    target = RUNTIME_CACHE / f'{kind}_runtime{ext}'
    tmp = RUNTIME_CACHE / f'{kind}_runtime_tmp{ext}'
    try:
        if tmp.exists():
            try: tmp.unlink()
            except Exception: pass
        shutil.copy2(source_path, tmp)
        try:
            if target.exists(): target.unlink()
        except Exception:
            pass
        try:
            tmp.replace(target)
        except Exception:
            shutil.copy2(tmp, target)
            try: tmp.unlink()
            except Exception: pass
        return target, {'source': str(source_path), 'snapshot': str(target), 'snapshot_created': True}
    except Exception as exc:
        try:
            if tmp.exists(): tmp.unlink()
        except Exception: pass
        if target.exists():
            return target, {'source': str(source_path), 'snapshot': str(target), 'snapshot_created': False, 'warning': str(exc)}
        raise


def refresh_state_from_db():
    try:
        STATE['warehouses'] = get_warehouses()
        STATE['rates_count'] = sum(1 for _ in get_all_rates())
    except Exception as exc:
        STATE.setdefault('errors', {})['db_state'] = str(exc)


def sync_masters_to_db(force=True):
    cfg = load_config()
    result = {'ok': True, 'backend': 'supabase_postgresql', 'errors': {}}
    STATE['syncing'] = True
    STATE['errors'] = {}
    try:
        init_supabase_schema()
    except Exception as exc:
        STATE['syncing'] = False
        STATE['errors']['supabase'] = str(exc)
        return {'ok': False, 'backend': 'supabase_postgresql', 'errors': {'supabase': str(exc)}, 'message': 'No se pudo conectar/inicializar Supabase'}

    try:
        src = master_path('agl')
        snap_path, snap = _safe_snapshot('agl_master', src)
        info = sync_rates_from_excel(snap_path)
        result['agl'] = {**info, **snap, 'source_path': str(src)}
        STATE['snapshots']['agl'] = snap
    except Exception as exc:
        result['ok'] = False
        result['errors']['agl'] = str(exc)
        STATE['errors']['agl'] = str(exc)

    try:
        src = master_path('status')
        snap_path, snap = _safe_snapshot('status_master', src)
        info = sync_status_from_excel(snap_path)
        result['status'] = {**info, **snap, 'source_path': str(src)}
        STATE['snapshots']['status'] = snap
    except Exception as exc:
        result['ok'] = False
        result['errors']['status'] = str(exc)
        STATE['errors']['status'] = str(exc)

    try:
        src = master_path('client')
        snap_path, snap = _safe_snapshot('client_master', src)
        info = sync_client_from_excel(snap_path)
        result['client'] = {**info, **snap, 'source_path': str(src)}
        STATE['snapshots']['client'] = snap
    except Exception as exc:
        result['ok'] = False
        result['errors']['client'] = str(exc)
        STATE['errors']['client'] = str(exc)

    STATE['last_sync_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    STATE['syncing'] = False
    refresh_state_from_db()
    result['warehouses'] = STATE.get('warehouses') or []
    result['rates_count'] = STATE.get('rates_count') or 0
    result['last_sync_at'] = STATE['last_sync_at']
    return result


@app.on_event('startup')
def startup():
    try:
        init_supabase_schema()
        refresh_state_from_db()
    except Exception as exc:
        STATE['errors']['startup'] = str(exc)


@app.get('/')
def home():
    return FileResponse(STATIC / 'index.html')

app.mount('/static', StaticFiles(directory=str(STATIC)), name='static')


@app.get('/api/config')
def api_config():
    return {'config': load_config(), 'state': {'backend': 'supabase_postgresql', 'warehouses': STATE.get('warehouses', []), 'rates_count': STATE.get('rates_count', 0), 'last_sync_at': STATE.get('last_sync_at',''), 'syncing': STATE.get('syncing', False), 'errors': STATE.get('errors', {})}}


@app.post('/api/config')
def api_save_config(payload: dict):
    cfg = save_config(payload or {})
    try:
        init_supabase_schema()
        refresh_state_from_db()
        return {'ok': True, 'config': cfg, 'state': {'backend': 'supabase_postgresql', **STATE}}
    except Exception as exc:
        STATE['errors']['config'] = str(exc)
        return {'ok': False, 'config': cfg, 'error': str(exc), 'state': STATE}


@app.post('/api/reload')
def api_reload(payload: dict = None):
    return sync_masters_to_db(force=True)


@app.get('/api/db-status')
def api_db_status():
    try:
        return db_status()
    except Exception as exc:
        return {'ok': False, 'backend': 'supabase_postgresql', 'error': str(exc)}


@app.get('/api/sync-status')
def api_sync_status():
    return {'ok': True, 'syncing': STATE.get('syncing', False), 'last_sync_at': STATE.get('last_sync_at',''), 'errors': STATE.get('errors', {})}


@app.get('/api/warehouses')
def api_warehouses():
    try:
        whs = get_warehouses()
        STATE['warehouses'] = whs
        return {'warehouses': whs}
    except Exception as exc:
        return {'warehouses': [], 'error': str(exc)}


@app.get('/api/warehouse/{warehouse}')
def api_warehouse(warehouse: str):
    try:
        return {'warehouse': warehouse, 'rows': get_rates_by_warehouse(warehouse)}
    except Exception as exc:
        return {'warehouse': warehouse, 'rows': [], 'error': str(exc)}


@app.get('/api/status/{agl_ref}')
def api_status(agl_ref: str):
    try:
        found = lookup_status(agl_ref)
        if found.get('found'):
            f = found.get('form') or {}
            enriched = client_lookup(f.get('customer') or f.get('bill_to') or '', f.get('brand') or '')
            if enriched.get('client_found'):
                f['customer'] = enriched.get('cliente') or f.get('customer') or ''
                f['bill_to'] = enriched.get('bill_to') or enriched.get('cliente') or f.get('bill_to') or f.get('customer') or ''
                f['ruc'] = enriched.get('ruc') or ''
                f['address'] = enriched.get('address') or ''
                f['phone'] = enriched.get('phone') or ''
                f['email'] = enriched.get('email') or ''
                f['payment'] = enriched.get('payment') or f.get('payment') or ''
            else:
                f.setdefault('address',''); f.setdefault('phone',''); f.setdefault('email',''); f.setdefault('payment','')
            if enriched.get('brand_found'):
                f['brand'] = enriched.get('brand') or f.get('brand') or ''
                f['description'] = enriched.get('description') or f.get('description') or ''
            f['_client_master'] = enriched
            found['form'] = f
        return found
    except Exception as exc:
        return {'found': False, 'message': 'Error buscando AGL Ref en Supabase', 'error': str(exc)}


@app.get('/api/client-lists')
def api_client_lists():
    try:
        return client_lists_db()
    except Exception as exc:
        return {'ok': False, 'error': str(exc), 'clients': [], 'brands': [], 'origins': [], 'destinations': [], 'direction_pairs': []}


@app.get('/api/client-lookup')
def api_client_lookup(customer: str = '', brand: str = ''):
    try:
        return {'ok': True, **client_lookup(customer or '', brand or '')}
    except Exception as exc:
        return {'ok': False, 'error': str(exc), 'client_found': False, 'brand_found': False}


@app.post('/api/calculate')
def api_calculate(payload: dict):
    wh = payload.get('warehouse') or payload.get('wh')
    form = payload.get('form') or {}
    service_qtys = payload.get('service_qtys') or {}
    rates = get_all_rates()
    return generate(wh, form, rates, service_qtys)


@app.post('/api/save-case')
def api_save_case(payload: dict):
    case_id, filename = save_case_db(payload)
    return {'ok': True, 'id': case_id, 'filename': filename, 'backend': 'supabase'}


@app.get('/api/cases')
def api_cases(q: str = ''):
    return {'cases': list_cases_db(q)}


@app.get('/api/cases/{case_id}')
def api_case(case_id: int):
    d = get_case_db(case_id)
    return {'found': bool(d), 'case': d}


@app.get('/api/inspect')
def api_inspect():
    return {'ok': True, 'mode': 'V18_SUPABASE_POSTGRESQL', 'config': load_config(), 'state': STATE, 'db': db_status() if not STATE.get('errors') else {}}


@app.post('/api/export-html')
def api_export_html(payload: dict):
    agl_ref = payload.get('agl_ref') or 'AGL'
    doc_type = payload.get('doc_type') or 'DOCUMENTO'
    doc_no = payload.get('doc_no') or 'BORRADOR'
    html = payload.get('html') or ''
    safe = ''.join(ch if ch.isalnum() or ch in ('-','_') else '_' for ch in f"{agl_ref}_{doc_type}_{doc_no}_{datetime.now().strftime('%Y-%m-%d')}")
    out_dir = Path(load_config().get('exports_dir') or EXPORTS)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f'{safe}.html'
    out.write_text(html, encoding='utf-8')
    return {'ok': True, 'path': str(out), 'filename': out.name}
