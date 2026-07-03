from pathlib import Path
import re, math
import pandas as pd

PREFERRED_STATUS_SHEET = 'STATUS CARGAS'


def norm(s):
    return re.sub(r'[^A-Z0-9]+', ' ', str(s or '').upper()).strip()


def norm_text(s):
    return re.sub(r'[^A-Z0-9]+', '', str(s or '').upper()).strip()


def clean(v):
    if v is None:
        return ''
    try:
        if pd.isna(v):
            return ''
    except Exception:
        pass
    if isinstance(v, float) and math.isnan(v):
        return ''
    t = str(v).strip()
    if t.lower() in {'#n/a', 'nan', 'nat', 'none'}:
        return ''
    return t


def parse_num(v):
    t = clean(v)
    if not t:
        return ''
    try:
        return float(str(t).replace(',', ''))
    except Exception:
        return t

ALIASES = {
    'agl_ref': ['AGL Ref.', 'AGL Ref', 'AGL REF', 'AGL Reference', 'REF AGL', 'REF'],
    'status': ['Status'],
    'invoice_no': ['AGL Inv.', 'AGL Inv', 'Invoice', 'Invoice No'],
    'po': ['PO#', 'PO', 'PO FACTURACION'],
    'brand': ['Brand', 'Marca'],
    'customer': ['Final Cust.', 'Final Cust', 'Final Cust. 1', 'Customer', 'Cliente'],
    'customer_2': ['Final Cust. 2', ' Final Cust. 2'],
    'comments': ['Comments', 'COMENTARIOS'],
    'release_agent': ['Release agent', 'Release Agent'],
    'warehouse_location': ['AGL WH Location', 'WH Location', 'Warehouse Location'],
    'pallets': ['Pallet', 'Pallets', 'PALLET'],
    'gross_weight': ['Weight (Kg)', 'Weight Kg', 'Gross Weight', 'Peso Bruto'],
    'cbm': ['Cbm', 'CBM'],
    'inner_boxes': ['Units', 'Unidades', 'CAJAS HIJAS'],
    'master_boxes': ['Mastex Box', 'Master Box', 'Master Boxes', 'CAJAS MADRES'],
    'pick_up_date': ['Pick Up Date', 'Pickup Date'],
    'commercial_value': ['Valor Comercial Master', 'Commercial Value', 'Valor Comercial', 'Commercial Value Master'],
    'eta_wh': ['ETA AGL WH', 'ETA WH'],
    'transit_days': ['Transit Days'],
    'finish_required': ['Required Finish Date for Client'],
    'finish_date': ['Finish Date'],
    'release_date': ['Release Date'],
    'billing_company': ['Billing Company', 'Bill To', 'BILLING COMPANY'],
}


def find_col(columns, names):
    nmap = {norm(c): str(c).strip() for c in columns}
    for name in names:
        nn = norm(name)
        if nn in nmap:
            return nmap[nn]
    for name in names:
        nn = norm(name)
        for nc, orig in nmap.items():
            if nn and (nn in nc or nc in nn):
                return orig
    return None


def load_status_df(path: Path):
    """Carga Status Master SIEMPRE desde hoja Status Cargas.

    Esto evita que el programa tome hojas pequeñas como Status Gubrand.
    La comparación ignora mayúsculas, espacios y caracteres especiales.
    """
    xls = pd.ExcelFile(path)
    sheet = None
    for sh in xls.sheet_names:
        if norm(sh) == norm(PREFERRED_STATUS_SHEET):
            sheet = sh
            break
    if sheet is None:
        raise ValueError(f"No se encontró la hoja '{PREFERRED_STATUS_SHEET}'. Hojas disponibles: {xls.sheet_names}")

    df = pd.read_excel(path, sheet_name=sheet, dtype=str)
    df.columns = [str(c).strip() for c in df.columns]
    ref_col = find_col(list(df.columns), ALIASES['agl_ref'])
    if not ref_col:
        raise ValueError(f"La hoja {sheet} no tiene columna AGL Ref. Columnas: {list(df.columns)}")

    # Optimización V6 Redention:
    # Excel a veces trae el rango usado hasta más de 1 millón de filas aunque estén vacías.
    # Conservamos solo filas con AGL Ref y precomputamos una llave normalizada para búsquedas rápidas.
    df['_excel_row'] = df.index + 2
    ref_series = df[ref_col].map(clean)
    df = df[ref_series != ''].copy()
    df['_agl_ref_norm'] = df[ref_col].map(norm_text)
    return df, sheet


def lookup_df(df, agl_ref: str, sheet: str = ''):
    ref_col = find_col(df.columns, ALIASES['agl_ref'])
    if not ref_col:
        raise ValueError('No se encontró columna AGL Ref en Status Master')
    target = norm_text(agl_ref)
    if '_agl_ref_norm' in df.columns:
        matches = df[df['_agl_ref_norm'] == target]
    else:
        matches = df[df[ref_col].apply(lambda x: norm_text(x) == target)]
    if matches.empty:
        return None
    row = matches.iloc[0]
    excel_row = int(row.get('_excel_row', matches.index[0] + 2))
    out = {'_sheet': sheet, '_row': excel_row, '_ref_col': str(ref_col)}
    for key, names in ALIASES.items():
        col = find_col(df.columns, names)
        if col:
            out[key] = clean(row.get(col))
    form = {
        # Campos visibles del formulario operativo
        'operation': out.get('po') or '',
        'agl_ref': out.get('agl_ref') or agl_ref,
        'pedido': out.get('invoice_no') or out.get('agl_ref') or agl_ref,
        'invoice_no': out.get('invoice_no') or '',

        # Datos generales para cierre y factura
        'customer': out.get('customer') or out.get('customer_2') or out.get('billing_company') or '',
        'bill_to': out.get('billing_company') or out.get('customer') or '',
        'billing_company': out.get('billing_company') or '',
        'brand': out.get('brand') or '',
        'release_agent': out.get('release_agent') or '',
        'warehouse_location': out.get('warehouse_location') or '',
        'po': out.get('po') or '',
        'pick_up_date': out.get('pick_up_date') or '',
        'eta_wh': out.get('eta_wh') or '',
        'transit_days': out.get('transit_days') or '',
        'finish_required': out.get('finish_required') or '',
        'finish_date': out.get('finish_date') or '',
        'release_date': out.get('release_date') or '',
        'comments': out.get('comments') or '',

        # Operational Data
        'pallets': parse_num(out.get('pallets')),
        'weight': parse_num(out.get('gross_weight')),
        'cbm': parse_num(out.get('cbm')),
        'units': parse_num(out.get('inner_boxes')),
        'master_boxes': parse_num(out.get('master_boxes')),
        'commercial_value': parse_num(out.get('commercial_value')),
        # Manuales por ahora
        'origin': '',
        'destination': '',
        'vendor': '',
        'elaborated_by': '',
        'agent': 'AGL PANAMA',
        'payment': 'CONTADO',
        'description': out.get('comments') or '',
    }
    return {'raw': out, 'form': form}


def lookup(path: Path, agl_ref: str):
    df, sheet = load_status_df(path)
    return lookup_df(df, agl_ref, sheet)


def suggestions_df(df, field: str):
    col = find_col(df.columns, ALIASES.get(field, [field]))
    if not col:
        return []
    vals = []
    seen = set()
    for v in df[col].dropna().tolist():
        t = clean(v)
        if not t:
            continue
        nt = norm(t)
        if nt and nt not in seen:
            seen.add(nt)
            vals.append(t)
        if len(vals) >= 250:
            break
    return vals


def suggestions(path: Path, field: str):
    df, _sheet = load_status_df(path)
    return suggestions_df(df, field)
