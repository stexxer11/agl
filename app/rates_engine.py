from pathlib import Path
import math, re
import pandas as pd

REQUIRED_ALIASES = {
    'wh': ['WH', 'WAREHOUSE'],
    'warehouse_item': ['Warehouse Items', 'Warehouse Item', 'WH Item'],
    'agl_item': ['AGL Items', 'AGL Item'],
    'cost': ['Cost'],
    'sell': ['Sell'],
    'warehouse_unit': ['Warehouse Unit', 'WH Unit'],
    'agl_unit': ['AGL Unit'],
    'warehouse_period': ['day / week / month Warehouse', 'WH Period', 'Period Warehouse'],
    'agl_period': ['day / week / month AGL', 'AGL Period', 'Period AGL'],
    'minimum_warehouse': ['Minimum Warehouse', 'Min WH'],
    'minimum_agl': ['Minimum AGL', 'Min AGL'],
}

def norm(s):
    return re.sub(r'[^A-Z0-9]+', ' ', str(s or '').upper()).strip()

def clean(v):
    if v is None: return ''
    if isinstance(v,float) and math.isnan(v): return ''
    return str(v).strip()

def parse_num(v):
    if v is None or v == '': return 0.0
    if isinstance(v, (int,float)) and not pd.isna(v): return float(v)
    s=str(v).replace('B/.','').replace('$','').replace('USD','').replace(',','').strip()
    if s in ['', '-', '--', 'nan', 'None']: return 0.0
    if s.endswith('%'):
        try: return float(s[:-1])/100
        except Exception: return 0.0
    try: return float(s)
    except Exception: return 0.0

def has_value(v):
    if v is None or pd.isna(v): return False
    t=str(v).strip()
    return t != '' and t.lower() not in {'nan','none'}

def find_col(columns, aliases):
    ncols={norm(c):c for c in columns}
    for a in aliases:
        na=norm(a)
        if na in ncols: return ncols[na]
    for a in aliases:
        na=norm(a)
        for nc, orig in ncols.items():
            if na and (na in nc or nc in na): return orig
    return None

def load_rates(path: Path):
    xls = pd.ExcelFile(path)
    sheet = 'WH' if 'WH' in xls.sheet_names else ('WAREHOUSES' if 'WAREHOUSES' in xls.sheet_names else xls.sheet_names[0])
    df = pd.read_excel(path, sheet_name=sheet)
    df.columns=[str(c).strip() for c in df.columns]
    mapped={}
    for key, aliases in REQUIRED_ALIASES.items():
        col=find_col(df.columns, aliases)
        mapped[key]=col
    rows=[]
    for idx, r in df.iterrows():
        wh=clean(r.get(mapped['wh'])) if mapped['wh'] else ''
        agl=clean(r.get(mapped['agl_item'])) if mapped['agl_item'] else ''
        witem=clean(r.get(mapped['warehouse_item'])) if mapped['warehouse_item'] else ''
        if not wh or (not agl and not witem):
            continue
        cost_val = r.get(mapped['cost']) if mapped['cost'] else None
        sell_val = r.get(mapped['sell']) if mapped['sell'] else None
        if not has_value(cost_val) or not has_value(sell_val) or not agl:
            continue
        rows.append({
            'id': len(rows)+1,
            'wh': wh,
            'warehouse_item': witem,
            'agl_item': agl,
            'cost': parse_num(cost_val),
            'sell': parse_num(sell_val),
            'warehouse_unit': clean(r.get(mapped['warehouse_unit'])) if mapped['warehouse_unit'] else '',
            'agl_unit': clean(r.get(mapped['agl_unit'])) if mapped['agl_unit'] else '',
            'warehouse_period': clean(r.get(mapped['warehouse_period'])) if mapped['warehouse_period'] else '',
            'agl_period': clean(r.get(mapped['agl_period'])) if mapped['agl_period'] else '',
            'minimum_warehouse': parse_num(r.get(mapped['minimum_warehouse'])) if mapped['minimum_warehouse'] else 0.0,
            'minimum_agl': parse_num(r.get(mapped['minimum_agl'])) if mapped['minimum_agl'] else 0.0,
            'source_row': int(idx)+2,
        })
    whs=sorted({r['wh'] for r in rows})
    return {'rows': rows, 'warehouses': whs, 'sheet': sheet}
