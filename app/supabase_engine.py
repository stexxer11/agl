from __future__ import annotations

import os
import re
import json
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor, Json, execute_values

from .config import load_config
from .rates_engine import load_rates
from .status_engine import load_status_df, ALIASES as STATUS_ALIASES, find_col as status_find_col, clean as status_clean, parse_num as status_parse_num, norm_text as status_norm_text
from .client_engine import load_client_master, CLIENT_ALIASES, BRAND_ALIASES, DIRECTION_ALIASES, find_col as client_find_col, clean as client_clean, norm_key


def norm_key_any(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").upper()).strip()


def _db_url() -> str:
    cfg = load_config()
    url = (
        os.environ.get("AGL_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or cfg.get("supabase_database_url")
        or cfg.get("database_url")
        or ""
    )
    url = str(url).strip().strip('"').strip("'")
    if not url:
        raise RuntimeError(
            "No hay conexión a Supabase/PostgreSQL. Configura supabase_database_url en config.json "
            "o define la variable de entorno AGL_DATABASE_URL."
        )
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


def conn():
    # sslmode=require suele ser necesario con Supabase.
    url = _db_url()
    if "sslmode=" not in url:
        sep = "&" if "?" in url else "?"
        url = url + sep + "sslmode=require"
    return psycopg2.connect(url)


def init_supabase_schema() -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS agl_rates (
        rate_key TEXT PRIMARY KEY,
        wh TEXT,
        warehouse_item TEXT,
        agl_item TEXT,
        cost NUMERIC,
        sell NUMERIC,
        warehouse_unit TEXT,
        agl_unit TEXT,
        warehouse_period TEXT,
        agl_period TEXT,
        minimum_warehouse NUMERIC,
        minimum_agl NUMERIC,
        source_row INTEGER,
        raw JSONB DEFAULT '{}'::jsonb,
        updated_at TIMESTAMPTZ DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS idx_agl_rates_wh ON agl_rates (upper(wh));

    CREATE TABLE IF NOT EXISTS status_refs (
        agl_ref_norm TEXT PRIMARY KEY,
        agl_ref TEXT,
        form JSONB DEFAULT '{}'::jsonb,
        raw JSONB DEFAULT '{}'::jsonb,
        sheet TEXT,
        source_row INTEGER,
        updated_at TIMESTAMPTZ DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS idx_status_refs_agl_ref ON status_refs (upper(agl_ref));

    CREATE TABLE IF NOT EXISTS clients (
        client_norm TEXT PRIMARY KEY,
        cliente TEXT,
        bill_to TEXT,
        ruc TEXT,
        address TEXT,
        phone TEXT,
        email TEXT,
        payment TEXT,
        bank_text TEXT,
        raw JSONB DEFAULT '{}'::jsonb,
        updated_at TIMESTAMPTZ DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS brands (
        brand_norm TEXT PRIMARY KEY,
        brand TEXT,
        description TEXT,
        raw JSONB DEFAULT '{}'::jsonb,
        updated_at TIMESTAMPTZ DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS directions (
        direction_key TEXT PRIMARY KEY,
        origin TEXT,
        destination TEXT,
        raw JSONB DEFAULT '{}'::jsonb,
        updated_at TIMESTAMPTZ DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS agl_cases (
        id BIGSERIAL PRIMARY KEY,
        agl_ref TEXT,
        customer TEXT,
        warehouse TEXT,
        title TEXT,
        payload JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ DEFAULT now(),
        updated_at TIMESTAMPTZ DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS idx_agl_cases_search ON agl_cases (upper(agl_ref), upper(customer));

    CREATE TABLE IF NOT EXISTS master_sync_log (
        id BIGSERIAL PRIMARY KEY,
        kind TEXT,
        source_path TEXT,
        rows_count INTEGER,
        status TEXT,
        message TEXT,
        created_at TIMESTAMPTZ DEFAULT now()
    );
    """
    with conn() as c:
        with c.cursor() as cur:
            cur.execute(ddl)


def db_status() -> Dict[str, Any]:
    init_supabase_schema()
    with conn() as c:
        with c.cursor(cursor_factory=RealDictCursor) as cur:
            out = {"ok": True, "backend": "supabase_postgresql"}
            for table in ["agl_rates", "status_refs", "clients", "brands", "directions", "agl_cases"]:
                cur.execute(f"SELECT COUNT(*) AS n FROM {table}")
                out[table] = int(cur.fetchone()["n"])
            cur.execute("SELECT * FROM master_sync_log ORDER BY id DESC LIMIT 5")
            out["last_sync"] = [dict(x) for x in cur.fetchall()]
            return out


def _log_sync(cur, kind: str, source_path: str, rows_count: int, status: str, message: str):
    cur.execute(
        "INSERT INTO master_sync_log(kind, source_path, rows_count, status, message) VALUES (%s,%s,%s,%s,%s)",
        (kind, source_path, rows_count, status, message),
    )


def sync_rates_from_excel(path: Path) -> Dict[str, Any]:
    data = load_rates(path)
    rows = data.get("rows", [])
    values = []
    for r in rows:
        key = f"{norm_key_any(r.get('wh'))}|{int(r.get('source_row') or r.get('id') or len(values)+1)}|{norm_key_any(r.get('agl_item') or r.get('warehouse_item'))}"
        values.append((
            key, r.get("wh"), r.get("warehouse_item"), r.get("agl_item"), r.get("cost"), r.get("sell"),
            r.get("warehouse_unit"), r.get("agl_unit"), r.get("warehouse_period"), r.get("agl_period"),
            r.get("minimum_warehouse"), r.get("minimum_agl"), r.get("source_row"), Json(r)
        ))
    init_supabase_schema()
    with conn() as c:
        with c.cursor() as cur:
            cur.execute("DELETE FROM agl_rates")
            if values:
                execute_values(cur, """
                    INSERT INTO agl_rates(rate_key, wh, warehouse_item, agl_item, cost, sell, warehouse_unit, agl_unit,
                        warehouse_period, agl_period, minimum_warehouse, minimum_agl, source_row, raw)
                    VALUES %s
                    ON CONFLICT (rate_key) DO UPDATE SET
                        wh=EXCLUDED.wh, warehouse_item=EXCLUDED.warehouse_item, agl_item=EXCLUDED.agl_item,
                        cost=EXCLUDED.cost, sell=EXCLUDED.sell, warehouse_unit=EXCLUDED.warehouse_unit,
                        agl_unit=EXCLUDED.agl_unit, warehouse_period=EXCLUDED.warehouse_period,
                        agl_period=EXCLUDED.agl_period, minimum_warehouse=EXCLUDED.minimum_warehouse,
                        minimum_agl=EXCLUDED.minimum_agl, source_row=EXCLUDED.source_row,
                        raw=EXCLUDED.raw, updated_at=now()
                """, values, page_size=1000)
            _log_sync(cur, "agl", str(path), len(values), "ok", f"AGL Master sincronizado: {len(values)} tarifas")
    return {"ok": True, "rows": len(values), "sheet": data.get("sheet"), "message": "AGL Master sincronizado en Supabase"}


def _status_form_from_row(df: pd.DataFrame, row: pd.Series, sheet: str, excel_row: int, ref_col: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    out: Dict[str, Any] = {"_sheet": sheet, "_row": excel_row, "_ref_col": str(ref_col)}
    for key, names in STATUS_ALIASES.items():
        col = status_find_col(df.columns, names)
        if col:
            out[key] = status_clean(row.get(col))
    agl_ref = out.get("agl_ref") or status_clean(row.get(ref_col))
    form = {
        "operation": out.get("po") or "",
        "agl_ref": agl_ref,
        "pedido": out.get("invoice_no") or out.get("agl_ref") or agl_ref,
        "invoice_no": out.get("invoice_no") or "",
        "customer": out.get("customer") or out.get("customer_2") or out.get("billing_company") or "",
        "bill_to": out.get("billing_company") or out.get("customer") or "",
        "billing_company": out.get("billing_company") or "",
        "brand": out.get("brand") or "",
        "origin": "",
        "destination": "",
        "pallets": status_parse_num(out.get("pallets")),
        "weight": status_parse_num(out.get("gross_weight")),
        "cbm": status_parse_num(out.get("cbm")),
        "units": status_parse_num(out.get("inner_boxes")),
        "master_boxes": status_parse_num(out.get("master_boxes")),
        "commercial_value": status_parse_num(out.get("commercial_value")),
        "comments": out.get("comments") or "",
        "release_agent": out.get("release_agent") or "",
        "warehouse_location": out.get("warehouse_location") or "",
        "po": out.get("po") or "",
        "pick_up_date": out.get("pick_up_date") or "",
        "eta_wh": out.get("eta_wh") or "",
    }
    return out, form


def sync_status_from_excel(path: Path) -> Dict[str, Any]:
    df, sheet = load_status_df(path)
    ref_col = status_find_col(df.columns, STATUS_ALIASES["agl_ref"])
    if not ref_col:
        raise ValueError("No se encontró AGL Ref en Status Master")
    values = []
    for idx, row in df.iterrows():
        agl_ref = status_clean(row.get(ref_col))
        ref_norm = status_norm_text(agl_ref)
        if not ref_norm:
            continue
        excel_row = int(row.get("_excel_row", idx + 2))
        raw, form = _status_form_from_row(df, row, sheet, excel_row, ref_col)
        values.append((ref_norm, agl_ref, Json(form), Json(raw), sheet, excel_row))
    init_supabase_schema()
    with conn() as c:
        with c.cursor() as cur:
            cur.execute("DELETE FROM status_refs")
            if values:
                execute_values(cur, """
                    INSERT INTO status_refs(agl_ref_norm, agl_ref, form, raw, sheet, source_row)
                    VALUES %s
                    ON CONFLICT (agl_ref_norm) DO UPDATE SET
                        agl_ref=EXCLUDED.agl_ref, form=EXCLUDED.form, raw=EXCLUDED.raw,
                        sheet=EXCLUDED.sheet, source_row=EXCLUDED.source_row, updated_at=now()
                """, values, page_size=1000)
            _log_sync(cur, "status", str(path), len(values), "ok", f"Status Master sincronizado: {len(values)} AGL refs")
    return {"ok": True, "rows": len(values), "sheet": sheet, "message": "Status Master sincronizado en Supabase"}


def sync_client_from_excel(path: Path) -> Dict[str, Any]:
    data = load_client_master(path)
    clients = data.get("clients")
    brands = data.get("brands")
    directions = data.get("directions")
    banks = data.get("banks") or {}
    client_values = []
    brand_values = []
    direction_values = []

    if clients is not None and not getattr(clients, "empty", True):
        c_cliente = client_find_col(clients.columns, CLIENT_ALIASES["cliente"])
        if c_cliente:
            for _, row in clients.iterrows():
                cliente = client_clean(row.get(c_cliente))
                key = norm_key(cliente)
                if not key:
                    continue
                raw = {str(k): client_clean(row.get(k)) for k in clients.columns}
                def get(alias_key):
                    col = client_find_col(clients.columns, CLIENT_ALIASES[alias_key])
                    return client_clean(row.get(col)) if col else ""
                bank_text = banks.get(key, "")
                client_values.append((key, cliente, get("bill_to"), get("ruc"), get("address"), get("phone"), get("email"), get("payment"), bank_text, Json(raw)))

    if brands is not None and not getattr(brands, "empty", True):
        c_brand = client_find_col(brands.columns, BRAND_ALIASES["brand"])
        c_desc = client_find_col(brands.columns, BRAND_ALIASES["description"])
        if c_brand:
            for _, row in brands.iterrows():
                brand = client_clean(row.get(c_brand))
                key = norm_key(brand)
                if not key:
                    continue
                desc = client_clean(row.get(c_desc)) if c_desc else ""
                raw = {str(k): client_clean(row.get(k)) for k in brands.columns}
                brand_values.append((key, brand, desc, Json(raw)))

    if directions is not None and not getattr(directions, "empty", True):
        c_origin = client_find_col(directions.columns, DIRECTION_ALIASES["origin"])
        c_dest = client_find_col(directions.columns, DIRECTION_ALIASES["destination"])
        if c_origin and c_dest:
            seen = set()
            for _, row in directions.iterrows():
                origin = client_clean(row.get(c_origin))
                dest = client_clean(row.get(c_dest))
                key = norm_key(origin) + "|" + norm_key(dest)
                if not origin or not dest or key in seen:
                    continue
                seen.add(key)
                raw = {str(k): client_clean(row.get(k)) for k in directions.columns}
                direction_values.append((key, origin, dest, Json(raw)))

    init_supabase_schema()
    with conn() as c:
        with c.cursor() as cur:
            cur.execute("DELETE FROM clients")
            cur.execute("DELETE FROM brands")
            cur.execute("DELETE FROM directions")
            if client_values:
                execute_values(cur, """
                    INSERT INTO clients(client_norm, cliente, bill_to, ruc, address, phone, email, payment, bank_text, raw)
                    VALUES %s
                    ON CONFLICT (client_norm) DO UPDATE SET
                    cliente=EXCLUDED.cliente, bill_to=EXCLUDED.bill_to, ruc=EXCLUDED.ruc, address=EXCLUDED.address,
                    phone=EXCLUDED.phone, email=EXCLUDED.email, payment=EXCLUDED.payment, bank_text=EXCLUDED.bank_text,
                    raw=EXCLUDED.raw, updated_at=now()
                """, client_values, page_size=1000)
            if brand_values:
                execute_values(cur, """
                    INSERT INTO brands(brand_norm, brand, description, raw) VALUES %s
                    ON CONFLICT (brand_norm) DO UPDATE SET brand=EXCLUDED.brand, description=EXCLUDED.description,
                    raw=EXCLUDED.raw, updated_at=now()
                """, brand_values, page_size=1000)
            if direction_values:
                execute_values(cur, """
                    INSERT INTO directions(direction_key, origin, destination, raw) VALUES %s
                    ON CONFLICT (direction_key) DO UPDATE SET origin=EXCLUDED.origin, destination=EXCLUDED.destination,
                    raw=EXCLUDED.raw, updated_at=now()
                """, direction_values, page_size=1000)
            _log_sync(cur, "client", str(path), len(client_values), "ok", f"Client Master sincronizado: {len(client_values)} clientes")
    return {"ok": True, "client_rows": len(client_values), "brand_rows": len(brand_values), "direction_rows": len(direction_values), "message": "Client Master sincronizado en Supabase"}


def get_warehouses() -> List[str]:
    init_supabase_schema()
    with conn() as c, c.cursor() as cur:
        cur.execute("SELECT DISTINCT wh FROM agl_rates WHERE COALESCE(wh,'')<>'' ORDER BY wh")
        return [r[0] for r in cur.fetchall()]


def get_rates_by_warehouse(warehouse: str) -> List[Dict[str, Any]]:
    init_supabase_schema()
    with conn() as c, c.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT rate_key AS id, wh, warehouse_item, agl_item, cost::float AS cost, sell::float AS sell,
                   warehouse_unit, agl_unit, warehouse_period, agl_period,
                   minimum_warehouse::float AS minimum_warehouse, minimum_agl::float AS minimum_agl, source_row
            FROM agl_rates WHERE upper(wh)=upper(%s) ORDER BY source_row NULLS LAST, agl_item
        """, (warehouse,))
        return [dict(x) for x in cur.fetchall()]


def get_all_rates() -> List[Dict[str, Any]]:
    init_supabase_schema()
    with conn() as c, c.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT rate_key AS id, wh, warehouse_item, agl_item, cost::float AS cost, sell::float AS sell,
                   warehouse_unit, agl_unit, warehouse_period, agl_period,
                   minimum_warehouse::float AS minimum_warehouse, minimum_agl::float AS minimum_agl, source_row
            FROM agl_rates ORDER BY wh, source_row NULLS LAST
        """)
        return [dict(x) for x in cur.fetchall()]


def lookup_status(agl_ref: str) -> Dict[str, Any]:
    init_supabase_schema()
    target = status_norm_text(agl_ref)
    with conn() as c, c.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT agl_ref, form, raw, sheet, source_row FROM status_refs WHERE agl_ref_norm=%s", (target,))
        row = cur.fetchone()
        if not row:
            cur.execute("SELECT agl_ref FROM status_refs WHERE agl_ref_norm LIKE %s ORDER BY agl_ref LIMIT 10", (target[:8] + "%",))
            return {"found": False, "message": f"AGL Ref no encontrada: {agl_ref}", "similar": [x["agl_ref"] for x in cur.fetchall()]}
        return {"found": True, "source": "supabase", "raw": row["raw"] or {}, "form": row["form"] or {}, "message": f"Encontrado en DB / fila {row.get('source_row')}", "_sheet": row.get("sheet")}


def client_lookup(customer: str = "", brand: str = "") -> Dict[str, Any]:
    init_supabase_schema()
    out: Dict[str, Any] = {"client_found": False, "brand_found": False}
    with conn() as c, c.cursor(cursor_factory=RealDictCursor) as cur:
        if customer:
            target = norm_key(customer)
            cur.execute("SELECT * FROM clients WHERE client_norm=%s OR client_norm LIKE %s OR %s LIKE '%%'||client_norm||'%%' LIMIT 1", (target, f"%{target}%", target))
            row = cur.fetchone()
            if row:
                out.update({"client_found": True, "cliente": row.get("cliente"), "bill_to": row.get("bill_to"), "ruc": row.get("ruc"), "address": row.get("address"), "phone": row.get("phone"), "email": row.get("email"), "payment": row.get("payment"), "bank_text": row.get("bank_text")})
        if brand:
            target = norm_key(brand)
            cur.execute("SELECT * FROM brands WHERE brand_norm=%s OR brand_norm LIKE %s OR %s LIKE '%%'||brand_norm||'%%' LIMIT 1", (target, f"%{target}%", target))
            row = cur.fetchone()
            if row:
                out.update({"brand_found": True, "brand": row.get("brand"), "description": row.get("description")})
    return out


def client_lists_db() -> Dict[str, Any]:
    init_supabase_schema()
    with conn() as c, c.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT cliente FROM clients WHERE COALESCE(cliente,'')<>'' ORDER BY cliente")
        clients = [x["cliente"] for x in cur.fetchall()]
        cur.execute("SELECT brand FROM brands WHERE COALESCE(brand,'')<>'' ORDER BY brand")
        brands = [x["brand"] for x in cur.fetchall()]
        cur.execute("SELECT origin FROM directions WHERE COALESCE(origin,'')<>'' ORDER BY origin")
        origins = list(dict.fromkeys([x["origin"] for x in cur.fetchall()]))
        cur.execute("SELECT destination FROM directions WHERE COALESCE(destination,'')<>'' ORDER BY destination")
        destinations = list(dict.fromkeys([x["destination"] for x in cur.fetchall()]))
        cur.execute("SELECT origin, destination FROM directions ORDER BY origin, destination")
        pairs = [dict(x) for x in cur.fetchall()]
        return {"ok": True, "clients": clients, "brands": brands, "origins": origins, "destinations": destinations, "direction_pairs": pairs, "counts": {"clients": len(clients), "brands": len(brands), "origins": len(origins), "destinations": len(destinations), "direction_pairs": len(pairs)}}


def save_case_db(payload: Dict[str, Any]) -> Tuple[int, str]:
    """Guarda expediente en Supabase.

    Regla V18:
    - Si viene case_id, actualiza ese expediente.
    - Si no viene case_id pero existe el mismo AGL Ref, actualiza el expediente más reciente de ese AGL Ref.
    - Si no existe, crea uno nuevo.
    Esto evita duplicados en Guardados y permite que todos editen el mismo expediente.
    """
    init_supabase_schema()
    form = payload.get("form") or {}
    agl_ref = str(payload.get("agl_ref") or form.get("agl_ref") or "").strip()
    customer = str(form.get("customer") or form.get("bill_to") or payload.get("customer") or "").strip()
    warehouse = str(payload.get("warehouse") or payload.get("selected_warehouse") or (payload.get("result") or {}).get("warehouse") or "").strip()
    title = str(payload.get("title") or f"{agl_ref} {customer}".strip()).strip()
    case_id = payload.get("case_id") or payload.get("id")

    with conn() as c, c.cursor(cursor_factory=RealDictCursor) as cur:
        # 1) Actualizar por case_id solo si pertenece al mismo AGL Ref.
        # Si el usuario abrió un expediente y luego cambió a otro AGL Ref,
        # NO se pisa el anterior: se crea/busca el expediente del nuevo AGL Ref.
        if case_id:
            cur.execute("SELECT agl_ref FROM agl_cases WHERE id=%s", (int(case_id),))
            existing_case = cur.fetchone()
            existing_ref = str(existing_case.get("agl_ref") or "").strip() if existing_case else ""
            same_ref = (not agl_ref and not existing_ref) or (agl_ref and existing_ref and agl_ref.upper() == existing_ref.upper())
            if same_ref:
                cur.execute("""
                    UPDATE agl_cases
                       SET agl_ref=%s, customer=%s, warehouse=%s, title=%s, payload=%s, updated_at=now()
                     WHERE id=%s
                 RETURNING id
                """, (agl_ref, customer, warehouse, title, Json(payload), int(case_id)))
                row = cur.fetchone()
                if row:
                    return int(row["id"]), f"case_{row['id']}.json"
            else:
                payload["case_id"] = None
                case_id = None

        # 2) Si no hay case_id, evitar duplicar por AGL Ref.
        if agl_ref:
            cur.execute("""
                SELECT id
                  FROM agl_cases
                 WHERE upper(coalesce(agl_ref,'')) = upper(%s)
                 ORDER BY updated_at DESC, id DESC
                 LIMIT 1
            """, (agl_ref,))
            existing = cur.fetchone()
            if existing:
                existing_id = int(existing["id"])
                payload["case_id"] = existing_id
                cur.execute("""
                    UPDATE agl_cases
                       SET agl_ref=%s, customer=%s, warehouse=%s, title=%s, payload=%s, updated_at=now()
                     WHERE id=%s
                 RETURNING id
                """, (agl_ref, customer, warehouse, title, Json(payload), existing_id))
                row = cur.fetchone()
                return int(row["id"]), f"case_{row['id']}.json"

        # 3) Crear si es nuevo o borrador sin AGL Ref.
        cur.execute("""
            INSERT INTO agl_cases(agl_ref, customer, warehouse, title, payload)
            VALUES (%s,%s,%s,%s,%s)
            RETURNING id
        """, (agl_ref, customer, warehouse, title, Json(payload)))
        row = cur.fetchone()
        return int(row["id"]), f"case_{row['id']}.json"

def list_cases_db(q: str = "") -> List[Dict[str, Any]]:
    init_supabase_schema()
    qn = f"%{str(q or '').upper()}%"
    with conn() as c, c.cursor(cursor_factory=RealDictCursor) as cur:
        if q:
            cur.execute("""
                SELECT id, agl_ref, customer, warehouse, title, created_at, updated_at
                FROM agl_cases
                WHERE upper(coalesce(agl_ref,'')||' '||coalesce(customer,'')||' '||coalesce(title,'')) LIKE %s
                ORDER BY updated_at DESC LIMIT 200
            """, (qn,))
        else:
            cur.execute("SELECT id, agl_ref, customer, warehouse, title, created_at, updated_at FROM agl_cases ORDER BY updated_at DESC LIMIT 200")
        rows = []
        for r in cur.fetchall():
            d = dict(r)
            if d.get("id") is not None:
                d["filename"] = f"case_{d['id']}.json"
            for k in ("created_at", "updated_at"):
                if d.get(k): d[k] = d[k].strftime("%Y-%m-%d %H:%M:%S")
            rows.append(d)
        return rows


def get_case_db(case_id: int) -> Optional[Dict[str, Any]]:
    init_supabase_schema()
    with conn() as c, c.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT payload FROM agl_cases WHERE id=%s", (int(case_id),))
        row = cur.fetchone()
        if not row:
            return None
        payload = row["payload"] or {}
        payload["case_id"] = int(case_id)
        payload["filename"] = f"case_{int(case_id)}.json"
        return payload
