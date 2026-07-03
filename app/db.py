from pathlib import Path
import json
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
SAVED = ROOT / 'saved'
SAVED.mkdir(exist_ok=True)
INDEX_PATH = SAVED / '_cases_index.json'


def saved_dir():
    cfg_path = ROOT / 'config.json'
    try:
        cfg = json.loads(cfg_path.read_text(encoding='utf-8'))
        d = Path(cfg.get('saved_dir') or SAVED)
        if not d.is_absolute():
            d = ROOT / d
    except Exception:
        d = SAVED
    d.mkdir(parents=True, exist_ok=True)
    return d


def _index_path():
    return saved_dir() / '_cases_index.json'


def _read_index():
    p = _index_path()
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding='utf-8'))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write_index(rows):
    _index_path().write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')


def init_db():
    """No usa SQLite. Los expedientes se guardan como JSON y se indexan en _cases_index.json."""
    saved_dir()
    if not _index_path().exists():
        _write_index([])


def safe_name(text: str) -> str:
    text = str(text or '').strip() or 'BORRADOR'
    return ''.join(ch if ch.isalnum() or ch in ('-', '_') else '_' for ch in text)[:120]


def _next_id(rows):
    ids = [int(x.get('id') or 0) for x in rows if str(x.get('id') or '').isdigit()]
    return (max(ids) + 1) if ids else 1


def case_filename(payload: dict):
    form = payload.get('form') or {}
    agl_ref = payload.get('agl_ref') or form.get('agl_ref') or 'AGL'
    customer = form.get('customer') or form.get('bill_to') or payload.get('customer') or 'CLIENTE'
    date = payload.get('date') or datetime.now().strftime('%Y-%m-%d')
    return f"{safe_name(agl_ref)}_{safe_name(customer)}_{safe_name(date)}.json"


def save_case(payload: dict):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    rows = _read_index()
    case_id = payload.get('case_id') or payload.get('id')
    if not case_id:
        case_id = _next_id(rows)
    case_id = int(case_id)

    form = payload.get('form') or {}
    agl_ref = payload.get('agl_ref') or form.get('agl_ref') or ''
    customer = form.get('customer') or form.get('bill_to') or ''
    warehouse = payload.get('warehouse') or (payload.get('result') or {}).get('warehouse') or ''
    title = payload.get('title') or f"{agl_ref} {customer}".strip()
    filename = payload.get('filename') or case_filename(payload)

    payload['case_id'] = case_id
    payload['filename'] = filename
    payload.setdefault('metadata', {})
    payload['metadata']['saved_at'] = datetime.now().isoformat(timespec='seconds')

    data = json.dumps(payload, ensure_ascii=False, indent=2)
    (saved_dir() / filename).write_text(data, encoding='utf-8')

    record = {
        'id': case_id,
        'agl_ref': agl_ref,
        'customer': customer,
        'warehouse': warehouse,
        'title': title,
        'filename': filename,
        'created_at': now,
        'updated_at': now,
    }

    found = False
    for i, r in enumerate(rows):
        if int(r.get('id') or 0) == case_id:
            record['created_at'] = r.get('created_at') or now
            rows[i] = record
            found = True
            break
    if not found:
        rows.append(record)
    rows.sort(key=lambda x: x.get('updated_at',''), reverse=True)
    _write_index(rows)
    return case_id, filename


def list_cases(q: str = ''):
    qn = str(q or '').lower().strip()
    rows = _read_index()
    if qn:
        rows = [r for r in rows if qn in json.dumps(r, ensure_ascii=False).lower()]
    return rows[:200]


def get_case(case_id: int):
    rows = _read_index()
    rec = None
    for r in rows:
        if int(r.get('id') or 0) == int(case_id):
            rec = dict(r)
            break
    if not rec:
        return None
    p = saved_dir() / rec.get('filename','')
    try:
        rec['payload'] = json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        rec['payload'] = {}
    return rec


# Compatibilidad con botones viejos de documento: se redirige al mismo JSON único.
def save_document(payload: dict):
    case_id, _filename = save_case(payload)
    return case_id


def list_documents(q: str = ''):
    return list_cases(q)


def get_document(doc_id: int):
    return get_case(doc_id)
