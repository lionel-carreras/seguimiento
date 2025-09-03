from django.shortcuts import render
from django.db import connections, connection
from .rules import RULES

# -----------------------
# util / conexión
# -----------------------
def _erp_conn():
    try:
        return connections['erp']
    except Exception:
        return connection

def _row_to_dict(row, cols):
    return {cols[i][0]: row[i] for i in range(len(cols))}

def _coerce_id(val):
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    return int(s) if s.isdigit() else s

def _collect_ids(*vals):
    """IDs únicos, preservando orden; cada item tipado (int si numérico)."""
    out, seen = [], set()
    for v in vals:
        s = str(v).strip() if v is not None else ''
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(_coerce_id(s))
    return out

# -----------------------
# queries a ERP
# -----------------------
def _fetch_envio(envio_id: int):
    sql = """
        SELECT TOP 1
            e.EnvioID,
            e.Estado,
            e.ClienteIDOrigen,
            e.ClienteIDDestino,
            e.SucursalIDOrigen,
            e.SucursalIDDestino,
            e.LocalidadOrigen,
            e.LocalidadDestino,
            e.DomicilioDestino,
            e.CodigoPostalDestino,
            e.SucursalIDEmision,
            e.FechaRecepcion,
            e.HoraRecepcion,
            -- sin segundos:
            CONVERT(varchar(10), e.FechaRecepcion, 120)                    AS FechaRecepcionStr,  -- YYYY-MM-DD
            LEFT(CONVERT(varchar(8), CAST(e.HoraRecepcion AS time),108),5) AS HoraRecepcionStr,  -- HH:MM
            e.Bultos,
            -- nombres de sucursales
            so.SucursalNombre AS SucursalOrigenNombre,
            sd.SucursalNombre AS SucursalDestinoNombre,
            se.SucursalNombre AS SucursalEmisionNombre
        FROM Envios e
        LEFT JOIN Sucursales so ON so.SucursalID = e.SucursalIDOrigen
        LEFT JOIN Sucursales sd ON sd.SucursalID = e.SucursalIDDestino
        LEFT JOIN Sucursales se ON se.SucursalID = e.SucursalIDEmision
        WHERE e.EnvioID = %s
    """
    with _erp_conn().cursor() as cur:
        cur.execute(sql, [envio_id])
        row = cur.fetchone()
        return _row_to_dict(row, cur.description) if row else None

def _fetch_movs(envio_id: int):
    sql = """
        SELECT
            CONVERT(varchar(16), m.updated_at, 120) AS updated_at,  -- YYYY-MM-DD HH:MM
            m.EnvioID,
            m.SucursalIDDestino,
            m.SucursalIDActual,
            sa.SucursalNombre AS SucursalActualNombre,
            sd.SucursalNombre AS SucursalDestinoNombre,
            m.operacion,
            m.Estado
        FROM trkpaqmovs m
        LEFT JOIN Sucursales sa ON sa.SucursalID = m.SucursalIDActual
        LEFT JOIN Sucursales sd ON sd.SucursalID = m.SucursalIDDestino
        WHERE m.EnvioID = %s
        ORDER BY m.updated_at DESC
    """
    with _erp_conn().cursor() as cur:
        cur.execute(sql, [envio_id])
        rows = cur.fetchall()
        return [_row_to_dict(r, cur.description) for r in rows]

# ---- clientes ----
def fetch_clientes_by_ids(ids):
    if not ids:
        return {}
    placeholders = ",".join(["%s"] * len(ids))
    sql = f"""
        SELECT ClienteID, ClienteNombre
        FROM Clientes
        WHERE ClienteID IN ({placeholders})
    """
    with _erp_conn().cursor() as cur:
        cur.execute(sql, ids)
        cols = cur.description
        data = {}
        for r in cur.fetchall():
            d = _row_to_dict(r, cols)
            data[str(d.get("ClienteID"))] = d
        return data

def fetch_clientes_for_envio(envio):
    cid_origen  = envio.get("ClienteIDOrigen")
    cid_destino = envio.get("ClienteIDDestino")
    ids = _collect_ids(cid_origen, cid_destino)
    mapa = fetch_clientes_by_ids(ids)
    return {
        "origen":  mapa.get(str(cid_origen))  if cid_origen  is not None else None,
        "destino": mapa.get(str(cid_destino)) if cid_destino is not None else None,
    }

# ---- sucursales ----
def fetch_sucursales_by_ids(ids):
    if not ids:
        return {}
    placeholders = ",".join(["%s"] * len(ids))
    sql = f"""
        SELECT SucursalID, SucursalNombre, Domicilio
        FROM Sucursales
        WHERE SucursalID IN ({placeholders})
    """
    with _erp_conn().cursor() as cur:
        cur.execute(sql, ids)
        cols = cur.description
        data = {}
        for r in cur.fetchall():
            d = _row_to_dict(r, cols)
            data[str(d.get("SucursalID"))] = d
        return data

def fetch_sucursales_for_envio(envio):
    sid_origen  = envio.get("SucursalIDOrigen")
    sid_destino = envio.get("SucursalIDDestino")
    sid_emision = envio.get("SucursalIDEmision")
    ids = _collect_ids(sid_origen, sid_destino, sid_emision)
    mapa = fetch_sucursales_by_ids(ids)
    return {
        "origen":  mapa.get(str(sid_origen))   if sid_origen  is not None else None,
        "destino": mapa.get(str(sid_destino))  if sid_destino is not None else None,
        "emision": mapa.get(str(sid_emision))  if sid_emision is not None else None,
    }

# -----------------------
# mapeos timeline + barra
# -----------------------
def _map_envio_to_step(envio: dict):
    # Primer paso fijo
    fr, hr = envio.get('FechaRecepcionStr'), envio.get('HoraRecepcionStr')
    when = f"{fr} {hr}".strip() if fr or hr else None

    suc_origen_nombre = (
        envio.get('SucursalOrigenNombre')
        or str(envio.get('SucursalIDOrigen') or '-')
    )

    return {
        'key': 'INICIO',
        'label': 'Recibimos tu envío',
        'when': when,
        'done': True,
        'detail': f"Tu envío fue recibido en la sucursal {suc_origen_nombre}"
    }

def _apply_rules(mov, envio):
    for rule in RULES:
        step = rule(mov, envio)
        if step:
            return step
    return None

def _build_progress_bar(envio: dict, timeline: list[dict]) -> list[dict]:
    steps = [
        {'title': 'Recibido',  'subtitle': '-', 'done': False},  # 0
        {'title': 'En camino', 'subtitle': '-', 'done': False},  # 1
        {'title': 'En destino','subtitle': '-', 'done': False},  # 2
        {'title': 'Reparto','subtitle': '-', 'done': False},  # 3
        {'title': 'Entregado', 'subtitle': '-', 'done': False},  # 4
    ]
    # dónde cae cada key
    index_by_key = {
        'CLASIFICACION': 0,   # si preferís que quede en "Recibido" poné 0
        'EN_CAMINO':    1,
        'DESTINO':      2,
        'REPARTO':      3,    # si luego agregás REPARTO, cae en "En destino" (ajusta a gusto)
        'ENTREGA':      4,
    }

    # Buscar INICIO donde esté (ahora queda al final del timeline)
    inicio = next((s for s in timeline if s.get('key') == 'INICIO'), None)
    if inicio:
        steps[0]['subtitle'] = inicio['label']
        steps[0]['done'] = True
    else:
        steps[0]['subtitle'] = (envio.get('Estado') or '-')
        steps[0]['done'] = True

    # Marcar las etapas según el resto de los pasos
    max_idx_done = 0
    seen = set()
    for step in timeline:
        if step.get('key') == 'INICIO':
            continue
        idx = index_by_key.get(step['key'])
        if idx is None or step['key'] in seen:
            continue
        steps[idx]['subtitle'] = step['label']
        steps[idx]['done'] = True
        seen.add(step['key'])
        if idx > max_idx_done:
            max_idx_done = idx

    # todo lo anterior a la etapa más avanzada queda 'done'
    for i in range(max_idx_done):
        steps[i]['done'] = True

    return steps

# -----------------------
# vista
# -----------------------
def envios(request):
    q = (request.GET.get('q') or '').strip()
    envio, movs, timeline, msg = None, [], [], ""

    if q:
        if not q.isdigit():
            msg = "El número de envío debe ser numérico."
        else:
            envio = _fetch_envio(int(q))
            if not envio:
                msg = f"No se encontró el envío #{q}."
            else:
                movs = _fetch_movs(envio['EnvioID'])

                # Timeline: MOVIMIENTOS (DESC) primero; INICIO al final (para que quede abajo)
                timeline, seen = [], set()

                for m in movs:  # DESC: el primero de cada key es el más nuevo
                    s = _apply_rules(m, envio)
                    if not s or s['key'] in seen:
                        continue
                    timeline.append(s)
                    seen.add(s['key'])

                s0 = _map_envio_to_step(envio)
                if s0:
                    timeline.append(s0)  # INICIO queda al fondo del timeline

    # Barra horizontal
    progress_steps = _build_progress_bar(envio, timeline) if envio else []

    # Estado actual (el MÁS RECIENTE = primer elemento del timeline si existe)
    current_step = timeline[0] if timeline else None

    # Datos enriquecidos
    clientes   = fetch_clientes_for_envio(envio)   if envio else {}
    sucursales = fetch_sucursales_for_envio(envio) if envio else {}

    ctx = {
        'q': q,
        'envio': envio,
        'movs': movs,
        'timeline': timeline,
        'progress_steps': progress_steps,
        'current_step': current_step,
        'clientes': clientes,
        'sucursales': sucursales,
        'msg': msg
    }
    return render(request, 'tracking/detail.html', ctx)
