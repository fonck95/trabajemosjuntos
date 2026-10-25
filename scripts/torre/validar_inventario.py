"""Valida el inventario de dotación de la torre con las reglas I1 a I13 del contrato (ESPECIFICACION_INTEGRACION.md, 4.6).

Uso:
  python3 scripts/torre/validar_inventario.py
      inventario_dotacion.json contra dotacion.json, laboratorio.json, la planta, el catálogo, implementos.json,
      exigencias_3100.json, habilitacion.json y las reglas escritas a mano (todo en data/).
  python3 scripts/torre/validar_inventario.py --fixture INVENTARIO_DATOS DOTACION
      un fixture de la forma de datos (4.5) contra su propia dotación de prueba; la planta es el archivo de
      insumos_sha1 que nombra «plantas» y la matriz, habilitacion_min.json, los dos junto al fixture
      (se pueden cambiar con --plantas y --habilitacion).
  python3 scripts/torre/validar_inventario.py --web INVENTARIO_WEB
      la forma web compacta (10.2) con su esquema y contra catalogo_equipos.json.

Imprime un informe JSON en la salida estándar (y un resumen de una línea en la de errores) y sale con 1 si hay errores
duros. Solo biblioteca estándar.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import comun as C  # noqa: E402

REGLAS = {
    'insumos': ('Insumos presentes y huellas al día (insumos_sha1 y sha256_dotacion)', 'duro'),
    'I1': ('Unidades por línea = cantidad; ids únicos y estables (regla 1.3); sin colisiones de h6', 'duro'),
    'I2': ('Sumas de precio por servicio iguales a la dotación; precio de cada línea igual al de su fuente', 'duro'),
    'I3': ('Huella de cada unidad de piso dentro del polígono libre (2 cm); las de pared tocan un muro; las de cielo, el cielo', 'duro'),
    'I4': ('Sin traslapes entre huellas de piso', 'duro'),
    'I5': ('Área de barrido de cada puerta libre', 'duro'),
    'I6': ('Paso libre ≥ 0,90 m desde una puerta o un vano abierto hasta un costado de cada cama, camilla, cuna, sillón y unidad odontológica', 'duro'),
    'I7': ('Cada exigencia evaluada con estado; diferencias con la investigación explicadas', 'duro'),
    'I8': ('Cada unidad con clase de riesgo de la enumeración, registro INVIMA y mantenimiento', 'duro'),
    'I9': ('dentro_de apunta a un contenedor del mismo recinto y a uno de sus compartimientos', 'duro'),
    'I10': ('apoyo en el mismo recinto y z = cara superior del apoyo (± 1 cm)', 'duro'),
    'I11': ('Ninguna unidad sin recinto, salvo fuera de la torre y equipos de cubierta', 'duro'),
    'I12': ('Nombres de línea en reglas y cubre_con coinciden; ambientes por nombre a una sola fila', 'duro'),
    'I13': ('Líneas de laboratorio.json en comodato suman $955.708.589', 'duro'),
    'I14': ('Todo el equipamiento fijo de dotacion.json queda ubicado (16.6)', 'duro'),
    'I15': ('Laboratorio completo: analizadores de laboratorio.json y dotación del laboratorio y la toma de muestras en sus recintos, '
            'con reactivos por prueba del menú (16.2)', 'duro'),
    'I16': ('Infraestructura sin precio de dotación y con su ítem de obra de presupuesto.json (16.3)', 'duro'),
    'I17': ('Paso físico con el mobiliario (6.4 y revisión adversarial): con las huellas de piso de más de 0,5 m² como obstáculo, '
            'un caminante de radio 0,30 m llega a cada recinto y a cada conexión vertical de su nivel, en una sola zona por cota; '
            'las unidades de cubierta y exteriores (recinto null) no chocan con muros, columnas ni otras unidades', 'duro'),
}
REGLAS_WEB = {'esquema': ('Forma web (10.2): campos, tipos e índices', 'duro'),
              'catalogo': ('Catálogo web igual a catalogo_equipos.json (lista cerrada del Anexo C)', 'duro')}

CLASES = ('I', 'IIa', 'IIb', 'III', 'no_dm', 'ivd', 'por_confirmar')
ESTADOS_CLASE = ('coherente', 'discrepancia', 'probable_discrepancia', 'regimen_distinto', 'por_confirmar', 'observacion')
ES_DM = ('si', 'no', 'ivd', 'por_confirmar')
REQUERIDO = ('si', 'no', 'por_confirmar')
PRIORIDADES = ('habilitacion', 'recomendado', 'por_confirmar', 'no_aplica')
MONTAJES = ('piso', 'pared', 'cielo', 'sobre', 'dentro', 'en_nucleo')
ESTADOS_UNIDAD = ('en_dotacion', 'cierre_brechas_propuesto', 'fuera_de_la_torre', 'cubierta', 'infraestructura', 'contexto')
ESTADOS_EXIG = ('cumple', 'parcial', 'falta', 'documento_pendiente', 'no_aplica')
EXIGIBLE = ('si', 'por_confirmar')
VERIFICACION = ('literal_compilacion', 'contenido_compilacion', 'fuente_secundaria', 'por_confirmar')
HABILITABLE = ('si', 'no', 'modalidad', 'sin_habilitacion_propia')
DE_INVESTIGACION = {'cubierto': 'cumple', 'parcial': 'parcial', 'falta': 'falta'}
COLUMNAS_WEB = ['id', 'linea_idx', 'piso', 'recinto', 'x', 'y', 'z', 'rot_z', 'apoyo_idx', 'dentro_de_idx', 'componente_de_idx',
                'montaje', 'estado']
TIPOS_IMPLEMENTO = ('equipo_biomedico', 'dispositivo', 'instrumental', 'insumo', 'medicamento')
FAMILIAS_PACIENTE = ('cama', 'camilla')
MODELOS_PACIENTE = ('sillon_reclinable', 'sillon_toma_muestras', 'unidad_odontologica')
LETRA_POR_LISTA = {'equipos': 'e', 'mobiliario': 'm', 'equipamiento_fijo': 'f'}
NOTA_SIN_EXIGENCIA = 'sin exigencia literal encontrada'
COMODATO_COP = 955708589
PASO_LIBRE_M = 0.90
SERVICIOS_LABORATORIO = ('Laboratorio clínico', 'Toma de muestras de laboratorio clínico')
PRESUPUESTO = C.TORRE / 'presupuesto.json'


def es_puesto_paciente(modelo: str, familia: str, variante=None, nombre_linea=None) -> bool:
    """Puestos de paciente de la regla I6: camas, camillas, cunas, sillones de paciente y unidades odontológicas. No lo son
    las camillas de transporte estacionadas, las plegadas guardadas ni los sillones de acompañante."""
    if variante == 'plegada' or modelo == 'camilla_transporte':
        return False
    if 'acompañante' in str(nombre_linea or '').lower():
        return False
    return familia in FAMILIAS_PACIENTE or modelo in MODELOS_PACIENTE


def en_vano(punto, muro, tol=0.03) -> bool:
    """¿El punto queda sobre el tramo interior (sin los 5 cm de cada punta) de un muro «abierto» (vano sin muro)?"""
    a, b = muro['a'], muro['b']
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    if L < 0.1:
        return False
    t = ((punto[0] - a[0]) * (b[0] - a[0]) + (punto[1] - a[1]) * (b[1] - a[1])) / L
    return 0.05 < t < L - 0.05 and C.distancia_punto_segmento(punto, a, b) < tol


def num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def entero(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


# --------------------------------------------------------------------------------------------------------------------
# Planta: recintos por id con su nivel
# --------------------------------------------------------------------------------------------------------------------
class Planta:
    def __init__(self, plantas: dict | None):
        self.recintos, self.nivel_de, self.niveles, self.subrecintos = {}, {}, {}, {}
        self.puertas_de, self.muros, self.abiertos_de = {}, {}, {}
        if not plantas:
            return
        for n in plantas.get('niveles', []):
            self.niveles[n.get('id')] = n
            pol = {}
            for r in n.get('recintos', []):
                self.recintos[r['id']] = r
                self.nivel_de[r['id']] = n
                pol[r['id']] = C.orientar_antihorario(r['poligono'])
            # baños y cabinas (subrecintos): lo que va adentro se revisa contra su polígono libre y su puerta
            for sb, r in C.subrecintos(n):
                self.subrecintos[sb['id']] = dict(sb, ambiente=sb.get('nombre'), z_piso_m=r.get('z_piso_m'), padre=r['id'])
                self.nivel_de[sb['id']] = n
                pol[sb['id']] = C.orientar_antihorario(sb['poligono'])
            muros = {m['id']: m for m in n.get('muros', [])}
            self.muros.update(muros)
            for m in n.get('muros', []):
                if m.get('tipo') == 'abierto':
                    for lado in m.get('lados') or []:
                        self.abiertos_de.setdefault(lado, []).append((m, pol))
            for pt in n.get('puertas', []):
                m = muros.get(pt.get('muro'))
                if not m:
                    continue
                for lado in (pt.get('desde'), pt.get('hacia')):
                    self.puertas_de.setdefault(lado, []).append((pt, m, pol))

    def libre(self, rid):
        r = self.recintos.get(rid) or self.subrecintos.get(rid)
        return C.orientar_antihorario(r['poligono_libre']) if r and r.get('poligono_libre') else None


# --------------------------------------------------------------------------------------------------------------------
# Forma de datos (4.5): modo normal y --fixture
# --------------------------------------------------------------------------------------------------------------------
class ValidadorDatos:
    def __init__(self, inf: C.Informe, inv: dict, dot: dict, cat: dict, planta: Planta, hab: dict | None,
                 exig: list | None, lab: dict | None, impl: dict | None, reglas_ub: dict | None, reglas_ex: dict | None,
                 programa: dict | None, fixture: bool):
        self.inf, self.inv, self.dot, self.cat, self.planta = inf, inv, dot, cat, planta
        self.hab, self.exig, self.lab, self.impl = hab, exig, lab, impl
        self.reglas_ub, self.reglas_ex, self.programa, self.fixture = reglas_ub, reglas_ex, programa, fixture
        self.lineas = [l for l in inv.get('lineas', []) if isinstance(l, dict)]
        self.unidades = [u for u in inv.get('unidades', []) if isinstance(u, dict)]
        self.L = {l.get('id'): l for l in self.lineas}
        self.U = {u.get('id'): u for u in self.unidades}
        self.modelos = cat.get('modelos', {})

    def err(self, r, m):
        self.inf.error(r, m)

    def av(self, r, m):
        self.inf.aviso(r, m)

    # ------------------------------------------------------------------------------------------------ utilidades
    def modelo_de(self, u):
        l = self.L.get(u.get('linea')) or {}
        m = u.get('modelo3d') or l.get('modelo3d')
        return m, self.modelos.get(m)

    def dim_de(self, u):
        m, d = self.modelo_de(u)
        l = self.L.get(u.get('linea')) or {}
        dim = u.get('dim_m') or l.get('dim_m') or (d or {}).get('dim_m')
        var = u.get('variante') or l.get('variante')
        if var and d and var in d.get('variantes', {}) and 'dim_m' in d['variantes'][var]:
            dim = d['variantes'][var]['dim_m']
        return dim

    def columnas_torre(self):
        """[(z0, z1, polígono, id)] de las columnas de los pisos de la torre con su sección del prediseño y la altura del
        piso (cotas absolutas)."""
        if getattr(self, '_cols_torre', None) is None:
            self._cols_torre = []
            for nid, n in self.planta.niveles.items():
                z0 = float(n.get('z') or 0.0)
                z1 = z0 + float(n.get('altura_entrepiso_m') or 0.0)
                for c in n.get('columnas', []) or []:
                    if not all(isinstance(c.get(k), (int, float)) for k in ('x', 'y')):
                        continue
                    b, hh = float(c.get('b', 0.6)) / 2, float(c.get('h', 0.6)) / 2
                    self._cols_torre.append((z0, z1, C.rect_a_poligono([c['x'] - b, c['y'] - hh, c['x'] + b, c['y'] + hh]),
                                             f'{c.get("id")} del {nid}'))
        return self._cols_torre

    def huella(self, u):
        dim = self.dim_de(u)
        pos = u.get('posicion')
        if not dim or not (isinstance(pos, list) and len(pos) >= 3 and all(num(x) for x in pos)):
            return None
        return C.rect_girado(pos[0], pos[1], dim[0], dim[1], u.get('rotacion_z') or 0.0)

    def es_base(self, u):
        m = C.RE_UNIDAD.match(str(u.get('id')))
        return bool(m) and m.group(4) is None

    def entrada_dotacion(self, l):
        ref = l.get('ref') or {}
        if l.get('origen') != 'dotacion' or not isinstance(ref, dict):
            return None
        lista, idx = ref.get('lista'), ref.get('idx')
        if lista == 'equipamiento_fijo':
            fuente = self.dot.get('equipamiento_fijo', [])
        else:
            srv = next((s for s in self.dot.get('servicios', []) if s.get('id') == ref.get('servicio')), None)
            fuente = (srv or {}).get(lista, [])
        if entero(idx) and 0 <= idx < len(fuente):
            return fuente[idx]
        return None

    # ------------------------------------------------------------------------------------------------ I1
    def i1(self):
        h6s = {}
        for l in self.lineas:
            lid = str(l.get('id'))
            self.inf.revisado('I1')
            m = C.RE_LINEA.match(lid)
            if not m:
                self.err('I1', f'{lid}: id de línea mal formado (L-servicio-tipo-h6)')
                continue
            servicio, letra, h = m.groups()
            if servicio != l.get('servicio') and not (letra == 'f' and servicio == 'fijo'):
                self.err('I1', f'{lid}: el servicio del id no es «{l.get("servicio")}»')
            origen = l.get('origen')
            if origen != C.ORIGEN_POR_LETRA[letra]:
                self.err('I1', f'{lid}: la letra «{letra}» exige origen «{C.ORIGEN_POR_LETRA[letra]}» y la línea dice «{origen}»')
            lista = (l.get('ref') or {}).get('lista') if isinstance(l.get('ref'), dict) else None
            if origen == 'dotacion' and LETRA_POR_LISTA.get(lista) != letra:
                self.err('I1', f'{lid}: la lista «{lista}» de la referencia no corresponde a la letra «{letra}»')
            esperado = C.h6(str(origen), servicio, letra, str(l.get('nombre')))
            if esperado != h:
                self.err('I1', f'{lid}: el h6 de «{origen}|{servicio}|{letra}|{l.get("nombre")}» es {esperado} (regla 1.3)')
            h6s.setdefault(h, []).append(lid)
            if not entero(l.get('cantidad')) or l['cantidad'] < 0:
                self.err('I1', f'{lid}: cantidad no entera')
        for h, ids in h6s.items():
            if len(set(ids)) > 1:
                self.err('I1', f'colisión de h6 {h} entre {sorted(set(ids))}')
        ids_l = [l.get('id') for l in self.lineas]
        rep = sorted({x for x in ids_l if ids_l.count(x) > 1}, key=str)
        if rep:
            self.err('I1', f'ids de línea repetidos: {rep}')
        ids_u = [u.get('id') for u in self.unidades]
        rep = sorted({x for x in ids_u if ids_u.count(x) > 1}, key=str)
        if rep:
            self.err('I1', f'ids de unidad repetidos: {rep}')
        por_linea = {}
        for u in self.unidades:
            uid = str(u.get('id'))
            self.inf.revisado('I1')
            m = C.RE_UNIDAD.match(uid)
            l = self.L.get(u.get('linea'))
            if not m:
                self.err('I1', f'{uid}: id de unidad mal formado (U-servicio-h6-kkk[-cn])')
                continue
            if l is None:
                self.err('I1', f'{uid}: la línea {u.get("linea")!r} no existe')
                continue
            srv, _, h = C.partes_linea(l['id'])
            if (m.group(1), m.group(2)) != (srv, h):
                self.err('I1', f'{uid}: el id no corresponde a su línea {l["id"]}')
            if m.group(4) is None:
                if u.get('k') != int(m.group(3)):
                    self.err('I1', f'{uid}: k = {u.get("k")} y el id dice {int(m.group(3))}')
                por_linea.setdefault(l['id'], []).append(int(m.group(3)))
            else:
                madre = uid.rsplit('-c', 1)[0]
                if madre not in self.U:
                    self.err('I1', f'{uid}: componente de una unidad que no existe ({madre})')
                if u.get('componente_de') not in (None, madre):
                    self.err('I1', f'{uid}: componente_de = {u.get("componente_de")!r} y el id dice {madre}')
        for l in self.lineas:
            ks = sorted(por_linea.get(l.get('id'), []))
            if l.get('tipo') == 'servicio' or l.get('sin_unidades'):
                if ks:
                    self.err('I1', f'{l.get("id")}: es un servicio sin unidades físicas y tiene {len(ks)} unidades')
                continue
            if entero(l.get('cantidad')) and ks != list(range(1, l['cantidad'] + 1)):
                self.err('I1', f'{l.get("id")}: {len(ks)} unidades (k = {ks}) para cantidad {l.get("cantidad")}')

    # ------------------------------------------------------------------------------------------------ I2
    def i2(self):
        calc = {}
        for l in self.lineas:
            d = self.entrada_dotacion(l)
            if l.get('origen') == 'dotacion':
                self.inf.revisado('I2')
                if d is None:
                    self.err('I2', f'{l.get("id")}: la referencia {l.get("ref")} no apunta a una línea de la dotación')
                    continue
                for campo_l, campo_d in (('precio_unitario_cop_2026', 'precio_unitario_cop_2026'),
                                         ('rango_precio_unitario_cop_2026', 'rango_precio_unitario_cop_2026'),
                                         ('tipo_precio', 'tipo_precio'), ('cantidad', 'cantidad')):
                    if campo_d in d and l.get(campo_l) != d.get(campo_d):
                        self.err('I2', f'{l.get("id")}: {campo_l} = {l.get(campo_l)!r} y la dotación dice {d.get(campo_d)!r}')
        for u in self.unidades:
            l = self.L.get(u.get('linea'))
            if not l or not self.es_base(u) or l.get('origen') != 'dotacion' or u.get('estado') == 'cierre_brechas_propuesto':
                continue
            precio = l.get('precio_unitario_cop_2026') or 0
            lista = (l.get('ref') or {}).get('lista')
            clave = 'fijo' if lista == 'equipamiento_fijo' else l.get('servicio')
            c = calc.setdefault(clave, {'unidades': 0, 'equipos': 0, 'mobiliario': 0, 'fijo': 0})
            c['unidades'] += 1
            c[{'equipos': 'equipos', 'mobiliario': 'mobiliario'}.get(lista, 'fijo')] += precio
        tot_inv = ((self.inv.get('totales') or {}).get('por_servicio') or {})
        for s in self.dot.get('servicios', []):
            sid = s.get('id')
            t = s.get('totales') or {}
            c = calc.get(sid, {'unidades': 0, 'equipos': 0, 'mobiliario': 0})
            self.inf.revisado('I2')
            for k, campo in (('equipos', 'equipos_cop_2026'), ('mobiliario', 'mobiliario_cop_2026')):
                if num(t.get(campo)) and c[k] != t[campo]:
                    self.err('I2', f'{sid}: {k} suman ${c[k]:,} en el inventario y ${t[campo]:,} en la dotación'.replace(',', '.'))
            ti = tot_inv.get(sid)
            if ti is None:
                if c['unidades']:
                    self.err('I2', f'{sid}: falta en totales.por_servicio')
                continue
            for k, campo in (('equipos', 'equipos_cop_2026'), ('mobiliario', 'mobiliario_cop_2026')):
                if ti.get(campo) != c[k]:
                    self.err('I2', f'{sid}: totales.por_servicio.{campo} = {ti.get(campo)} y las unidades suman {c[k]}')
            if ti.get('unidades') != c['unidades']:
                self.err('I2', f'{sid}: totales.por_servicio.unidades = {ti.get("unidades")} y hay {c["unidades"]}')
            coincide = all(not num(t.get(campo)) or c[k] == t[campo]
                           for k, campo in (('equipos', 'equipos_cop_2026'), ('mobiliario', 'mobiliario_cop_2026')))
            if ti.get('coincide_con_dotacion') is not coincide:
                self.err('I2', f'{sid}: coincide_con_dotacion = {ti.get("coincide_con_dotacion")} y el cálculo da {coincide}')
        if self.dot.get('equipamiento_fijo'):
            meta = (self.dot.get('totales_equipamiento_fijo') or {}).get('total_cop_2026')
            hecho = calc.get('fijo', {}).get('fijo', 0)
            self.inf.revisado('I2')
            if num(meta) and hecho != meta:
                self.err('I2', f'equipamiento fijo: ${hecho:,} en el inventario y ${meta:,} en la dotación'.replace(',', '.'))

    # ------------------------------------------------------------------------------------------------ I3 a I6
    def unidades_en(self, rid):
        return [u for u in self.unidades if u.get('recinto') == rid]

    def i3_a_i6(self):
        if not self.planta.recintos:
            for k in ('I3', 'I4', 'I5', 'I6'):
                self.err(k, 'no hay planta para comprobar posiciones')
            return
        por_recinto = {}
        for u in self.unidades:
            if u.get('recinto') is not None:
                # lo que va en un baño o una cabina se revisa en su subrecinto (polígono libre, puerta y paso propios)
                por_recinto.setdefault(u.get('subrecinto') or u['recinto'], []).append(u)
        for rid, us in por_recinto.items():
            r = self.planta.recintos.get(rid)
            if r is None and rid in self.planta.subrecintos:
                r = self.planta.subrecintos[rid]
                malos = [u.get('id') for u in us if u.get('recinto') != r['padre']]
                if malos:
                    self.err('I3', f'{rid}: el subrecinto es de {r["padre"]} y {malos} dicen otro recinto')
            if r is None:
                continue          # I11 lo informa
            nivel = self.planta.nivel_de[rid]
            libre = self.planta.libre(rid)
            alto_libre = nivel.get('altura_libre_m', 3.0)
            z0 = float(r.get('z_piso_m') or 0.0)          # piso del recinto respecto al de su nivel (terraza del piso 3)
            de_piso = []
            cols = [C.rect_a_poligono([c['x'] - c.get('b', 0.6) / 2, c['y'] - c.get('h', 0.6) / 2, c['x'] + c.get('b', 0.6) / 2,
                                       c['y'] + c.get('h', 0.6) / 2]) + [c.get('id')] for c in nivel.get('columnas', []) or []]
            cajas3d = []
            for u in us:
                uid = u.get('id')
                mid, m = self.modelo_de(u)
                if m is None:
                    self.err('I3', f'{uid}: modelo3d {mid!r} no está en el catálogo')
                    continue
                if u.get('piso') != nivel.get('piso'):
                    self.err('I3', f'{uid}: piso {u.get("piso")!r} y su recinto {rid} es del piso {nivel.get("piso")!r}')
                h = self.huella(u)
                mont = u.get('montaje')
                if h is None or libre is None:
                    self.err('I3', f'{uid}: sin posición o sin polígono libre para comprobar')
                    continue
                self.inf.revisado('I3')
                dim, z = self.dim_de(u), u['posicion'][2] - z0
                if mont in ('piso', 'pared', 'cielo', 'en_nucleo'):
                    for cp in cols:
                        if C.convexos_se_traslapan(h, cp[:4], 0.02):
                            self.err('I3', f'{uid} ({mid}): la huella entra en la columna {cp[4]} (las columnas van de piso a cielo)')
                if mont in ('piso', 'pared', 'cielo', 'en_nucleo', 'sobre'):
                    cajas3d.append((u, h, z, z + dim[2], mid))
                if mont in ('piso', 'en_nucleo'):
                    if not C.poligono_dentro_de(h, libre, 0.02):
                        self.err('I3', f'{uid} ({mid}): la huella se sale del polígono libre de {rid}')
                    if abs(z) > 0.01 and mont == 'piso':
                        self.err('I3', f'{uid}: montaje de piso con z = {z}')
                    de_piso.append((u, h, mid, m))
                elif mont == 'pared':
                    if not C.poligono_dentro_de(h, libre, 0.02):
                        self.err('I3', f'{uid} ({mid}): la huella se sale del polígono libre de {rid}')
                    rot = u.get('rotacion_z') or 0.0
                    p = u['posicion']
                    espalda = (p[0] + math.sin(rot) * dim[1] / 2, p[1] - math.cos(rot) * dim[1] / 2)
                    if C.distancia_a_borde(espalda, libre) > 0.02:
                        self.err('I3', f'{uid} ({mid}): montaje de pared y su espalda no toca la cara de un muro')
                    elif any(en_vano(espalda, mu) for mu, _pol in self.planta.abiertos_de.get(rid, [])):
                        self.err('I3', f'{uid} ({mid}): montaje de pared en un vano abierto (no hay muro)')
                    if z < 0.30:
                        de_piso.append((u, h, mid, m))
                elif mont == 'cielo':
                    if not C.poligono_dentro_de(h, libre, 0.02):
                        self.err('I3', f'{uid} ({mid}): la huella se sale del polígono libre de {rid} (entra en un muro)')
                    if abs(z + dim[2] - alto_libre) > 0.02:
                        self.err('I3', f'{uid} ({mid}): montaje de cielo con z + alto = {z + dim[2]:.2f} m y el cielo está a {alto_libre} m')
            # I4: traslapes entre huellas de piso
            for i, (u1, h1, *_r1) in enumerate(de_piso):
                for u2, h2, *_r2 in de_piso[i + 1:]:
                    self.inf.revisado('I4')
                    if C.convexos_se_traslapan(h1, h2, 0.005):
                        self.err('I4', f'{rid}: {u1.get("id")} y {u2.get("id")} se traslapan')
            # I4 (3D): cajas de pared, de cielo, de piso y sobre apoyos que se cruzan en el espacio (salvo apoyo y contenido)
            for i, (u1, h1, a1, b1, m1) in enumerate(cajas3d):
                for u2, h2, a2, b2, m2 in cajas3d[i + 1:]:
                    if u1.get('montaje') in ('piso', 'en_nucleo') and u2.get('montaje') in ('piso', 'en_nucleo'):
                        continue          # ya revisado arriba con las huellas de piso
                    if u1.get('apoyo') == u2.get('id') or u2.get('apoyo') == u1.get('id'):
                        continue
                    if min(b1, b2) - max(a1, a2) <= 0.01:
                        continue
                    self.inf.revisado('I4')
                    if C.convexos_se_traslapan(h1, h2, 0.005):
                        self.err('I4', f'{rid}: {u1.get("id")} ({m1}) y {u2.get("id")} ({m2}) se cruzan en 3D '
                                       f'(z {a1:.2f}-{b1:.2f} y {a2:.2f}-{b2:.2f} m)')
            # I5: barrido de puertas
            for pt, muro, pol in self.planta.puertas_de.get(rid, []):
                for hoja in C.hojas_puerta(pt, muro, pol):
                    if hoja['lado'] != rid:
                        continue
                    self.inf.revisado('I5')
                    pts = C.sector(hoja['bisagra'], hoja['radio'], hoja['ang0'], hoja['ang1'])
                    for u, h, mid, _m in de_piso:
                        if any(C.punto_estrictamente_dentro(x, h, 0.005) for x in pts) or \
                           any(C.en_sector(v, hoja['bisagra'], hoja['radio'], hoja['ang0'], hoja['ang1'], 0.005) for v in h):
                            self.err('I5', f'{rid}: {u.get("id")} ({mid}) queda en el barrido de la puerta {pt.get("id")}')
            # I6: paso libre a un costado de camas, camillas, cunas, sillones y unidades odontológicas
            pacientes = [(u, h, mid, m) for u, h, mid, m in de_piso
                         if es_puesto_paciente(mid, m.get('familia'), u.get('variante') or (self.L.get(u.get('linea')) or {}).get('variante'),
                                               (self.L.get(u.get('linea')) or {}).get('nombre'))]
            if pacientes:
                self.i6(rid, libre, de_piso, pacientes)

    def i6(self, rid, libre, de_piso, pacientes):
        x0, y0, x1, y1 = C.caja(libre)
        rej = C.Rejilla(x0 - 0.2, y0 - 0.2, x1 + 0.2, y1 + 0.2, 0.10)
        rej.pintar_poligono(libre, 1)
        for _u, h, _mid, _m in de_piso:
            rej.pintar_poligono(h, 0)
        holgura = rej.holgura()
        # paso de 0,90 m: el centro de cada celda del camino queda a 0,45 m o más del centro de la celda ocupada más cercana
        umbral = PASO_LIBRE_M / 2
        transitable = bytearray(1 if rej.libre[k] and holgura[k] >= umbral - 1e-9 else 0 for k in range(len(rej.libre)))
        semillas = []

        def semilla(punto, muro, pol):
            n = C.normal_hacia(muro['a'], muro['b'], punto, pol[rid]) if rid in pol else None
            if n is None:
                return
            for paso in (0.5, 0.6, 0.7, 0.8):
                d = float(muro.get('espesor', 0.12) or 0.0) / 2 + paso
                c = rej.celda_de(punto[0] + n[0] * d, punto[1] + n[1] * d)
                if c and transitable[c[1] * rej.nx + c[0]]:
                    semillas.append(c)
                    return
        for pt, muro, pol in self.planta.puertas_de.get(rid, []):
            if pt.get('hacia') in self.planta.subrecintos and pt.get('desde') == rid:
                continue              # la puerta del baño propio no es una entrada al recinto
            semilla(pt['centro'], muro, pol)
        # los vanos abiertos (muro «abierto» de la planta) también son entradas, cada 0,20 m
        for muro, pol in self.planta.abiertos_de.get(rid, []):
            L = math.hypot(muro['b'][0] - muro['a'][0], muro['b'][1] - muro['a'][1])
            s = 0.3
            while s <= L - 0.3 + 1e-9:
                semilla((muro['a'][0] + (muro['b'][0] - muro['a'][0]) * s / L, muro['a'][1] + (muro['b'][1] - muro['a'][1]) * s / L),
                        muro, pol)
                s = round(s + 0.2, 6)
        for u, h, mid, m in pacientes:
            self.inf.revisado('I6')
            if not semillas:
                self.err('I6', f'{rid}: no hay paso libre de {PASO_LIBRE_M} m junto a ninguna puerta ni vano abierto del recinto')
                return
            dist = rej.distancias(semillas, transitable)
            dim = self.dim_de(u)
            p, rot = u['posicion'], u.get('rotacion_z') or 0.0
            alcanza = False
            for j in range(rej.ny):
                for i in range(rej.nx):
                    k = j * rej.nx + i
                    if math.isinf(dist[k]):
                        continue
                    lx, ly = C.a_local(rej.centro(i, j), p[0], p[1], rot)
                    if abs(ly) <= dim[1] / 2 and dim[0] / 2 < abs(lx) <= dim[0] / 2 + umbral + 0.25:
                        alcanza = True
                        break
                if alcanza:
                    break
            if not alcanza:
                self.err('I6', f'{rid}: {u.get("id")} ({mid}) sin paso libre de {PASO_LIBRE_M} m desde la puerta hasta uno de sus costados')

    # ------------------------------------------------------------------------------------------------ I17
    def i17(self):
        """Paso físico con el mobiliario: lo que tapa vanos, puertas y corredores no se ve en I5 ni en I6."""
        if not self.planta.niveles:
            self.err('I17', 'no hay planta para comprobar el paso físico')
            return
        grandes, nulas = {}, {}
        for u in self.unidades:
            # nivel de la unidad (o el de su recinto, si la unidad no lo trae)
            nid = u.get('nivel') or (self.planta.nivel_de.get(u.get('recinto')) or {}).get('id')
            # la cabina del ascensor (en_nucleo) se pisa: no es obstáculo
            if u.get('montaje') != 'piso' or u.get('posicion') is None:
                if u.get('recinto') is None and u.get('posicion') is not None and u.get('montaje') not in ('dentro',):
                    nulas.setdefault(nid, []).append(u)
                continue
            h = self.huella(u)
            if h is None:
                continue
            if u.get('recinto') is None:
                nulas.setdefault(nid, []).append(u)
            dim = self.dim_de(u)
            if dim[0] * dim[1] > 0.5 + 1e-9:
                grandes.setdefault(nid, []).append(C.caja(h))
        for nid, n in self.planta.niveles.items():
            self.inf.revisado('I17')
            sem = C.semillas_de_paso(n)
            if not sem:
                continue
            r = C.alcance_fisico(n, 0.30, sem, obstaculos=grandes.get(nid, []))
            for nombre in r['sin_lugar']:
                self.err('I17', f'{nid}: {nombre}: el mobiliario no deja dónde pararse (radio 0,30 m)')
            for z, grupos in sorted(r['por_cota'].items()):
                if len(grupos) > 1:
                    self.err('I17', f'{nid}: a la cota {z:+.2f} m el mobiliario parte el nivel en {len(grupos)} zonas: '
                                    + ' | '.join(', '.join(g) for g in grupos))
            for rid in r['no_alcanzables']:
                amb = (self.planta.recintos.get(rid) or self.planta.subrecintos.get(rid) or {}).get('ambiente') or ''
                if amb.startswith('Montacargas'):
                    continue
                self.err('I17', f'{nid}: {rid} ({amb}): el mobiliario no deja llegar (radio 0,30 m)')
            # unidades sin recinto (cubierta y exteriores): ni muros, ni columnas, ni otras unidades
            us = nulas.get(nid, [])
            if not us:
                continue
            muros = [m for m in n.get('muros', []) if m.get('tipo') != 'abierto' and float(m.get('espesor') or 0) > 0]
            cajas = []
            z_nivel = float(n.get('z') or 0.0)
            for u in us:
                h = self.huella(u)
                if h is None:
                    continue
                dim = self.dim_de(u)
                z = float(u['posicion'][2])
                cajas.append((u, h, z, z + dim[2]))
                # columnas de la torre a la misma altura, de cualquier piso (coordinación BIM, 17.4): la marquesina de la
                # bahía y las filas de la terraza del piso 3 quedan junto a las columnas de los pisos 2 y 4
                za, zb_u = z_nivel + z, z_nivel + z + dim[2]
                for c_z0, c_z1, c_pol, c_id in self.columnas_torre():
                    if min(zb_u, c_z1) - max(za, c_z0) > 0.01 and C.convexos_se_traslapan(h, c_pol, 0.005):
                        self.err('I17', f'{u.get("id")} ({self.modelo_de(u)[0]}, {nid}): entra en la columna {c_id} '
                                        f'(de {c_z0:.2f} a {c_z1:.2f} m)')
                for m in muros:
                    e = float(m['espesor']) / 2
                    zb = float(m.get('z_base_m') or 0.0)
                    if not (z < zb + float(m.get('altura') or 0) - 0.01 and z + dim[2] > zb + 0.01):
                        continue
                    (ax, ay), (bx, by) = m['a'], m['b']
                    caja_m = [min(ax, bx) - (e if ax == bx else 0), min(ay, by) - (e if ay == by else 0),
                              max(ax, bx) + (e if ax == bx else 0), max(ay, by) + (e if ay == by else 0)]
                    if C.convexos_se_traslapan(h, C.rect_a_poligono(caja_m), 0.005):
                        self.err('I17', f'{u.get("id")} ({self.modelo_de(u)[0]}, {nid}): atraviesa el muro {m.get("id")}')
            for i, (u1, h1, a1, b1) in enumerate(cajas):
                for u2, h2, a2, b2 in cajas[i + 1:]:
                    if u1.get('apoyo') == u2.get('id') or u2.get('apoyo') == u1.get('id'):
                        continue
                    if min(b1, b2) - max(a1, a2) > 0.01 and C.convexos_se_traslapan(h1, h2, 0.005):
                        self.err('I17', f'{nid}: {u1.get("id")} y {u2.get("id")} se cruzan')

    # ------------------------------------------------------------------------------------------------ I7
    def registro_exigencias(self):
        reg = {}
        if self.exig:
            for e in self.exig:
                reg[e.get('id')] = e
        if self.hab:
            for s in self.hab.get('servicios', []):
                for e in s.get('exigencias', []) or []:
                    reg.setdefault(e.get('id'), e)
            for e in (self.hab.get('todos_los_servicios') or {}).get('detalle', []) or []:
                reg.setdefault(e.get('id'), e)
        return reg

    def i7(self):
        reg = self.registro_exigencias()
        if not reg:
            self.err('I7', 'no hay registro de exigencias (exigencias_3100.json o habilitacion.json)')
        for l in self.lineas:
            self.inf.revisado('I7')
            ex = l.get('exigencias')
            if not isinstance(ex, list):
                self.err('I7', f'{l.get("id")}: «exigencias» debe ser una lista')
                continue
            for e in ex:
                eid = e.get('id')
                if not C.RE_EXIGENCIA.match(str(eid)):
                    self.err('I7', f'{l.get("id")}: id de exigencia mal formado {eid!r}')
                    continue
                if eid not in reg:
                    self.err('I7', f'{l.get("id")}: la exigencia {eid} no está en el registro')
                    continue
                if e.get('exigible') != reg[eid].get('exigible'):
                    self.err('I7', f'{l.get("id")}: {eid} exigible = {e.get("exigible")!r} y el registro dice {reg[eid].get("exigible")!r}')
                if 'verificacion_texto' in e and e['verificacion_texto'] != reg[eid].get('verificacion_texto'):
                    self.err('I7', f'{l.get("id")}: {eid} verificacion_texto distinto del registro')
            if l.get('prioridad') == 'habilitacion' and not ex and NOTA_SIN_EXIGENCIA not in str(l.get('nota_exigencias', '')):
                self.err('I7', f'{l.get("id")}: línea de habilitación sin exigencias y sin la nota «habilitación según '
                               'dotacion.json; sin exigencia literal encontrada»')
        if self.hab is None:
            self.err('I7', 'falta la matriz de habilitación')
            return
        self.matriz(self.hab)

    def matriz(self, hab):
        cortes = [f.get('id') for f in hab.get('fecha_referencia', []) if isinstance(f, dict)]
        if not {'corte_2026', 'apertura'} <= set(cortes):
            self.err('I7', f'fecha_referencia debe traer los cortes corte_2026 y apertura (trae {cortes})')
        escenarios = hab.get('escenarios') or ['dotacion_actual', 'con_cierre_de_brechas']
        for campo in ('texto_alcance', 'norma', 'alcance'):
            if not isinstance(hab.get(campo), str) or not hab[campo]:
                self.err('I7', f'falta «{campo}» en la matriz')
        if not isinstance(hab.get('estandares_no_evaluados'), list) or not hab['estandares_no_evaluados']:
            self.err('I7', 'falta la lista estandares_no_evaluados')
        if 'servicio habilitado' in C.texto_json(hab).lower():
            self.err('I7', 'la matriz usa la frase prohibida «servicio habilitado» (13.6)')
        por_recinto = {}

        def revisar(e, srv_id, cuenta):
            eid = e.get('id')
            q = f'{srv_id}: {eid}: '
            self.inf.revisado('I7')
            if e.get('exigible') not in EXIGIBLE:
                self.err('I7', f'{q}exigible {e.get("exigible")!r} no es si ni por_confirmar')
            if e.get('verificacion_texto') not in VERIFICACION:
                self.err('I7', f'{q}verificacion_texto {e.get("verificacion_texto")!r} fuera de la escala única (4.2)')
            if e.get('exigible') == 'si' and e.get('verificacion_texto') not in ('literal_compilacion', 'contenido_compilacion'):
                self.err('I7', f'{q}exigible «si» solo con literal_compilacion o contenido_compilacion (4.2)')
            if e.get('texto_disponible') is False and e.get('texto_corto'):
                self.err('I7', f'{q}sin texto oficial disponible no puede traer texto_corto entre comillas')
            est = e.get('estado') or {}
            for c in cortes:
                for s in escenarios:
                    v = (est.get(c) or {}).get(s)
                    if v not in ESTADOS_EXIG:
                        self.err('I7', f'{q}sin estado válido en {c} / {s} ({v!r})')
            if e.get('referencia') is True and any((est.get(c) or {}).get(s) != 'no_aplica' for c in cortes for s in escenarios):
                self.err('I7', f'{q}las exigencias por analogía (referencia) quedan no_aplica')
            inv_est = DE_INVESTIGACION.get(e.get('estado_investigacion'))
            propio = (est.get('corte_2026') or {}).get('dotacion_actual')
            if inv_est and propio and propio != inv_est and propio != 'no_aplica':
                if e.get('diferencia'):
                    self.av('I7', f'{q}{propio} frente a «{e.get("estado_investigacion")}» de la investigación: {e["diferencia"]}')
                else:
                    self.err('I7', f'{q}{propio} frente a «{e.get("estado_investigacion")}» de la investigación, sin explicar en «diferencia»')
            for uid in e.get('unidades', []) or []:
                if uid not in self.U:
                    self.err('I7', f'{q}la unidad {uid} no está en el inventario')
            if cuenta is not None and e.get('referencia') is not True:
                for c in cortes:
                    for s in escenarios:
                        v = (est.get(c) or {}).get(s)
                        grupo = 'exigibles' if e.get('exigible') == 'si' else 'por_confirmar'
                        if v in ESTADOS_EXIG and v != 'no_aplica':
                            cuenta.setdefault(c, {}).setdefault(s, {}).setdefault(grupo, {}).setdefault(v, 0)
                            cuenta[c][s][grupo][v] += 1
            for rid in e.get('recintos', []) or []:
                por_recinto.setdefault(rid, []).append(e)

        for s in hab.get('servicios', []):
            sid = s.get('id')
            if s.get('habilitable') not in HABILITABLE:
                self.err('I7', f'{sid}: habilitable {s.get("habilitable")!r} no es uno de {HABILITABLE}')
            if s.get('habilitable') != 'si' and not s.get('marco'):
                self.err('I7', f'{sid}: un servicio que no es habilitable lleva su «marco»')
            cuenta = {}
            for e in s.get('exigencias', []) or []:
                revisar(e, sid, cuenta)
            if s.get('habilitable') == 'si':
                res = s.get('resumen') or {}
                for c in cortes:
                    for esc in escenarios:
                        dado = (res.get(c) or {}).get(esc) or {}
                        hecho = (cuenta.get(c) or {}).get(esc) or {}
                        for grupo in ('exigibles', 'por_confirmar'):
                            for v, n in (dado.get(grupo) or {}).items():
                                if n != (hecho.get(grupo) or {}).get(v, 0):
                                    self.err('I7', f'{sid}: resumen {c}/{esc}/{grupo}/{v} = {n} y las exigencias dan '
                                                   f'{(hecho.get(grupo) or {}).get(v, 0)}')
                            for v, n in (hecho.get(grupo) or {}).items():
                                if v not in (dado.get(grupo) or {}):
                                    self.err('I7', f'{sid}: el resumen {c}/{esc}/{grupo} no cuenta «{v}» ({n})')
        tds = hab.get('todos_los_servicios') or {}
        for e in tds.get('detalle', []) or []:
            revisar(e, 'todos_los_servicios', None)
        for eid in tds.get('exigencias', []) or []:
            if not str(eid).startswith('EX-TOD-'):
                self.err('I7', f'todos_los_servicios: {eid} no es una fila EX-TOD-…')
        # color de cada recinto: solo las exigibles de dotación cuentan
        for rid, dato in (hab.get('por_recinto') or {}).items():
            es = por_recinto.get(rid, [])
            for c in cortes:
                vals = [(e.get('estado') or {}).get(c, {}).get('dotacion_actual') for e in es
                        if e.get('exigible') == 'si' and e.get('referencia') is not True and not str(e.get('id')).startswith('EX-TOD-')]
                esperado = 'falta' if 'falta' in vals else 'parcial' if 'parcial' in vals else 'cumple'
                dado = (dato.get('estado') or {}).get(c)
                if dado != esperado:
                    self.err('I7', f'por_recinto {rid}: {c} = {dado!r} y sus exigencias exigibles dan {esperado}')
            pc = sum(1 for e in es if e.get('exigible') == 'por_confirmar')
            if dato.get('por_confirmar') != pc:
                self.err('I7', f'por_recinto {rid}: por_confirmar = {dato.get("por_confirmar")} y hay {pc}')
            if sorted(dato.get('exigencias', [])) != sorted(e.get('id') for e in es):
                self.err('I7', f'por_recinto {rid}: exigencias {dato.get("exigencias")} y las que lo citan son '
                               f'{sorted(e.get("id") for e in es)}')

    # ------------------------------------------------------------------------------------------------ I8 a I11
    def ficha_riesgo(self, u):
        """Clase, registro y mantenimiento que valen para una unidad: los suyos o los de su línea."""
        l = self.L.get(u.get('linea')) or {}
        if not self.es_base(u):
            return u.get('clase_riesgo'), u.get('registro_invima'), u.get('mantenimiento')
        return (u.get('clase_riesgo') or l.get('clase_riesgo'), u.get('registro_invima') or l.get('registro_invima'),
                u.get('mantenimiento') or l.get('mantenimiento'))

    def i8(self):
        for l in self.lineas:
            if l.get('es_dispositivo_medico') not in ES_DM:
                self.err('I8', f'{l.get("id")}: es_dispositivo_medico {l.get("es_dispositivo_medico")!r} fuera de {ES_DM}')
            cr = l.get('clase_riesgo') or {}
            if isinstance(cr, dict) and cr.get('estado') not in ESTADOS_CLASE:
                self.err('I8', f'{l.get("id")}: clase_riesgo.estado {cr.get("estado")!r} fuera de {ESTADOS_CLASE}')
            if l.get('prioridad') not in PRIORIDADES:
                self.err('I8', f'{l.get("id")}: prioridad {l.get("prioridad")!r} fuera de {PRIORIDADES}')
        for u in self.unidades:
            uid = u.get('id')
            self.inf.revisado('I8')
            cr, reg, mant = self.ficha_riesgo(u)
            vig = cr.get('vigente') if isinstance(cr, dict) else cr
            if vig not in CLASES:
                self.err('I8', f'{uid}: clase de riesgo {vig!r} fuera de la enumeración {CLASES}')
            if not isinstance(reg, dict) or reg.get('requerido') not in REQUERIDO:
                self.err('I8', f'{uid}: registro_invima.requerido ausente o fuera de {REQUERIDO}')
            elif vig in ('IIb', 'III') and reg.get('usado_permitido') is not False:
                self.err('I8', f'{uid}: clase {vig}: usado_permitido debe ser false (Decreto 4725 modificado por el 582 de 2017)')
            if not isinstance(mant, dict) or not isinstance(mant.get('personal_inscrito_invima'), bool) \
                    or not isinstance(mant.get('calibracion'), bool):
                self.err('I8', f'{uid}: mantenimiento sin personal_inscrito_invima o calibracion booleanos')
            elif vig in ('IIb', 'III') and mant['personal_inscrito_invima'] is not True:
                self.err('I8', f'{uid}: clase {vig}: el mantenimiento lo hace personal inscrito en el INVIMA (Decreto 4725, art. 39)')

    def i9_i10(self):
        for u in self.unidades:
            uid = u.get('id')
            mont = u.get('montaje')
            if mont not in MONTAJES and not (mont is None and u.get('estado') == 'fuera_de_la_torre'):
                self.err('I9', f'{uid}: montaje {mont!r} fuera de {MONTAJES}')
            d = u.get('dentro_de')
            if mont == 'dentro' and not d:
                self.err('I9', f'{uid}: montaje «dentro» sin dentro_de')
            if d:
                self.inf.revisado('I9')
                c = self.U.get(d)
                if c is None:
                    self.err('I9', f'{uid}: dentro_de {d} no existe')
                else:
                    _, mc = self.modelo_de(c)
                    if not mc or not mc.get('contenedor'):
                        self.err('I9', f'{uid}: {d} no es un contenedor')
                    elif u.get('compartimiento') not in mc.get('compartimientos', []):
                        self.err('I9', f'{uid}: compartimiento {u.get("compartimiento")!r} no es de {d} ({mc.get("compartimientos")})')
                    if c.get('recinto') != u.get('recinto'):
                        self.err('I9', f'{uid}: su contenedor {d} está en otro recinto')
                if mont != 'dentro':
                    self.err('I9', f'{uid}: tiene dentro_de y su montaje es {mont!r}')
            a = u.get('apoyo')
            if mont == 'sobre' and not a:
                self.err('I10', f'{uid}: montaje «sobre» sin apoyo')
            if a:
                self.inf.revisado('I10')
                b = self.U.get(a)
                if b is None:
                    self.err('I10', f'{uid}: apoyo {a} no existe')
                    continue
                if b.get('recinto') != u.get('recinto'):
                    self.err('I10', f'{uid}: su apoyo {a} está en otro recinto')
                db = self.dim_de(b)
                try:
                    tope = b['posicion'][2] + db[2]
                    if abs(u['posicion'][2] - tope) > 0.01:
                        self.err('I10', f'{uid}: z = {u["posicion"][2]} y la cara superior de {a} está a {tope:.3f} m')
                    hb = self.huella(b)
                    if hb and not C.punto_en_poligono(u['posicion'], hb, 0.02):
                        self.av('I10', f'{uid}: el centro no queda sobre la huella de su apoyo {a}')
                except (TypeError, KeyError, IndexError):
                    self.err('I10', f'{uid}: no se puede comprobar la altura sobre {a}')

    def i11(self):
        fuera = {f.get('linea') for f in self.inv.get('fuera_de_la_torre', []) if isinstance(f, dict)}
        for u in self.unidades:
            self.inf.revisado('I11')
            rid = u.get('recinto')
            if rid is None:
                if u.get('linea') in fuera or u.get('estado') == 'fuera_de_la_torre' or \
                        str(u.get('ubicacion', '')).startswith(('cubierta', 'exterior')):
                    continue
                self.err('I11', f'{u.get("id")}: sin recinto (solo se permite fuera de la torre o en la cubierta sin planta)')
            elif self.planta.recintos and rid not in self.planta.recintos:
                self.err('I11', f'{u.get("id")}: el recinto {rid} no existe en la planta')
            if u.get('estado') not in ESTADOS_UNIDAD:
                self.err('I11', f'{u.get("id")}: estado {u.get("estado")!r} fuera de {ESTADOS_UNIDAD}')

    # ------------------------------------------------------------------------------------------------ I12 y I13
    def ref_linea(self, donde, ref):
        if not isinstance(ref, dict) or 'linea' not in ref:
            return
        self.inf.revisado('I12')
        l = self.L.get(ref['linea'])
        if l is None:
            self.err('I12', f'{donde}: la línea {ref["linea"]} no existe')
        elif 'nombre' not in ref:
            self.err('I12', f'{donde}: la referencia a {ref["linea"]} no trae el nombre de la línea')
        elif ref['nombre'] != l.get('nombre'):
            self.err('I12', f'{donde}: {ref["linea"]} se llama «{l.get("nombre")}», no «{ref["nombre"]}»')

    def ref_ambiente(self, donde, ref, ambientes):
        if ref in (None, '*'):
            return
        self.inf.revisado('I12')
        try:
            C.resolver_ambiente(ref, ambientes)
        except C.ErrorAmbiente as e:
            self.err('I12', f'{donde}: {e}')

    def i12(self):
        for l in self.lineas:
            d = self.entrada_dotacion(l)
            if d is not None:
                self.inf.revisado('I12')
                if d.get('nombre') != l.get('nombre'):
                    self.err('I12', f'{l.get("id")}: «{l.get("nombre")}» y la dotación dice «{d.get("nombre")}»')
        # ambientes del fixture o del programa
        if self.fixture:
            amb = {}
            for r in self.planta.recintos.values():
                if isinstance(r.get('fila'), int):
                    amb[r['fila']] = {'nombre': r.get('ambiente'), 'servicio': r.get('servicio_programa')}
            ambientes = [amb.get(i, {}) for i in range(max(amb) + 1)] if amb else []
        else:
            ambientes = (self.programa or {}).get('ambientes', [])
        for u in self.unidades:
            r = self.planta.recintos.get(u.get('recinto'))
            if r and 'ambiente' in u and u['ambiente'] != r.get('ambiente'):
                self.err('I12', f'{u.get("id")}: ambiente «{u["ambiente"]}» y su recinto es «{r.get("ambiente")}»')
        for e in self.registro_exigencias().values():
            for a in e.get('ambientes', []) or []:
                self.ref_ambiente(f'exigencia {e.get("id")}', a, ambientes)
            for c in e.get('cubre_con', []) or []:
                self.ref_linea(f'exigencia {e.get("id")} → cubre_con', c)
            regla = e.get('regla') or {}
            for it in regla.get('items', []) or []:
                if 'linea' in it:
                    self.ref_linea(f'exigencia {e.get("id")} → regla', it)
            if isinstance(regla.get('dentro_de'), dict):
                self.ref_linea(f'exigencia {e.get("id")} → regla.dentro_de', regla['dentro_de'])
        for r in (self.reglas_ub or {}).get('reglas', []):
            self.ref_linea('reglas_ubicacion', r)
            for rep in r.get('reparto', []):
                self.ref_ambiente(f'reglas_ubicacion {r.get("linea")}', rep.get('ambiente'), ambientes)
        inf = (self.reglas_ub or {}).get('infraestructura') or {}
        for r in inf.get('reglas', []):
            if r.get('elemento') not in (inf.get('elementos') or {}):
                self.err('I12', f'reglas_ubicacion → infraestructura: elemento {r.get("elemento")!r} sin definir')
            for rep in r.get('reparto', []):
                self.ref_ambiente(f'reglas_ubicacion → infraestructura {r.get("elemento")}', rep.get('ambiente'), ambientes)
        for r in (self.reglas_ex or {}).get('reglas', []):
            for c in r.get('cubre_con', []) or []:
                self.ref_linea('reglas_exigencias → cubre_con', c)
        for nombre, p in ((self.impl or {}).get('plantillas') or {}).items() if not self.fixture else ():
            for ref in p.get('lineas_que_la_usan', []) or []:
                self.ref_linea(f'implementos.{nombre}', ref)
        for l in self.lineas:
            p = l.get('plantilla_contenido')
            if p and self.impl is not None and p not in (self.impl.get('plantillas') or {}):
                self.err('I12', f'{l.get("id")}: la plantilla {p!r} no está en implementos.json')

    def i13(self):
        lab_lineas = [l for l in self.lineas if l.get('origen') == 'laboratorio']
        if not lab_lineas:
            if self.fixture:
                self.inf.omitir('I13', 'el fixture no trae líneas de laboratorio.json')
            else:
                self.err('I13', 'no hay líneas de laboratorio.json en el inventario')
            return
        com = [l for l in lab_lineas if l.get('adquisicion') == 'comodato']
        total = sum((l.get('precio_unitario_cop_2026') or 0) * (l.get('cantidad') or 0) for l in com)
        self.inf.revisado('I13', len(lab_lineas))
        meta = (self.dot.get('totales_generales') or {}).get('analizadores_de_laboratorio_en_comodato_valor_de_mercado_cop_2026',
                                                             COMODATO_COP)
        if total != COMODATO_COP or total != meta:
            self.err('I13', f'las líneas en comodato suman ${total:,} y deben sumar ${COMODATO_COP:,}'.replace(',', '.'))
        if len(com) != 9 or sum(l.get('cantidad') or 0 for l in com) != 10:
            self.err('I13', f'comodato: {len(com)} líneas y {sum(l.get("cantidad") or 0 for l in com)} unidades (se esperan 9 y 10)')
        for l in lab_lineas:
            if l.get('adquisicion') not in ('comodato', 'programa_o_compra', 'opcional'):
                self.err('I13', f'{l.get("id")}: adquisicion {l.get("adquisicion")!r} fuera de comodato, programa_o_compra u opcional')

    # ------------------------------------------------------------------------------------------------ I14 a I16 (16)
    def i14(self):
        fijo = [l for l in self.lineas if (l.get('ref') or {}).get('lista') == 'equipamiento_fijo']
        if not fijo:
            self.inf.omitir('I14', 'el inventario no trae equipamiento fijo')
            return
        esperadas = len(self.dot.get('equipamiento_fijo', []))
        if len(fijo) != esperadas:
            self.err('I14', f'{len(fijo)} líneas de equipamiento fijo y dotacion.json trae {esperadas}')
        fuera = {f.get('linea') for f in self.inv.get('fuera_de_la_torre', []) if isinstance(f, dict)}
        for l in fijo:
            us = [u for u in self.unidades if u.get('linea') == l.get('id') and self.es_base(u)]
            self.inf.revisado('I14', len(us))
            for u in us:
                if u.get('recinto') is None and l.get('id') not in fuera and not str(u.get('ubicacion', '')).startswith(('cubierta', 'exterior')):
                    self.err('I14', f'{u.get("id")} «{l.get("nombre")}»: sin ubicar (ni recinto, ni zona, ni fuera de la torre)')
                if u.get('recinto') is not None and self.planta.recintos and not u.get('posicion'):
                    self.err('I14', f'{u.get("id")} «{l.get("nombre")}»: sin posición en su recinto')

    def i15(self):
        if self.fixture:
            self.inf.omitir('I15', 'el fixture no trae el laboratorio')
            return
        lab = [l for l in self.lineas if l.get('origen') == 'laboratorio']
        n_lab = len((self.lab or {}).get('equipos', []))
        if len(lab) != n_lab:
            self.err('I15', f'{len(lab)} líneas de laboratorio.json en el inventario y el archivo trae {n_lab}')
        prog = (self.programa or {}).get('ambientes', [])
        filas_lab = {i for i, a in enumerate(prog) if a.get('servicio') in SERVICIOS_LABORATORIO}
        for l in lab + [l for l in self.lineas if l.get('origen') == 'dotacion' and l.get('servicio') in ('laboratorio', 'toma_muestras')]:
            for u in (u for u in self.unidades if u.get('linea') == l.get('id') and self.es_base(u)):
                self.inf.revisado('I15')
                m = C.RE_RECINTO.match(str(u.get('recinto')))
                r_planta = self.planta.recintos.get(u.get('recinto')) or {}
                tec_lab = bool(C.RE_TECNICO.match(str(u.get('recinto')))) and r_planta.get('servicio_programa') in SERVICIOS_LABORATORIO
                if not tec_lab and (not m or int(m.group(2)) not in filas_lab):
                    self.err('I15', f'{u.get("id")} «{l.get("nombre")}»: no está en un recinto del laboratorio o de la toma de muestras')
        plantillas = (self.impl or {}).get('plantillas') or {}
        cubiertas = set()
        for nombre, p in plantillas.items():
            for it in p.get('items', []):
                cubiertas.update(it.get('pruebas') or [])
        for l in lab:
            p = plantillas.get(l.get('plantilla_contenido'))
            if not p:
                self.err('I15', f'{l.get("id")} «{l.get("nombre")}»: el analizador no tiene plantilla de reactivos en implementos.json')
                continue
            reactivos = [it for it in p.get('items', []) if it.get('pruebas') and it.get('almacenamiento')]
            if not reactivos:
                self.err('I15', f'{l.get("id")}: su plantilla no trae reactivos con pruebas y condición de almacenamiento')
        for m in (self.lab or {}).get('menu', []):
            if m.get('en_sitio') and m.get('id') not in cubiertas:
                self.err('I15', f'la prueba «{m.get("id")}» del menú no tiene reactivo o insumo en implementos.json')

    def i16(self):
        infra = [l for l in self.lineas if l.get('origen') == 'infraestructura']
        if not infra:
            self.inf.omitir('I16', 'el inventario no trae capa de infraestructura')
            return
        items = {}
        if PRESUPUESTO.exists() and not self.fixture:
            for cap in C.cargar_json(PRESUPUESTO).get('capitulos', []):
                for it in cap.get('items', []):
                    items[str(it.get('codigo'))] = it.get('descripcion')
        for l in infra:
            self.inf.revisado('I16')
            if l.get('precio_unitario_cop_2026') not in (None, 0) or l.get('rango_precio_unitario_cop_2026'):
                self.err('I16', f'{l.get("id")}: la infraestructura no lleva precio de dotación')
            if l.get('capa') not in ('infraestructura', 'contexto'):
                self.err('I16', f'{l.get("id")}: capa {l.get("capa")!r} (se espera infraestructura o contexto)')
            for c in l.get('cita_presupuesto', []) or []:
                if items and items.get(c.get('item')) != c.get('descripcion'):
                    self.err('I16', f'{l.get("id")}: el ítem {c.get("item")} no corresponde a presupuesto.json')
        for u in self.unidades:
            l = self.L.get(u.get('linea')) or {}
            if l.get('origen') == 'infraestructura' and u.get('estado') not in ('infraestructura', 'contexto') \
                    and not (u.get('estado') == 'cierre_brechas_propuesto' and u.get('propuesta_obra')):
                self.err('I16', f'{u.get("id")}: unidad de infraestructura con estado {u.get("estado")!r}')

    def correr(self):
        self.i1()
        self.i2()
        self.i3_a_i6()
        self.i7()
        self.i8()
        self.i9_i10()
        self.i11()
        self.i12()
        self.i13()
        self.i14()
        self.i15()
        self.i16()
        self.i17()


# --------------------------------------------------------------------------------------------------------------------
# Forma web (10.2)
# --------------------------------------------------------------------------------------------------------------------
def validar_web(inf: C.Informe, web: dict, cat: dict):
    E = lambda r, m: inf.error(r, m)
    modelos = cat.get('modelos', {})
    if web.get('v') != 2:
        E('esquema', f'v = {web.get("v")!r}; se espera 2')
    for campo, tipo in (('catalogo', dict), ('lineas', list), ('columnas_unidades', list), ('unidades', list),
                        ('implementos', dict), ('recintos', dict), ('totales', dict)):
        if not isinstance(web.get(campo), tipo):
            E('esquema', f'falta «{campo}» ({tipo.__name__})')
    if web.get('columnas_unidades') != COLUMNAS_WEB:
        E('esquema', f'columnas_unidades debe ser {COLUMNAS_WEB}')
    catw = web.get('catalogo') or {}
    for mid, c in catw.items():
        inf.revisado('catalogo')
        m = modelos.get(mid)
        if m is None:
            E('catalogo', f'{mid}: no está en la lista cerrada del Anexo C (catalogo_equipos.json)')
            continue
        esperado = {'f': m['familia'], 'dim': m['dim_m'], 'b': m['b_m'], 'mont': m['montaje'], 'anc': m['anclaje'],
                    'masa': m['masa_kg'], 'hcg': m['h_cg_m'], 'mu': m['mu'], 'cont': m['contenedor'],
                    'comp': m.get('compartimientos', [])}
        if set(c) != set(esperado):
            E('esquema', f'catalogo.{mid}: campos {sorted(c)}; se esperan {sorted(esperado)}')
        for k, v in esperado.items():
            if k in c and c[k] != v:
                E('catalogo', f'{mid}.{k} = {c[k]!r} y el catálogo dice {v!r}')
    lineas = web.get('lineas') or []
    implementos = web.get('implementos') or {}
    for i, l in enumerate(lineas):
        q = f'lineas[{i}] {l.get("id")}: '
        inf.revisado('esquema')
        if not C.RE_LINEA.match(str(l.get('id'))):
            E('I1', f'{q}id mal formado')
        else:
            srv, letra, _ = C.partes_linea(l['id'])
            if srv != l.get('servicio') and not (letra == 'f' and srv == 'fijo'):
                E('I1', f'{q}el servicio del id no es «{l.get("servicio")}»')
        for campo in ('nombre', 'servicio', 'tipo', 'tipo_precio', 'metodo_precio'):
            if not isinstance(l.get(campo), str):
                E('esquema', f'{q}falta «{campo}»')
        if not entero(l.get('cantidad')) or l['cantidad'] < 0:
            E('esquema', f'{q}cantidad no entera')
        if l.get('modelo3d') is not None and l.get('modelo3d') not in catw:
            E('I12', f'{q}modelo3d {l.get("modelo3d")!r} no está en el catálogo del archivo')
        cl = l.get('clase') or {}
        inf.revisado('I8')
        if l.get('modelo3d') is not None or l.get('plantilla') is not None:
            inf.revisado('I12')
        if cl.get('vigente') not in CLASES:
            E('I8', f'{q}clase.vigente {cl.get("vigente")!r} fuera de {CLASES}')
        if cl.get('estado') not in ESTADOS_CLASE:
            E('I8', f'{q}clase.estado {cl.get("estado")!r} fuera de {ESTADOS_CLASE}')
        rg = l.get('registro') or {}
        if rg.get('requerido') not in REQUERIDO or not isinstance(rg.get('usado_permitido'), bool):
            E('I8', f'{q}registro con requerido de {REQUERIDO} y usado_permitido booleano')
        mt = l.get('mantenimiento') or {}
        if not (isinstance(mt.get('personal_inscrito_invima'), bool) and isinstance(mt.get('calibracion'), bool)):
            E('I8', f'{q}mantenimiento sin personal_inscrito_invima o calibracion booleanos')
        if cl.get('vigente') in ('IIb', 'III') and (mt.get('personal_inscrito_invima') is not True or rg.get('usado_permitido') is not False):
            E('I8', f'{q}clase {cl.get("vigente")}: personal inscrito en el INVIMA y sin usados (Decreto 4725)')
        for e in l.get('exigencias') or []:
            if not C.RE_EXIGENCIA.match(str(e.get('id'))) or e.get('exigible') not in EXIGIBLE:
                E('esquema', f'{q}exigencia mal formada {e}')
        if l.get('prioridad') not in PRIORIDADES:
            E('esquema', f'{q}prioridad {l.get("prioridad")!r} fuera de {PRIORIDADES}')
        if l.get('plantilla') is not None and l['plantilla'] not in implementos:
            E('I12', f'{q}plantilla {l["plantilla"]!r} no está en implementos')
        if l.get('precio') is not None and not entero(l['precio']):
            E('esquema', f'{q}precio debe ser entero o null')
        rango = l.get('rango')
        if rango is not None and not (isinstance(rango, list) and len(rango) == 2 and all(num(x) for x in rango) and rango[0] <= rango[1]):
            E('esquema', f'{q}rango debe ser [mínimo, máximo] o null')
        if not isinstance(l.get('fuentes_precio'), list):
            E('esquema', f'{q}fuentes_precio debe ser una lista')
    filas = web.get('unidades') or []
    n = len(filas)
    ids = []
    base_por_linea = {}
    for k, f in enumerate(filas):
        inf.revisado('esquema')
        if not isinstance(f, list) or len(f) != len(COLUMNAS_WEB):
            E('esquema', f'unidades[{k}]: debe tener {len(COLUMNAS_WEB)} columnas')
            continue
        u = dict(zip(COLUMNAS_WEB, f))
        ids.append(u['id'])
        q = f'unidades[{k}] {u["id"]}: '
        m = C.RE_UNIDAD.match(str(u['id']))
        if not m:
            E('I1', f'{q}id mal formado')
            continue
        if not entero(u['linea_idx']) or not 0 <= u['linea_idx'] < len(lineas):
            E('esquema', f'{q}linea_idx fuera de rango')
            continue
        l = lineas[u['linea_idx']]
        if C.RE_LINEA.match(str(l.get('id'))):
            srv, _, h = C.partes_linea(l['id'])
            if (m.group(1), m.group(2)) != (srv, h):
                E('I1', f'{q}no corresponde a su línea {l["id"]}')
        for col in ('x', 'y', 'z', 'rot_z'):
            if not num(u[col]):
                E('esquema', f'{q}{col} no numérico')
        for col in ('apoyo_idx', 'dentro_de_idx', 'componente_de_idx'):
            if not entero(u[col]) or not -1 <= u[col] < n or u[col] == k:
                E('esquema', f'{q}{col} = {u[col]!r} fuera de rango')
        if u['montaje'] not in MONTAJES:
            E('esquema', f'{q}montaje {u["montaje"]!r} fuera de {MONTAJES}')
        if u['estado'] not in ESTADOS_UNIDAD:
            E('esquema', f'{q}estado {u["estado"]!r} fuera de {ESTADOS_UNIDAD}')
        if u['recinto'] is None and u['estado'] not in ('fuera_de_la_torre', 'cubierta'):
            E('I11', f'{q}sin recinto')
        if u['piso'] not in (1, 2, 3, 4, 'BT', 'CUB', None):
            E('esquema', f'{q}piso {u["piso"]!r} no válido')
        if m.group(4) is None:
            base_por_linea.setdefault(u['linea_idx'], []).append(int(m.group(3)))
            if u['componente_de_idx'] != -1:
                E('I1', f'{q}una unidad sin sufijo -cN no es componente')
        elif u['componente_de_idx'] == -1:
            E('I1', f'{q}componente sin componente_de_idx')
        # I9 e I10 con el catálogo del archivo
        if u['montaje'] == 'sobre':
            if not entero(u['apoyo_idx']) or u['apoyo_idx'] < 0:
                E('I10', f'{q}montaje «sobre» sin apoyo_idx')
            elif 0 <= u['apoyo_idx'] < n and isinstance(filas[u['apoyo_idx']], list) and len(filas[u['apoyo_idx']]) == len(COLUMNAS_WEB):
                a = dict(zip(COLUMNAS_WEB, filas[u['apoyo_idx']]))
                inf.revisado('I10')
                la = lineas[a['linea_idx']] if entero(a['linea_idx']) and 0 <= a['linea_idx'] < len(lineas) else {}
                ca = catw.get(la.get('modelo3d')) or {}
                if a['recinto'] != u['recinto']:
                    E('I10', f'{q}su apoyo está en otro recinto')
                if ca.get('dim') and num(a['z']) and num(u['z']) and abs(u['z'] - (a['z'] + ca['dim'][2])) > 0.01:
                    E('I10', f'{q}z = {u["z"]} y la cara superior del apoyo está a {a["z"] + ca["dim"][2]:.3f} m')
        if u['montaje'] == 'dentro':
            d = u['dentro_de_idx']
            if not entero(d) or d < 0:
                E('I9', f'{q}montaje «dentro» sin dentro_de_idx')
            elif d < n and isinstance(filas[d], list) and len(filas[d]) == len(COLUMNAS_WEB):
                c = dict(zip(COLUMNAS_WEB, filas[d]))
                inf.revisado('I9')
                lc = lineas[c['linea_idx']] if entero(c['linea_idx']) and 0 <= c['linea_idx'] < len(lineas) else {}
                if not (catw.get(lc.get('modelo3d')) or {}).get('cont'):
                    E('I9', f'{q}su contenedor no es un modelo contenedor')
                if c['recinto'] != u['recinto']:
                    E('I9', f'{q}su contenedor está en otro recinto')
    rep = sorted({x for x in ids if ids.count(x) > 1}, key=str)
    if rep:
        E('I1', f'ids de unidad repetidos: {rep}')
    for i, l in enumerate(lineas):
        inf.revisado('I1')
        ks = sorted(base_por_linea.get(i, []))
        if entero(l.get('cantidad')) and ks != list(range(1, l['cantidad'] + 1)):
            E('I1', f'{l.get("id")}: {len(ks)} unidades (k = {ks}) para cantidad {l.get("cantidad")}')
    for nombre, items in implementos.items():
        if not isinstance(items, list):
            E('esquema', f'implementos.{nombre} debe ser una lista')
            continue
        for it in items:
            if not isinstance(it.get('n'), str) or it.get('tipo') not in TIPOS_IMPLEMENTO:
                E('esquema', f'implementos.{nombre}: ítem con n y tipo de {TIPOS_IMPLEMENTO}: {it}')
            if it.get('c') is not None and not entero(it.get('c')):
                E('esquema', f'implementos.{nombre}: cantidad no entera: {it}')
    for rid, r in (web.get('recintos') or {}).items():
        est = r.get('estado') or {}
        if not all(est.get(c) in ESTADOS_EXIG for c in ('corte_2026', 'apertura')):
            E('esquema', f'recintos.{rid}: estado de corte_2026 y apertura en {ESTADOS_EXIG}')
        if not all(C.RE_EXIGENCIA.match(str(x)) for x in r.get('exig', [])) or not entero(r.get('por_confirmar')):
            E('esquema', f'recintos.{rid}: exig (ids de exigencia) y por_confirmar (entero)')
    if 'servicio habilitado' in C.texto_json(web).lower():
        E('esquema', 'la forma web usa la frase prohibida «servicio habilitado» (13.6)')


# --------------------------------------------------------------------------------------------------------------------
def leer(inf, regla, ruta, obligatorio=True):
    try:
        return C.cargar_json(ruta)
    except (FileNotFoundError, ValueError) as e:
        if obligatorio:
            inf.error(regla, str(e))
        return None


def revisar_huellas(inf, inv, rutas: dict, ruta_dot: Path, esperadas=()):
    hs = inv.get('insumos_sha1')
    if not isinstance(hs, dict):
        inf.error('insumos', 'falta insumos_sha1')
        hs = {}
    for nombre in esperadas:
        if nombre not in hs:
            inf.error('insumos', f'insumos_sha1 no trae {nombre}')
    for nombre, h in hs.items():
        inf.revisado('insumos')
        ruta = rutas.get(nombre)
        if ruta is None or not Path(ruta).exists():
            inf.error('insumos', f'no se encuentra el insumo {nombre}')
        elif C.sha1_archivo(ruta) != h:
            inf.error('insumos', f'{nombre} cambió después de generar el inventario (sha1 distinto): regenerar')
    if ruta_dot.exists() and inv.get('sha256_dotacion') != C.sha256_archivo(ruta_dot):
        inf.error('insumos', f'sha256_dotacion no corresponde a {C.relativa(ruta_dot)}')


def main(argv=None):
    ap = argparse.ArgumentParser(description='Valida el inventario de dotación de la torre (reglas I1-I13 del contrato, 4.6).')
    modo = ap.add_mutually_exclusive_group()
    modo.add_argument('--fixture', nargs=2, type=Path, metavar=('INVENTARIO_DATOS', 'DOTACION'))
    modo.add_argument('--web', type=Path, metavar='INVENTARIO_WEB')
    ap.add_argument('--plantas', type=Path)
    ap.add_argument('--habilitacion', type=Path)
    ap.add_argument('--inventario', type=Path, default=C.INVENTARIO, help='inventario de datos a validar (por defecto, el de data/)')
    ap.add_argument('--catalogo', type=Path, default=C.CATALOGO)
    a = ap.parse_args(argv)

    if a.web:
        inf = C.Informe('validar_inventario', {**REGLAS_WEB, **{k: REGLAS[k] for k in ('I1', 'I8', 'I9', 'I10', 'I11', 'I12')}},
                        archivo=C.relativa(a.web), modo='web')
        web = leer(inf, 'esquema', a.web)
        cat = leer(inf, 'catalogo', a.catalogo)
        if web is not None and cat is not None:
            validar_web(inf, web, cat)
        else:
            inf.omitir_resto('no se pudo leer la forma web o el catálogo')
        inf.salir()

    if a.fixture:
        ruta_inv, ruta_dot = a.fixture
        carpeta = ruta_inv.resolve().parent
        inf = C.Informe('validar_inventario', REGLAS, archivo=C.relativa(ruta_inv), dotacion=C.relativa(ruta_dot), modo='fixture')
        inv = leer(inf, 'insumos', ruta_inv)
        dot = leer(inf, 'insumos', ruta_dot)
        cat = leer(inf, 'insumos', a.catalogo)
        if inv is None or dot is None or cat is None:
            inf.omitir_resto('no se pudo leer el inventario, la dotación o el catálogo')
            inf.salir()
        hs = inv.get('insumos_sha1') or {}
        nombre_plantas = next((k for k in hs if 'planta' in k), 'plantas_min.json')
        ruta_pl = a.plantas or carpeta / nombre_plantas
        ruta_hab = a.habilitacion or carpeta / 'habilitacion_min.json'
        rutas = {Path(ruta_dot).name: ruta_dot, nombre_plantas: ruta_pl}
        rutas.update({k: (carpeta / k if (carpeta / k).exists() else C.TORRE / k) for k in hs if k not in rutas})
        revisar_huellas(inf, inv, rutas, Path(ruta_dot))
        plantas = leer(inf, 'insumos', ruta_pl)
        hab = leer(inf, 'I7', ruta_hab)
        impl = C.cargar_json(C.IMPLEMENTOS) if C.IMPLEMENTOS.exists() else None
        inf.cabecera.update(plantas=C.relativa(ruta_pl), habilitacion=C.relativa(ruta_hab))
        ValidadorDatos(inf, inv, dot, cat, Planta(plantas), hab, None, None, impl, None, None, None, True).correr()
        inf.salir()

    inf = C.Informe('validar_inventario', REGLAS, archivo=C.relativa(a.inventario), modo='completo')
    inv = leer(inf, 'insumos', a.inventario)
    dot = leer(inf, 'insumos', C.DOTACION)
    cat = leer(inf, 'insumos', a.catalogo)
    if inv is None or dot is None or cat is None:
        inf.omitir_resto('no se pudo leer el inventario, la dotación o el catálogo')
        inf.salir()
    ruta_pl = a.plantas or C.PLANTAS
    rutas = {'dotacion.json': C.DOTACION, 'laboratorio.json': C.LABORATORIO, ruta_pl.name: ruta_pl,
             'reglas_ubicacion.json': C.REGLAS_UBICACION, 'catalogo_equipos.json': a.catalogo,
             'implementos.json': C.IMPLEMENTOS, 'exigencias_3100.json': C.EXIGENCIAS,
             'normas_4725_1732.json': C.FUENTES_INVESTIGACION / 'normas_4725_1732.json', 'programa.json': C.PROGRAMA,
             'presupuesto.json': PRESUPUESTO}
    revisar_huellas(inf, inv, rutas, C.DOTACION,
                    esperadas=('dotacion.json', 'laboratorio.json', ruta_pl.name, 'reglas_ubicacion.json',
                               'catalogo_equipos.json', 'implementos.json', 'exigencias_3100.json'))
    plantas = leer(inf, 'insumos', ruta_pl)
    hab = leer(inf, 'I7', a.habilitacion or (a.inventario.parent / C.HABILITACION.name))
    ex = leer(inf, 'I7', C.EXIGENCIAS)
    ex = ex.get('exigencias', []) if isinstance(ex, dict) else ex
    lab = leer(inf, 'I13', C.LABORATORIO)
    impl = leer(inf, 'I12', C.IMPLEMENTOS)
    rub = leer(inf, 'I12', C.REGLAS_UBICACION)
    rex = leer(inf, 'I12', C.REGLAS_EXIGENCIAS, obligatorio=False)
    prog = leer(inf, 'I12', C.PROGRAMA)
    ValidadorDatos(inf, inv, dot, cat, Planta(plantas), hab, ex, lab, impl, rub, rex, prog, False).correr()
    inf.salir()


if __name__ == '__main__':
    main()
