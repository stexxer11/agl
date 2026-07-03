from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data'
CONFIG_PATH = ROOT / 'config.json'
DATA.mkdir(exist_ok=True)

DEFAULTS = {
    'agl_master_path': str(DATA / 'AGL_MASTER.xlsx'),
    'status_master_path': str(DATA / 'STATUS_MASTER_AGL.xlsx'),
    'client_master_path': str(DATA / 'CLIENT_MASTER.xlsx'),
    'saved_dir': str(ROOT / 'saved'),
    'exports_dir': str(ROOT / 'exports'),
    'supabase_database_url': '',
}



def load_config():
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
            return {**DEFAULTS, **data}
        except Exception:
            return DEFAULTS.copy()
    save_config(DEFAULTS)
    return DEFAULTS.copy()


def save_config(data: dict):
    base = load_config() if CONFIG_PATH.exists() else DEFAULTS.copy()
    cfg = {**base, **(data or {})}
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding='utf-8')
    return cfg


def resolve_path(value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else (ROOT / p)

def master_path(kind: str) -> Path:
    cfg = load_config()
    
    if kind == 'agl':
        key = 'agl_master_path'
    elif kind == 'status':
        key = 'status_master_path'
    elif kind == 'client':
        key = 'client_master_path'
    else:
        raise ValueError(f'Master desconocido: {kind}')
    return resolve_path(cfg[key])
