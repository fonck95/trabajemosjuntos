"""Genera el inventario de dotación de la torre, su CSV y la matriz de cumplimiento en dotación e infraestructura
(contrato: data/proyectos/torre_hospital/ESPECIFICACION_INTEGRACION.md, secciones 4.4 a 4.8 y 16).

Entradas (data/):
  proyectos/torre_hospital/dotacion.json          líneas de los 15 servicios, equipamiento fijo y cierre de brechas
  proyectos/torre_hospital/laboratorio.json       analizadores (comodato, programa o compra, opcional)
  edificios/torre_hospital_plantas.json           la planta (recintos, muros, puertas, ventanas)
  proyectos/torre_hospital/reglas_ubicacion.json  cómo se ubica cada línea y la capa de infraestructura (a mano)
  proyectos/torre_hospital/catalogo_equipos.json  modelos 3D con medidas y datos para el riesgo sísmico
  proyectos/torre_hospital/implementos.json       contenido de contenedores, kits y laboratorio (a mano)
  proyectos/torre_hospital/exigencias_3100.json   exigencias normalizadas (normalizar_exigencias.py)
  proyectos/torre_hospital/fuentes_investigacion/normas_4725_1732.json   revisión del Decreto 4725
  proyectos/torre_hospital/programa.json y presupuesto.json   filas de ambientes e ítems de obra citados
Salidas:
  proyectos/torre_hospital/inventario_dotacion.json   (4.5: líneas y unidades)
  proyectos/torre_hospital/inventario_dotacion.csv    (una fila por unidad; UTF-8 con BOM, «;», decimales con coma)
  proyectos/torre_hospital/habilitacion.json          (4.8: matriz con dos cortes de fecha y dos escenarios; 16.6: lo que
                                                       falta en cada servicio y lo que cuesta cerrarlo)

Nada se ubica a mano: las posiciones salen de las estrategias de reglas_ubicacion.json sobre la planta de toda la torre
(EXT, P1 a P4, BT y CUB). Cada recinto se amuebla por fases (lo fijo, las cabeceras de los puestos de paciente con su
camino de 0,90 m desde la puerta, lo que va contra la pared, las filas de sillas, lo colgado, lo que va encima y lo que va
dentro) y, si algo queda sin lugar o sin paso libre (I6), se prueba la siguiente posición del primer puesto y se queda
con la mejor variante. La cubierta y los exteriores que pasan por encima de varios recintos (pérgola y marquesina
solares, filas de la terraza, barandas, casetas) se ubican con los puntos de la planta o, si no los trae, del programa.
Si la planta no existe todavía, con --sin-planta se generan las unidades con su recinto (id estable de la regla 1.3) y
posicion null.

Uso:
  python3 scripts/torre/generar_inventario.py [--verificar] [--sin-planta]
  python3 scripts/torre/generar_inventario.py --fixture DIR    (insumos de prueba en DIR: dotacion*.json, plantas*.json,
                                                               reglas_ubicacion*.json y, si están, exigencias*.json y
                                                               laboratorio*.json; escribe en DIR)
Solo biblioteca estándar (Python 3.12). Salida determinista: dos corridas dan los mismos bytes.
"""
from __future__ import annotations

import argparse
import csv
import io
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import comun as C  # noqa: E402

NORMAS_4725 = C.FUENTES_INVESTIGACION / 'normas_4725_1732.json'
PRESUPUESTO = C.TORRE / 'presupuesto.json'
CSV = C.TORRE / 'inventario_dotacion.csv'

CLASES = ('I', 'IIa', 'IIb', 'III', 'no_dm', 'ivd', 'por_confirmar')
ESTADOS_EXIG = ('cumple', 'parcial', 'falta', 'documento_pendiente', 'no_aplica')
CORTES = [{'id': 'corte_2026', 'fecha': '2026-10-23', 'regla': 'Res. 3100 con sus modificaciones vigentes'},
          {'id': 'apertura', 'fecha': '2030-04-01', 'tipo_dato': 'estimacion (apertura «hacia abril de 2030», docs/11)',
           'regla': 'Exigencias con vigencia_hasta anterior quedan no_aplica; esterilización con la Res. 914 de 2025, por_confirmar hasta leer el manual DMER'}]
ESCENARIOS = ['dotacion_actual', 'con_cierre_de_brechas']
TEXTO_ALCANCE = ('Esta matriz revisa la dotación y la infraestructura. No revisa talento humano, historia clínica ni interdependencia '
                 '(por ejemplo, urgencias depende de imágenes, laboratorio y transporte asistencial): no dice si un servicio se puede habilitar.')
NOTA_SIN_EXIGENCIA = 'habilitación según dotacion.json; sin exigencia literal encontrada'
CAMPOS_AL_COMPRAR = ['marca', 'modelo', 'serie', 'registro_sanitario', 'vence_registro', 'fecha_compra', 'fecha_instalacion', 'hoja_de_vida']
# equipos que se calibran (4.5, lista de B; estimación): por palabra del nombre
CALIBRA = ('báscula', 'bascula', 'tensiómetro', 'termohigrómetro', 'termómetro', 'flujómetro', 'monitor', 'desfibrilador', 'bomba de infusión',
           'oxímetro', 'cardiotocógrafo', 'monitor fetal', 'autoclave', 'refrigerador de vacunas', 'registrador', 'analizador', 'centrífuga',
           'microcentrífuga', 'incubadora', 'micropipeta', 'balanza', 'coagulómetro', 'lector', 'genexpert', 'espirómetro', 'electrocardiógrafo',
           'ventilador', 'glucómetro', 'doppler', 'ecógrafo', 'rayos x', 'electrobisturí', 'servocuna', 'lámpara de calor', 'fototerapia',
           'regulador de vacío', 'nevera', 'congelador', 'cabina de bioseguridad', 'baño serológico', 'otoemisiones', 'cpap')
# reclasificaciones de la investigación (4.5): sin cambiar la prioridad de dotacion.json
RECLASIFICADOS = [
    ('partos', 'Incubadora neonatal estacionaria', 'recomendado', None),
    ('partos', 'Lámpara de fototerapia LED', 'recomendado', None),
    ('partos', 'Sillón reclinable para acompañante (TPR)', 'recomendado', None),
    ('hospitalizacion', 'Sillón reclinable para acompañante', 'recomendado', None),
    ('esterilizacion', 'Lavadora desinfectora de instrumental', 'por_confirmar (Res. 914)', None),
    ('consulta_externa', 'Equipo de otoemisiones acústicas (tamizaje auditivo del recién nacido)', None, 'Res. 3280 de 2018 (no la Res. 3100)'),
]
NOMBRE_SERVICIO_INFRA = {
    'vestibulo': 'Vestíbulo y admisiones', 'apoyo_tecnico': 'Apoyo y áreas técnicas', 'circulacion': 'Circulación vertical y ductos',
    'bloque_tecnico': 'Bloque técnico', 'cubierta': 'Cubierta técnica', 'exteriores': 'Exteriores',
}
# imágenes se parte en 744 (rayos X) y 745 (ecografía) por el recinto (4.8)
FILAS_745 = {105, 106}
PASO_LIBRE_M = 0.90               # paso libre hasta el costado de cada puesto de paciente (I6)
APOYOS_SUPERFICIE = {'puesto_trabajo': (1.2, 0.7)}    # escritorio del puesto (sin las sillas): ancho máximo y fondo, contra la espalda


class ErrorGenerador(ValueError):
    pass


def r2(x):
    return C.redondear(x, 3)


def ang(x):
    return C.redondear(math.atan2(math.sin(x), math.cos(x)) % (2 * math.pi), 4)


# ======================================================================================================================
# Insumos
# ======================================================================================================================
class Insumos:
    def __init__(self, rutas: dict, fixture: bool = False, sin_planta: bool = False):
        self.rutas = rutas
        self.fixture = fixture
        self.dot = C.cargar_json(rutas['dotacion'])
        self.lab = C.cargar_json(rutas['laboratorio']) if rutas.get('laboratorio') and Path(rutas['laboratorio']).exists() else {'equipos': []}
        self.cat = C.cargar_json(rutas['catalogo'])
        self.modelos = self.cat['modelos']
        self.impl = C.cargar_json(rutas['implementos'])
        self.plantillas = self.impl.get('plantillas', {})
        self.reglas = C.cargar_json(rutas['reglas_ubicacion'])
        ex = C.cargar_json(rutas['exigencias']) if rutas.get('exigencias') and Path(rutas['exigencias']).exists() else {'exigencias': []}
        self.exig_doc = ex
        self.exig = ex.get('exigencias', [])
        self.n4725 = C.cargar_json(rutas['normas_4725']) if rutas.get('normas_4725') and Path(rutas['normas_4725']).exists() else {}
        self.presupuesto = C.cargar_json(rutas['presupuesto']) if rutas.get('presupuesto') and Path(rutas['presupuesto']).exists() else {}
        self.items_presupuesto = {}
        self.items_presupuesto_dato = {}
        for cap in self.presupuesto.get('capitulos', []):
            for itp in cap.get('items', []):
                self.items_presupuesto[str(itp.get('codigo'))] = itp.get('descripcion')
                self.items_presupuesto_dato[str(itp.get('codigo'))] = itp
        self.plantas = None
        ruta_pl = rutas.get('plantas')
        if ruta_pl and Path(ruta_pl).exists() and not sin_planta:
            self.plantas = C.cargar_json(ruta_pl)
        elif not sin_planta:
            raise ErrorGenerador(f'no existe la planta {C.relativa(ruta_pl)}: genérela con generar_plantas.py o use --sin-planta')
        if fixture:
            self.ambientes = self._ambientes_de_planta()
        else:
            self.ambientes = C.cargar_json(rutas['programa'])['ambientes']

    def _ambientes_de_planta(self):
        """En los fixtures las filas no existen en programa.json: se toman de la planta (como validar_inventario --fixture)."""
        amb = {}
        for n in (self.plantas or {}).get('niveles', []):
            for r in n.get('recintos', []):
                if isinstance(r.get('fila'), int):
                    a = amb.setdefault(r['fila'], {'nombre': r.get('ambiente'), 'servicio': r.get('servicio_programa'), 'cantidad': 0,
                                                   'piso': n.get('piso')})
                    a['cantidad'] += 1
        return [amb.get(i, {'nombre': None, 'servicio': None, 'cantidad': 0, 'piso': None}) for i in range(max(amb) + 1)] if amb else []

    def huellas(self) -> dict:
        orden = ['dotacion', 'laboratorio', 'plantas', 'reglas_ubicacion', 'catalogo', 'implementos', 'exigencias', 'normas_4725',
                 'programa', 'presupuesto']
        rutas = [self.rutas[k] for k in orden if self.rutas.get(k) and Path(self.rutas[k]).exists()
                 and not (k == 'plantas' and self.plantas is None)]
        return C.insumos_sha1(rutas)


# ======================================================================================================================
# Clase de riesgo, registro y mantenimiento (Decreto 4725; 4.5 y 4.7.3)
# ======================================================================================================================
def clase_vigente(texto) -> str:
    t = str(texto or '').strip()
    if t in CLASES:
        return t
    tl = t.lower()
    if tl.startswith('no es dispositivo') or tl.startswith('equipo industrial'):
        return 'no_dm'
    if 'diagnóstico in vitro' in tl or tl == 'ivd':
        return 'ivd'
    if t in ('I (probable)',):
        return 'I'
    return 'por_confirmar'


def ficha_clase(x: dict, origen: str) -> tuple[dict, dict | None, str]:
    """(clase_riesgo, clase_riesgo_revision, es_dispositivo_medico) de una línea de dotacion.json, laboratorio.json o del cierre."""
    repo = x.get('clase_riesgo')
    vig = clase_vigente(repo)
    rev = x.get('clase_riesgo_revision')
    estado = rev.get('estado') if isinstance(rev, dict) else 'coherente'
    if estado not in ('coherente', 'discrepancia', 'probable_discrepancia', 'regimen_distinto', 'por_confirmar', 'observacion'):
        estado = 'por_confirmar'
    cr = {'repo': repo, 'vigente': vig, 'estado': estado,
          'regla': rev.get('regla') if isinstance(rev, dict) else None,
          'fuente': (rev.get('fuente') if isinstance(rev, dict) else
                     ('revisión del Decreto 4725 (sin observación)' if origen != 'laboratorio' else 'laboratorio.json (régimen de diagnóstico in vitro)'))}
    if vig == 'no_dm' and estado == 'por_confirmar' and isinstance(rev, dict) and str(rev.get('valor', '')).strip().lower() == 'por_confirmar':
        # el repositorio dice «equipo industrial» o «no es dispositivo médico», pero la revisión del Decreto 4725 lo deja por
        # confirmar con el INVIMA (central de gases, generador PSA, PACS): no se publica como «no es dispositivo médico»
        vig = 'por_confirmar'
        cr['vigente'] = vig
    prudente = clase_prudente(vig, estado, rev)
    if prudente:
        cr['clase_prudente'] = prudente
    if vig in ('I', 'IIa', 'IIb', 'III'):
        es = 'si'
    elif vig == 'ivd':
        es = 'ivd'
    elif vig == 'no_dm':
        es = 'por_confirmar' if estado == 'por_confirmar' else 'no'
    else:
        es = 'por_confirmar'
    if estado == 'regimen_distinto':
        es = 'por_confirmar'
    return cr, (dict(rev) if isinstance(rev, dict) else None), es


def clase_prudente(vig: str, estado: str, rev) -> str | None:
    """Clase más estricta que la revisión del Decreto 4725 deja abierta (IIa o IIb del oxímetro: «IIb si es para vigilancia
    continua con alarmas»). Si caben varias reglas, rige la más estricta (art. 6, según la revisión): mientras no se confirme
    con el registro sanitario del modelo comprado, la unidad se trata con las reglas de esa clase (sin usados, mantenimiento
    por personal inscrito). None si no aplica."""
    if estado != 'por_confirmar' or vig not in ('I', 'IIa') or not isinstance(rev, dict):
        return None
    texto = f'{rev.get("valor") or ""} {rev.get("nota") or ""}'
    m = re.search(r'Revisi[oó]n:\s*(.*)$', texto)
    texto = m.group(1) if m else texto
    if re.search(r'\bIII\b', texto):
        return 'III'
    if re.search(r'\bIIb\b', texto):
        return 'IIb'
    return None


def registro_invima(vig: str, estado: str, es_dm: str, prudente: str | None = None) -> dict:
    nota_usados = ('Prohibido comprar o recibir en donación equipos usados IIb y III (Decreto 4725 modificado por el Decreto 582 de 2017; '
                   'artículo 37 o 36 según la compilación, por confirmar)')
    if vig in ('IIb', 'III'):
        d = {'requerido': 'si', 'via': f'evaluacion_tecnica ({vig}, Decreto 4725 art. 18)', 'usado_permitido': False, 'nota': nota_usados}
    elif vig in ('I', 'IIa'):
        d = {'requerido': 'si', 'via': f'automatico ({vig}, Decreto 4725 art. 17)', 'usado_permitido': True,
             'nota': 'Usados de clase I o IIa solo como tecnología controlada, con permiso de comercialización y certificado de máximo 5 años de fabricación (por confirmar en el texto oficial)'}
    elif vig == 'ivd':
        d = {'requerido': 'si', 'via': 'diagnóstico in vitro (Decreto 3770 de 2004)', 'usado_permitido': True, 'nota': None}
    elif vig == 'no_dm':
        d = {'requerido': 'no', 'via': None, 'usado_permitido': True, 'nota': 'No es dispositivo médico (por confirmar: definición del art. 2 del Decreto 4725 no leída en el texto oficial)'}
    else:
        d = {'requerido': 'por_confirmar', 'via': None, 'usado_permitido': True, 'nota': None}
    if estado == 'regimen_distinto' or (estado == 'por_confirmar' and es_dm in ('por_confirmar', 'no')):
        d['requerido'] = 'por_confirmar'
        d['nota'] = 'Régimen o concepto del INVIMA por confirmar (revisión del Decreto 4725)'
    if prudente:
        d['usado_permitido'] = False
        d['clase_por_confirmar'] = f'{vig} o {prudente}'
        d['nota'] = (f'Clase por confirmar entre {vig} y {prudente} (revisión del Decreto 4725): mientras no se confirme con la clase del '
                     f'registro sanitario del modelo comprado, rige la más estricta ({prudente}): no se compran ni reciben usados.')
    return d


def mantenimiento(x: dict, vig: str, nombre: str, comodato: bool = False, prudente: str | None = None) -> dict:
    n = nombre.lower()
    inscrito = vig in ('IIb', 'III') or prudente in ('IIb', 'III')
    cita = None
    if vig in ('IIb', 'III'):
        cita = 'Decreto 4725, art. 39'
    elif inscrito:
        cita = f'Decreto 4725, art. 39 (clase por confirmar entre {vig} y {prudente}: se aplica la más estricta hasta conocer el registro del modelo comprado)'
    return {'anual_pct': None if comodato else x.get('mantenimiento_anual_pct'),
            'vida_util_anios': x.get('vida_util_anios'),
            'preventivo': ('a cargo del proveedor del comodato, según el manual del fabricante, con hoja de vida' if comodato else
                           'según el manual del fabricante, con hoja de vida (Res. 3100, num. 11.1.3)'),
            'personal_inscrito_invima': inscrito,
            'calibracion': any(p in n for p in CALIBRA),
            'cita_inscripcion': cita}


def fuentes_precio(texto) -> list:
    """Todas las URL o referencias del campo «fuente» de la línea (no solo la primera)."""
    t = str(texto or '')
    urls = re.findall(r'https?://[^\s);,]+', t)
    return urls if urls else ([t] if t else [])


# ======================================================================================================================
# Líneas (4.5)
# ======================================================================================================================
def indice_exigencias(exig: list) -> dict:
    """{id de línea: [exigencias que la citan en cubre_con o en la regla]} en el orden de exigencias_3100.json."""
    idx = {}
    for e in exig:
        ids = [c.get('linea') for c in e.get('cubre_con', []) or [] if c.get('linea')]
        ids += [c.get('linea') for c in (e.get('regla') or {}).get('items', []) or [] if c.get('linea')]
        dl = (e.get('regla') or {}).get('dentro_de')
        if isinstance(dl, dict) and dl.get('linea'):
            ids.append(dl['linea'])
        for lid in dict.fromkeys(ids):
            idx.setdefault(lid, []).append(e)
    return idx


def ref_exigencia(e: dict) -> dict:
    return {'id': e['id'], 'exigible': e.get('exigible'), 'verificacion_texto': e.get('verificacion_texto')}


def excesos(ins: Insumos) -> dict:
    """Justificación de las líneas recomendadas, desde excesos_recomendados de las investigaciones (si están)."""
    salida = {}
    for n in ('res3100_urgencias_e_internacion.json', 'res3100_consulta_y_ambulatorio.json', 'res3100_apoyo_diagnostico.json'):
        ruta = C.FUENTES_INVESTIGACION / n
        if ins.fixture or not ruta.exists():
            continue
        for s in C.cargar_json(ruta).get('servicios', []):
            for x in s.get('excesos_recomendados', []) or []:
                for nombre in str(x.get('item_dotacion', '')).split(' | '):
                    texto = x.get('recomendacion') or x.get('justificacion')
                    por_que = x.get('por_que_no_lo_exige_la_3100') or x.get('por_que_es_exceso')
                    if texto:
                        salida.setdefault((s['id'], nombre.strip()), f'{por_que} {texto}'.strip() if por_que else texto)
    return salida


def construir_lineas(ins: Insumos) -> list[dict]:
    idx = indice_exigencias(ins.exig)
    reglas = {r['linea']: r for r in ins.reglas.get('reglas', [])}
    exc = excesos(ins)
    lineas = []

    def base(lid, origen, ref, servicio, tipo, capa, x, cantidad, especificacion):
        r = reglas.get(lid, {})
        cr, rev, es = ficha_clase(x, origen)
        exs = [ref_exigencia(e) for e in idx.get(lid, [])]
        d = {'id': lid, 'origen': origen, 'ref': ref, 'servicio': servicio, 'tipo': tipo, 'capa': capa, 'nombre': x['nombre'],
             'cantidad': cantidad, 'especificacion': especificacion, 'modelo3d': r.get('modelo3d'), 'variante': r.get('variante'),
             'dim_m': r.get('dim_m'), 'clase_riesgo': cr, 'clase_riesgo_revision': rev, 'es_dispositivo_medico': es,
             'registro_invima': registro_invima(cr['vigente'], cr['estado'], es, cr.get('clase_prudente')), 'tecnologia_controlada': None,
             'componentes': [], 'exigencias': exs}
        return d, r

    for s in ins.dot.get('servicios', []):
        for lista, letra, tipo in (('equipos', 'e', 'equipo'), ('mobiliario', 'm', 'mobiliario')):
            for i, x in enumerate(s.get(lista, [])):
                lid = C.id_linea(s['id'], letra, x['nombre'])
                d, r = base(lid, 'dotacion', {'servicio': s['id'], 'lista': lista, 'idx': i}, s['id'], tipo, 'dotacion', x,
                            x['cantidad'], x.get('especificacion'))
                completar_dotacion(d, x, r, s['id'], exc)
                lineas.append(d)
    for i, x in enumerate(ins.dot.get('equipamiento_fijo', [])):
        lid = C.id_linea('fijo', 'f', x['nombre'])
        d, r = base(lid, 'dotacion', {'servicio': 'fijo', 'lista': 'equipamiento_fijo', 'idx': i}, 'fijo', 'equipamiento_fijo', 'fijo',
                    x, x['cantidad'], x.get('especificacion'))
        completar_dotacion(d, x, r, 'fijo', exc)
        d['componentes_texto'] = x.get('componentes') if isinstance(x.get('componentes'), str) else None
        d['riesgo_doble_conteo_con_obra'] = x.get('riesgo_doble_conteo_con_obra')
        lineas.append(d)
    for i, x in enumerate(ins.lab.get('equipos', [])):
        lid = C.id_linea('laboratorio', 'c', x['nombre'])
        d, r = base(lid, 'laboratorio', {'lista': 'laboratorio.json → equipos', 'idx': i}, 'laboratorio', 'equipo', 'laboratorio', x,
                    x['cantidad'], ' · '.join(v for v in (x.get('funcion'), x.get('capacidad')) if v))
        completar_laboratorio(d, x, r)
        lineas.append(d)
    cierre = ins.dot.get('cierre_brechas_habilitacion') or {}
    ex_por_id = {e['id']: e for e in ins.exig}
    for i, x in enumerate(cierre.get('items', [])):
        lid = C.id_linea(x['servicio'], 'x', x['nombre'])
        d, r = base(lid, 'cierre_brechas', {'lista': 'cierre_brechas_habilitacion.items', 'idx': i}, x['servicio'],
                    'servicio' if x.get('tipo') == 'servicio' else 'cierre', 'cierre_brechas', x, x['cantidad'], x.get('especificacion'))
        d['exigencias'] = [ref_exigencia(ex_por_id[e['id']]) if e['id'] in ex_por_id else {'id': e['id'], 'exigible': None,
                                                                                            'verificacion_texto': None}
                           for e in x.get('exigencias', []) or []]
        completar_cierre(d, x, r)
        lineas.append(d)
    return lineas


def completar_dotacion(d, x, r, servicio, exc):
    vig = d['clase_riesgo']['vigente']
    d['componentes'] = [dict(c) for c in x.get('componentes', [])] if isinstance(x.get('componentes'), list) else []
    if not d['exigencias'] and x.get('prioridad') == 'habilitacion':
        d['nota_exigencias'] = NOTA_SIN_EXIGENCIA
    d['prioridad'] = x.get('prioridad')
    d['prioridad_revisada'] = None
    d['norma_base'] = None
    for srv, nombre, pr, nb in RECLASIFICADOS:
        if srv == servicio and nombre == x['nombre']:
            d['prioridad_revisada'], d['norma_base'] = pr, nb
    if servicio != 'fijo' and 'Canecas' in x['nombre']:
        d['norma_base'] = d['norma_base'] or 'Gestión de residuos (Res. 591 de 2024), no la Res. 3100'
    just = exc.get((servicio, x['nombre']))
    d['justificacion_recomendado'] = just if (x.get('prioridad') == 'recomendado' or d['prioridad_revisada']) else None
    d['mantenimiento'] = mantenimiento(x, vig, x['nombre'], prudente=d['clase_riesgo'].get('clase_prudente'))
    d['precio_unitario_cop_2026'] = x.get('precio_unitario_cop_2026')
    d['rango_precio_unitario_cop_2026'] = x.get('rango_precio_unitario_cop_2026')
    d['tipo_precio'] = x.get('tipo_precio')
    d['metodo_precio'] = x.get('metodo_precio')
    d['fuentes_precio'] = fuentes_precio(x.get('fuente'))
    d['nota_interna'] = x.get('nota')
    d['ajuste_v2'] = x.get('ajuste_v2')
    d['plantilla_contenido'] = r.get('plantilla_contenido')


def completar_laboratorio(d, x, r):
    mc = str(x.get('modelo_de_compra', '')).lower()
    if mc.startswith('opcional'):
        adq, prioridad = 'opcional', 'recomendado'
    elif 'comodato' in mc:
        adq, prioridad = 'comodato', 'habilitacion'
    else:
        adq, prioridad = 'programa_o_compra', 'habilitacion'
    pm = x.get('precio_mercado') or {}
    d['adquisicion'] = adq
    d['modelo_de_compra'] = x.get('modelo_de_compra')
    d['prioridad'] = prioridad
    d['prioridad_revisada'] = None
    d['norma_base'] = None
    d['justificacion_recomendado'] = ('Opcional: recomendado cuando haya más de 150 aislamientos al mes; fuera de la matriz'
                                      if adq == 'opcional' else None)
    d['mantenimiento'] = mantenimiento({}, d['clase_riesgo']['vigente'], x['nombre'], comodato=(adq != 'programa_o_compra'))
    d['precio_unitario_cop_2026'] = x.get('precio_unitario_cop_2026')
    d['rango_precio_unitario_cop_2026'] = pm.get('rango')
    d['tipo_precio'] = 'valor_de_mercado'
    d['tipo_precio_referencia'] = pm.get('tipo')
    d['metodo_precio'] = 'Valor de mercado de laboratorio.json (no suma a la dotación)'
    d['fuentes_precio'] = fuentes_precio(pm.get('fuente'))
    d['en_presupuesto'] = False
    d['nota_precio'] = {'comodato': 'Comodato pagado con reactivos: no suma a la dotación (valor de mercado informativo)',
                        'programa_o_compra': 'No presupuestado; por confirmar con el programa nacional de tuberculosis (si se compra, sumar $144,0 millones al P5)',
                        'opcional': 'Opcional, recomendado cuando haya más de 150 aislamientos al mes; fuera de la matriz'}[adq]
    d['nota_interna'] = None
    d['plantilla_contenido'] = r.get('plantilla_contenido')
    if not d['exigencias'] and prioridad == 'habilitacion':
        d['nota_exigencias'] = NOTA_SIN_EXIGENCIA


def completar_cierre(d, x, r):
    d['prioridad'] = x.get('prioridad')
    d['prioridad_revisada'] = None
    d['norma_base'] = None
    d['justificacion_recomendado'] = x.get('nota') if x.get('prioridad') == 'recomendado' else None
    d['mantenimiento'] = mantenimiento(x, d['clase_riesgo']['vigente'], x['nombre'], prudente=d['clase_riesgo'].get('clase_prudente'))
    d['precio_unitario_cop_2026'] = x.get('precio_unitario_cop_2026')
    d['rango_precio_unitario_cop_2026'] = x.get('rango_precio_unitario_cop_2026')
    d['tipo_precio'] = x.get('tipo_precio')
    d['metodo_precio'] = x.get('fuente')
    d['fuentes_precio'] = fuentes_precio(x.get('fuente'))
    d['proyecto'] = x.get('proyecto')
    d['naturaleza'] = x.get('naturaleza')
    d['depende_de'] = x.get('depende_de')
    d['dentro_de_linea'] = x.get('dentro_de_linea')
    d['nota_interna'] = x.get('nota')
    d['plantilla_contenido'] = r.get('plantilla_contenido')
    if not d['exigencias'] and x.get('prioridad') == 'habilitacion':
        d['nota_exigencias'] = NOTA_SIN_EXIGENCIA


# ======================================================================================================================
# Geometría de un recinto: rejilla de 5 cm con lo ocupado, el barrido de las puertas y los pasos libres
# ======================================================================================================================
class Sala:
    CEL = 0.05

    def __init__(self, recinto: dict, nivel: dict, poligonos_nivel: dict, reservar_pasos: bool = False):
        self.reservar = reservar_pasos
        self.r = recinto
        self.id = recinto['id']
        self.nivel = nivel
        self.alto_libre = float(nivel.get('altura_libre_m', 3.0))
        self.z0 = float(recinto.get('z_piso_m') or 0.0)          # piso del recinto respecto al de su nivel (terraza del piso 3)
        self.pol_nivel = poligonos_nivel
        self.libre = C.limpiar_poligono(C.orientar_antihorario(recinto.get('poligono_libre') or recinto['poligono']))
        self.eje = C.orientar_antihorario(recinto['poligono'])
        X0, Y0, X1, Y1 = C.caja(self.libre)
        self.X0, self.Y0 = X0, Y0
        c = self.CEL
        self.nx = max(1, int(math.ceil((X1 - X0) / c - 1e-9)))
        self.ny = max(1, int(math.ceil((Y1 - Y0) / c - 1e-9)))
        n = self.nx * self.ny
        self.dentro = bytearray(n)
        for r in C.rectangulos(self.libre) if C.es_ortogonal(self.libre) else []:
            self._pintar(self.dentro, r, 1)
        if not C.es_ortogonal(self.libre):
            for j in range(self.ny):
                for i in range(self.nx):
                    if C.punto_en_poligono(self._centro(i, j), self.libre, 0.0):
                        self.dentro[j * self.nx + i] = 1
        self.ocupado = bytearray(n)
        self.puerta = bytearray(n)
        self.paso = bytearray(n)
        self.camino = bytearray(n)      # camino de 0,90 m reservado desde una entrada hasta el costado de un puesto de paciente
        self.version = 0                # cambia cada vez que cambia lo ocupado (caché de la rejilla de paso)
        self.cajas_piso = []            # huellas exactas de lo que está en el piso
        self.altura = [0.0] * n
        self._sat_duro = None
        self._sat_paso = None
        self.bordes = []
        pts = self.libre
        for k in range(len(pts)):
            a, b = pts[k], pts[(k + 1) % len(pts)]
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            if L < 1e-6:
                continue
            u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
            nin = (-u[1], u[0])                         # polígono antihorario: el interior queda a la izquierda
            nout = (-nin[0], -nin[1])
            orient = 'n' if nout[1] > 0.5 else 's' if nout[1] < -0.5 else 'e' if nout[0] > 0.5 else 'o'
            self.bordes.append({'k': len(self.bordes), 'a': tuple(a), 'b': tuple(b), 'L': L, 'u': u, 'nin': nin, 'orient': orient,
                                'puertas': [], 'ventanas': [], 'pared': [], 'abiertos': []})
        self.puertas = []
        self.puertas_muro = []
        self.muros_abiertos = []    # muros «abierto» del recinto (vanos sin puerta): también son entradas (I6)
        self.unidades = []          # unidades colocadas (para apoyos, contenedores y «junto_a»)
        self.cursor = {}            # ocupación de la cara superior de cada apoyo
        self._abiertos()
        self._puertas_y_ventanas(poligonos_nivel)
        self.columnas = []          # columnas de la retícula que sobresalen en el recinto (de piso a cielo)
        self._columnas()
        self._reservar_pasos()

    # ---------------------------------------------------------------------------------------------- bordes sin muro
    def _abiertos(self):
        """Tramos de cada borde del polígono libre que no tienen un muro de verdad detrás (muro «abierto» de la planta o
        borde sin muro, como los de los patios): ahí no se cuelga ni se arrima nada, y los vanos abiertos son entradas."""
        reales = {id(b): [] for b in self.bordes}
        for m in self.nivel.get('muros', []):
            if m.get('tipo') == 'abierto' and self.id in (m.get('lados') or []):
                self.muros_abiertos.append(m)
            if m.get('tipo') == 'abierto':
                continue
            horizontal = C.es_horizontal(m['a'], m['b'])
            e = float(m.get('espesor', 0.0) or 0.0) / 2
            for b in self.bordes:
                if horizontal != (abs(b['u'][1]) < 0.5):
                    continue
                ax, ay = b['a']
                afuera = -((m['a'][0] - ax) * b['nin'][0] + (m['a'][1] - ay) * b['nin'][1])
                if abs(afuera - e) > 0.03:
                    continue
                t0 = (m['a'][0] - ax) * b['u'][0] + (m['a'][1] - ay) * b['u'][1]
                t1 = (m['b'][0] - ax) * b['u'][0] + (m['b'][1] - ay) * b['u'][1]
                lo, hi = max(0.0, min(t0, t1) - e - 0.02), min(b['L'], max(t0, t1) + e + 0.02)
                if hi > lo:
                    reales[id(b)].append((lo, hi))
        for b in self.bordes:
            t = 0.0
            for lo, hi in sorted(reales[id(b)]):
                if lo > t + 0.05:
                    b['abiertos'].append((t, lo))
                t = max(t, hi)
            if b['L'] > t + 0.05:
                b['abiertos'].append((t, b['L']))

    # ---------------------------------------------------------------------------------------------- columnas
    def _columnas(self):
        """Las columnas (0,80 × 0,80 m y 0,90 × 0,90 m en el eje A desde el prediseño DMO; las medidas salen de la planta)
        sobresalen de la cara de los muros (revisión adversarial): no se pisan (fuera de `dentro`), ninguna huella las
        cruza y en los bordes que tapan no se cuelga ni se arrima nada."""
        X0, Y0, X1, Y1 = C.caja(self.libre)
        for c in self.nivel.get('columnas', []) or []:
            b2, h2 = float(c.get('b', 0.6)) / 2, float(c.get('h', 0.6)) / 2
            q = (c['x'] - b2, c['y'] - h2, c['x'] + b2, c['y'] + h2)
            if q[2] <= X0 + 1e-6 or q[0] >= X1 - 1e-6 or q[3] <= Y0 + 1e-6 or q[1] >= Y1 - 1e-6:
                continue
            self.columnas.append(q)
            self._pintar(self.dentro, (q[0] - 0.012, q[1] - 0.012, q[2] + 0.012, q[3] + 0.012), 0)
            esquinas = ((q[0], q[1]), (q[2], q[3]), (q[0], q[3]), (q[2], q[1]))
            for b in self.bordes:
                ax, ay = b['a']
                ts = [(x - ax) * b['u'][0] + (y - ay) * b['u'][1] for x, y in esquinas]
                ds = [(x - ax) * b['nin'][0] + (y - ay) * b['nin'][1] for x, y in esquinas]
                if max(ds) <= 0.005 or min(ds) > 0.05:
                    continue
                t0, t1 = max(0.0, min(ts)), min(b['L'], max(ts))
                if t1 > t0:
                    b['pared'].append((t0 - 0.02, t1 + 0.02, 0.0, 99.0))
        self._sat_duro = self._sat_paso = None

    # ---------------------------------------------------------------------------------------------- pasos entre vanos
    def _entradas(self):
        """Puntos a 0,45 m adentro de cada puerta y de cada tramo de 0,5 m de los vanos abiertos del recinto:
        (x, y, borde, t, largo del vano, recinto del otro lado, ancho que cubre la entrada)."""
        out = []
        for pt, m in self.puertas_muro:
            b, t = self._borde_de(pt['centro'], m, 0.05)
            if b is not None:
                otro = pt['hacia'] if pt.get('desde') == self.id else pt.get('desde')
                out.append((b['a'][0] + b['u'][0] * t + b['nin'][0] * 0.45, b['a'][1] + b['u'][1] * t + b['nin'][1] * 0.45, b, t,
                            float(pt['ancho']), otro, float(pt['ancho'])))
        for m in self.muros_abiertos:
            # un vano abierto largo es una entrada en cada tramo de 0,5 m (no solo en su centro)
            L = math.hypot(m['b'][0] - m['a'][0], m['b'][1] - m['a'][1])
            otro = next((x for x in m.get('lados') or [] if x != self.id), None)
            n_ = max(1, int(L / 0.5))
            for k in range(n_):
                f = (k + 0.5) / n_
                c = (m['a'][0] + (m['b'][0] - m['a'][0]) * f, m['a'][1] + (m['b'][1] - m['a'][1]) * f)
                b, t = self._borde_de(c, m, 0.05)
                if b is None:
                    continue
                out.append((b['a'][0] + b['u'][0] * t + b['nin'][0] * 0.45, b['a'][1] + b['u'][1] * t + b['nin'][1] * 0.45, b, t,
                            L, otro, L / n_))
        return out

    def _externa(self, otro) -> bool:
        """¿La entrada lleva a una circulación, a un recinto de paso o al exterior (se sigue por afuera del recinto)?"""
        if otro in (None, 'exterior'):
            return True
        if any(sb.get('id') == otro for sb in self.r.get('subrecintos') or []):
            return False                       # baño del recinto: se entra desde adentro
        r = next((x for x in self.nivel.get('recintos', []) if x.get('id') == otro), None)
        return r is None or r.get('tipo') == 'circulacion' or bool(r.get('de_paso')) or bool(r.get('exterior'))

    def _reservar_pasos(self):
        """Revisión adversarial (mobiliario que tapa vanos y accesos): si el recinto se amuebla con reserva (segunda vuelta
        de `amueblar`, cuando la primera deja una entrada sin paso), se reserva un paso de 0,70 m entre la primera entrada
        (puerta o vano abierto) y cada una de las demás: ahí no se pone nada de piso."""
        if not self.reservar:
            return
        ent = self._entradas()
        nx, ny, c = self.nx, self.ny, self.CEL
        if len(ent) < 2:
            self._sat_duro = self._sat_paso = None
            return
        # celdas donde cabe el centro de un caminante de 0,30 m de radio (cuadrado de 0,25 m de lado medio)
        r = 5
        fuera = self._sat(lambda k: 0 if self.dentro[k] else 1)
        ok = bytearray(nx * ny)
        for j in range(ny):
            for i in range(nx):
                i0, j0, i1, j1 = i - r, j - r, i + r, j + r
                if i0 < 0 or j0 < 0 or i1 >= nx or j1 >= ny:
                    continue
                if self._suma(fuera, i0, j0, i1, j1) == 0:
                    ok[j * nx + i] = 1

        def celda(x, y):
            i = int((x - self.X0) / c)
            j = int((y - self.Y0) / c)
            best = None
            for dj in range(-8, 9):
                for di in range(-8, 9):
                    a_, b_ = i + di, j + dj
                    if 0 <= a_ < nx and 0 <= b_ < ny and ok[b_ * nx + a_]:
                        d2 = di * di + dj * dj
                        if best is None or d2 < best[0]:
                            best = (d2, a_, b_)
            return None if best is None else best[2] * nx + best[1]
        semillas = [celda(x, y) for x, y, *_ in ent]
        if semillas[0] is None:
            return
        previo = [-1] * (nx * ny)
        previo[semillas[0]] = semillas[0]
        cola = [semillas[0]]
        k_ = 0
        while k_ < len(cola):
            k = cola[k_]
            k_ += 1
            i, j = k % nx, k // nx
            for kk in ((k - 1) if i > 0 else -1, (k + 1) if i < nx - 1 else -1, (k - nx) if j > 0 else -1,
                       (k + nx) if j < ny - 1 else -1):
                if kk >= 0 and ok[kk] and previo[kk] < 0:
                    previo[kk] = k
                    cola.append(kk)
        media = 0.35
        for s_ in semillas[1:]:
            if s_ is None or previo[s_] < 0:
                continue
            k = s_
            while True:
                x, y = self._centro(k % nx, k // nx)
                self._pintar(self.camino, (x - media, y - media, x + media, y + media), 1)
                if k == semillas[0]:
                    break
                k = previo[k]
        self._sat_duro = self._sat_paso = None

    def entradas_bloqueadas(self) -> int:
        """Entradas (puertas y vanos abiertos) a las que un caminante de 0,30 m de radio no llega desde las que dan afuera
        del recinto, con las huellas de piso de más de 0,5 m² y las columnas como obstáculo. Usa la rejilla de 5 cm de la
        regla I17 del validador (mismo origen que comun.rejilla_de_paso, para que las celdas caigan igual) y la misma
        erosión (comun.erosionar): cada vano se prolonga 0,40 m hacia afuera con su ancho y el caminante entra por él."""
        # vanos de menos de 0,65 m (compuertas de montacargas, rendijas): por ahí no pasa un caminante (V22 los exceptúa)
        ent = [e_ for e_ in self._entradas() if e_[4] >= 0.65 - 1e-6]
        if len(ent) < 2:
            return 0
        c = self.CEL
        cont = self.nivel.get('contorno') or [v for r in self.nivel.get('recintos', []) for v in r.get('poligono') or []]
        gx, gy = min(v[0] for v in cont) - 1.0, min(v[1] for v in cont) - 1.0        # origen de comun.rejilla_de_paso
        x0 = gx + math.floor((self.X0 - 0.6 - gx) / c + 1e-9) * c
        y0 = gy + math.floor((self.Y0 - 0.6 - gy) / c + 1e-9) * c
        rej = C.Rejilla(x0, y0, self.X0 + self.nx * c + 0.6, self.Y0 + self.ny * c + 0.6, c)
        rej.pintar_poligono(self.libre)
        for q in self.columnas:
            rej.pintar_rect(*q, valor=0)
        for p in self.unidades:
            if p.montaje == 'piso' and p.w * p.d > 0.5 + 1e-9:
                rej.pintar_rect(*Sala.caja(p.cx, p.cy, p.w, p.d, p.rot), valor=0)
        semillas = []
        for x, y, b, t, L, otro, w in ent:
            w += 0.10 if w < L - 1e-6 else 0.0            # tramos de un vano abierto: se solapan para no dejar rendijas
            ex, ey = b['a'][0] + b['u'][0] * t, b['a'][1] + b['u'][1] * t
            pa = (ex - b['u'][0] * w / 2, ey - b['u'][1] * w / 2)
            pb = (ex + b['u'][0] * w / 2 - b['nin'][0] * 0.40, ey + b['u'][1] * w / 2 - b['nin'][1] * 0.40)
            rej.pintar_rect(min(pa[0], pb[0]), min(pa[1], pb[1]), max(pa[0], pb[0]), max(pa[1], pb[1]), valor=1)
            semillas.append((ex - b['nin'][0] * 0.05, ey - b['nin'][1] * 0.05))
        pasa = C.erosionar(rej, C.RADIO_CAMINANTE_M)
        nx = rej.nx

        def celda(x, y):
            ij = rej.celda_de(x, y)
            return None if ij is None or not pasa[ij[1] * nx + ij[0]] else ij[1] * nx + ij[0]
        # un vano abierto es una sola entrada aunque se muestree cada 0,5 m (los extremos quedan pegados a su borde): se
        # prueba también su punto medio
        grupo = [('vano', e_[5]) if e_[6] < e_[4] - 1e-6 else ('puerta', i) for i, e_ in enumerate(ent)]
        for g in sorted({g for g in grupo if g[0] == 'vano'}, key=str):
            ks = [i for i, g_ in enumerate(grupo) if g_ == g]
            ent.append(ent[ks[0]])
            grupo.append(g)
            semillas.append((sum(semillas[i][0] for i in ks) / len(ks), sum(semillas[i][1] for i in ks) / len(ks)))
        sem = [celda(x, y) for x, y in semillas]
        externas = [i for i, e_ in enumerate(ent) if self._externa(e_[5])]
        origen = [sem[i] for i in externas if sem[i] is not None] if externas else ([sem[0]] if sem[0] is not None else [])
        grupos_int = sorted({grupo[i] for i in range(len(ent)) if i not in externas}, key=str) if externas else \
            sorted({grupo[i] for i in range(1, len(ent))} - {grupo[0]}, key=str)
        if not origen:
            return len(grupos_int)
        # las entradas externas se unen por afuera (corredor o recinto de paso): basta con llegar a una de ellas
        visto = bytearray(len(pasa))
        for o in origen:
            visto[o] = 1
        cola, k_ = list(origen), 0
        while k_ < len(cola):
            k = cola[k_]
            k_ += 1
            i = k % nx
            for kk in ((k - 1) if i > 0 else -1, (k + 1) if i < nx - 1 else -1, k - nx, k + nx):
                if 0 <= kk < len(pasa) and pasa[kk] and not visto[kk]:
                    visto[kk] = 1
                    cola.append(kk)
        llega = {grupo[i] for i in range(len(ent)) if sem[i] is not None and visto[sem[i]]}
        return sum(1 for g in grupos_int if g not in llega)

    # ---------------------------------------------------------------------------------------------- rejilla
    def _centro(self, i, j):
        return self.X0 + (i + 0.5) * self.CEL, self.Y0 + (j + 0.5) * self.CEL

    def _rango(self, a0, a1, origen, n):
        c = self.CEL
        lo = int(math.ceil((a0 - origen) / c - 0.5 - 1e-9))
        hi = int(math.floor((a1 - origen) / c - 0.5 + 1e-9))
        return lo, hi

    def _pintar(self, arr, caja, valor):
        x0, y0, x1, y1 = caja
        i0, i1 = self._rango(x0, x1, self.X0, self.nx)
        j0, j1 = self._rango(y0, y1, self.Y0, self.ny)
        for j in range(max(0, j0), min(self.ny - 1, j1) + 1):
            base = j * self.nx
            for i in range(max(0, i0), min(self.nx - 1, i1) + 1):
                arr[base + i] = valor

    def _sat(self, f):
        nx, ny = self.nx, self.ny
        s = [0] * ((nx + 1) * (ny + 1))
        for j in range(ny):
            fila = 0
            for i in range(nx):
                fila += f(j * nx + i)
                s[(j + 1) * (nx + 1) + i + 1] = s[j * (nx + 1) + i + 1] + fila
        return s

    def _suma(self, s, i0, j0, i1, j1):
        w = self.nx + 1
        return s[(j1 + 1) * w + i1 + 1] - s[j0 * w + i1 + 1] - s[(j1 + 1) * w + i0] + s[j0 * w + i0]

    def _sats(self):
        if self._sat_duro is None:
            dentro, ocup, pu, ca = self.dentro, self.ocupado, self.puerta, self.camino
            self._sat_duro = self._sat(lambda k: 1 if (not dentro[k] or ocup[k] or pu[k] or ca[k]) else 0)
            pa = self.paso
            self._sat_paso = self._sat(lambda k: 1 if pa[k] else 0)
        return self._sat_duro, self._sat_paso

    def libre_caja(self, caja, permitir_paso=False, permitir_puerta=False, h=None) -> bool:
        """¿La caja [x0, y0, x1, y1] está dentro del polígono libre y sin nada ocupado (ni barrido de puerta ni paso)?"""
        x0, y0, x1, y1 = caja
        i0, i1 = self._rango(x0, x1, self.X0, self.nx)
        j0, j1 = self._rango(y0, y1, self.Y0, self.ny)
        if i0 < 0 or j0 < 0 or i1 >= self.nx or j1 >= self.ny or i1 < i0 or j1 < j0:
            return False
        if permitir_puerta:          # respaldo: solo lo de afuera y lo ocupado (ni barridos, ni pasos, ni caminos)
            dentro, ocup = self.dentro, self.ocupado
            for j in range(j0, j1 + 1):
                base = j * self.nx
                for i in range(i0, i1 + 1):
                    if not dentro[base + i] or ocup[base + i]:
                        return False
        else:
            duro, paso = self._sats()
            if self._suma(duro, i0, j0, i1, j1):
                return False
            if not permitir_paso and self._suma(paso, i0, j0, i1, j1):
                return False
        # la rejilla de 5 cm puede no ver un traslape de menos de una celda: se revisa también contra las huellas exactas
        for q0, r0, q1, r1 in self.cajas_piso + self.columnas:
            if min(x1, q1) - max(x0, q0) > 0.004 and min(y1, r1) - max(y0, r0) > 0.004:
                return False
        if not C.poligono_dentro_de(C.rect_a_poligono(caja), self.libre, 0.01):
            return False
        # lo que ya cuelga de las paredes por encima de 0,30 m (lavamanos, tableros, tomas): nada de piso debajo que lo
        # alcance (revisión adversarial: choques 3D); sin la altura de la pieza se supone 2,0 m
        z1 = 2.0 if h is None else h
        for p in self.unidades:
            if p.montaje == 'pared' and 0.30 - 1e-9 <= p.z < z1 - 0.01:
                q0, r0, q1, r1 = Sala.caja(p.cx, p.cy, p.w, p.d, p.rot)
                if min(x1, q1) - max(x0, q0) > 0.004 and min(y1, r1) - max(y0, r0) > 0.004:
                    return False
        return True

    def choca_3d(self, caja, z0, z1, excluir=()) -> bool:
        """¿La caja [x0, y0, x1, y1] entre las cotas z0 y z1 cruza una unidad ya colocada (de piso, pared, cielo o sobre un
        apoyo) o una columna? Revisión adversarial: choques 3D entre unidades de pared, de cielo y de piso."""
        x0, y0, x1, y1 = caja
        for q0, r0, q1, r1 in self.columnas:
            if min(x1, q1) - max(x0, q0) > 0.004 and min(y1, r1) - max(y0, r0) > 0.004:
                return True
        for p in self.unidades:
            if p.montaje == 'dentro' or p.id in excluir:
                continue
            if min(z1, p.z + p.h) - max(z0, p.z) <= 0.01:
                continue
            q0, r0, q1, r1 = Sala.caja(p.cx, p.cy, p.w, p.d, p.rot)
            if min(x1, q1) - max(x0, q0) > 0.004 and min(y1, r1) - max(y0, r0) > 0.004:
                return True
        return False

    def sin_paso(self, caja) -> bool:
        """¿La caja (recortada a la rejilla) no toca ninguna banda de paso reservada?"""
        x0, y0, x1, y1 = caja
        i0, i1 = self._rango(x0, x1, self.X0, self.nx)
        j0, j1 = self._rango(y0, y1, self.Y0, self.ny)
        i0, j0, i1, j1 = max(0, i0), max(0, j0), min(self.nx - 1, i1), min(self.ny - 1, j1)
        if i1 < i0 or j1 < j0:
            return True
        _, paso = self._sats()
        return self._suma(paso, i0, j0, i1, j1) == 0

    def dentro_libre(self, caja) -> bool:
        x0, y0, x1, y1 = caja
        i0, i1 = self._rango(x0, x1, self.X0, self.nx)
        j0, j1 = self._rango(y0, y1, self.Y0, self.ny)
        if i0 < 0 or j0 < 0 or i1 >= self.nx or j1 >= self.ny:
            return False
        for j in range(j0, j1 + 1):
            for i in range(i0, i1 + 1):
                k = j * self.nx + i
                if not self.dentro[k] or self.ocupado[k]:
                    return False
        return True

    def reservar_camino(self, centros, media=PASO_LIBRE_M / 2):
        for x, y in centros:
            self._pintar(self.camino, (x - media, y - media, x + media, y + media), 1)
        self._sat_duro = self._sat_paso = None

    def ocupar(self, caja, alto, paso=False):
        x0, y0, x1, y1 = caja
        e = 0.012
        arr = self.paso if paso else self.ocupado
        self._pintar(arr, (x0 - e, y0 - e, x1 + e, y1 + e), 1)
        if not paso:
            self.cajas_piso.append((x0, y0, x1, y1))
            self.version += 1
            i0, i1 = self._rango(x0 - e, x1 + e, self.X0, self.nx)
            j0, j1 = self._rango(y0 - e, y1 + e, self.Y0, self.ny)
            for j in range(max(0, j0), min(self.ny - 1, j1) + 1):
                for i in range(max(0, i0), min(self.nx - 1, i1) + 1):
                    k = j * self.nx + i
                    self.altura[k] = max(self.altura[k], alto)
        self._sat_duro = self._sat_paso = None

    def rehacer_ocupacion(self, excluir=None):
        """Vuelve a pintar lo ocupado desde las piezas de piso (y de pared bajas), sin la pieza `excluir`."""
        n = self.nx * self.ny
        self.ocupado = bytearray(n)
        self.altura = [0.0] * n
        self.cajas_piso = []
        self.version += 1
        for p in self.unidades:
            if p is excluir:
                continue
            if p.montaje in ('piso', 'en_nucleo') or (p.montaje == 'pared' and p.z < 0.30):
                self.ocupar(Sala.caja(p.cx, p.cy, p.w, p.d, p.rot), p.z + p.h if p.montaje == 'pared' else p.h)
        self._sat_duro = self._sat_paso = None

    def alto_en(self, caja) -> float:
        x0, y0, x1, y1 = caja
        i0, i1 = self._rango(x0, x1, self.X0, self.nx)
        j0, j1 = self._rango(y0, y1, self.Y0, self.ny)
        h = 0.0
        for j in range(max(0, j0), min(self.ny - 1, j1) + 1):
            for i in range(max(0, i0), min(self.nx - 1, i1) + 1):
                h = max(h, self.altura[j * self.nx + i])
        return h

    # ---------------------------------------------------------------------------------------------- puertas y ventanas
    def _borde_de(self, centro, muro, holgura):
        """Borde del polígono libre que corresponde a un vano centrado en `centro` del muro: (borde, t)."""
        horizontal = C.es_horizontal(muro['a'], muro['b'])
        e = float(muro.get('espesor', 0.12)) / 2 + holgura
        for b in self.bordes:
            if horizontal != (abs(b['u'][1]) < 0.5):
                continue
            ax, ay = b['a']
            t = (centro[0] - ax) * b['u'][0] + (centro[1] - ay) * b['u'][1]
            dist = abs((centro[0] - ax) * b['nin'][0] + (centro[1] - ay) * b['nin'][1])
            if dist <= e + 1e-6 and -0.3 <= t <= b['L'] + 0.3:
                return b, t
        return None, None

    def _puertas_y_ventanas(self, poligonos_nivel):
        muros = {m['id']: m for m in self.nivel.get('muros', [])}
        for pt in self.nivel.get('puertas', []):
            if self.id not in (pt.get('desde'), pt.get('hacia')):
                continue
            m = muros.get(pt.get('muro'))
            if not m:
                continue
            self.puertas.append(pt)
            self.puertas_muro.append((pt, m))
            b, t = self._borde_de(pt['centro'], m, 0.05)
            w = float(pt['ancho'])
            if b is not None:
                b['puertas'].append((t - w / 2 - 0.05, t + w / 2 + 0.05))
                # zona de aproximación de la puerta: se deja libre para entrar y para el paso libre (I6). Fondo de 1,1 m; en
                # recintos chicos (baños, depósitos) se acorta para que quepa un aparato de 0,95 m enfrente (mínimo 0,5 m)
                hondo = max((v[0] - b['a'][0]) * b['nin'][0] + (v[1] - b['a'][1]) * b['nin'][1] for v in self.libre)
                fondo = min(1.1, max(0.5, hondo - 0.95))
                p0 = (b['a'][0] + b['u'][0] * (t - w / 2 - 0.05), b['a'][1] + b['u'][1] * (t - w / 2 - 0.05))
                p1 = (b['a'][0] + b['u'][0] * (t + w / 2 + 0.05) + b['nin'][0] * fondo,
                      b['a'][1] + b['u'][1] * (t + w / 2 + 0.05) + b['nin'][1] * fondo)
                self._pintar(self.puerta, (min(p0[0], p1[0]), min(p0[1], p1[1]), max(p0[0], p1[0]), max(p0[1], p1[1])), 1)
            for hoja in C.hojas_puerta(pt, m, poligonos_nivel):
                if hoja['lado'] != self.id:
                    continue
                bx, by = hoja['bisagra']
                R = hoja['radio'] + 0.05
                for j in range(self.ny):
                    for i in range(self.nx):
                        x, y = self._centro(i, j)
                        if abs(x - bx) <= R and abs(y - by) <= R and \
                                (C.en_sector((x, y), hoja['bisagra'], R, hoja['ang0'] - 0.05, hoja['ang1'] + 0.05, 0.0)
                                 or math.hypot(x - bx, y - by) <= 0.1):
                            self.puerta[j * self.nx + i] = 1
        for vn in self.nivel.get('ventanas', []):
            m = muros.get(vn.get('muro'))
            if not m:
                continue
            b, t = self._borde_de(vn['centro'], m, 0.05)
            if b is None:
                continue
            w = float(vn.get('ancho', 1.0))
            z0 = float(vn.get('antepecho', 1.0))
            b['ventanas'].append((t - w / 2, t + w / 2, z0, z0 + float(vn.get('alto', 2.0))))
        self._sat_duro = self._sat_paso = None

    def puerta_principal(self):
        return self.puertas[0]['centro'] if self.puertas else None

    # ---------------------------------------------------------------------------------------------- bordes
    def bordes_por(self, pared=None, compartidos=None, solo=False) -> list:
        bs = [b for b in self.bordes if b['L'] >= 0.3]
        pp = self.puerta_principal()

        def dist_puerta(b):
            if pp is None:
                return 0.0
            mx, my = (b['a'][0] + b['b'][0]) / 2, (b['a'][1] + b['b'][1]) / 2
            return math.hypot(mx - pp[0], my - pp[1])

        def macizo(b):
            """Largo del borde con muro de verdad (sin los vanos abiertos)."""
            return b['L'] - sum(t1 - t0 for t0, t1 in b['abiertos'])
        if compartidos is not None:
            sel = [b for b in bs if b['k'] in compartidos]
            if solo:
                return sel
            return sel + [b for b in sorted(bs, key=lambda b: (-macizo(b), b['k'])) if b['k'] not in compartidos]
        if pared in ('n', 's', 'e', 'o'):
            return sorted(bs, key=lambda b: (b['orient'] != pared, -macizo(b), b['k']))
        if pared == 'corta':
            return sorted(bs, key=lambda b: (macizo(b) < 0.3, b['L'], b['k']))
        if pared == 'opuesta_puerta':
            return sorted(bs, key=lambda b: (-round(dist_puerta(b), 2), -macizo(b), b['k']))
        if pared == 'junto_puerta':
            return sorted(bs, key=lambda b: (not b['puertas'], round(dist_puerta(b), 2), b['k']))
        if pared == 'sin_puerta':
            return sorted(bs, key=lambda b: (bool(b['puertas']) or bool(b['abiertos']), -macizo(b), b['k']))
        return sorted(bs, key=lambda b: (-macizo(b), b['k']))

    @staticmethod
    def rot_de(nin):
        return math.atan2(-nin[0], nin[1])

    @staticmethod
    def caja(cx, cy, w, d, rot):
        c, s = abs(math.cos(rot)), abs(math.sin(rot))
        hx = (w * c + d * s) / 2
        hy = (w * s + d * c) / 2
        return (cx - hx, cy - hy, cx + hx, cy + hy)

    def contra(self, b, t, w, d, sep=0.0):
        """Centro y giro de un objeto de ancho w y fondo d con la espalda contra el borde b, centrado en t."""
        cx = b['a'][0] + b['u'][0] * t + b['nin'][0] * (d / 2 + sep)
        cy = b['a'][1] + b['u'][1] * t + b['nin'][1] * (d / 2 + sep)
        return cx, cy, self.rot_de(b['nin'])

    def choca_vano(self, b, t, w, alto, z0=0.0, solo_puertas=False):
        for p0, p1 in b['puertas']:
            if t + w / 2 > p0 and t - w / 2 < p1 and z0 < 2.15:
                return True
        for a0, a1 in b['abiertos']:
            if t + w / 2 > a0 + 1e-6 and t - w / 2 < a1 - 1e-6:
                return True
        if solo_puertas:
            return False
        for v0, v1, vz0, vz1 in b['ventanas']:
            if t + w / 2 > v0 and t - w / 2 < v1 and z0 + alto > vz0 + 0.05 and z0 < vz1:
                return True
        return False

    def choca_pared(self, b, t, w, z0, z1, sep=0.0):
        for q0, q1, qz0, qz1 in b['pared']:
            if t + w / 2 + sep / 2 > q0 and t - w / 2 - sep / 2 < q1 and z1 > qz0 and z0 < qz1:
                return True
        return False


def pasos(a, b, paso=0.05):
    """Valores de a a b (inclusive) cada `paso`, sin errores de punto flotante."""
    if b < a - 1e-9:
        return []
    n = int(math.floor((b - a) / paso + 1e-9))
    return [a + i * paso for i in range(n + 1)]


class Pieza:
    """Lo que se sabe de una unidad colocada en un recinto (para apoyos, contenedores y «junto_a»)."""
    __slots__ = ('id', 'modelo', 'cx', 'cy', 'z', 'rot', 'w', 'd', 'h', 'borde', 'montaje', 'contenedor', 'compartimientos', 'n_junto',
                 'n_dentro', 'paciente', 'estrategia')

    def __init__(self, uid, modelo, cx, cy, z, rot, w, d, h, borde, montaje, contenedor=False, compartimientos=()):
        self.id, self.modelo, self.cx, self.cy, self.z, self.rot = uid, modelo, cx, cy, z, rot
        self.w, self.d, self.h, self.borde, self.montaje = w, d, h, borde, montaje
        self.contenedor, self.compartimientos = contenedor, list(compartimientos)
        self.n_junto = 0
        self.n_dentro = 0
        self.paciente = False
        self.estrategia = None

    def ejes(self):
        c, s = math.cos(self.rot), math.sin(self.rot)
        return (c, s), (-s, c)


class Colocador:
    """Estrategias de reglas_ubicacion.json (lista cerrada del contrato, 4.6) sobre una Sala."""

    def contra_pared(self, sala, w, d, h, pared=None, sep=0.0, compartidos=None, preferir='inicio', esquina=False, solo=False,
                     bajo_ventana=False):
        for b in sala.bordes_por(pared, compartidos, solo):
            if b['L'] + 1e-6 < w:
                r = self._contra_linea(sala, b, w, d, h, sep, esquina, bajo_ventana)
                if r:
                    return r
                continue
            ts = [w / 2, b['L'] - w / 2] if esquina else pasos(w / 2, b['L'] - w / 2)
            if preferir == 'centro':
                ts = sorted(ts, key=lambda t: (round(abs(t - b['L'] / 2), 3), t))
            elif preferir == 'final':
                ts = list(reversed(ts))
            for t in ts:
                if sala.choca_vano(b, t, w, h, solo_puertas=bajo_ventana) or sala.choca_pared(b, t, w, 0.0, h):
                    continue
                cx, cy, rot = sala.contra(b, t, w, d, sep)
                caja = Sala.caja(cx, cy, w, d, rot)
                if sala.libre_caja(caja, h=h) and not sala.choca_3d(caja, 0.0, h):
                    return cx, cy, rot, b['k'], caja
        return None

    def _contra_linea(self, sala, b, w, d, h, sep, esquina, bajo_ventana):
        """Contra una pared hecha de tramos casi alineados (muros de distinto espesor, a 10 cm o menos): la pieza se apoya en
        la cara que queda más adentro y no puede tapar puertas ni vanos de ninguno de los tramos."""
        u, nin = b['u'], b['nin']
        ax, ay = b['a']
        linea = []
        for c in sala.bordes:
            if c['orient'] != b['orient']:
                continue
            off = (c['a'][0] - ax) * nin[0] + (c['a'][1] - ay) * nin[1]
            if abs(off) <= 0.1:
                ta = (c['a'][0] - ax) * u[0] + (c['a'][1] - ay) * u[1]
                linea.append((c, ta, ta + c['L'], off))
        if len(linea) < 2:
            return None
        tramos = []
        for _c, ta, tb, _off in sorted(linea, key=lambda x: x[1]):
            if tramos and ta <= tramos[-1][1] + 0.02:
                tramos[-1][1] = max(tramos[-1][1], tb)
            else:
                tramos.append([ta, tb])
        lo, hi = next(((t0, t1) for t0, t1 in tramos if t0 <= 1e-6 and t1 >= b['L'] - 1e-6), (0.0, b['L']))
        if hi - lo + 1e-6 < w:
            return None
        o0 = max(off for _c, ta, tb, off in linea if tb > lo and ta < hi)
        ts = [lo + w / 2, hi - w / 2] if esquina else pasos(lo + w / 2, hi - w / 2)
        for t in ts:
            choca = False
            for c, ta, tb, _off in linea:
                t0, t1 = max(ta, t - w / 2), min(tb, t + w / 2)
                if t1 - t0 <= 1e-6:
                    continue
                tm = (t0 + t1) / 2 - ta
                if sala.choca_vano(c, tm, t1 - t0, h, solo_puertas=bajo_ventana) or sala.choca_pared(c, tm, t1 - t0, 0.0, h):
                    choca = True
                    break
            if choca:
                continue
            cx = ax + u[0] * t + nin[0] * (o0 + d / 2 + sep)
            cy = ay + u[1] * t + nin[1] * (o0 + d / 2 + sep)
            rot = Sala.rot_de(nin)
            caja = Sala.caja(cx, cy, w, d, rot)
            if sala.libre_caja(caja, h=h):
                return cx, cy, rot, b['k'], caja
        return None

    def candidatos_cabecera(self, sala, w, d, h, lat=1.0, pies=1.0, bandas=2, pared=None):
        """Posiciones de un puesto de paciente con la cabecera contra una pared sin puerta ni vano, en orden de preferencia:
        con 0,9 m libres a cada lado (o a uno, con bandas=1) y a los pies, y 1,0 m entre puestos; luego con una banda; al
        final sin bandas. Cada candidato trae las bandas que se reservan y el modo que se logró."""
        modos = ('dos_lados', 'un_lado', 'sin_banda') if bandas >= 2 else ('un_lado', 'sin_banda')
        for modo in modos:
            for b in sala.bordes_por(pared or 'sin_puerta'):
                if b['L'] + 1e-6 < w:
                    continue
                for t in pasos(w / 2, b['L'] - w / 2):
                    if sala.choca_vano(b, t, w, h, solo_puertas=True) or sala.choca_pared(b, t, w, 0.0, h):
                        continue
                    cx, cy, rot = sala.contra(b, t, w, d)
                    caja = Sala.caja(cx, cy, w, d, rot)
                    if not sala.libre_caja(caja, h=h) or not sala.sin_paso(Sala.caja(cx, cy, w + 0.1, d, rot)):
                        continue
                    u, n = b['u'], b['nin']
                    bandas_c = []
                    for s_ in (-1, 1):
                        bc = (cx + u[0] * s_ * (w / 2 + lat / 2), cy + u[1] * s_ * (w / 2 + lat / 2))
                        bandas_c.append(Sala.caja(bc[0], bc[1], lat, d, rot))
                    pc = (cx + n[0] * (d / 2 + pies / 2), cy + n[1] * (d / 2 + pies / 2))
                    pie = Sala.caja(pc[0], pc[1], w, pies, rot)
                    ok = [sala.dentro_libre(x) for x in bandas_c]
                    ok_pie = sala.dentro_libre(pie)
                    if modo == 'dos_lados' and not (all(ok) and ok_pie):
                        continue
                    if modo == 'un_lado' and not (any(ok) and ok_pie):
                        continue
                    opciones = [ok]
                    if modo == 'un_lado' and bandas < 2 and all(ok):
                        # con una sola banda: primero la que queda hacia el centro del recinto, luego la otra
                        X0, Y0, X1, Y1 = C.caja(sala.libre)
                        mx, my = (X0 + X1) / 2, (Y0 + Y1) / 2
                        dist = [math.hypot((x[0] + x[2]) / 2 - mx, (x[1] + x[3]) / 2 - my) for x in bandas_c]
                        primero = [dist[0] <= dist[1], dist[1] < dist[0]]
                        opciones = [primero, [not primero[0], not primero[1]]]
                    elif modo == 'un_lado' and all(ok):
                        opciones = [[True, False], [False, True]]
                    for op in opciones:
                        reservas = [x for x, o in zip(bandas_c, op) if o] + ([pie] if ok_pie else [])
                        yield cx, cy, rot, b['k'], caja, reservas, modo

    def cabecera_a_pared(self, sala, w, d, h, lat=1.0, pies=1.0, bandas=2, pared=None):
        return next(self.candidatos_cabecera(sala, w, d, h, lat, pies, bandas, pared), None)

    def junto_a(self, sala, R: Pieza, w, d, h, lado='cabecera'):
        """Al lado de la cabecera de R (lado «cabecera»), a sus pies («pies») o de frente («frente», sillas de mesón).
        Primero busca fuera de las bandas de paso; luego en la banda, pero pegado a la cabecera; al final, donde quepa."""
        ux, uy = R.ejes()
        lados = []
        for s_ in (1, -1):
            for off in pasos(0.0, max(0.0, R.d - d)):
                cx = R.cx + s_ * ux[0] * (R.w / 2 + w / 2 + 0.03) + uy[0] * (-R.d / 2 + d / 2 + off)
                cy = R.cy + s_ * ux[1] * (R.w / 2 + w / 2 + 0.03) + uy[1] * (-R.d / 2 + d / 2 + off)
                lados.append((cx, cy, R.rot, off == 0.0))
        giro = R.rot + (math.pi if lado == 'frente' else 0.0)
        pies = []
        for off in [0.0] + [x for k in pasos(0.05, R.w / 2 + 0.6) for x in (k, -k)]:
            cx = R.cx + uy[0] * (R.d / 2 + d / 2 + 0.03) + ux[0] * off
            cy = R.cy + uy[1] * (R.d / 2 + d / 2 + 0.03) + ux[1] * off
            pies.append((cx, cy, giro, lado in ('pies', 'frente')))
        cands = pies + lados if lado in ('pies', 'frente') else lados + pies
        for paso_ok, solo_cabecera in ((False, False), (True, True), (True, False)):
            for cx, cy, rot, cab in cands:
                if solo_cabecera and not cab:
                    continue
                caja = Sala.caja(cx, cy, w, d, rot)
                if sala.libre_caja(caja, permitir_paso=paso_ok, h=h):
                    return cx, cy, rot, None, caja
        return None

    def pared_altura(self, sala, w, d, h, z, pared=None, R: Pieza | None = None, sep=0.0):
        if R is not None:
            orden = sorted(sala.bordes, key=lambda b: (b['k'] != R.borde, self._dist_borde(b, R), b['k']))
        else:
            orden = sala.bordes_por(pared)
        for b in orden:
            if b['L'] + 1e-6 < w:
                continue
            ts = pasos(w / 2, b['L'] - w / 2)
            if R is not None:
                t0 = (R.cx - b['a'][0]) * b['u'][0] + (R.cy - b['a'][1]) * b['u'][1]
                ts = sorted(ts, key=lambda t: (round(abs(t - t0), 3), t))
            for t in ts:
                if sala.choca_vano(b, t, w, h, z) or sala.choca_pared(b, t, w, z, z + h, sep):
                    continue
                cx, cy, rot = sala.contra(b, t, w, d)
                caja = Sala.caja(cx, cy, w, d, rot)
                if not C.poligono_dentro_de(C.rect_a_poligono(caja), sala.libre, 0.01):
                    continue
                if sala.alto_en(caja) > z - 0.05 + 1e-3:
                    continue
                if z < 0.30 and not sala.libre_caja(caja, permitir_paso=True):
                    continue
                if sala.choca_3d(caja, z, z + h):
                    continue
                b['pared'].append((t - w / 2 - sep / 2, t + w / 2 + sep / 2, z, z + h))
                return cx, cy, rot, b['k'], caja
        return None

    @staticmethod
    def _dist_borde(b, R):
        ax, ay = b['a']
        dist = abs((R.cx - ax) * b['nin'][0] + (R.cy - ay) * b['nin'][1])
        t = (R.cx - ax) * b['u'][0] + (R.cy - ay) * b['u'][1]
        fuera = max(0.0, -t, t - b['L'])
        return round(dist + fuera, 3)

    def centro(self, sala, w, d, h, rot_fija=None, permitir_paso=False, permitir_puerta=False):
        cx0, cy0 = C.centroide(sala.libre)
        X0, Y0, X1, Y1 = C.caja(sala.libre)
        largo_x = (X1 - X0) >= (Y1 - Y0)
        if rot_fija is None:
            rot = 0.0 if ((w >= d) == largo_x) else math.pi / 2
        else:
            rot = rot_fija
        alcance = max(X1 - X0, Y1 - Y0)
        anillos = pasos(0.0, alcance, 0.1)
        for r in anillos:
            cands = [(0.0, 0.0)] if r == 0 else []
            if r > 0:
                for k in pasos(-r, r, 0.1):
                    cands += [(k, -r), (k, r), (-r, k), (r, k)]
            for dx, dy in cands:
                caja = Sala.caja(cx0 + dx, cy0 + dy, w, d, rot)
                if sala.libre_caja(caja, permitir_paso=permitir_paso, permitir_puerta=permitir_puerta, h=h):
                    return cx0 + dx, cy0 + dy, rot, None, caja
        return None

    def cuadricula(self, sala, w, d, h, pasillo=1.2, pared='opuesta_puerta', patron='enfrentadas', rodillas=0.45, grupo=None,
                   filas_max=40):
        """Filas paralelas a una pared, que corren por todo el recinto (no solo por el tramo de esa pared): la primera de
        espaldas al muro; después, pares espalda con espalda, con un pasillo de `pasillo` entre las filas que se miran
        (patrón «enfrentadas»), o todas mirando hacia el mismo lado con `rodillas` libres entre filas (patrón «teatro»), o
        islas de dos filas espalda con espalda separadas del muro y entre sí por el pasillo (patrón «islas», estanterías)."""
        base = sala.cursor.get(('cuadricula', grupo)) if grupo else None
        r = self._filas(sala, w, d, h, pasillo, pared, patron, rodillas, grupo, base, solo_primera=False, filas_max=filas_max)
        if r is None and base is not None:
            # llena la pared de las filas: las piezas que sobran van de espaldas a otra pared (solo la primera fila)
            r = self._filas(sala, w, d, h, pasillo, pared, patron, rodillas, None, None, solo_primera=True, filas_max=1)
        return r

    def _filas(self, sala, w, d, h, pasillo, pared, patron, rodillas, grupo, base, solo_primera, filas_max=40):
        for b in sala.bordes_por(pared):
            if base is not None and b['k'] != base:     # todas las filas de un mismo grupo salen de la misma pared
                continue
            u, nin = b['u'], b['nin']
            ax, ay = b['a']
            # la pared puede venir en tramos casi alineados (muros de distinto espesor): se toman juntos, a la cara más adentro
            linea = []
            for c in sala.bordes:
                if c['orient'] != b['orient']:
                    continue
                off = (c['a'][0] - ax) * nin[0] + (c['a'][1] - ay) * nin[1]
                if abs(off) > 0.1:
                    continue
                ta = (c['a'][0] - ax) * u[0] + (c['a'][1] - ay) * u[1]
                linea.append((c, ta, ta + c['L'], off))
            macizo = sum(c['L'] - sum(t1 - t0 for t0, t1 in c['abiertos']) for c, *_ in linea)
            if macizo + 1e-6 < min(w, 1.0):
                continue
            o0 = max(off for *_, off in linea)
            ts = [(v[0] - ax) * u[0] + (v[1] - ay) * u[1] for v in sala.libre]
            hondo = max((v[0] - ax) * nin[0] + (v[1] - ay) * nin[1] for v in sala.libre)
            rot0 = Sala.rot_de(nin)
            for fila in range(0, filas_max):
                if patron == 'teatro':
                    o = o0 + fila * (d + rodillas)
                    rot = rot0
                elif patron == 'islas':             # pares espalda con espalda, separados del muro y entre sí por el pasillo
                    o = o0 + pasillo + (fila // 2) * (2 * d + pasillo) + (fila % 2) * d
                    rot = rot0 + (math.pi if fila % 2 == 0 else 0.0)
                else:
                    o = o0 + fila * d + ((fila + 1) // 2) * pasillo
                    rot = rot0 + (math.pi if fila % 2 == 1 else 0.0)
                if o + d > hondo + 1e-6 or (solo_primera and fila > 0):
                    break
                for t in pasos(min(ts) + w / 2, max(ts) - w / 2):
                    if fila == 0 and patron != 'islas':   # la espalda de la primera fila va contra esta pared, sin puertas ni vanos
                        cubierto, choca = 0.0, False
                        for c, ta, tb, _off in linea:
                            t0, t1 = max(ta, t - w / 2), min(tb, t + w / 2)
                            if t1 - t0 <= 1e-6:
                                continue
                            cubierto += t1 - t0
                            tm = (t0 + t1) / 2 - ta
                            if sala.choca_vano(c, tm, t1 - t0, h) or sala.choca_pared(c, tm, t1 - t0, 0.0, h):
                                choca = True
                                break
                        if choca or cubierto < w / 2:
                            continue
                    cx = ax + u[0] * t + nin[0] * (o + d / 2)
                    cy = ay + u[1] * t + nin[1] * (o + d / 2)
                    caja = Sala.caja(cx, cy, w, d, rot)
                    if solo_primera:              # pieza suelta en otra pared: con su pasillo libre al frente
                        fx, fy = ax + u[0] * t + nin[0] * (o + d + pasillo / 2), ay + u[1] * t + nin[1] * (o + d + pasillo / 2)
                        if not sala.dentro_libre(Sala.caja(fx, fy, w, pasillo, rot)):
                            continue
                    if sala.libre_caja(caja, h=h):
                        if grupo:
                            sala.cursor[('cuadricula', grupo)] = b['k']
                        return cx, cy, rot, (b['k'] if fila == 0 else None), caja
        return None


# ======================================================================================================================
# Ubicación de las unidades (4.6)
# ======================================================================================================================
FASE = {'zona': 0, 'fija': 0, 'posiciones_fijas': 0, 'en_nucleo': 0, 'esquina_sanitaria': 1, 'cabecera_a_pared': 2, 'pared_fija': 2, 'contra_pared': 3, 'fila': 3,
        'esquina': 3, 'centro': 3, 'cuadricula': 3, 'junto_a': 5, 'pared_altura': 6, 'cielo': 7, 'sobre': 8, 'dentro': 9,
        'fuera_de_la_torre': 0}
SANITARIOS = ('inodoro', 'ducha', 'poceta_aseo')
# aparatos que van dentro del baño o de la cabina del recinto (subrecinto de la planta; revisión adversarial)
EN_BANO = ('inodoro', 'ducha', 'barra_apoyo')
FAMILIAS_PACIENTE = ('cama', 'camilla')
MODELOS_PACIENTE = ('sillon_reclinable', 'sillon_toma_muestras', 'unidad_odontologica')
# piezas que la reparación del paso libre puede mover a otra pared (sin nada encima)
MOVIBLES = ('atril', 'mesa_noche', 'mesa_puente', 'mesa_auxiliar', 'mesa_mayo', 'escalerilla', 'lampara_cuello_cisne', 'lampara_rodable',
            'carro_curaciones', 'carro_medicamentos', 'carro_equipo', 'carro_ropa', 'canecas_residuos', 'silla_ruedas', 'silla_trabajo',
            'silla_laboratorio', 'sillon_reclinable', 'cuna_acrilico', 'caja_termica', 'estiba', 'tabla_espinal', 'bascula_piso', 'ups',
            'monitor_signos', 'incubadora_lab', 'compresero', 'espejo_postural', 'kit_rehabilitacion', 'bicicleta_estatica')

def es_puesto_paciente(modelo, familia, variante=None, nombre_linea=None) -> bool:
    """Puestos de paciente de la regla I6 (la misma definición que validar_inventario.py)."""
    if variante == 'plegada' or modelo == 'camilla_transporte':
        return False
    if 'acompañante' in str(nombre_linea or '').lower():
        return False
    return familia in FAMILIAS_PACIENTE or modelo in MODELOS_PACIENTE


def nivel_de_programa(piso) -> tuple[str, object]:
    if isinstance(piso, int) and 1 <= piso <= 4:
        return f'P{piso}', piso
    p = str(piso).lower()
    if 'bloque' in p:
        return 'BT', 'BT'
    if p.startswith('cubierta'):
        return 'CUB', 'CUB'
    return 'EXT', 'EXT'


class Asignacion:
    __slots__ = ('linea', 'k', 'e', 'rid', 'zona', 'pieza_zona', 'fuera', 'elemento', 'ref', 'orden', 'unidad')

    def __init__(self, linea, k, e, rid=None, zona=None, pieza_zona=None, fuera=None, elemento=None, ref=None, orden=0):
        self.linea, self.k, self.e, self.rid, self.zona, self.pieza_zona = linea, k, e, rid, zona, pieza_zona
        self.fuera, self.elemento, self.ref, self.orden, self.unidad = fuera, elemento, ref, orden, None


class Generador:
    def __init__(self, ins: Insumos):
        self.ins = ins
        self.avisos = []
        self.lineas = construir_lineas(ins)
        self.L = {l['id']: l for l in self.lineas}
        self.reglas = {r['linea']: r for r in ins.reglas.get('reglas', [])}
        self.unidades = []
        self.U = {}
        self.salas = {}
        self.col = Colocador()
        self._salto, self._primeros, self._agotado = None, {}, False
        self.comps = []
        self.fuera = []
        self.recintos, self.nivel_de, self.por_fila, self.circ = {}, {}, {}, {}
        self.poligonos = {}
        self.subs_de, self.padre_de = {}, {}       # baños y cabinas de cada recinto (subrecintos de la planta)
        if ins.plantas:
            for n in ins.plantas.get('niveles', []):
                pol = {r['id']: C.orientar_antihorario(r['poligono']) for r in n.get('recintos', [])}
                self.poligonos[n['id']] = pol
                for sb, r in C.subrecintos(n):
                    # el baño se amuebla como un recinto propio (su polígono libre y su puerta); la unidad sigue siendo del
                    # recinto del programa y lleva «subrecinto»
                    d = {'id': sb['id'], 'ambiente': sb.get('nombre'), 'tipo': 'recinto', 'poligono': sb['poligono'],
                         'poligono_libre': sb.get('poligono_libre'), 'puertas': list(sb.get('puertas') or []),
                         'acceso': [r['id']], 'z_piso_m': r.get('z_piso_m'), 'area_libre_m2': sb.get('area_libre_m2')}
                    self.recintos[sb['id']] = d
                    self.nivel_de[sb['id']] = n
                    pol[sb['id']] = C.orientar_antihorario(sb['poligono'])
                    self.subs_de.setdefault(r['id'], []).append(d)
                    self.padre_de[sb['id']] = r['id']
                for r in n.get('recintos', []):
                    self.recintos[r['id']] = r
                    self.nivel_de[r['id']] = n
                    if isinstance(r.get('fila'), int):
                        self.por_fila.setdefault(r['fila'], []).append(r['id'])
                    if r.get('tipo') == 'circulacion':
                        self.circ.setdefault(n['id'], []).append(r['id'])
            for f in self.por_fila:
                self.por_fila[f].sort(key=lambda rid: (self.recintos[rid].get('k') or 0, rid))

    def aviso(self, m):
        self.avisos.append(m)

    # ---------------------------------------------------------------------------------------------- recintos
    def recintos_de(self, fila, ks=None) -> list[str]:
        if self.ins.plantas is not None:
            ids = list(self.por_fila.get(fila, []))
        else:
            a = self.ins.ambientes[fila]
            nv, _ = nivel_de_programa(a.get('piso'))
            ids = [f'{nv}-A{fila:03d}-{k:02d}' for k in range(1, int(a.get('cantidad') or 0) + 1)]
        if ks:
            ids = [ids[k - 1] for k in ks if 0 < k <= len(ids)]
        return ids

    def datos_recinto(self, rid):
        """(nivel, piso, ambiente) del recinto."""
        rid = self.padre_de.get(rid, rid)          # lo del baño es del recinto del programa
        if rid in self.recintos:
            n = self.nivel_de[rid]
            return n['id'], n.get('piso', n['id']), self.recintos[rid].get('ambiente')
        m = re.match(r'^([A-Z0-9]+)-A(\d{3})-(\d{2})$', rid)
        fila = int(m.group(2))
        a = self.ins.ambientes[fila]
        nv, piso = nivel_de_programa(a.get('piso'))
        return nv, piso, a.get('nombre')

    def sala(self, rid) -> Sala | None:
        if self.ins.plantas is None or rid not in self.recintos:
            return None
        if rid not in self.salas:
            n = self.nivel_de[rid]
            self.salas[rid] = Sala(self.recintos[rid], n, self.poligonos[n['id']])
        return self.salas[rid]

    # ---------------------------------------------------------------------------------------------- modelos
    def ficha_modelo(self, modelo, variante=None, dim=None):
        m = self.ins.modelos.get(modelo)
        if m is None:
            raise ErrorGenerador(f'modelo3d {modelo!r} no está en el catálogo')
        f = {'dim': list(m['dim_m']), 'montaje': m['montaje'], 'anclaje': m['anclaje'], 'masa': m.get('masa_kg'), 'hcg': m.get('h_cg_m'),
             'mu': m.get('mu'), 'b': m.get('b_m'), 'contenedor': bool(m.get('contenedor')), 'comp': list(m.get('compartimientos', []))}
        if dim:
            f['dim'] = list(dim)
            f['b'] = round(min(dim[0], dim[1]) / 2, 3)
            if m.get('masa_por_metro_kg'):
                f['masa'] = round(m['masa_por_metro_kg'] * dim[0], 1)
        v = (m.get('variantes') or {}).get(variante) if variante else None
        if v:
            if 'dim_m' in v:
                f['dim'] = list(v['dim_m'])
                f['b'] = round(min(v['dim_m'][0], v['dim_m'][1]) / 2, 3)
            for k_v, k_f in (('montaje', 'montaje'), ('anclaje', 'anclaje'), ('masa_kg', 'masa'), ('h_cg_m', 'hcg'), ('mu', 'mu')):
                if k_v in v:
                    f[k_f] = v[k_v]
        return f

    # ---------------------------------------------------------------------------------------------- asignaciones
    def asignar(self) -> list[Asignacion]:
        asg = []
        orden = 0
        for l in self.lineas:
            r = self.reglas.get(l['id'])
            if r is None:
                raise ErrorGenerador(f'{l["id"]} «{l["nombre"]}»: sin regla en reglas_ubicacion.json')
            if r.get('nombre') != l['nombre']:
                raise ErrorGenerador(f'reglas_ubicacion: {l["id"]} se llama «{l["nombre"]}», no «{r.get("nombre")}»')
            if l['tipo'] == 'servicio' or r.get('sin_unidades'):
                l['sin_unidades'] = r.get('sin_unidades') or 'Servicio: no tiene unidades físicas.'
                continue
            k = 0
            for e in r.get('reparto', []):
                for item in self._expandir(e, l['nombre']):
                    k += 1
                    orden += 1
                    rid, zona, pz, fuera = item
                    asg.append(Asignacion(l['id'], k, e, rid, zona, pz, fuera, orden=orden))
            if k != l['cantidad']:
                raise ErrorGenerador(f'{l["id"]} «{l["nombre"]}»: el reparto ubica {k} unidades y la cantidad es {l["cantidad"]}')
        return asg

    def _expandir(self, e, nombre):
        """[(recinto, zona, pieza de zona, fuera)] para un tramo del reparto, uno por unidad."""
        if 'fuera_de_la_torre' in e:
            return [(None, None, None, e['fuera_de_la_torre'])] * int(e.get('cantidad', 1))
        if 'paneles' in e:
            return self.filas_paneles(e)
        if 'circulaciones' in e:
            out = []
            for nv in e['circulaciones']:
                for rid in sorted(self.circ.get(nv, [])):
                    out += [(rid, None, None, None)] * int(e.get('por_recinto', 1))
            return out
        rids = []
        if 'recinto' in e and self.ins.plantas is not None:
            # recinto no programado de la planta (por ejemplo, P2-TEC-02, biología molecular): sin planta va al «ambiente»
            if e['recinto'] not in self.recintos:
                raise ErrorGenerador(f'«{nombre}»: la planta no tiene el recinto {e["recinto"]}')
            rids = [e['recinto']]
        elif 'ambiente' in e:
            try:
                fila = C.resolver_ambiente(e['ambiente'], self.ins.ambientes)
            except C.ErrorAmbiente as err:
                raise ErrorGenerador(f'«{nombre}»: {err}') from None
            rids = self.recintos_de(fila, e.get('recintos_k'))
        if rids and e.get('estrategia') == 'zona' and 'zona' in e:
            # puntos del programa dentro de un recinto de la planta (las ambulancias en sus cupos): pieza fija en ese recinto
            z = e['zona']
            pts = [pz['punto'] for pz in z['piezas']] if 'piezas' in z else z.get('puntos', [])
            out = []
            for i in range(int(e.get('cantidad', len(pts)))):
                pt = pts[i % len(pts)]
                rid = next((r for r in rids if r in self.recintos and C.punto_en_poligono(pt, self.recintos[r]['poligono'], 0.0)),
                           rids[i % len(rids)])
                out.append((rid, z, {'punto': pt, 'rotacion_deg': z.get('rotacion_deg', 0)}, None))
            return out
        if not rids and 'zona' in e:
            z = e['zona']
            if 'piezas' in z:
                return [(None, z, p, None) for p in z['piezas']][:int(e.get('cantidad', len(z['piezas'])))]
            pts = z.get('puntos', [])
            n = int(e.get('cantidad', e.get('por_recinto', len(pts))))
            return [(None, z, {'punto': pts[i % len(pts)]}, None) for i in range(n)]
        if not rids:
            if self.ins.plantas is not None and 'ambiente' in e:
                raise ErrorGenerador(f'«{nombre}»: la planta no tiene recintos de la fila {e["ambiente"]}')
            return []
        if 'cantidad' in e:
            n = int(e['cantidad'])
            return [(rids[i % len(rids)], None, None, None) for i in range(n)]
        return [(rid, None, None, None) for rid in rids for _ in range(int(e.get('por_recinto', 1)))]

    def filas_paneles(self, e):
        """Una pieza por fila de paneles solares de la planta (niveles[].paneles_solares): las filas de la terraza van en su
        recinto (filas_rect); las de la pérgola y la marquesina, que pasan por encima de varios recintos, quedan como zona
        del nivel. Las filas corren a lo largo del eje (rumbo 0 = norte), con sus módulos de 2,28 × 1,13 m."""
        gid = e['paneles']
        grupo, nivel = None, None
        for n in (self.ins.plantas or {}).get('niveles', []):
            for g in n.get('paneles_solares', []) or []:
                if g.get('id') == gid:
                    grupo, nivel = g, n
        if grupo is None:
            if self.ins.plantas is None:
                return []
            raise ErrorGenerador(f'paneles {gid!r}: la planta no trae ese grupo de paneles solares')
        mod = grupo.get('modulo_m') or [2.28, 1.13]
        kwp_mod = float(grupo.get('kwp_modulo') or 0.55)
        base = {'nivel': nivel['id'], 'nombre': grupo.get('nombre'), 'grupo': gid}
        out = []
        if grupo.get('filas_rect'):
            z = float(grupo.get('z_piso_m') or 0.0)
            for f in grupo['filas_rect']:
                x0, y0, x1, y1 = f['rect']
                largo_x = (x1 - x0) >= (y1 - y0)
                L, D = (x1 - x0, y1 - y0) if largo_x else (y1 - y0, x1 - x0)
                pz = {'punto': [r2((x0 + x1) / 2), r2((y0 + y1) / 2)], 'dim_m': [r2(L), r2(D), 1.0], 'rotacion_deg': 0 if largo_x else 90,
                      'fila': f['id'], 'modulos': f.get('modulos'), 'kwp': C.redondear((f.get('modulos') or 0) * kwp_mod, 2)}
                rid = next((r['id'] for r in nivel.get('recintos', [])
                            if C.punto_en_poligono(pz['punto'], r.get('poligono_libre') or r['poligono'], 0.0)), None)
                out.append((rid, dict(base, z=z), pz, None))
            return out
        cx, cy = grupo['centro']
        largo, ancho = float(grupo['largo_m']), float(grupo['ancho_m'])
        nf, nc = int(grupo['filas']), int(grupo['columnas'])
        rumbo = math.radians(float(grupo.get('rumbo_eje') or 0.0))
        vx, vy = math.cos(rumbo), -math.sin(rumbo)            # a lo ancho (rumbo 0: hacia el este)
        L = min(largo, nc * mod[0])
        alto = float(grupo.get('altura_m') or 0.0)
        for i in range(nf):
            o = -ancho / 2 + ancho / nf * (i + 0.5)
            # revisión adversarial: las filas de la pérgola y de la marquesina van arriba de su estructura (montaje «cielo» a la
            # altura de la planta, 0,10 m de alto) y no ocupan el piso; la variante «elevada» trae los postes de los extremos
            pz = {'punto': [r2(cx + vx * o), r2(cy + vy * o)], 'dim_m': [r2(L), mod[1], 0.1],
                  'rotacion_deg': C.redondear(90 - math.degrees(rumbo), 4), 'fila': f'{gid}-F{i + 1}', 'modulos': nc,
                  'kwp': C.redondear(nc * kwp_mod, 2), 'montaje': 'cielo', 'variante': 'elevada'}
            out.append((None, dict(base, z=alto), pz, None))
        return out

    # ---------------------------------------------------------------------------------------------- infraestructura
    def servicio_infra(self, fila=None, nivel=None):
        inf = self.ins.reglas.get('infraestructura', {})
        if fila is not None:
            a = self.ins.ambientes[fila]
            por_piso = inf.get('servicio_por_piso', {})
            if str(a.get('piso')) in por_piso:
                return por_piso[str(a.get('piso'))]
            srv = inf.get('servicio_de_programa', {}).get(a.get('servicio'))
            if srv:
                return srv
            return re.sub(r'[^a-z0-9]+', '_', str(a.get('servicio', 'infraestructura')).lower()).strip('_')[:30] or 'infraestructura'
        if nivel in ('CUB', 'CUB-T'):
            return 'cubierta'
        if nivel == 'EXT':
            return 'exteriores'
        return 'circulacion'

    def linea_infra(self, elemento, servicio):
        el = self.ins.reglas['infraestructura']['elementos'][elemento]
        lid = C.id_linea(servicio, 'i', el['nombre'])
        if lid in self.L:
            return self.L[lid]
        ex_por_id = {e['id']: e for e in self.ins.exig}
        citas = []
        for cod in el.get('presupuesto', []):
            desc = self.ins.items_presupuesto.get(cod)
            if desc is None and self.ins.items_presupuesto:
                raise ErrorGenerador(f'infraestructura «{elemento}»: el ítem {cod} no está en presupuesto.json')
            citas.append({'item': cod, 'descripcion': desc})
        capa = el.get('capa', 'infraestructura')
        # ¿el ítem de obra citado es en realidad una línea de equipamiento fijo de dotacion.json (P3 del presupuesto)? Entonces
        # el elemento es parte física de esa línea, que ya tiene precio: no es «obra» y no suma (condensadoras, llamado)
        parte = None
        for cod in el.get('presupuesto', []):
            fuente = str((self.ins.items_presupuesto_dato.get(cod) or {}).get('fuente') or '')
            m = re.match(r"dotacion\.json, equipamiento fijo: '([^']+)'", fuente)
            if m:
                lf = C.id_linea('fijo', 'f', m.group(1))
                if lf not in self.L:
                    raise ErrorGenerador(f'infraestructura «{elemento}»: el ítem {cod} cita la línea fija «{m.group(1)}», que no está en dotacion.json')
                parte = {'linea': lf, 'nombre': m.group(1), 'item': cod}
                break
        d = {'id': lid, 'origen': 'infraestructura', 'ref': {'elemento': elemento}, 'servicio': servicio, 'tipo': 'infraestructura',
             'capa': capa, 'nombre': el['nombre'], 'cantidad': 0, 'especificacion': el.get('norma'), 'modelo3d': el['modelo3d'],
             'variante': None, 'dim_m': None,
             'clase_riesgo': {'repo': None, 'vigente': 'no_dm', 'estado': 'coherente', 'regla': None,
                              'fuente': 'capa de infraestructura (obra o contexto): no es dispositivo médico'},
             'clase_riesgo_revision': None, 'es_dispositivo_medico': 'no',
             'registro_invima': {'requerido': 'no', 'via': None, 'usado_permitido': True, 'nota': None}, 'tecnologia_controlada': None,
             'componentes': [], 'exigencias': [ref_exigencia(ex_por_id[x]) for x in el.get('exigencias', []) if x in ex_por_id],
             'prioridad': 'no_aplica', 'prioridad_revisada': None, 'norma_base': el.get('norma'), 'justificacion_recomendado': None,
             'mantenimiento': {'anual_pct': None, 'vida_util_anios': None, 'preventivo': 'mantenimiento de la edificación',
                               'personal_inscrito_invima': False, 'calibracion': False, 'cita_inscripcion': None},
             'precio_unitario_cop_2026': None, 'rango_precio_unitario_cop_2026': None,
             'tipo_precio': 'contexto (no se presupuesta en la torre)' if capa == 'contexto' else 'obra (presupuesto.json; no es dotación)',
             'metodo_precio': 'Ítem de obra citado; no suma al costo de la dotación' if citas else 'Sin precio: contexto del recorrido',
             'fuentes_precio': [], 'cita_presupuesto': citas, 'nota_interna': None, 'plantilla_contenido': None, 'elemento': elemento}
        if parte:
            d['parte_de_linea'] = parte
            d['tipo_precio'] = f'incluido en la línea de equipamiento fijo «{parte["nombre"]}» (dotacion.json; ítem {parte["item"]} del presupuesto)'
            d['metodo_precio'] = 'No suma: es parte física de una línea de equipamiento fijo que ya tiene precio en dotacion.json'
        self.lineas.append(d)
        self.L[lid] = d
        return d

    def asignar_infra(self, diferidas=False) -> list[Asignacion]:
        asg = []
        inf = self.ins.reglas.get('infraestructura') or {}
        for regla in inf.get('reglas', []):
            el = regla['elemento']
            for e in regla['reparto']:
                es_dif = 'por_unidad_de' in e
                if es_dif != diferidas:
                    continue
                if es_dif:
                    fila = C.resolver_ambiente(e['ambiente'], self.ins.ambientes)
                    for rid in self.recintos_de(fila):
                        refs = [u for u in self.unidades if u['recinto'] == rid and u.get('_modelo') in e['por_unidad_de']
                                and C.RE_UNIDAD.match(u['id']).group(4) is None]
                        for u in refs:
                            l = self.linea_infra(el, self.servicio_infra(fila))
                            l['cantidad'] += 1
                            asg.append(Asignacion(l['id'], l['cantidad'], e, rid, elemento=el, ref=u['id']))
                    continue
                fila = C.resolver_ambiente(e['ambiente'], self.ins.ambientes) if 'ambiente' in e else None
                for rid, zona, pz, fuera in self._expandir(e, el):
                    if fila is not None:
                        srv = self.servicio_infra(fila)
                    elif zona:
                        srv = self.servicio_infra(nivel=zona.get('nivel'))
                    else:
                        srv = self.servicio_infra(nivel=None)            # circulaciones
                    l = self.linea_infra(el, srv)
                    l['cantidad'] += 1
                    asg.append(Asignacion(l['id'], l['cantidad'], e, rid, zona, pz, fuera, elemento=el))
        return asg

    # ---------------------------------------------------------------------------------------------- unidades
    def nueva_unidad(self, a: Asignacion) -> dict:
        l = self.L[a.linea]
        uid = C.id_unidad_de_linea(l['id'], a.k)
        e = a.e
        modelo = l['modelo3d']
        variante = e.get('variante') or l.get('variante')
        dim = (a.pieza_zona or {}).get('dim_m') or e.get('dim_m') or l.get('dim_m')
        f = self.ficha_modelo(modelo, variante, dim)
        u = {'id': uid, 'linea': l['id'], 'k': a.k, 'piso': None, 'nivel': None, 'recinto': a.rid, 'ambiente': None,
             'posicion': None, 'rotacion_z': None, 'montaje': None, 'apoyo': None, 'dentro_de': None, 'compartimiento': None,
             'riesgo_sismico': None, 'contenido': None, 'campos_al_comprar': None, 'estado': None,
             '_modelo': modelo, '_ficha': f, '_variante': variante, '_dim_propia': (a.pieza_zona or {}).get('dim_m') or e.get('dim_m')}
        if variante and variante != l.get('variante'):
            u['variante'] = variante
        if u['_dim_propia'] and u['_dim_propia'] != l.get('dim_m'):
            u['dim_m'] = list(u['_dim_propia'])
        if a.rid:
            u['nivel'], u['piso'], u['ambiente'] = self.datos_recinto(a.rid)
        elif a.fuera:
            u['estado'] = 'fuera_de_la_torre'
            u['ubicacion'] = a.fuera
            self.fuera.append({'linea': l['id'], 'nombre': l['nombre'], 'unidad': uid, 'ubicacion': a.fuera})
        elif a.zona:
            zn = a.zona.get('nivel')
            info = (self.ins.reglas.get('zonas_sin_planta') or {}).get(zn, {})
            u['nivel'] = 'CUB' if zn in ('CUB', 'CUB-T') else zn
            nv = next((n for n in (self.ins.plantas or {}).get('niveles', []) if n['id'] == u['nivel']), None)
            u['piso'] = nv.get('piso', u['nivel']) if nv else u['nivel']
            if nv is not None:
                cola = ' (posición de la planta: pasa por encima de varios recintos)' if a.zona.get('grupo') else \
                       ' (posición del programa sobre la planta; no queda dentro de un recinto)'
            else:
                cola = ' (sin planta; posición del programa)'
            u['ubicacion'] = ('cubierta: ' if u['nivel'] == 'CUB' else 'exterior: ') + (a.zona.get('nombre') or info.get('nombre') or zn) + cola
            u['nivel_z'] = nv.get('z') if nv else info.get('nivel_z')
        if a.pieza_zona and a.pieza_zona.get('fila'):
            pz = a.pieza_zona
            u['paneles'] = {'grupo': (a.zona or {}).get('grupo'), 'fila': pz['fila'], 'modulos': pz.get('modulos'), 'kwp': pz.get('kwp'),
                            'tipo_dato': 'estimación (módulos de ≈ 550 W de 2,28 × 1,13 m; data/edificios/torre_hospital.json)'}
        if u['estado'] is None:
            u['estado'] = {'cierre_brechas': 'cierre_brechas_propuesto', 'infraestructura': 'infraestructura'}.get(l['origen'], 'en_dotacion')
            if l.get('capa') == 'contexto':
                u['estado'] = 'contexto'
            if l['origen'] == 'infraestructura' and e.get('propuesta_obra'):
                # elemento de obra que la planta propone pero el diseño de obra no trae: cuenta solo con el cierre de brechas
                u['estado'] = 'cierre_brechas_propuesto'
                u['propuesta_obra'] = e['propuesta_obra']
        if l['origen'] != 'infraestructura':
            u['campos_al_comprar'] = {c: None for c in CAMPOS_AL_COMPRAR}
        a.unidad = u
        self.unidades.append(u)
        self.U[uid] = u
        return u

    # ---------------------------------------------------------------------------------------------- colocación
    def estrategia(self, a: Asignacion) -> str:
        if a.fuera:
            return 'fuera_de_la_torre'
        if a.zona and not a.rid:
            return 'zona'
        if a.pieza_zona and a.rid:
            return 'fija'                       # pieza con posición de la planta (filas de paneles de la terraza)
        est = a.e.get('estrategia')
        if est == 'zona':
            return 'centro'                     # la planta sí trae el recinto: se ubica dentro de él
        if a.elemento in SANITARIOS and est == 'esquina':
            return 'esquina_sanitaria'
        if a.elemento in ('lavamanos', 'lavamanos_quirurgico') and est == 'pared_altura':
            return 'pared_fija'                 # aparato de obra: va antes que los muebles, que no lo pueden tapar
        return est

    def ejecutar(self):
        asg = self.asignar() + self.asignar_infra()
        self.a_subrecintos(asg)
        for a in asg:
            self.nueva_unidad(a)
        dif = self.asignar_infra(diferidas=True)        # tomas y llamados por puesto: dependen del modelo, no de la posición
        for a in dif:
            self.nueva_unidad(a)
        asg += dif
        for i, a in enumerate(asg):
            a.orden = i
        self.crear_componentes()
        por_sala, sueltas = {}, []
        for a in asg:
            if a.rid and self.estrategia(a) not in ('zona', 'fuera_de_la_torre') and self.sala(a.rid) is not None:
                por_sala.setdefault(a.rid, []).append(a)
            else:
                sueltas.append(a)
        for a in sorted(sueltas, key=self.clave):
            self.colocar(a)
        for rid in sorted(por_sala):
            self.amueblar(rid, por_sala[rid])
        for u in self.comps:
            if u['_colocado'] is False:
                self.colocar_componente(u, None)
        for u in self.unidades:
            if u.get('recinto') in self.padre_de:
                u['_sub'] = u['recinto']
                u['recinto'] = self.padre_de[u['recinto']]
        self.contenidos()
        for u in self.unidades:
            self.riesgo(u)
        self.lineas = [l for l in self.lineas if l['origen'] != 'infraestructura' or l['cantidad'] > 0]
        orden_l = {l['id']: i for i, l in enumerate(self.lineas)}
        self.unidades.sort(key=lambda u: (orden_l[u['linea']], u['k'], u['id']))

    def a_subrecintos(self, asg):
        """Revisión adversarial (baños): el inodoro, la ducha, las barras de apoyo, el lavamanos de la unidad sanitaria y el
        llamado junto al inodoro de un recinto con baño o con cabinas van dentro de ellos. Los inodoros se reparten entre las cabinas en orden; la barra va a la
        cabina PMR (o al baño más grande) y la ducha al baño más grande."""
        por = {}
        for a in asg:
            if not a.rid or a.rid not in self.subs_de:
                continue
            modelo = self.L[a.linea]['modelo3d']
            # el lavamanos de la unidad sanitaria (reparto sin «pared»; el del consultorio va «junto_puerta») entra al baño
            # cuando el recinto tiene uno solo; en las baterías con cabinas queda afuera, en la zona común
            lav = modelo == 'lavamanos' and not a.e.get('pared') and len(self.subs_de[a.rid]) == 1
            if modelo in EN_BANO or lav or (modelo == 'llamado_enfermeria' and a.e.get('junto_a') == 'inodoro'):
                por.setdefault((a.rid, modelo), []).append(a)
        for (rid, modelo), lista in sorted(por.items()):
            subs = sorted(self.subs_de[rid], key=lambda d: d['id'])
            grande = max(subs, key=lambda d: (d.get('area_libre_m2') or 0.0, d['id']))
            if modelo == 'inodoro':
                for i, a in enumerate(sorted(lista, key=lambda a: (a.orden, a.k))):
                    a.rid = subs[i % len(subs)]['id']
                continue
            destino = grande
            if modelo == 'barra_apoyo':
                destino = next((d for d in subs if 'PMR' in (d.get('ambiente') or '')), grande)
            for a in lista:
                a.rid = destino['id']

    def clave(self, a):
        est = self.estrategia(a)
        f = a.unidad['_ficha']['dim']
        area = f[0] * f[1] if FASE[est] in (1, 2, 3, 4, 8) else 0.0     # en un baño, la ducha antes que el inodoro
        return (FASE[est], -round(area, 4), a.orden)

    # ---------------------------------------------------------------------------------------------- un recinto completo
    MAX_VARIANTES = 16

    def amueblar(self, rid, asgs):
        """Ubica todo lo de un recinto (por fases) y, si queda algo sin lugar o un puesto de paciente sin paso libre, lo
        intenta de nuevo con la siguiente posición posible del primer puesto de paciente. Se queda con la mejor variante."""
        orden = sorted(asgs, key=self.clave)
        madres = {a.unidad['id'] for a in asgs}
        comps = [c for c in self.comps if c['componente_de'] in madres]
        propias = [a.unidad for a in asgs] + comps
        base = [dict(u) for u in propias]
        hay_paciente = any(self.estrategia(a) == 'cabecera_a_pared' for a in asgs)
        n0 = len(self.avisos)
        mejor = None
        vueltas = [(v, r_) for r_ in (False, True) for v in range(self.MAX_VARIANTES if hay_paciente else 1)]
        saltar = None
        for v, reservar in vueltas:
            if reservar == saltar:
                continue
            if reservar and mejor is not None and mejor['puntaje'][0] == 0:
                break                         # la primera vuelta ya dejó todas las entradas con paso y todo en su lugar
            for u, b in zip(propias, base):
                u.clear()
                u.update(b)
            del self.avisos[n0:]
            n = self.nivel_de[rid]
            sala = Sala(self.recintos[rid], n, self.poligonos[n['id']], reservar_pasos=reservar)
            self.salas[rid] = sala
            self._salto = v
            self._agotado = False
            if v == 0:
                self._primeros = {}
            fases = sorted({FASE[self.estrategia(a)] for a in orden})
            ultima_de_piso = max([f for f in fases if f <= 5], default=None)
            for fase in fases:
                for a in orden:
                    if FASE[self.estrategia(a)] == fase:
                        self.colocar(a)
                if fase >= 3:
                    for c in comps:
                        if c['_ficha']['montaje'] == 'piso' and not c['_colocado']:
                            self.colocar_componente(c, sala)
                if fase == ultima_de_piso:
                    self.reparar_paso(sala)
            for c in comps:
                if not c['_colocado']:
                    self.colocar_componente(c, sala)
            av = self.avisos[n0:]
            fallas = len(self.fallas_paso(sala))
            bloqueadas = sala.entradas_bloqueadas()
            puntaje = (sum('NO CABE' in x for x in av) + bloqueadas, fallas, sum(('sin lugar' in x) or ('sobrecupo' in x) for x in av))
            if mejor is None or puntaje < mejor['puntaje']:
                mejor = {'puntaje': puntaje, 'sala': sala, 'avisos': list(av), 'estado': [dict(u) for u in propias],
                         'bloqueadas': bloqueadas}
            if puntaje == (0, 0, 0):
                break
            if self._agotado:
                saltar = reservar             # sin más variantes de puesto en esta vuelta: se pasa a la siguiente
        for u, b in zip(propias, mejor['estado']):
            u.clear()
            u.update(b)
        del self.avisos[n0:]
        self.avisos += mejor['avisos']
        if mejor['bloqueadas']:
            self.aviso(f'{rid}: el mobiliario deja {mejor["bloqueadas"]} entrada(s) sin paso de 0,60 m (revisar la regla; I17)')
        self.salas[rid] = mejor['sala']

    def piezas(self, sala, modelos, contenedor=False):
        if isinstance(modelos, str):
            modelos = [modelos]
        out = []
        for m in modelos:
            out += [p for p in sala.unidades if p.modelo == m and (p.contenedor or not contenedor)]
        return out

    def elegir(self, cands, atributo='n_junto'):
        if not cands:
            return None
        return min(cands, key=lambda p: (getattr(p, atributo), cands.index(p)))

    def colocar(self, a: Asignacion):
        u = a.unidad
        est = self.estrategia(a)
        if est == 'fuera_de_la_torre':
            return
        f = u['_ficha']
        w, d, h = f['dim']
        if est == 'zona':
            pz = a.pieza_zona or {}
            pt = pz.get('punto')
            rot = math.radians(pz.get('rotacion_deg', a.zona.get('rotacion_deg', 0)))
            z = float(a.zona.get('z', 0.0))
            u['posicion'] = [r2(pt[0]), r2(pt[1]), r2(z)] if pt else None
            u['rotacion_z'] = ang(rot)
            u['montaje'] = pz.get('montaje') or a.zona.get('montaje') or 'piso'
            if pz.get('variante'):
                u['variante'] = pz['variante']
            return
        sala = self.sala(a.rid)
        if sala is None:
            self.relacionar_sin_geometria(a, est)
            return
        e = a.e
        res = self._intentar(sala, a, est, e, w, d, h)
        if res is None and e.get('alternativa'):
            alt = dict(e)
            alt.update(e['alternativa'])
            alt.pop('alternativa', None)
            est2 = alt.get('estrategia', est)
            res = self._intentar(sala, a, est2, alt, w, d, h)
            if res is not None:
                u['_alternativa'] = est2
        if res is None:
            res = self._respaldo(sala, a, est, w, d, h)
        self._registrar(sala, a, res, f)

    def _intentar(self, sala, a, est, e, w, d, h):
        u = a.unidad
        col = self.col
        if est in ('contra_pared', 'fila', 'esquina', 'esquina_sanitaria'):
            pared = 'junto_puerta' if est == 'esquina_sanitaria' and not e.get('pared') else e.get('pared')
            bv = bool(e.get('bajo_ventana'))           # se puede poner delante de una ventana (el alféizar queda detrás)
            r = col.contra_pared(sala, w, d, h, pared=pared, sep=float(e.get('separacion_pared_m', 0.0)),
                                 esquina=est in ('esquina', 'esquina_sanitaria'), bajo_ventana=bv, preferir=e.get('preferir', 'inicio'))
            if r is None and est in ('esquina', 'esquina_sanitaria'):
                r = col.contra_pared(sala, w, d, h, pared=pared, bajo_ventana=bv)
            return ('piso', r, None) if r else None
        if est == 'cabecera_a_pared':
            salto, self._salto = self._salto, None      # la variante elige la posición solo del primer puesto del recinto
            bandas = int(e.get('bandas', 2))
            if salto is None:                            # los demás puestos: la primera posición con camino
                elegidos = self.posiciones_puesto(sala, w, d, h, bandas, 1, e.get('pared'))
            else:                                        # el primero: lista guardada para todas las variantes del recinto
                if u['id'] not in self._primeros:
                    self._primeros[u['id']] = self.posiciones_puesto(sala, w, d, h, bandas, self.MAX_VARIANTES, e.get('pared'))
                elegidos = self._primeros[u['id']]
                if salto >= max(1, len(elegidos)):
                    self._agotado = True
                    elegidos = elegidos[:1]
                else:
                    elegidos = elegidos[salto:salto + 1]
            if elegidos and elegidos[0][1] is not None:
                (cx, cy, rot, bk, caja, reservas, modo), cam = elegidos[0]
                for res in reservas:
                    sala.ocupar(res, 0.0, paso=True)
                sala.reservar_camino(cam)
                if modo == 'sin_banda':
                    self.aviso(f'{u["id"]} ({u["_modelo"]}) en {a.rid}: sin 0,9 m libres a un costado (se revisa con la regla I6)')
                return ('piso', (cx, cy, rot, bk, caja), None)
            if elegidos:
                (cx, cy, rot, bk, caja, reservas, modo), _ = elegidos[0]
                for res in reservas:
                    sala.ocupar(res, 0.0, paso=True)
                self.aviso(f'{u["id"]} ({u["_modelo"]}) en {a.rid}: sin camino de 0,9 m desde la puerta hasta un costado')
                return ('piso', (cx, cy, rot, bk, caja), None)
            return None
        if est == 'centro':
            r = col.centro(sala, w, d, h)
            return ('piso', r, None) if r else None
        if est == 'cuadricula':
            r = col.cuadricula(sala, w, d, h, pasillo=float(e.get('pasillo_m', 1.2)), pared=e.get('pared', 'opuesta_puerta'),
                               patron=e.get('patron', 'enfrentadas'), rodillas=float(e.get('rodillas_m', 0.45)),
                               grupo=e.get('grupo') or a.linea, filas_max=int(e.get('filas_max', 40)))
            return ('piso', r, None) if r else None
        if est == 'fija':
            pz = a.pieza_zona
            cx, cy = pz['punto']
            rot = math.radians(pz.get('rotacion_deg', 0))
            caja = Sala.caja(cx, cy, w, d, rot)
            return ('piso', (cx, cy, rot, None, caja), None) if sala.libre_caja(caja, permitir_paso=True) else None
        if est == 'en_nucleo':
            r = col.centro(sala, w, d, h, permitir_paso=True) or col.centro(sala, w, d, h, permitir_paso=True, permitir_puerta=True)
            return ('en_nucleo', r, None) if r else None
        if est == 'posiciones_fijas':
            for pos in e.get('posiciones', [{'ref': 'centro'}]):
                if pos.get('ref') == 'punto':              # punto del recinto (pieza compuesta con su lugar en la sala)
                    cx, cy = pos['punto']
                    rot = math.radians(float(pos.get('rotacion_deg', 0.0)))
                    caja = Sala.caja(cx, cy, w, d, rot)
                    if sala.libre_caja(caja, permitir_paso=True, h=h):
                        return ('piso', (cx, cy, rot, None, caja), None)
                    continue
                if pos.get('ref') == 'pared_compartida':
                    ks = self.bordes_compartidos(sala, pos['con'])
                    r = col.contra_pared(sala, w, d, h, compartidos=ks, preferir='centro')
                else:
                    X0, Y0, X1, Y1 = C.caja(sala.libre)
                    rot = 0.0 if (X1 - X0) >= (Y1 - Y0) else math.pi / 2
                    if pos.get('eje') == 'corto':          # el lado largo de la pieza a lo ancho del recinto
                        rot = math.pi / 2 - rot
                    r = col.centro(sala, w, d, h, rot_fija=rot if pos.get('eje') in ('largo', 'corto') else None)
                if r:
                    return ('piso', r, None)
            return None
        if est == 'junto_a':
            cands = self.piezas(sala, e.get('junto_a'))
            for R in sorted(cands, key=lambda p: (p.n_junto, cands.index(p))):
                r = col.junto_a(sala, R, w, d, h, lado=e.get('lado'))
                if r:
                    R.n_junto += 1
                    return ('piso', r, None)
            if not cands:
                self.aviso(f'{u["id"]} ({u["_modelo"]}) en {a.rid}: no hay {e.get("junto_a")} en el recinto para ponerlo al lado')
            return None
        if est in ('pared_altura', 'pared_fija'):
            z = float(e.get('altura_m', 1.2))
            R = None
            if a.ref:
                R = next((p for p in sala.unidades if p.id == a.ref), None)
            elif e.get('junto_a'):
                cands = self.piezas(sala, e['junto_a'])
                R = self.elegir(cands)
            r = col.pared_altura(sala, w, d, h, z, pared=e.get('pared'), R=R, sep=float(e.get('separacion_m', 0.0)))
            if r is None and R is not None:
                r = col.pared_altura(sala, w, d, h, z, pared=e.get('pared'))
            if r and R is not None:
                R.n_junto += 1
            return ('pared', r, z) if r else None
        if est == 'cielo':
            z = sala.alto_libre - h
            R = self.elegir(self.piezas(sala, e['sobre'])) if e.get('sobre') else None
            if R is not None and e.get('lado') == 'costado':
                ux, uy = R.ejes()
                # el riel corre junto al costado de la cama, de la cara del muro de la cabecera (5 cm) a 0,1 m más allá de los
                # pies; se recorta a la cara de los muros y se busca el costado y la distancia que no crucen otra unidad
                for sep_c in (0.45, 0.55, 0.65, 0.35, 0.75):
                    for s in (1, -1):
                        for largo in (round(R.d + 0.2, 2), round(R.d + 0.1, 2), round(R.d, 2), round(R.d - 0.2, 2)):
                            for corr in (0.0, -0.1, 0.1, -0.2, 0.2, -0.3, 0.3):
                                cx = R.cx + s * ux[0] * (R.w / 2 + sep_c) + uy[0] * corr
                                cy = R.cy + s * ux[1] * (R.w / 2 + sep_c) + uy[1] * corr
                                caja = Sala.caja(cx, cy, largo, d, R.rot + math.pi / 2)
                                if not C.poligono_dentro_de(C.rect_a_poligono(caja), sala.libre, 0.0):
                                    continue
                                if sala.choca_3d(caja, z, z + h):
                                    continue
                                a.unidad['dim_m'] = [largo, d, h]
                                R.n_junto += 1
                                return ('cielo', (cx, cy, R.rot + math.pi / 2, None, caja), z)
                largo = round(R.d + 0.2, 2)
                a.unidad['dim_m'] = [largo, d, h]
                self.aviso(f'{a.unidad["id"]} (riel_cortina) en {a.rid}: sin lugar libre junto a {R.id}; queda sobre la cama')
            if R is not None:
                R.n_junto += 1
                return ('cielo', (R.cx, R.cy, R.rot, None, Sala.caja(R.cx, R.cy, w, d, R.rot)), z)
            cx, cy = C.centroide(sala.libre)
            return ('cielo', (cx, cy, 0.0, None, Sala.caja(cx, cy, w, d, 0.0)), z)
        if est == 'sobre':
            return self._sobre(sala, a, e, w, d, h)
        if est == 'dentro':
            cands = []
            for m in (e.get('dentro') or []):
                cands += [p for p in sala.unidades if p.modelo == m and p.contenedor and p.id != u['id']]
            if not cands:
                return None
            Cn = min(cands, key=lambda p: (cands.index(p) if p.modelo == cands[0].modelo else 1000 + cands.index(p), p.n_dentro))
            comp = e.get('compartimiento')
            if comp not in Cn.compartimientos:
                comp = Cn.compartimientos[Cn.n_dentro % len(Cn.compartimientos)] if Cn.compartimientos else None
            Cn.n_dentro += 1
            return ('dentro', Cn, comp)
        raise ErrorGenerador(f'estrategia desconocida {est!r} ({u["id"]})')

    def _sobre(self, sala, a, e, w, d, h):
        apoyos = []
        for m in (e.get('sobre') or []):
            apoyos += [p for p in sala.unidades if p.modelo == m and p.id != a.unidad['id']]
        if apoyos and all(A.modelo == a.unidad['_modelo'] for A in apoyos):
            # pila del mismo modelo (estibas): encima de la última de la pila, no al lado (revisión adversarial: choques 3D)
            arriba = {self.U[q.id].get('apoyo') for q in sala.unidades if q.montaje == 'sobre' and q.id in self.U}
            cima = [A for A in apoyos if A.id not in arriba]
            if cima:
                A = min(cima, key=lambda q: (q.z, apoyos.index(q)))
                return ('sobre', (A.cx, A.cy, A.rot, None, None), A)
        if e.get('repartir'):                         # uno por apoyo, por turnos (p. ej. un juego por unidad odontológica)
            apoyos.sort(key=lambda A: (sala.cursor.get(('n', A.id, a.unidad['linea']), 0), sala.cursor.get(('n', A.id), 0)))
        for A in apoyos:
            sup = APOYOS_SUPERFICIE.get(A.modelo)
            if sup:                                   # el escritorio va contra la espalda del puesto; las sillas, al frente
                W, D = min(sup[0], A.w), min(sup[1], A.d)
                ox, oy = 0.0, -A.d / 2 + D / 2
            else:
                (W, D), (ox, oy) = (A.w, A.d), (0.0, 0.0)
            st = sala.cursor.setdefault(A.id, [])
            for ww, dd, giro in ((w, d, 0.0), (d, w, math.pi / 2)):
                if ww > W + 1e-6 or dd > D + 1e-6:
                    continue
                pos = None
                for i_f, fila in enumerate(st):
                    ultima = i_f == len(st) - 1
                    if fila[2] + ww <= W + 1e-6 and (dd <= fila[1] + 1e-6 or (ultima and fila[0] + dd <= D + 1e-6)):
                        fila[1] = max(fila[1], dd)
                        pos = (-W / 2 + fila[2] + ww / 2, -D / 2 + fila[0] + dd / 2)
                        fila[2] += ww + 0.02
                        break
                if pos is None:
                    y0 = sum(f_[1] + 0.02 for f_ in st)
                    if y0 + dd <= D + 1e-6:
                        st.append([y0, dd, ww + 0.02])
                        pos = (-W / 2 + ww / 2, -D / 2 + y0 + dd / 2)
                if pos is not None:
                    ux, uy = A.ejes()
                    lx, ly = ox + pos[0], oy + pos[1]
                    cx = A.cx + ux[0] * lx + uy[0] * ly
                    cy = A.cy + ux[1] * lx + uy[1] * ly
                    if sala.choca_3d(Sala.caja(cx, cy, ww, dd, A.rot), A.z + A.h, A.z + A.h + h, excluir=(A.id,)):
                        continue
                    for k in (('n', A.id), ('n', A.id, a.unidad['linea'])):
                        sala.cursor[k] = sala.cursor.get(k, 0) + 1
                    return ('sobre', (cx, cy, A.rot + giro, None, None), A)
        # sin lugar sobre ningún apoyo: la regla sigue con su alternativa o el respaldo (repisa en la pared), no se apila en el
        # centro del apoyo (revisión adversarial: choques 3D)
        return None

    def _respaldo(self, sala, a, est, w, d, h):
        u = a.unidad
        col = self.col
        fase = FASE[est]
        if fase in (6,) or est in ('sobre', 'dentro'):
            z = 0.9 if est != 'pared_altura' else float(a.e.get('altura_m', 1.2))
            r = col.pared_altura(sala, w, d, h, z)
            if r:
                self.aviso(f'{u["id"]} ({u["_modelo"]}) en {a.rid}: sin lugar para «{est}»; va en la pared a {z} m')
                return ('pared', r, z)
        if u['_ficha']['montaje'] == 'pared':
            # lo que va colgado nunca baja al piso: otra pared a la misma altura y, si no, más arriba (hasta el cielo raso)
            z0 = float(a.e.get('altura_m', 1.2))
            for z in [z0] + [C.redondear(z0 + k * 0.3, 2) for k in range(1, 8) if z0 + k * 0.3 + h <= sala.alto_libre - 0.05]:
                r = col.pared_altura(sala, w, d, h, z)
                if r:
                    self.aviso(f'{u["id"]} ({u["_modelo"]}) en {a.rid}: sin lugar para «{est}» junto a su puesto; va en otra pared a {z} m')
                    return ('pared', r, z)
        r = col.contra_pared(sala, w, d, h) or col.centro(sala, w, d, h) or col.centro(sala, w, d, h, permitir_paso=True)
        if r:
            self.aviso(f'{u["id"]} ({u["_modelo"]}) en {a.rid}: sin lugar para «{est}»; se ubicó contra una pared o en el centro libre')
            return ('piso', r, None)
        cx, cy = C.centroide(sala.libre)
        self.aviso(f'{u["id"]} ({u["_modelo"]}) en {a.rid}: NO CABE en el recinto; queda en el centro (revisar la regla)')
        return ('piso', (cx, cy, 0.0, None, Sala.caja(cx, cy, w, d, 0.0)), None)

    def _registrar(self, sala, a, res, f):
        u = a.unidad
        montaje, r, extra = res
        w, d, h = (u.get('dim_m') or f['dim'])
        if montaje == 'dentro':
            Cn, comp = r, extra
            cu = self.U[Cn.id]
            u.update(montaje='dentro', dentro_de=Cn.id, compartimiento=comp,
                     posicion=list(cu['posicion']) if cu['posicion'] else None, rotacion_z=cu['rotacion_z'])
            return
        cx, cy, rot, bk, caja = r
        if montaje == 'sobre':
            A = extra
            z = A.z + A.h
            u.update(montaje='sobre', apoyo=A.id, posicion=[r2(cx), r2(cy), r2(z + sala.z0)], rotacion_z=ang(rot))
            p = Pieza(u['id'], u['_modelo'], cx, cy, z, rot, w, d, h, None, 'sobre', f['contenedor'], f['comp'])
            sala.unidades.append(p)
            return
        z = 0.0 if montaje in ('piso', 'en_nucleo') else float(extra)
        u.update(montaje=montaje, posicion=[r2(cx), r2(cy), r2(z + sala.z0)], rotacion_z=ang(rot))
        if montaje in ('piso', 'en_nucleo'):
            sala.ocupar(caja, h)
        elif montaje == 'pared' and z < 0.30:
            sala.ocupar(caja, z + h)
        pz = Pieza(u['id'], u['_modelo'], cx, cy, z, rot, w, d, h, bk, montaje, f['contenedor'], f['comp'])
        l = self.L[u['linea']]
        md = self.ins.modelos.get(u['_modelo']) or {}
        pz.paciente = montaje == 'piso' and es_puesto_paciente(u['_modelo'], md.get('familia'), u.get('_variante'), l['nombre'])
        pz.estrategia = self.estrategia(a)
        sala.unidades.append(pz)

    def posiciones_puesto(self, sala, w, d, h, bandas, n, pared=None):
        """Hasta n posiciones distintas (a 0,5 m o más entre sí) para un puesto de paciente, cada una con su camino de 0,90 m
        desde una entrada hasta un costado. Si ninguna tiene camino, devuelve la primera posición sin camino."""
        out, firmas, fallidos, primero = [], [], [], None
        for cand in self.col.candidatos_cabecera(sala, w, d, h, bandas=bandas, pared=pared):
            cx, cy, rot, bk, caja, reservas, modo = cand
            if primero is None:
                primero = cand
            if any(math.hypot(cx - x, cy - y) < 0.3 and m == modo for x, y, m in fallidos):
                continue
            firma = (modo, round(rot, 3), tuple(sorted((round((r[0] + r[2]) / 2 - cx, 1), round((r[1] + r[3]) / 2 - cy, 1))
                                                      for r in reservas)))
            if any(math.hypot(cx - c[0][0], cy - c[0][1]) < 0.5 and f == firma for c, f in zip(out, firmas)):
                continue
            cam = self.camino_hasta(sala, cx, cy, w, d, rot)
            if cam is None:
                fallidos.append((cx, cy, modo))
                continue
            out.append((cand, cam))
            firmas.append(firma)
            if len(out) >= n:
                break
        if not out and primero is not None:
            out = [(primero, None)]
        return out

    # ---------------------------------------------------------------------------------------------- paso libre (I6)
    def rejilla_paso(self, sala, extra=()):
        """Rejilla de 0,10 m del recinto con lo que hay en el piso (y la huella de `extra`, un puesto que se está probando), y
        las celdas por donde cabe un paso de 0,90 m (mismo cálculo que la regla I6 de validar_inventario.py: la holgura es la
        distancia por la rejilla, con pasos ortogonales y diagonales, al centro de la celda ocupada más cercana)."""
        umbral = PASO_LIBRE_M / 2
        cache = getattr(sala, '_paso', None)
        clave = (sala.version, len(sala.unidades))
        if cache is None or cache[0] != clave:
            x0, y0, x1, y1 = C.caja(sala.libre)
            rej = C.Rejilla(x0 - 0.2, y0 - 0.2, x1 + 0.2, y1 + 0.2, 0.10)
            rej.pintar_poligono(sala.libre, 1)
            for p in sala.unidades:
                if p.montaje in ('piso', 'en_nucleo') or (p.montaje == 'pared' and p.z < 0.30):
                    rej.pintar_poligono(C.rect_girado(p.cx, p.cy, p.w, p.d, p.rot), 0)
            holgura = rej.holgura()
            trans = bytearray(1 if rej.libre[k] and holgura[k] >= umbral - 1e-9 else 0 for k in range(len(rej.libre)))
            cache = (clave, rej, holgura, trans)
            sala._paso = cache
        _, rej, holgura, trans = cache
        if not extra:
            return rej, trans
        (cx, cy, w, d, rot), = extra
        caja = Sala.caja(cx, cy, w, d, rot)
        ii = rej._rango(caja[0], caja[2], rej.x0, rej.nx)
        jj = rej._rango(caja[1], caja[3], rej.y0, rej.ny)
        if not ii or not jj:
            return rej, trans
        i0, i1, j0, j1 = ii[0], ii[-1], jj[0], jj[-1]
        c, c2 = rej.celda, rej.celda * math.sqrt(2)
        nueva = bytearray(trans)
        nx = rej.nx
        alcance = int(math.ceil(umbral / c)) + 1
        for j in range(max(0, j0 - alcance), min(rej.ny - 1, j1 + alcance) + 1):
            dy = j0 - j if j < j0 else (j - j1 if j > j1 else 0)
            for i in range(max(0, i0 - alcance), min(nx - 1, i1 + alcance) + 1):
                k = j * nx + i
                if not nueva[k]:
                    continue
                dx = i0 - i if i < i0 else (i - i1 if i > i1 else 0)
                o = c * (max(dx, dy) - min(dx, dy)) + c2 * min(dx, dy)
                if (dx == 0 and dy == 0) or o < umbral - 1e-9:
                    nueva[k] = 0
        return rej, nueva

    @staticmethod
    def semillas(sala, rej, trans) -> list:
        """Celdas de entrada: frente a cada puerta y a lo largo de cada vano abierto, a 0,5-0,8 m de la cara del muro."""
        out = []

        def una(punto, muro):
            n = C.normal_hacia(muro['a'], muro['b'], punto, sala.eje)
            if n is None:
                return
            for paso in (0.5, 0.6, 0.7, 0.8):
                dd = float(muro.get('espesor', 0.12) or 0.0) / 2 + paso
                c = rej.celda_de(punto[0] + n[0] * dd, punto[1] + n[1] * dd)
                if c and trans[c[1] * rej.nx + c[0]]:
                    out.append(c)
                    return
        for pt, muro in sala.puertas_muro:
            una(pt['centro'], muro)
        for m in sala.muros_abiertos:
            L = math.hypot(m['b'][0] - m['a'][0], m['b'][1] - m['a'][1])
            for s in pasos(0.3, L - 0.3, 0.2):
                una((m['a'][0] + (m['b'][0] - m['a'][0]) * s / L, m['a'][1] + (m['b'][1] - m['a'][1]) * s / L), m)
        return out

    @staticmethod
    def al_costado(rej, cx, cy, w, d, rot):
        """Celdas desde las que se atiende el puesto: a un costado (largo), a no más de 0,70 m de él (como la regla I6)."""
        umbral = PASO_LIBRE_M / 2
        out = set()
        R = max(w, d) / 2 + umbral + 0.3
        c = rej.celda
        i0, i1 = max(0, int((cx - R - rej.x0) / c)), min(rej.nx - 1, int((cx + R - rej.x0) / c) + 1)
        j0, j1 = max(0, int((cy - R - rej.y0) / c)), min(rej.ny - 1, int((cy + R - rej.y0) / c) + 1)
        co, si = math.cos(rot), math.sin(rot)
        for j in range(j0, j1 + 1):
            dy = rej.y0 + (j + 0.5) * c - cy
            for i in range(i0, i1 + 1):
                dx = rej.x0 + (i + 0.5) * c - cx
                lx, ly = dx * co + dy * si, -dx * si + dy * co
                if abs(ly) <= d / 2 and w / 2 < abs(lx) <= w / 2 + umbral + 0.25:
                    out.add(j * rej.nx + i)
        return out

    def camino_hasta(self, sala, cx, cy, w, d, rot):
        """Centros de las celdas de un camino de 0,90 m desde una entrada hasta un costado del puesto (cx, cy, w, d, rot),
        con lo que ya está en el piso; None si no hay."""
        # prueba rápida: si sin el puesto ya no se llega a su costado, con el puesto tampoco
        rej0, trans0 = self.rejilla_paso(sala)
        cache = getattr(sala, '_dist0', None)
        if cache is None or cache[0] is not trans0:
            sem0 = self.semillas(sala, rej0, trans0)
            cache = (trans0, rej0.distancias(sem0, trans0) if sem0 else None)
            sala._dist0 = cache
        if cache[1] is None or all(math.isinf(cache[1][k]) or not trans0[k]
                                   for k in self.al_costado(rej0, cx, cy, w, d, rot)):
            return None
        rej, trans = self.rejilla_paso(sala, extra=[(cx, cy, w, d, rot)])
        sem = self.semillas(sala, rej, trans)
        if not sem:
            return None
        dist = rej.distancias(sem, trans)
        objetivo = [k for k in self.al_costado(rej, cx, cy, w, d, rot) if not math.isinf(dist[k])]
        if not objetivo:
            return None
        k = min(objetivo, key=lambda q: (dist[q], q))
        nx = rej.nx
        camino = [rej.centro(k % nx, k // nx)]
        while dist[k] > 1e-9:
            i, j = k % nx, k // nx
            mejor = None
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    a, b = i + di, j + dj
                    if (di or dj) and 0 <= a < nx and 0 <= b < rej.ny and dist[b * nx + a] < dist[k] - 1e-9:
                        if mejor is None or dist[b * nx + a] < dist[mejor]:
                            mejor = b * nx + a
            if mejor is None:
                break
            k = mejor
            camino.append(rej.centro(k % nx, k // nx))
        return camino

    def fallas_paso(self, sala) -> list:
        """Puestos de paciente sin paso libre de 0,90 m desde una entrada hasta uno de sus costados (mismo cálculo que I6)."""
        pacientes = [p for p in sala.unidades if p.paciente]
        if not pacientes:
            return []
        rej, trans = self.rejilla_paso(sala)
        semillas = self.semillas(sala, rej, trans)
        if not semillas:
            return list(pacientes)
        dist = rej.distancias(semillas, trans)
        fallan = []
        for p in pacientes:
            if not any(not math.isinf(dist[k]) for k in self.al_costado(rej, p.cx, p.cy, p.w, p.d, p.rot)):
                fallan.append(p)
        return fallan

    def reparar_paso(self, sala):
        """Si un puesto de paciente queda sin paso libre, mueve a otra pared las piezas sueltas que lo estorban."""
        fallan = self.fallas_paso(sala)
        if not fallan:
            return
        con_hijos = {u.get('apoyo') for u in self.unidades if u.get('recinto') == sala.id and u.get('apoyo')}
        presupuesto = 40                       # pruebas de paso como máximo (cada una recalcula la rejilla del recinto)
        for _ in range(6):
            if not fallan:
                return
            movibles = [p for p in sala.unidades if p.montaje == 'piso' and p.modelo in MOVIBLES and not p.paciente and p.id not in con_hijos]
            if not movibles:
                break

            def cerca(p):
                return min(math.hypot(p.cx - q.cx, p.cy - q.cy) for q in fallan)
            mejoro = False
            for p in sorted(movibles, key=lambda p: (round(cerca(p), 2), p.id)):
                viejo = (p.cx, p.cy, p.rot, p.borde)
                sala.rehacer_ocupacion(excluir=p)
                cands = []
                for b in sala.bordes_por(None):
                    for pref in ('inicio', 'centro', 'final'):
                        r = self.col.contra_pared(sala, p.w, p.d, p.h, compartidos=[b['k']], preferir=pref, solo=True)
                        if r is not None and all(abs(r[0] - c[0]) > 0.3 or abs(r[1] - c[1]) > 0.3 for c in cands):
                            cands.append(r)
                for r in cands:
                    if presupuesto <= 0:
                        break
                    presupuesto -= 1
                    p.cx, p.cy, p.rot, p.borde = r[0], r[1], r[2], r[3]
                    sala.rehacer_ocupacion()
                    nuevos = self.fallas_paso(sala)
                    if len(nuevos) < len(fallan):
                        fallan = nuevos
                        mejoro = True
                        u = self.U[p.id]
                        u['posicion'] = [r2(p.cx), r2(p.cy), r2(sala.z0)]
                        u['rotacion_z'] = ang(p.rot)
                        for h in self.unidades:
                            if h.get('dentro_de') == p.id:
                                h['posicion'] = list(u['posicion'])
                                h['rotacion_z'] = u['rotacion_z']
                        break
                    p.cx, p.cy, p.rot, p.borde = viejo
                    sala.rehacer_ocupacion(excluir=p)
                else:
                    p.cx, p.cy, p.rot, p.borde = viejo
                sala.rehacer_ocupacion()
                if not fallan:
                    return
            if not mejoro:
                break
        for p in fallan:
            self.aviso(f'{p.id} ({p.modelo}) en {sala.id}: sin paso libre de 0,9 m hasta un costado (revisar la regla o la planta)')

    def bordes_compartidos(self, sala, ref) -> list:
        fila = C.resolver_ambiente(ref, self.ins.ambientes)
        ks = []
        for rid in self.recintos_de(fila):
            if rid not in self.recintos:
                continue
            for p, q in C.bordes_comunes(sala.eje, C.orientar_antihorario(self.recintos[rid]['poligono'])):
                for b in sala.bordes:
                    if C.es_horizontal(p, q) == (abs(b['u'][1]) < 0.5):
                        dist = abs((p[0] - b['a'][0]) * b['nin'][0] + (p[1] - b['a'][1]) * b['nin'][1])
                        if dist < 0.3 and b['k'] not in ks:
                            ks.append(b['k'])
        return ks

    def relacionar_sin_geometria(self, a, est):
        """Sin planta: recinto y montaje por la estrategia; apoyo y contenedor por el modelo, sin posición."""
        u = a.unidad
        e = a.e
        montaje = {'pared_altura': 'pared', 'pared_fija': 'pared', 'cielo': 'cielo', 'sobre': 'sobre', 'dentro': 'dentro',
                   'en_nucleo': 'en_nucleo'}.get(est, 'piso')
        u['montaje'] = montaje
        if est in ('sobre', 'dentro'):
            modelos = e.get('sobre') if est == 'sobre' else e.get('dentro')
            cands = [x for m in (modelos or []) for x in self.unidades
                     if x['recinto'] == u['recinto'] and x['_modelo'] == m and x['id'] != u['id'] and x.get('montaje') != 'dentro'
                     and (est == 'sobre' or x['_ficha']['contenedor'])]
            if cands:
                cont = min(cands, key=lambda x: (x.get('_n', 0), cands.index(x)))
                cont['_n'] = cont.get('_n', 0) + 1
                if est == 'sobre':
                    u['apoyo'] = cont['id']
                else:
                    u['dentro_de'] = cont['id']
                    comps = cont['_ficha']['comp']
                    comp = e.get('compartimiento')
                    u['compartimiento'] = comp if comp in comps else (comps[(cont['_n'] - 1) % len(comps)] if comps else None)
            else:
                alt = (e.get('alternativa') or {}).get('estrategia')
                u['montaje'] = 'pared'
                if not alt:
                    self.aviso(f'{u["id"]} ({u["_modelo"]}) en {u["recinto"]}: sin {"apoyo" if est == "sobre" else "contenedor"} en el recinto; va en la pared')

    # ---------------------------------------------------------------------------------------------- componentes y contenido
    def crear_componentes(self):
        """Unidades componentes (4.4 y 4.7.3): equipos biomédicos de los kits y componentes declarados en dotacion.json. Se
        crean antes de ubicar; las de piso se ubican con su recinto y las demás van dentro de su unidad madre."""
        self.comps = []
        for u in [x for x in self.unidades]:
            l = self.L[u['linea']]
            items = []
            for c in l.get('componentes') or []:
                if isinstance(c, dict):
                    items.append({'nombre': c['nombre'], 'clase_riesgo': c.get('clase'), 'nota_clase': c.get('regla'),
                                  'modelo3d': 'estuche', 'fuente': 'componentes de la línea en dotacion.json (revisión del Decreto 4725)'})
            p = self.ins.plantillas.get(l.get('plantilla_contenido')) or {}
            for it in p.get('items', []):
                if it.get('tipo') == 'equipo_biomedico':
                    for _ in range(int(it.get('cantidad') or 1)):
                        items.append(it)
            for it in (self.reglas.get(l['id']) or {}).get('componentes_fisicos', []) or []:
                for _ in range(int(it.get('cantidad') or 1)):
                    items.append(it)
            for n, it in enumerate(items, start=1):
                self.comps.append(self.componente(u, l, n, it))

    def componente(self, madre, l, n, it):
        vig = clase_vigente(it.get('clase_riesgo'))
        cid = C.id_componente(madre['id'], n)
        modelo = it.get('modelo3d') or 'equipo_mesa'
        f = self.ficha_modelo(modelo)
        reg = registro_invima(vig, 'observacion', 'si' if vig in ('I', 'IIa', 'IIb', 'III') else 'por_confirmar')
        mant = dict(it.get('mantenimiento') or {})
        mant.setdefault('personal_inscrito_invima', vig in ('IIb', 'III'))
        mant.setdefault('calibracion', any(p in it['nombre'].lower() for p in CALIBRA))
        mant.setdefault('anual_pct', None)
        u = {'id': cid, 'linea': l['id'], 'k': madre['k'], 'componente_de': madre['id'], 'nombre': it['nombre'], 'modelo3d': modelo,
             'piso': madre['piso'], 'nivel': madre['nivel'], 'recinto': madre['recinto'], 'ambiente': madre['ambiente'],
             'posicion': None, 'rotacion_z': None, 'montaje': 'dentro', 'apoyo': None, 'dentro_de': None, 'compartimiento': None,
             'riesgo_sismico': None, 'contenido': None,
             'clase_riesgo': {'repo': it.get('clase_riesgo'), 'vigente': vig, 'estado': 'observacion', 'regla': it.get('nota_clase'),
                              'fuente': it.get('fuente') or 'revisión del Decreto 4725 (los kits se inventarían por componente)'},
             'registro_invima': reg, 'mantenimiento': mant, 'precio_unitario_cop_2026': 0,
             'campos_al_comprar': {c: None for c in CAMPOS_AL_COMPRAR}, 'estado': madre['estado'],
             '_modelo': modelo, '_ficha': f, '_colocado': False}
        if madre.get('ubicacion'):
            u['ubicacion'] = madre['ubicacion']
        self.unidades.append(u)
        self.U[cid] = u
        return u

    def colocar_componente(self, u, sala):
        """Componente de piso (la báscula de un kit): contra una pared libre de su recinto; si no cabe, o si no es de piso,
        dentro de su unidad madre."""
        u['_colocado'] = True
        madre = self.U[u['componente_de']]
        f, mf = u['_ficha'], madre['_ficha']
        cid, modelo = u['id'], u['_modelo']
        if f['montaje'] == 'piso' and sala is not None:
            r = self.col.contra_pared(sala, *f['dim'])
            if r:
                cx, cy, rot, bk, caja = r
                sala.ocupar(caja, f['dim'][2])
                u.update(montaje='piso', posicion=[r2(cx), r2(cy), r2(sala.z0)], rotacion_z=ang(rot))
                sala.unidades.append(Pieza(cid, modelo, cx, cy, 0.0, rot, *f['dim'], bk, 'piso'))
                return
            self.aviso(f'{cid} ({modelo}): no cabe en el piso de {madre["recinto"]}; queda dentro de su kit')
        elif f['montaje'] == 'piso' and sala is None and madre['recinto'] and self.ins.plantas is None:
            u['montaje'] = 'piso'
            return
        if mf['contenedor']:
            u.update(montaje='dentro', dentro_de=madre['id'], compartimiento=mf['comp'][0] if mf['comp'] else None,
                     posicion=list(madre['posicion']) if madre['posicion'] else None, rotacion_z=madre['rotacion_z'])
        else:
            u.update(montaje='dentro', dentro_de=madre.get('dentro_de'), compartimiento=madre.get('compartimiento'),
                     posicion=list(madre['posicion']) if madre['posicion'] else None, rotacion_z=madre['rotacion_z'])

    def contenidos(self):
        dentro = {}
        for u in self.unidades:
            if u.get('dentro_de'):
                dentro.setdefault(u['dentro_de'], []).append(u['id'])
        for u in self.unidades:
            if u.get('componente_de'):
                continue
            p = self.L[u['linea']].get('plantilla_contenido')
            ids = sorted(dentro.get(u['id'], []))
            if p or ids:
                u['contenido'] = {'plantilla': p, 'unidades': ids}

    def riesgo(self, u):
        f = u['_ficha']
        dim = u.get('dim_m') or f['dim']
        anc = {'pared': 'pared', 'cielo': 'cielo', 'sobre': 'sobre', 'dentro': 'dentro', 'en_nucleo': 'en_nucleo'}.get(u.get('montaje'), f['anclaje'])
        if u.get('montaje') in (None,):
            u['riesgo_sismico'] = None
            return
        b = f['b'] if f['b'] is not None and not u.get('dim_m') else round(min(dim[0], dim[1]) / 2, 3)
        u['riesgo_sismico'] = {'anclaje': anc, 'masa_kg': f['masa'], 'h_cg_m': f['hcg'], 'mu': f['mu'], 'b_m': b,
                               'bx_m': r2(dim[0] / 2), 'by_m': r2(dim[1] / 2)}

    # ---------------------------------------------------------------------------------------------- salida: unidades limpias
    def unidades_salida(self) -> list[dict]:
        out = []
        for u in self.unidades:
            d = {}
            for k, v in u.items():
                if k.startswith('_'):
                    continue
                d[k] = v
                if k == 'recinto' and u.get('_sub'):
                    d['subrecinto'] = u['_sub']
            if d.get('rotacion_z') is None and d.get('posicion') is not None:
                d['rotacion_z'] = 0.0
            out.append(d)
        return out


# ======================================================================================================================
# Matriz de cumplimiento en dotación e infraestructura (4.8)
# ======================================================================================================================
DE_INVESTIGACION = {'cubierto': 'cumple', 'parcial': 'parcial', 'falta': 'falta'}
VIGENTES = ('en_dotacion', 'infraestructura', 'contexto')


class Matriz:
    def __init__(self, gen: Generador):
        self.g = gen
        self.ins = gen.ins
        self.base = {}                      # línea → unidades base (sin componentes)
        for u in gen.unidades:
            if not u.get('componente_de'):
                self.base.setdefault(u['linea'], []).append(u)
        self.infra = {}                      # elemento → líneas de infraestructura
        for l in gen.lineas:
            if l['origen'] == 'infraestructura':
                self.infra.setdefault(l.get('elemento'), []).append(l['id'])
        self.cierre_de = {}                  # exigencia → líneas del cierre que la citan
        for l in gen.lineas:
            if l['origen'] == 'cierre_brechas':
                for e in l.get('exigencias', []):
                    self.cierre_de.setdefault(e['id'], []).append(l['id'])
        self.sin_planta = self.ins.plantas is None

    # ------------------------------------------------------------------------------------------------ conteos
    def unidades(self, lineas, recintos=None, esc='dotacion_actual'):
        out = []
        for lid in lineas:
            for u in self.base.get(lid, []):
                if u['estado'] not in VIGENTES and not (esc == 'con_cierre_de_brechas' and u['estado'] == 'cierre_brechas_propuesto'):
                    continue
                if recintos is not None and u['recinto'] not in recintos:
                    continue
                out.append(u)
        return out

    def lineas_infra(self, elementos):
        out = []
        for el in elementos or []:
            if el not in (self.ins.reglas.get('infraestructura') or {}).get('elementos', {}):
                raise ErrorGenerador(f'elemento de infraestructura desconocido en una regla de exigencia: {el!r}')
            out += self.infra.get(el, [])
        return out

    def grupos(self, x, regla):
        """[(líneas, n, grupo)] que cuenta la regla: los «grupos» escritos a mano o, si no hay, uno por ítem (total_servicio) o
        uno con todos los ítems (por recinto, puesto o piso). Las líneas del cierre de brechas que citan la exigencia se agregan
        como grupos propios: en la dotación actual cuentan cero (por eso la exigencia queda parcial) y con el cierre, sus
        unidades. Un grupo escrito a mano puede traer sus propios «puestos» (por_puesto) o «ambientes» (por_recinto)."""
        tipo = regla.get('tipo')
        n0 = int(regla.get('n', regla.get('n_por_recinto', 1)) or 1)
        if regla.get('grupos'):
            gs = [([i['linea'] for i in g.get('lineas', []) if i.get('linea')] + self.lineas_infra(g.get('infra')), int(g.get('n', n0)), g)
                  for g in regla['grupos']]
            return gs
        items = [i['linea'] for i in regla.get('items', []) or [] if i.get('linea')]
        if not items and tipo == 'total_servicio':
            items = [c['linea'] for c in x.get('cubre_con', []) if c.get('linea')]
        infra = self.lineas_infra(regla.get('infra'))
        extra = [lid for lid in self.cierre_de.get(x['id'], []) if lid not in items]
        if tipo == 'total_servicio':
            gs = [([lid], n0, {}) for lid in items] + ([(infra, n0, {})] if infra else [])
        else:
            gs = [(items + infra, n0, {})] if (items or infra) else []
        return gs + [([lid], n0, {}) for lid in extra]

    def recintos(self, x):
        out = []
        for a in x.get('ambientes', []) or []:
            out += self.g.recintos_de(a['fila'])
        return out

    def recintos_de_ambientes(self, ambientes):
        out = []
        for a in ambientes or []:
            fila = C.resolver_ambiente({k: v for k, v in a.items() if k in ('fila', 'nombre', 'servicio_programa')}, self.ins.ambientes)
            out += self.g.recintos_de(fila)
        return out

    def recintos_del_servicio(self, x):
        """Recintos de los servicios del programa de la exigencia (y los de sus ambientes): donde cuenta total_servicio.
        None si la exigencia no tiene servicio (filas de todos los servicios)."""
        srv = set(x.get('servicios_programa') or [])
        if not srv:
            return None
        out = set(self.recintos(x))
        if self.sin_planta:
            for f, a in enumerate(self.ins.ambientes):
                if a.get('servicio') in srv:
                    out.update(self.g.recintos_de(f))
        else:
            out.update(rid for rid, r in self.g.recintos.items() if r.get('servicio_programa') in srv)
        return out

    # ------------------------------------------------------------------------------------------------ una exigencia
    def evaluar(self, x, esc):
        """(estado, requerido, encontrado, unidades, nota) de una exigencia en un escenario, sin los cortes de fecha."""
        regla = x.get('regla') or {'tipo': 'sin_regla'}
        tipo = regla.get('tipo')
        if x.get('referencia'):
            return 'no_aplica', None, None, [], 'exigencia por analogía: se muestra como referencia'
        if tipo == 'documental':
            return 'documento_pendiente', None, None, [], 'exigencia documental: la elabora la E.S.E.'
        gs = self.grupos(x, regla)
        inv = DE_INVESTIGACION.get(x.get('estado_investigacion'), 'falta')
        if tipo == 'sin_regla' or (tipo in ('total_servicio', 'por_recinto', 'por_puesto', 'por_piso') and not gs):
            extra = self.cierre_de.get(x['id'], [])
            if extra and esc == 'con_cierre_de_brechas':
                us = self.unidades(extra, esc=esc)
                hechas = {u['linea'] for u in us}
                est = 'cumple' if all(l in hechas for l in extra) else inv
                return est, len(extra), len(hechas), [u['id'] for u in us], 'cubierta por el cierre de brechas'
            return inv, None, None, [], 'estado tomado de la investigación (sin regla automática)'
        recs = self.recintos(x)
        if tipo == 'total_servicio':
            # cada ítem cuenta en los recintos del servicio de la exigencia; las líneas compartidas entre servicios (centrales,
            # equipos de piso) cuentan donde estén solo si la regla las declara con su motivo
            compartidas = {c.get('linea') for c in regla.get('compartidas', []) or []}
            del_servicio = self.recintos_del_servicio(x)
            req, enc, us = 0, 0, []
            for lineas, n, _g in gs:
                if any(self.g.L[l]['origen'] == 'infraestructura' for l in lineas):
                    donde = recs or (sorted(del_servicio) if del_servicio is not None else None)
                    ug = self.unidades(lineas, donde, esc)
                else:
                    ug = [u for u in self.unidades(lineas, None, esc)
                          if del_servicio is None or u['linea'] in compartidas or u['recinto'] in del_servicio]
                req += n
                enc += min(len(ug), n)
                us += ug
            return self.cerrar(regla, self.estado(req, enc), req, enc, [u['id'] for u in us], None)
        if tipo in ('por_recinto', 'existe_ambiente'):
            if tipo == 'existe_ambiente' and not gs:
                faltan = [r for r in recs if not self.sin_planta and r not in self.g.recintos]
                req = len(recs)
                return ('falta' if faltan or not recs else 'cumple'), req, req - len(faltan), [], \
                       ('se verifica contra el programa (sin planta)' if self.sin_planta else 'se verifica contra la planta')
            req, enc, us = 0, 0, []
            por_rec = {}
            for lineas, n, g in gs:
                donde = self.recintos_de_ambientes(g['ambientes']) if g.get('ambientes') else recs
                for rid in donde:
                    ug = self.unidades(lineas, [rid], esc)
                    req += n
                    enc += min(len(ug), n)
                    us += ug
                    pr = por_rec.setdefault(rid, [0, 0])
                    pr[0] += n
                    pr[1] += min(len(ug), n)
            return self.cerrar(regla, self.estado(req, enc), req, enc, [u['id'] for u in us], None, por_rec)
        if tipo == 'por_puesto':
            npp = int(regla.get('n_por_puesto', 1) or 1)
            req, enc, us = 0, 0, []
            por_rec = {}
            for lineas, n, g in gs:
                for p in (g.get('puestos') or regla.get('puestos', [])):
                    fila = C.resolver_ambiente({k: v for k, v in p.items() if k in ('fila', 'nombre', 'servicio_programa')}, self.ins.ambientes)
                    for rid in self.g.recintos_de(fila):
                        ug = self.unidades(lineas, [rid], esc)
                        q = p['n'] * npp * (n if regla.get('grupos') else 1)
                        req += q
                        enc += min(len(ug), q)
                        us += ug
                        pr = por_rec.setdefault(rid, [0, 0])
                        pr[0] += q
                        pr[1] += min(len(ug), q)
            return self.cerrar(regla, self.estado(req, enc), req, enc, [u['id'] for u in us], None, por_rec)
        if tipo == 'por_piso':
            niveles = sorted({self.g.datos_recinto(r)[0] for r in recs})
            req, enc, us = 0, 0, []
            for nv in niveles:
                for lineas, n, _g in gs:
                    ug = [u for u in self.unidades(lineas, None, esc) if u.get('nivel') == nv]
                    req += n
                    enc += min(len(ug), n)
                    us += ug
            return self.cerrar(regla, self.estado(req, enc), req, enc, [u['id'] for u in us], None)
        if tipo == 'contenido':
            cont = (regla.get('dentro_de') or {}).get('linea')
            contenedores = {u['id'] for u in self.unidades([cont], esc=esc)}
            req, enc, us = 0, 0, []
            n = int(regla.get('n', 1) or 1)
            for it in regla.get('items', []) or []:
                req += n
                if it.get('linea'):
                    ug = [u for u in self.unidades([it['linea']], esc=esc)
                          if u.get('dentro_de') in contenedores or u.get('apoyo') in contenedores]
                    enc += min(len(ug), n)
                    us += ug
                else:
                    p = self.ins.plantillas.get((self.g.L.get(cont) or {}).get('plantilla_contenido')) or {}
                    if contenedores and any(it['nombre'].lower() in i['nombre'].lower() for i in p.get('items', [])):
                        enc += n
            return self.estado(req, enc), req, enc, [u['id'] for u in us], None
        if tipo == 'area_libre_por_puesto':
            if self.sin_planta:
                return inv, None, None, [], 'área libre por puesto: se calcula con la planta (sin planta, estado de la investigación)'
            req, enc = 0, 0
            for p in regla.get('puestos', []):
                fila = C.resolver_ambiente({k: v for k, v in p.items() if k in ('fila', 'nombre', 'servicio_programa')}, self.ins.ambientes)
                for rid in self.g.recintos_de(fila):
                    req += 1
                    area = (self.g.recintos.get(rid) or {}).get('area_libre_m2') or 0.0
                    if area / max(1, p['n']) >= float(regla.get('m2', 0)):
                        enc += 1
            return self.estado(req, enc), req, enc, [], 'área libre del recinto entre sus puestos (incluye baño y guardarropa: por confirmar)'
        return inv, None, None, [], 'estado tomado de la investigación'

    @staticmethod
    def cerrar(regla, est, req, enc, us, nota, por_rec=None):
        """Resultado de una regla física. Si la regla trae además una parte documental (un certificado firmado, por ejemplo),
        lo físico completo no basta: queda documento_pendiente con la nota del documento que falta. `por_rec` lleva el estado
        de cada recinto (lo encontrado en él) para el color del recinto."""
        doc = regla.get('parte_documental')
        if doc and est == 'cumple':
            est, nota = 'documento_pendiente', f'Los equipos están; falta el documento: {doc}'
        elif doc:
            nota = f'Además de los equipos falta el documento: {doc}'
        res = (est, req, enc, us, nota)
        if por_rec is not None:
            return res + ({rid: Matriz.estado(q, e) for rid, (q, e) in por_rec.items()},)
        return res

    @staticmethod
    def estado(req, enc):
        if req and enc >= req:
            return 'cumple'
        if enc and enc > 0:
            return 'parcial'
        return 'falta'

    def por_corte(self, x, corte, est):
        f = corte['fecha']
        if x.get('vigencia_hasta') and x['vigencia_hasta'] < f:
            return 'no_aplica'
        if x.get('vigencia_desde') and x['vigencia_desde'] > f:
            return 'no_aplica'
        return est

    def diferencia(self, x, propio, nota, req, enc):
        manual = x.get('diferencia')
        if manual:
            return manual
        inv = x.get('estado_investigacion')
        tipo = (x.get('regla') or {}).get('tipo')
        com = (x.get('comentario') or '').strip()
        base = f'El cruce con este inventario da «{propio}» y la revisión de la Res. 3100 dio «{inv}»'
        if tipo == 'documental':
            return f'{base}: es una exigencia documental y queda como documento pendiente hasta que la E.S.E. lo elabore.'
        if tipo == 'total_servicio':
            q = f' ({enc} de {req} ítems con al menos una unidad)' if req else ''
            return (f'{base}: la regla verifica que cada ítem que la cubre exista en la torre{q}; la revisión también miró cantidad, '
                    f'especificación o ambiente' + (f': «{com}»' if com else '.'))
        if req is not None:
            return f'{base}: se encontraron {enc} de {req} unidades requeridas' + (f'; la revisión dice: «{com}»' if com else '.')
        return f'{base}' + (f': {nota}.' if nota else '.')

    # ------------------------------------------------------------------------------------------------ matriz
    def construir(self) -> dict:
        servicios_meta = self.ins.exig_doc.get('servicios_matriz') or {}
        entradas = {}
        por_servicio = {}
        todos = []
        for x in self.ins.exig:
            ev = {esc: self.evaluar(x, esc) for esc in ESCENARIOS}
            estado = {c['id']: {esc: self.por_corte(x, c, ev[esc][0]) for esc in ESCENARIOS} for c in CORTES}
            propio = estado['corte_2026']['dotacion_actual']
            inv = DE_INVESTIGACION.get(x.get('estado_investigacion'))
            dif = None
            if inv and propio != inv and propio != 'no_aplica':
                dif = self.diferencia(x, propio, ev['dotacion_actual'][4], ev['dotacion_actual'][1], ev['dotacion_actual'][2])
            texto = x.get('texto')
            corto = None
            if x.get('texto_disponible') and texto:
                corto = texto if len(texto) <= 180 else texto[:177].rstrip() + '…'
            recs = self.recintos(x)
            uni = list(dict.fromkeys(ev['dotacion_actual'][3] + ev['con_cierre_de_brechas'][3]))
            d = {'id': x['id'], 'estandar': x.get('estandar'), 'numeral': x.get('numeral'), 'numeral_confirmado': x.get('numeral_confirmado'),
                 'texto_corto': corto, 'que_exige': x.get('que_exige'), 'texto_disponible': x.get('texto_disponible'),
                 'verificacion_texto': x.get('verificacion_texto'), 'exigible': x.get('exigible'),
                 'ambientes': [{'fila': a['fila'], 'nombre': a['nombre']} for a in x.get('ambientes', []) or []], 'recintos': recs,
                 'regla': x.get('regla'), 'requerido': ev['dotacion_actual'][1],
                 'encontrado': {esc: ev[esc][2] for esc in ESCENARIOS}, 'unidades': uni,
                 'cierre_de_brechas': self.cierre_de.get(x['id'], []),
                 'estado': estado, 'nota_estado': ev['dotacion_actual'][4], 'estado_investigacion': x.get('estado_investigacion'),
                 'diferencia': dif, 'referencia': bool(x.get('referencia')), 'vigencia_hasta': x.get('vigencia_hasta'),
                 'vigencia_desde': x.get('vigencia_desde'), 'misma_que': x.get('misma_que'), 'fuente_url': x.get('fuente_url')}
            pr = ev['dotacion_actual'][5] if len(ev['dotacion_actual']) > 5 else None
            if pr:
                # estado de cada recinto con lo que se encontró en él (color del recinto en el recorrido)
                d['estado_por_recinto'] = {rid: {c['id']: self.por_corte(x, c, st) for c in CORTES} for rid, st in sorted(pr.items())}
            entradas[x['id']] = d
            if x['id'].startswith('EX-TOD-'):
                todos.append(d)
                continue
            srv = x.get('servicio_matriz') or x.get('servicio')
            if srv == 'imagenes':
                filas = {a['fila'] for a in x.get('ambientes', []) or []}
                srv = 'imagenes_745' if filas and filas <= FILAS_745 else 'imagenes_744'
                if srv == 'imagenes_744' and filas & FILAS_745:
                    por_servicio.setdefault('imagenes_745', {'propias': [], 'compartidas': []})['compartidas'].append(x['id'])
            por_servicio.setdefault(srv, {'propias': [], 'compartidas': []})['propias'].append(d)
        servicios = []
        orden = list(servicios_meta) + sorted(s for s in por_servicio if s not in servicios_meta)
        for sid in orden:
            meta = servicios_meta.get(sid, {'nombre': sid, 'habilitable': 'no', 'marco': 'Servicio sin ficha en reglas_exigencias.json'})
            ps = por_servicio.get(sid, {'propias': [], 'compartidas': []})
            s = {'id': sid}
            s.update(meta)
            if meta.get('habilitable') == 'si':
                s['resumen'] = self.resumen(ps['propias'])
            s['exigencias'] = ps['propias']
            if ps['compartidas']:
                s['exigencias_compartidas'] = ps['compartidas']
            servicios.append(s)
        por_recinto = {}
        for d in entradas.values():
            for rid in d['recintos']:
                por_recinto.setdefault(rid, []).append(d)
        recintos_out = {}
        for rid in sorted(por_recinto):
            es = por_recinto[rid]
            est = {}
            for c in CORTES:
                vals = [(e.get('estado_por_recinto') or {}).get(rid, {}).get(c['id']) or e['estado'][c['id']]['dotacion_actual'] for e in es
                        if e['exigible'] == 'si' and not e['referencia'] and not e['id'].startswith('EX-TOD-')]
                est[c['id']] = 'falta' if 'falta' in vals else 'parcial' if 'parcial' in vals else 'cumple'
            recintos_out[rid] = {'estado': est, 'exigencias': [e['id'] for e in es],
                                 'por_confirmar': sum(1 for e in es if e['exigible'] == 'por_confirmar')}
        resumen_faltantes = self.faltantes(servicios)
        return {'servicios': servicios,
                'todos_los_servicios': {'exigencias': [d['id'] for d in todos], 'detalle': todos,
                                        'nota': 'Se muestran una vez; no suman en los resúmenes por servicio'},
                'faltantes_por_servicio': resumen_faltantes,
                'por_recinto': recintos_out}

    # ------------------------------------------------------------------------------------------------ faltantes y costo del cierre
    SERVICIO_MATRIZ = {'expansion_emergencias': 'sala_expansion', 'imagenes': 'imagenes_744'}

    def faltantes(self, servicios) -> dict:
        """Por servicio: las exigencias que hoy faltan o están a medias (en cualquiera de los dos cortes), con los ítems del
        cierre de brechas que las cubren, y el costo del cierre del servicio (cada ítem del cierre cuenta en un solo servicio)."""
        cierre = [l for l in self.g.lineas if l['origen'] == 'cierre_brechas']
        de_servicio = {}
        for l in cierre:
            de_servicio.setdefault(self.SERVICIO_MATRIZ.get(l['servicio'], l['servicio']), []).append(l)
        malos = ('falta', 'parcial')
        tabla = []
        for s in servicios:
            sid = s['id']
            filas = []
            for e in s['exigencias']:
                est = e['estado']
                if est['corte_2026']['dotacion_actual'] in malos or est['apertura']['dotacion_actual'] in malos:
                    filas.append({'id': e['id'], 'exigible': e['exigible'], 'estandar': e['estandar'],
                                  'que_exige': e.get('que_exige') or e.get('texto_corto'),
                                  'estado': {c: {'dotacion_actual': est[c]['dotacion_actual'], 'con_cierre_de_brechas': est[c]['con_cierre_de_brechas']}
                                             for c in ('corte_2026', 'apertura')},
                                  'requerido': e['requerido'], 'encontrado': e['encontrado'], 'cierre_de_brechas': e['cierre_de_brechas'],
                                  'queda_sin_cubrir': est['apertura']['con_cierre_de_brechas'] in malos})
            items = []
            for l in de_servicio.get(sid, []):
                pu = l.get('precio_unitario_cop_2026')
                items.append({'linea': l['id'], 'nombre': l['nombre'], 'cantidad': l['cantidad'], 'precio_unitario_cop_2026': pu,
                              'total_cop_2026': None if pu is None else pu * l['cantidad'], 'tipo_precio': l.get('tipo_precio'),
                              'proyecto': l.get('proyecto'), 'naturaleza': l.get('naturaleza'), 'prioridad': l.get('prioridad'),
                              'exigencias': [x['id'] for x in l.get('exigencias', [])]})
            inv = sum(i['total_cop_2026'] or 0 for i in items if i['naturaleza'] == 'inversion')
            op = sum(i['total_cop_2026'] or 0 for i in items if i['naturaleza'] == 'operacion_anual')
            pp = {}
            for i in items:
                if i['naturaleza'] == 'inversion' and i['proyecto']:
                    pp[i['proyecto']] = pp.get(i['proyecto'], 0) + (i['total_cop_2026'] or 0)
            costo = {'items': len(items), 'inversion_con_precio_cop_2026': inv, 'operacion_anual_cop_2026': op,
                     'items_sin_precio': sum(1 for i in items if i['precio_unitario_cop_2026'] is None), 'inversion_por_proyecto': dict(sorted(pp.items())),
                     'tipo': 'calculo_propio', 'nota': 'No suma los ítems por cotizar; la operación anual va aparte de la inversión.'}
            s['faltantes'] = {'exigencias': filas, 'cierre_de_brechas': items, 'costo_cierre': costo,
                              'nota': ('Exigencias que hoy faltan o están a medias (estado «falta» o «parcial» en la dotación actual, '
                                       'en el corte de 2026 o en la apertura) y los ítems del cierre de brechas del servicio.')}
            tabla.append({'servicio': sid, 'nombre': s.get('nombre'), 'habilitable': s.get('habilitable'),
                          'exigibles_que_faltan': sum(1 for f in filas if f['exigible'] == 'si'),
                          'por_confirmar_que_faltan': sum(1 for f in filas if f['exigible'] != 'si'),
                          'sin_cubrir_con_el_cierre': sum(1 for f in filas if f['queda_sin_cubrir']),
                          'items_cierre': costo['items'], 'inversion_con_precio_cop_2026': inv, 'operacion_anual_cop_2026': op,
                          'items_sin_precio': costo['items_sin_precio']})
        sin_servicio = [l['id'] for l in cierre if self.SERVICIO_MATRIZ.get(l['servicio'], l['servicio']) not in {s['id'] for s in servicios}]
        if sin_servicio:
            raise ErrorGenerador(f'ítems del cierre sin servicio en la matriz: {sin_servicio}')
        return {'tabla': tabla,
                'total': {'items_cierre': len(cierre),
                          'inversion_con_precio_cop_2026': sum(t['inversion_con_precio_cop_2026'] for t in tabla),
                          'operacion_anual_cop_2026': sum(t['operacion_anual_cop_2026'] for t in tabla),
                          'items_sin_precio': sum(t['items_sin_precio'] for t in tabla)},
                'tipo': 'calculo_propio',
                'nota': ('Cada ítem del cierre de brechas cuenta en el servicio que lo pide (la sala de expansión es «expansion_emergencias» '
                         'en la dotación; imágenes va en 744). Las sumas no incluyen ítems por cotizar.')}

    def resumen(self, exs):
        res = {}
        for c in CORTES:
            res[c['id']] = {}
            for esc in ESCENARIOS:
                g = {'exigibles': {k: 0 for k in ('cumple', 'parcial', 'falta', 'documento_pendiente')},
                     'por_confirmar': {k: 0 for k in ('cumple', 'parcial', 'falta', 'documento_pendiente')}}
                for e in exs:
                    if e['referencia']:
                        continue
                    v = e['estado'][c['id']][esc]
                    if v == 'no_aplica':
                        continue
                    grupo = 'exigibles' if e['exigible'] == 'si' else 'por_confirmar'
                    g[grupo][v] = g[grupo].get(v, 0) + 1
                res[c['id']][esc] = g
        return res


# ======================================================================================================================
# Totales (4.5) y salida
# ======================================================================================================================
def totales(gen: Generador) -> dict:
    ins = gen.ins
    lin = gen.lineas
    base = [u for u in gen.unidades if not u.get('componente_de')]
    calc = {}
    for u in base:
        l = gen.L[u['linea']]
        if l['origen'] != 'dotacion':
            continue
        lista = l['ref']['lista']
        clave = 'fijo' if lista == 'equipamiento_fijo' else l['servicio']
        c = calc.setdefault(clave, {'unidades': 0, 'equipos': 0, 'mobiliario': 0, 'fijo': 0})
        c['unidades'] += 1
        c[{'equipos': 'equipos', 'mobiliario': 'mobiliario'}.get(lista, 'fijo')] += l['precio_unitario_cop_2026'] or 0
    por_servicio = {}
    for s in ins.dot.get('servicios', []):
        c = calc.get(s['id'], {'unidades': 0, 'equipos': 0, 'mobiliario': 0})
        t = s.get('totales') or {}
        por_servicio[s['id']] = {'unidades': c['unidades'], 'equipos_cop_2026': c['equipos'], 'mobiliario_cop_2026': c['mobiliario'],
                                 'coincide_con_dotacion': c['equipos'] == t.get('equipos_cop_2026') and c['mobiliario'] == t.get('mobiliario_cop_2026')}
    out = {'por_servicio': por_servicio}
    if ins.dot.get('equipamiento_fijo'):
        c = calc.get('fijo', {'unidades': 0, 'fijo': 0})
        meta = (ins.dot.get('totales_equipamiento_fijo') or {}).get('total_cop_2026')
        out['equipamiento_fijo'] = {'unidades': c['unidades'], 'total_cop_2026': c['fijo'], 'coincide_con_dotacion': c['fijo'] == meta,
                                    'fuera_de_la_torre': len(gen.fuera)}
    lab = [l for l in lin if l['origen'] == 'laboratorio']
    if lab:
        def suma(ls):
            return {'lineas': len(ls), 'unidades': sum(l['cantidad'] for l in ls),
                    'valor_mercado_cop_2026': sum((l['precio_unitario_cop_2026'] or 0) * l['cantidad'] for l in ls)}
        lj = suma(lab)
        for adq in ('comodato', 'programa_o_compra', 'opcional'):
            lj[adq] = suma([l for l in lab if l['adquisicion'] == adq])
        lj['programa_o_compra']['en_presupuesto'] = False
        lj['opcional']['nota'] = 'Recomendado cuando haya más de 150 aislamientos al mes; fuera de la matriz'
        lj['comodato']['coincide_con_dotacion'] = lj['comodato']['valor_mercado_cop_2026'] == \
            (ins.dot.get('totales_generales') or {}).get('analizadores_de_laboratorio_en_comodato_valor_de_mercado_cop_2026')
        lj['tipo'] = 'dato del repositorio (laboratorio.json) y cálculo propio (sumas)'
        out['laboratorio_json'] = lj
    hab = sum((l['precio_unitario_cop_2026'] or 0) * l['cantidad'] for l in lin
              if l['origen'] == 'dotacion' and l['servicio'] != 'fijo' and l.get('prioridad') == 'habilitacion')
    recl = sum((l['precio_unitario_cop_2026'] or 0) * l['cantidad'] for l in lin
               if l['origen'] == 'dotacion' and l['servicio'] != 'fijo' and l.get('prioridad') == 'habilitacion'
               and l.get('prioridad_revisada') == 'recomendado')
    meta = (ins.dot.get('totales_generales') or {}).get('solo_items_de_habilitacion_cop_2026')
    out['habilitacion_cop_2026'] = {'segun_dotacion': hab, 'sin_reclasificados': hab - recl, 'reclasificados': recl,
                                    'coincide_con_dotacion': (meta is None) or hab == meta, 'tipo': 'calculo_propio'}
    cierre = [l for l in lin if l['origen'] == 'cierre_brechas']
    if cierre:
        pp = {}
        for p in ('P4', 'P5', 'P6'):
            ls = [l for l in cierre if l.get('proyecto') == p and l.get('naturaleza') == 'inversion']
            pp[p] = {pr + '_cop_2026': sum((l['precio_unitario_cop_2026'] or 0) * l['cantidad'] for l in ls if l.get('prioridad') == pr)
                     for pr in ('habilitacion', 'recomendado', 'por_confirmar')}
            pp[p]['items'] = len(ls)
            pp[p]['items_sin_precio'] = sum(1 for l in ls if l['precio_unitario_cop_2026'] is None)
        op = [l for l in cierre if l.get('naturaleza') == 'operacion_anual']
        out['cierre_brechas'] = {
            'por_proyecto': pp,
            'inversion_con_precio_cop_2026': sum((l['precio_unitario_cop_2026'] or 0) * l['cantidad'] for l in cierre if l.get('naturaleza') == 'inversion'),
            'operacion_anual_cop_2026': sum((l['precio_unitario_cop_2026'] or 0) * l['cantidad'] for l in op),
            'items': len(cierre), 'items_sin_precio': sum(1 for l in cierre if l['precio_unitario_cop_2026'] is None),
            'unidades': sum(1 for u in base if u['estado'] == 'cierre_brechas_propuesto'),
            'tipo': 'calculo_propio', 'nota': 'Las sumas no incluyen ítems por cotizar; la operación anual va aparte y no se suma a la inversión.'}
    infra = {}
    for l in lin:
        if l['origen'] == 'infraestructura':
            i = infra.setdefault(l['elemento'], {'unidades': 0, 'presupuesto': [c['item'] for c in l.get('cita_presupuesto', [])]})
            i['unidades'] += l['cantidad']
    # comparación con el presupuesto de obra por ÍTEM (no por modelo 3D): cada elemento se cuenta en su primer ítem en
    # unidades («un»); los que solo citan ítems globales o en metros no se comparan
    dato = ins.items_presupuesto_dato
    por_item = {}
    for el, i in infra.items():
        cod = next((c for c in i['presupuesto'] if (dato.get(c) or {}).get('unidad') == 'un'), None)
        i['item_conteo'] = cod
        if cod:
            itp = dato[cod]
            g = por_item.setdefault(cod, {'descripcion': itp.get('descripcion'), 'unidad': 'un', 'cantidad_presupuesto': itp.get('cantidad'),
                                          'valor_unitario_cop_2026': itp.get('valor_unitario_costo_directo'), 'elementos': [],
                                          'unidades_ubicadas': 0})
            g['elementos'].append(el)
            g['unidades_ubicadas'] += i['unidades']
    pendientes = []
    for cod, g in por_item.items():
        q = g['cantidad_presupuesto']
        dif = g['unidades_ubicadas'] - q if isinstance(q, (int, float)) else None
        g['diferencia'] = dif
        if dif and dif > 0:
            vu = g.get('valor_unitario_cop_2026')
            costo = f' (≈ ${C.redondear(dif * vu / 1e6, 1):g} millones de obra sin presupuesto a ${vu:,} cada uno; cálculo propio)'.replace(',', '.') if vu else ''
            g['nota'] = (f'La planta ubica {dif} más de los que presupuesta el ítem {cod}: el ítem quedaría corto si se mantiene la '
                         f'ubicación{costo}.')
            pendientes.append(f'Ítem {cod} de presupuesto.json ({g["descripcion"]}): {g["unidades_ubicadas"]} ubicados frente a {q} '
                              f'presupuestados{costo}.')
        elif dif and dif < 0:
            g['nota'] = (f'El ítem {cod} presupuesta {-dif} más de los que ubica la planta (margen del ítem o elementos por ubicar).')
    mods = [u['paneles'] for u in gen.unidades if u.get('paneles')]
    if mods and 'panel_solar_fila' in infra:
        infra['panel_solar_fila']['modulos'] = sum(m.get('modulos') or 0 for m in mods)
        infra['panel_solar_fila']['kwp'] = C.redondear(sum(m.get('kwp') or 0 for m in mods), 1)
        infra['panel_solar_fila']['por_grupo'] = {g: sum(m.get('modulos') or 0 for m in mods if m.get('grupo') == g)
                                                 for g in sorted({m.get('grupo') for m in mods if m.get('grupo')})}
    out['infraestructura'] = {'por_elemento': dict(sorted(infra.items())), 'por_item_presupuesto': dict(sorted(por_item.items(), key=lambda kv: [int(x) for x in kv[0].split('.')])),
                              'pendientes_presupuesto': pendientes, 'precio': 'sin precio de dotación (es obra o contexto)',
                              'tipo': 'cálculo propio (conteo de las unidades ubicadas frente a la cantidad del presupuesto de obra, por ítem)'}
    capas, niveles = {}, {}
    for u in gen.unidades:
        capa = gen.L[u['linea']]['capa']
        k = capa + (' (componentes)' if u.get('componente_de') else '')
        capas[k] = capas.get(k, 0) + 1
        nv = u.get('nivel') or 'fuera_de_la_torre'
        n = niveles.setdefault(nv, {'total': 0, 'por_capa': {}, 'con_posicion': 0, 'dentro_de_otra': 0, 'sin_recinto': 0})
        n['total'] += 1
        n['por_capa'][k] = n['por_capa'].get(k, 0) + 1
        n['con_posicion'] += 1 if u.get('posicion') else 0
        n['dentro_de_otra'] += 1 if u.get('montaje') == 'dentro' else 0
        n['sin_recinto'] += 1 if not u.get('recinto') else 0
    orden_nv = ['EXT', 'P1', 'P2', 'P3', 'P4', 'BT', 'CUB', 'fuera_de_la_torre']
    por_nivel = {}
    for nv in sorted(niveles, key=lambda x: (orden_nv.index(x) if x in orden_nv else 99, x)):
        n = niveles[nv]
        n['por_capa'] = dict(sorted(n['por_capa'].items()))
        por_nivel[nv] = n
    out['unidades'] = {'total': len(gen.unidades), 'por_capa': dict(sorted(capas.items())),
                       'componentes': sum(1 for u in gen.unidades if u.get('componente_de')), 'por_nivel': por_nivel,
                       'con_posicion': sum(1 for u in gen.unidades if u.get('posicion')),
                       'nota': ('«con_posicion»: unidades con x, y, z; las que van dentro de otra (contenido de carros, mesones, '
                                'neveras y kits) llevan la posición de su contenedor. «sin_recinto»: zonas de la cubierta y de los '
                                'exteriores que pasan por encima de varios recintos (pérgola y marquesina) y lo que '
                                'queda fuera de la torre.')}
    return out


def generar(rutas: dict, fixture=False, sin_planta=False, fecha=None):
    ins = Insumos(rutas, fixture=fixture, sin_planta=sin_planta)
    gen = Generador(ins)
    gen.ejecutar()
    fecha = fecha or ins.reglas.get('fecha')
    hs = ins.huellas()
    lineas_out = []
    for l in gen.lineas:
        d = dict(l)
        lineas_out.append(d)
    inv = {
        'id': 'torre_hospital_inventario_dotacion', 'version': 2, 'generado_por': 'scripts/torre/generar_inventario.py', 'fecha': fecha,
        'insumos_sha1': hs, 'sha256_dotacion': C.sha256_archivo(rutas['dotacion']),
        'moneda_y_base': ins.dot.get('moneda_y_base', 'Pesos constantes de 2026 (dotacion.json)'),
        'norma_vigente': 'Res. 3100 de 2019 y modificaciones (la Res. 1732 de 2026 fue revocada por la Res. 2080 de 2026)',
        'campos_res3100_decreto4725': ['servicio y ambiente', 'nombre genérico', 'marca', 'modelo', 'serie',
                                       'registro sanitario o permiso de comercialización INVIMA y vencimiento', 'clase de riesgo',
                                       'tecnología controlada', 'fecha de instalación y de compra', 'hoja de vida',
                                       'responsable del mantenimiento (inscrito en el INVIMA si es IIb o III)', 'referente de tecnovigilancia'],
        'capas': {'dotacion': 'Equipos y mobiliario de los 15 servicios de dotacion.json', 'fijo': 'Equipamiento fijo e industrial de dotacion.json',
                  'laboratorio': 'Analizadores de laboratorio.json (comodato, programa o compra y opcional): no suman a la dotación',
                  'cierre_brechas': 'Propuesta de cierre de brechas para la habilitación (sección de dotacion.json): suma aparte',
                  'infraestructura': 'Lo que piden los estándares de infraestructura y se ve en el recorrido: es obra, sin precio de dotación',
                  'contexto': 'Elementos de contexto del recorrido (ambulancias): no son de la torre'},
        'estado_planta': 'sin planta: unidades con recinto y sin posición' if ins.plantas is None else
                         ('planta de prueba' if fixture else 'planta del anteproyecto (estimación)'),
        'lineas': lineas_out,
        'unidades': gen.unidades_salida(),
        'fuera_de_la_torre': gen.fuera,
        'totales': totales(gen),
        'avisos_ubicacion': gen.avisos,
    }
    mat = Matriz(gen).construir()
    hab = {
        'id': 'torre_hospital_habilitacion', 'version': 2, 'generado_por': 'scripts/torre/generar_inventario.py', 'fecha': fecha,
        'insumos_sha1': None, 'norma': 'Res. 3100 de 2019 y modificaciones', 'alcance': 'Cumplimiento en dotación e infraestructura',
        'estandares_evaluados': ['dotación', 'infraestructura', 'medicamentos, dispositivos médicos e insumos (parcial)', 'procesos prioritarios (parcial)'],
        'estandares_no_evaluados': ['talento humano', 'historia clínica y registros', 'interdependencia'],
        'texto_alcance': TEXTO_ALCANCE, 'fecha_referencia': CORTES,
        'aviso_vigencia': 'La Res. 1732 de 2026 fue revocada por la Res. 2080 del 8-sep-2026 antes de regir.',
        'aviso_textos': 'Textos tomados de compilaciones oficiales vistas por buscador o de guías secundarias; cotejar con el Diario Oficial antes de radicar o de la visita previa.',
        'escenarios': ESCENARIOS,
        'estados': {'cumple': 'Hay lo que pide la exigencia', 'parcial': 'Hay una parte', 'falta': 'No hay',
                    'documento_pendiente': 'Exigencia documental que elabora la E.S.E.', 'no_aplica': 'No rige en ese corte o es solo de referencia'},
    }
    hab.update(mat)
    return inv, hab, gen


def texto_csv(inv: dict) -> str:
    L = {l['id']: l for l in inv['lineas']}
    cols = ['unidad', 'componente_de', 'linea', 'capa', 'servicio', 'tipo', 'nombre', 'cantidad_linea', 'k', 'nivel', 'piso', 'recinto',
            'ambiente', 'ubicacion', 'x', 'y', 'z', 'rotacion_z', 'montaje', 'apoyo', 'dentro_de', 'compartimiento', 'estado', 'modelo3d',
            'especificacion', 'clase_riesgo', 'estado_clase', 'es_dispositivo_medico', 'registro_requerido', 'via_registro',
            'usado_permitido', 'mantenimiento_anual_pct', 'vida_util_anios', 'personal_inscrito_invima', 'calibracion',
            'precio_unitario_cop_2026', 'tipo_precio', 'rango_min_cop_2026', 'rango_max_cop_2026', 'adquisicion', 'en_presupuesto',
            'valor_mercado_cop_2026', 'nota_precio', 'proyecto', 'naturaleza', 'parte_de_linea', 'prioridad', 'prioridad_revisada',
            'exigencias', 'cita_presupuesto'] + CAMPOS_AL_COMPRAR
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=';', lineterminator='\n')
    w.writerow(cols)

    def num(v):
        if v is None:
            return ''
        if isinstance(v, bool):
            return 'si' if v else 'no'
        if isinstance(v, float):
            return f'{v:.3f}'.rstrip('0').rstrip('.').replace('.', ',')
        return str(v)
    for u in inv['unidades']:
        l = L[u['linea']]
        comp = bool(u.get('componente_de'))
        cr = u.get('clase_riesgo') if comp else l['clase_riesgo']
        rg = u.get('registro_invima') if comp else l['registro_invima']
        mt = u.get('mantenimiento') if comp else l['mantenimiento']
        pos = u.get('posicion') or [None, None, None]
        rango = l.get('rango_precio_unitario_cop_2026') or [None, None]
        # los equipos de laboratorio.json (comodato, programa o compra, opcional) no son dotación presupuestada: su valor de
        # mercado va en su propia columna, para que sumar la columna de precio no mezcle el comodato
        lab = l['origen'] == 'laboratorio'
        precio = 0 if comp else (None if lab else l.get('precio_unitario_cop_2026'))
        mercado = None if comp else (l.get('precio_unitario_cop_2026') if lab else None)
        if lab:
            rango = [None, None]
        en_pres = l.get('en_presupuesto')
        if en_pres is None and l['origen'] == 'dotacion':
            en_pres = True
        elif en_pres is None and l['origen'] == 'cierre_brechas':
            en_pres = False
        fila = [u['id'], u.get('componente_de'), l['id'], l['capa'], l['servicio'], l['tipo'], u.get('nombre') or l['nombre'],
                l['cantidad'], u['k'], u.get('nivel'), u.get('piso'), u.get('recinto'), u.get('ambiente'), u.get('ubicacion'),
                pos[0], pos[1], pos[2], u.get('rotacion_z'), u.get('montaje'), u.get('apoyo'), u.get('dentro_de'), u.get('compartimiento'),
                u.get('estado'), u.get('modelo3d') or l.get('modelo3d'), l.get('especificacion'), (cr or {}).get('vigente'),
                (cr or {}).get('estado'), l.get('es_dispositivo_medico'), (rg or {}).get('requerido'), (rg or {}).get('via'),
                (rg or {}).get('usado_permitido'), (mt or {}).get('anual_pct'), (mt or {}).get('vida_util_anios'),
                (mt or {}).get('personal_inscrito_invima'), (mt or {}).get('calibracion'),
                precio, 'componente (precio en la línea madre)' if comp else l.get('tipo_precio'),
                rango[0], rango[1], l.get('adquisicion'), en_pres, mercado, l.get('nota_precio'), l.get('proyecto'), l.get('naturaleza'),
                (l.get('parte_de_linea') or {}).get('linea'), l.get('prioridad'), l.get('prioridad_revisada'),
                ' '.join(e['id'] for e in l.get('exigencias', [])), ' '.join(c['item'] for c in l.get('cita_presupuesto', []) or [])]
        fila += [(u.get('campos_al_comprar') or {}).get(c) for c in CAMPOS_AL_COMPRAR]
        w.writerow([num(v) for v in fila])
    return '﻿' + buf.getvalue()


def rutas_reales(sin_planta=False) -> dict:
    return {'dotacion': C.DOTACION, 'laboratorio': C.LABORATORIO, 'plantas': C.PLANTAS, 'reglas_ubicacion': C.REGLAS_UBICACION,
            'catalogo': C.CATALOGO, 'implementos': C.IMPLEMENTOS, 'exigencias': C.EXIGENCIAS, 'normas_4725': NORMAS_4725,
            'programa': C.PROGRAMA, 'presupuesto': PRESUPUESTO}


def rutas_fixture(carpeta: Path) -> dict:
    def uno(patron, defecto=None):
        c = sorted(carpeta.glob(patron))
        return c[0] if c else defecto
    return {'dotacion': uno('dotacion*.json'), 'laboratorio': uno('laboratorio*.json'), 'plantas': uno('plantas*.json'),
            'reglas_ubicacion': uno('reglas_ubicacion*.json'), 'catalogo': uno('catalogo*.json', C.CATALOGO),
            'implementos': uno('implementos*.json', C.IMPLEMENTOS), 'exigencias': uno('exigencias*.json'),
            'normas_4725': None, 'programa': None, 'presupuesto': uno('presupuesto*.json')}


def escribir_salidas(inv, hab, dir_inv: Path, dir_hab: Path, nombre_inv='inventario_dotacion.json', nombre_hab='habilitacion.json',
                     verificar=False) -> int:
    ruta_inv, ruta_hab, ruta_csv = dir_inv / nombre_inv, dir_hab / nombre_hab, dir_inv / Path(nombre_inv).with_suffix('.csv').name
    texto_inv = C.texto_json(inv)
    hab['insumos_sha1'] = {nombre_inv: C.sha1_texto(texto_inv), **{k: v for k, v in inv['insumos_sha1'].items()
                                                                   if k.startswith('exigencias') or 'planta' in k}}
    texto_hab = C.texto_json(hab)
    csvt = texto_csv(inv)
    if verificar:
        malos = [str(r) for r, t in ((ruta_inv, texto_inv), (ruta_hab, texto_hab), (ruta_csv, csvt))
                 if not r.exists() or r.read_text(encoding='utf-8') != t]
        if malos:
            sys.stderr.write('generar_inventario: no están al día: ' + ', '.join(C.relativa(m) for m in malos) + '\n')
            return 1
        sys.stderr.write('generar_inventario: inventario, CSV y matriz al día\n')
        return 0
    for r, t in ((ruta_inv, texto_inv), (ruta_hab, texto_hab), (ruta_csv, csvt)):
        if not r.exists() or r.read_text(encoding='utf-8') != t:
            r.write_text(t, encoding='utf-8')
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description='Genera el inventario de dotación y la matriz de cumplimiento de la torre (contrato, 4.5-4.8 y 16).')
    ap.add_argument('--verificar', action='store_true', help='no escribe; sale con 1 si algún archivo cambiaría')
    ap.add_argument('--sin-planta', action='store_true', help='genera sin planta: unidades con recinto y sin posición')
    ap.add_argument('--fixture', type=Path, metavar='DIR', help='insumos de prueba en DIR (escribe en DIR)')
    a = ap.parse_args(argv)
    try:
        if a.fixture:
            rutas = rutas_fixture(a.fixture)
            inv, hab, gen = generar(rutas, fixture=True, sin_planta=a.sin_planta)
            rc = escribir_salidas(inv, hab, a.fixture, a.fixture, verificar=a.verificar)
        else:
            rutas = rutas_reales()
            inv, hab, gen = generar(rutas, sin_planta=a.sin_planta)
            rc = escribir_salidas(inv, hab, C.TORRE, C.TORRE, verificar=a.verificar)
    except (ErrorGenerador, C.ErrorAmbiente, FileNotFoundError, ValueError) as err:
        sys.stderr.write(f'generar_inventario: {err}\n')
        return 2
    t = inv['totales']
    sys.stderr.write(f'generar_inventario: {len(inv["lineas"])} líneas, {t["unidades"]["total"]} unidades '
                     f'({t["unidades"]["componentes"]} componentes), {len(inv["avisos_ubicacion"])} avisos de ubicación\n')
    return rc


if __name__ == '__main__':
    sys.exit(main())
