# -*- coding: utf-8 -*-
# Reglas de negocio para armar pasos del timeline desde trkpaqmovs

def _norm(v):
    return (str(v or '')).strip().upper()

def _step(key, label, when, detail=''):
    return {'key': key, 'label': label, 'when': when, 'done': True, 'detail': detail}

# --- REGLAS ---

def rule_clasificacion(mov, envio):
    """
    EN PROCESO DE CLASIFICACIÓN
    - En la sucursal de ORIGEN
    - operacion = 'C'
    """
    try:
        if (
            str(mov.get('SucursalIDActual')) == str(envio.get('SucursalIDOrigen')) and
            _norm(mov.get('operacion')) == 'C'
        ):
            nombre_dest = mov.get('SucursalDestinoNombre') or envio.get('SucursalIDDestino')
            detail = f"Tu envío está en preparación para ser enviado a la sucursal de {nombre_dest}"
            return _step('CLASIFICACION', 'En Proceso de Clasificación', mov.get('updated_at'), detail)
    except Exception:
        pass
    return None

def rule_en_viaje(mov, envio):
    """
    EN CAMINO A DESTINO
    - En la sucursal de ORIGEN
    - operacion = 'V' (viaje)
    """
    try:
        if (
            str(mov.get('SucursalIDActual')) == str(envio.get('SucursalIDOrigen')) and
            _norm(mov.get('operacion')) == 'V'
        ):
            nombre_origen = (
                mov.get('SucursalActualNombre')
                or envio.get('SucursalOrigenNombre')
                or str(envio.get('SucursalIDOrigen') or '-')
            )
            nombre_destino = (
                mov.get('SucursalDestinoNombre')
                or envio.get('SucursalDestinoNombre')
                or str(envio.get('SucursalIDDestino') or '-')
            )
            detail = f"En viaje hacia la sucursal {nombre_destino}"
            return _step('EN_CAMINO', 'En camino a destino', mov.get('updated_at'), detail)
    except Exception:
        pass
    return None


def rule_destino(mov, envio):
    """
    RECIBIDO EN SUCURSAL DESTINO
    - En la sucursal de DESTINO
    - operacion = 'D'
    """
    try:
        if (
            str(mov.get('SucursalIDActual')) == str(envio.get('SucursalIDDestino')) and
            _norm(mov.get('operacion')) == 'D'
        ):
            nombre_dest = mov.get('SucursalDestinoNombre') or envio.get('SucursalIDDestino')
            return _step(
                'DESTINO',
                'Recibido en Suc. Destino',
                mov.get('updated_at'),
                f'Tu envío está en el centro de distribución {nombre_dest}'
            )
    except Exception:
        pass
    return None


# Registro en orden (la primera que matchee, gana)
RULES = [
    rule_clasificacion,
    rule_en_viaje,
    rule_destino,
]
