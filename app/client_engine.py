from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd


def norm(value: Any) -> str:
    return re.sub(r'[^A-Z0-9]+', ' ', str(value or '').upper()).strip()


def norm_key(value: Any) -> str:
    return re.sub(r'[^A-Z0-9]+', '', str(value or '').upper()).strip()


def clean(value: Any) -> str:
    if value is None:
        return ''
    try:
        if pd.isna(value):
            return ''
    except Exception:
        pass
    text = str(value).strip()
    if text.lower() in {'nan', 'nat', 'none', '#n/a'}:
        return ''
    return text


def find_col(columns, aliases: List[str]) -> Optional[str]:
    nmap = {norm(c): str(c).strip() for c in columns}
    for a in aliases:
        na = norm(a)
        if na in nmap:
            return nmap[na]
    for a in aliases:
        na = norm(a)
        for nc, orig in nmap.items():
            if na and (na in nc or nc in na):
                return orig
    return None

CLIENT_ALIASES = {
    'cliente': ['CLIENTE', 'Customer', 'Final Cust.', 'Final Cust'],
    'bill_to': ['FACTURAR A:', 'FACTURAR A', 'Bill To', 'Billing Company'],
    'ruc': ['RUC:', 'RUC'],
    'address': ['DIRECCIÓN:', 'DIRECCION:', 'DIRECCIÓN', 'DIRECCION', 'Address'],
    'phone': ['TELÉFONO:', 'TELEFONO:', 'TELÉFONO', 'TELEFONO', 'Phone', 'Telefono'],
    'email': ['EMAIL:', 'EMAIL', 'Correo'],
    'payment': ['FORMA DE PAGO:', 'FORMA DE PAGO', 'Payment', 'Payment Terms'],
}
BRAND_ALIASES = {
    'brand': ['BRAND', 'MARCA', 'Marca'],
    'description': ['DESCRIPCION', 'DESCRIPCIÓN', 'Description'],
}
DIRECTION_ALIASES = {
    'origin': ['ORIGEN', 'Origin'],
    'destination': ['DESTINO', 'Destination'],
}


def _read_sheet_table(path: Path, sheet_name: str) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=sheet_name, dtype=str)
    df.columns = [str(c).strip() for c in df.columns]
    return df.fillna('')


def _find_sheet_case(sheet_names: List[str], wanted: str) -> Optional[str]:
    nw = norm(wanted)
    for sh in sheet_names:
        if norm(sh) == nw:
            return sh
    for sh in sheet_names:
        if nw in norm(sh) or norm(sh) in nw:
            return sh
    return None


def _extract_section_from_flat_sheet(path: Path, section_name: str) -> pd.DataFrame:
    """Soporta un solo Excel donde varias tablas están una debajo de otra.
    Busca una celda con el nombre de sección, toma la fila de encabezados debajo
    y lee hasta encontrar una fila vacía o la próxima sección conocida.
    """
    raw = pd.read_excel(path, sheet_name=0, dtype=str, header=None).fillna('')
    target = norm(section_name)
    start = None
    for r in range(len(raw)):
        row_text = ' '.join(clean(x) for x in raw.iloc[r].tolist())
        if norm(row_text) == target or target in norm(row_text):
            start = r
            break
    if start is None:
        return pd.DataFrame()

    # Buscar encabezados en las próximas 4 filas, usando la que tenga más celdas con texto.
    header_row = start + 1
    best_count = -1
    for rr in range(start + 1, min(start + 5, len(raw))):
        count = sum(1 for x in raw.iloc[rr].tolist() if clean(x))
        if count > best_count:
            best_count = count
            header_row = rr
    headers = [clean(x) for x in raw.iloc[header_row].tolist()]
    # quitar columnas vacías al inicio/fin pero conservar orden
    used_cols = [i for i, h in enumerate(headers) if h]
    if not used_cols:
        return pd.DataFrame()
    first, last = min(used_cols), max(used_cols)
    headers = headers[first:last+1]

    section_markers = {'CLIENTES','MARCAS','DIRECCIONES','VENDEDORES','ELABORADO POR','BODEGA','BANCOS'}
    data = []
    blank_run = 0
    for rr in range(header_row + 1, len(raw)):
        vals = [clean(x) for x in raw.iloc[rr, first:last+1].tolist()]
        row_join = norm(' '.join(vals))
        if any(row_join == norm(x) for x in section_markers if norm(x) != target):
            break
        if not any(vals):
            blank_run += 1
            if blank_run >= 3:
                break
            continue
        blank_run = 0
        # si la fila parece título de otra sección, parar
        if len([v for v in vals if v]) == 1 and norm(vals[0]) in {norm(x) for x in section_markers}:
            break
        data.append(vals)
    if not data:
        return pd.DataFrame(columns=headers)
    # normalizar largo
    data = [row + ['']*(len(headers)-len(row)) for row in data]
    df = pd.DataFrame(data, columns=headers)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def load_client_master(path: Path) -> Dict[str, Any]:
    if not Path(path).exists():
        return {'ok': False, 'error': f'No existe CLIENT_MASTER: {path}', 'clients': pd.DataFrame(), 'brands': pd.DataFrame(), 'banks': {}}
    path = Path(path)
    xls = pd.ExcelFile(path)
    clients_sheet = _find_sheet_case(xls.sheet_names, 'CLIENTES')
    brands_sheet = _find_sheet_case(xls.sheet_names, 'MARCAS')
    banks_sheet = _find_sheet_case(xls.sheet_names, 'BANCOS')
    directions_sheet = _find_sheet_case(xls.sheet_names, 'DIRECCIONES')

    clients = _read_sheet_table(path, clients_sheet) if clients_sheet else _extract_section_from_flat_sheet(path, 'CLIENTES')
    brands = _read_sheet_table(path, brands_sheet) if brands_sheet else _extract_section_from_flat_sheet(path, 'MARCAS')
    directions = _read_sheet_table(path, directions_sheet) if directions_sheet else _extract_section_from_flat_sheet(path, 'DIRECCIONES')
    banks_df = _read_sheet_table(path, banks_sheet) if banks_sheet else _extract_section_from_flat_sheet(path, 'BANCOS')

    banks: Dict[str, str] = {}
    if not banks_df.empty:
        # Formato simple: Cliente | Banco texto
        c_client = find_col(banks_df.columns, ['CLIENTE','Customer'])
        c_text = find_col(banks_df.columns, ['BANCO TEXTO','BANCO','BANK TEXT','Bank'])
        if c_client and c_text:
            for _, row in banks_df.iterrows():
                key = norm_key(row.get(c_client))
                txt = clean(row.get(c_text))
                if key and txt:
                    banks[key] = txt
        else:
            # Formato horizontal: cada columna es un cliente y debajo hay líneas bancarias.
            for col in banks_df.columns:
                title = clean(col)
                if not title or norm_key(title) in {'UNNAMED0','NAN'}:
                    continue
                lines = [clean(v) for v in banks_df[col].tolist() if clean(v)]
                if lines:
                    banks[norm_key(title)] = '\n'.join(lines)

    return {
        'ok': True,
        'path': str(path),
        'sheets': xls.sheet_names,
        'clients_sheet': clients_sheet or 'detectado_en_hoja_unica',
        'brands_sheet': brands_sheet or 'detectado_en_hoja_unica',
        'clients': clients,
        'brands': brands,
        'banks': banks,
        'directions': directions,
        'directions_sheet': directions_sheet or 'detectado_en_hoja_unica',
        'client_rows': len(clients),
        'brand_rows': len(brands),
        'direction_rows': len(directions),
        'bank_clients': len(banks),
    }


def lookup_client(client_data: Dict[str, Any], customer_name: str, brand_name: str = '') -> Dict[str, Any]:
    clients = client_data.get('clients')
    brands = client_data.get('brands')
    banks = client_data.get('banks') or {}
    out: Dict[str, Any] = {'client_found': False, 'brand_found': False}

    if clients is not None and not getattr(clients, 'empty', True) and customer_name:
        c_cliente = find_col(clients.columns, CLIENT_ALIASES['cliente'])
        if c_cliente:
            target = norm_key(customer_name)
            # exacto primero; luego contains en ambos sentidos
            match = clients[clients[c_cliente].apply(lambda v: norm_key(v) == target)]
            if match.empty:
                match = clients[clients[c_cliente].apply(lambda v: target and (target in norm_key(v) or norm_key(v) in target))]
            if not match.empty:
                row = match.iloc[0]
                out['client_found'] = True
                for key, aliases in CLIENT_ALIASES.items():
                    col = find_col(clients.columns, aliases)
                    if col:
                        out[key] = clean(row.get(col))
                bank_key = norm_key(out.get('cliente') or customer_name)
                if bank_key in banks:
                    out['bank_text'] = banks[bank_key]

    if brands is not None and not getattr(brands, 'empty', True) and brand_name:
        c_brand = find_col(brands.columns, BRAND_ALIASES['brand'])
        c_desc = find_col(brands.columns, BRAND_ALIASES['description'])
        if c_brand:
            target = norm_key(brand_name)
            match = brands[brands[c_brand].apply(lambda v: norm_key(v) == target)]
            if match.empty:
                match = brands[brands[c_brand].apply(lambda v: target and (target in norm_key(v) or norm_key(v) in target))]
            if not match.empty:
                row = match.iloc[0]
                out['brand_found'] = True
                out['brand'] = clean(row.get(c_brand)) or brand_name
                if c_desc:
                    out['description'] = clean(row.get(c_desc))

    return out



def _unique_values(df: pd.DataFrame, aliases: List[str], limit: int = 1000) -> List[str]:
    if df is None or getattr(df, 'empty', True):
        return []
    col = find_col(df.columns, aliases)
    if not col:
        return []
    out: List[str] = []
    seen = set()
    for v in df[col].tolist():
        t = clean(v)
        nt = norm_key(t)
        if not t or not nt or nt in seen:
            continue
        seen.add(nt)
        out.append(t)
        if len(out) >= limit:
            break
    return out


def client_lists(client_data: Dict[str, Any]) -> Dict[str, Any]:
    clients = client_data.get('clients')
    brands = client_data.get('brands')
    directions = client_data.get('directions')

    origins = _unique_values(directions, DIRECTION_ALIASES['origin'])
    destinations = _unique_values(directions, DIRECTION_ALIASES['destination'])
    direction_pairs: List[Dict[str, str]] = []
    if directions is not None and not getattr(directions, 'empty', True):
        c_origin = find_col(directions.columns, DIRECTION_ALIASES['origin'])
        c_dest = find_col(directions.columns, DIRECTION_ALIASES['destination'])
        if c_origin and c_dest:
            seen = set()
            for _, row in directions.iterrows():
                o = clean(row.get(c_origin))
                d = clean(row.get(c_dest))
                key = (norm_key(o), norm_key(d))
                if o and d and key not in seen:
                    seen.add(key)
                    direction_pairs.append({'origin': o, 'destination': d})

    return {
        'ok': bool(client_data.get('ok')),
        'clients': _unique_values(clients, CLIENT_ALIASES['cliente']),
        'brands': _unique_values(brands, BRAND_ALIASES['brand']),
        'origins': origins,
        'destinations': destinations,
        'direction_pairs': direction_pairs,
        'counts': {
            'clients': len(_unique_values(clients, CLIENT_ALIASES['cliente'])),
            'brands': len(_unique_values(brands, BRAND_ALIASES['brand'])),
            'origins': len(origins),
            'destinations': len(destinations),
            'direction_pairs': len(direction_pairs),
        }
    }
