import re

def norm(s):
    return re.sub(r'[^A-Z0-9]+', ' ', str(s or '').upper()).strip()

def n(v):
    try:
        if v is None or v == '': return 0.0
        return float(str(v).replace(',','').replace('$','').replace('B/.','').replace('USD','').strip())
    except Exception:
        return 0.0

def smart_round(value):
    value = float(value or 0)
    return round(value, 4 if 0 < abs(value) < 0.01 else 2)

def line_total(qty, rate, minimum=0, days=1):
    total = n(qty) * n(rate) * (n(days) if days else 1)
    # Regla del motor PySide original: 0 es válido; blanco no.
    # Si hay mínimo AGL y la cantidad existe, el mínimo aplica aunque el rate sea 0.
    if n(minimum) and n(qty) > 0 and total < n(minimum):
        total = n(minimum)
    return smart_round(total)

def suggest_quantity(item, unit, period, form):
    unit_u=norm(unit); item_u=norm(item); period_u=norm(period)
    def gv(k): return n(form.get(k))
    if 'PALLET' in unit_u or unit_u == 'PLT': return gv('pallets')
    if 'MASTER BOX' in unit_u or 'CTN' in unit_u: return gv('master_boxes')
    if 'INNER' in unit_u or 'SUB BOX' in unit_u or 'PAIR' in unit_u or 'UNDS' in unit_u: return gv('units')
    if 'CBM' in unit_u:
        cbm=gv('cbm')
        if 'MONTH' in period_u or 'MONTH' in item_u: return cbm * (gv('storage_months') or 1)
        if 'WEEK' in period_u or 'WEEK' in item_u: return cbm * (gv('storage_weeks') or 1)
        if 'DAY' in period_u or 'DAY' in item_u: return cbm * (gv('storage_days') or 1)
        return cbm
    if 'COMMERCIAL VALUE' in unit_u: return gv('commercial_value')
    if 'DAY' in unit_u: return gv('storage_days')
    if 'WEEK' in unit_u: return gv('storage_weeks')
    if 'MONTH' in unit_u: return gv('storage_months')
    if 'WAREHOUSE IN' in item_u or item_u.endswith(' IN') or ' IN ' in item_u: return gv('pedidos_in') or gv('inbound_orders')
    if 'WAREHOUSE OUT' in item_u or item_u.endswith(' OUT') or ' OUT ' in item_u: return gv('pedidos_out') or gv('outbound_orders')
    if 'HANDLING' in item_u or 'MANEJO' in item_u or 'SHIPMENT' in unit_u: return 0.0
    if 'LABEL' in item_u and ('MASTER' in item_u or 'CARTON' in item_u): return gv('master_boxes')
    if 'LABEL' in item_u and ('SUB' in item_u or 'INNER' in item_u): return gv('units')
    if 'LABEL' in item_u and 'PALLET' in item_u: return gv('pallets')
    if 'SEGREGATION' in item_u: return gv('master_boxes')
    if 'PICKING' in item_u: return gv('units')
    if 'PALLET' in item_u: return gv('pallets')
    return 0.0

def generate(warehouse, form, rates_rows, service_qtys=None):
    service_qtys = service_qtys or {}
    wh_rows=[r for r in rates_rows if norm(r.get('wh')) == norm(warehouse)]
    sales=[]; costs=[]
    for i,r in enumerate(wh_rows):
        key=str(r.get('id') or i)
        qty = service_qtys.get(key)
        if qty is None:
            # Autofill desactivado por ahora: las cantidades de servicios se llenan manualmente.
            qty = 0
        qty=n(qty)
        if qty == 0:
            continue
        sell=n(r.get('sell')); cost=n(r.get('cost'))
        sale_total=line_total(qty, sell, r.get('minimum_agl'))
        # Regla del motor anterior: líneas con costo 0 no se muestran en COSTO,
        # pero sí pueden aparecer en VENTA y afectar profit.
        cost_total=smart_round(qty * cost)
        sales.append({'rate_id': key, 'item': r.get('agl_item') or r.get('warehouse_item'), 'qty': qty, 'unit': r.get('agl_unit') or '', 'rate': sell, 'days': '', 'total': sale_total})
        if cost != 0:
            costs.append({'rate_id': key, 'provider': warehouse, 'item': r.get('warehouse_item') or r.get('agl_item'), 'qty': qty, 'unit': r.get('warehouse_unit') or r.get('agl_unit') or '', 'rate': cost, 'days': '', 'total': cost_total})
    sale_total=smart_round(sum(n(x['total']) for x in sales))
    cost_total=smart_round(sum(n(x['total']) for x in costs))
    profit=smart_round(sale_total-cost_total)
    commercial=n(form.get('commercial_value'))
    return {
        'warehouse': warehouse, 'form': form, 'sales': sales, 'costs': costs,
        'sale_total': sale_total, 'cost_total': cost_total, 'profit': profit,
        'margin_pct': round((profit/sale_total*100) if sale_total else 0,2),
        'logistics_fee_pct': round((sale_total/commercial*100) if commercial else 0,2),
    }
