"""Normaliza las exigencias de la Res. 3100 de 2019 de las tres investigaciones en un solo formato (contrato, 4.2).

Entrada:
  data/proyectos/torre_hospital/fuentes_investigacion/res3100_urgencias_e_internacion.json   (86 filas)
  data/proyectos/torre_hospital/fuentes_investigacion/res3100_consulta_y_ambulatorio.json    (52 + 7 de todos los servicios)
  data/proyectos/torre_hospital/fuentes_investigacion/res3100_apoyo_diagnostico.json         (43 + 11 de todos los servicios)
  data/proyectos/torre_hospital/reglas_exigencias.json   (a mano: tabla de servicios, reglas y cubre_con)
  data/proyectos/torre_hospital/programa.json            (ambientes por fila)
  data/proyectos/torre_hospital/dotacion.json y laboratorio.json (líneas que cubren cada exigencia)
Salida:
  data/proyectos/torre_hospital/exigencias_3100.json     (199 filas, cada una con su «origen»)

Reglas que aplica (4.2): una sola escala de verificación; «exigible» y «numeral_confirmado» calculados por regla (no a mano);
«texto» solo con el texto de la fila (nunca el resumen); ambientes por fila del programa con la tabla cerrada
servicio_a_programa; ids EX-{SRV}-{nnn} por posición dentro de (archivo, servicio) y EX-TOD-{C|A}{nn}; vigencia de las
exigencias de esterilización que deroga la Res. 914 de 2025; las de la sala de expansión «por analogía» quedan como
referencia; los datos superados de las investigaciones (Res. 482 de 2018, transición de la Res. 1732) se corrigen aquí.

Uso: python3 scripts/torre/normalizar_exigencias.py [--verificar]
  --verificar  no escribe: sale con 1 si el archivo guardado no es el que se generaría.
Solo biblioteca estándar. Falla (código 2) si un servicio no está en la tabla, si un id citado no existe o no coincide con
su origen, si un nombre de línea no coincide o si un ambiente citado por nombre es ambiguo.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import comun as C  # noqa: E402

ARCH_URG = 'res3100_urgencias_e_internacion.json'
ARCH_CON = 'res3100_consulta_y_ambulatorio.json'
ARCH_APO = 'res3100_apoyo_diagnostico.json'
TIPOS_REGLA = ('por_recinto', 'por_puesto', 'total_servicio', 'por_piso', 'contenido', 'existe_ambiente',
               'area_libre_por_puesto', 'documental', 'sin_regla')
VERIF_EXIGIBLE = ('literal_compilacion', 'contenido_compilacion')
# El numeral no está confirmado si el propio texto del numeral lo dice (marcas del 4.2) o si dice que difiere entre copias o que
# no se recuperó (sección 15 del contrato: «12.1 frente a 9.2; 17.1.2.x frente a 17.2.1.x»), y tampoco si la fila es de guía
# secundaria o paráfrasis (fuente_secundaria o por_confirmar).
MARCAS_NUMERAL = ('por confirmar', 'según guía', 'según la guía', 'según normas.json', 'por analogía', 'no se pudo confirmar',
                  'no recuperad', 'según una de las copias', 'lo numera', 'en la copia', 'en la cancillería', 'en el icbf', 'colegio')
VERIF_NUMERAL_NO_CONFIRMADO = ('fuente_secundaria', 'por_confirmar')
# Compilaciones oficiales (4.2: Cancillería, ICBF, Invima, normograma de Supersalud): sitios .gov.co. Una fila «literal» o de
# «contenido» de compilación que solo cita un sitio privado o de consultoría baja a fuente_secundaria (y queda por_confirmar).
RE_URL_OFICIAL = re.compile(r'^https?://[^/]*\.gov\.co(/|$)', re.I)
# Exigencias documentales (licencias, certificados, documentos firmados, programas, información documentada, contratos): se
# detectan en el texto de la fila (texto literal y resumen) antes de mirar si hay ítems de dotación, en cualquier estándar.
RE_DOCUMENTAL = re.compile(r'\blicencia\b|\bcertific(?:ado|ados|a|an|ar|que)\b|\bdocumentos? firmados?\b|\blos firma\b|'
                           r'\bprogramas? de (?:mantenimiento|capacitaci[oó]n|tecnovigilancia|farmacovigilancia|reactivovigilancia)|'
                           r'\bprogramas de farmacovigilancia|\binformaci[oó]n documentada sobre\b|\bsiguiente informaci[oó]n documentada\b|'
                           r'\bhojas? de vida\b|\bhoja\(s\) de vida\b|\bcontrato\b|\bregistro de la relaci[oó]n de los equipos\b', re.I)
SIN_TEXTO = ('[paráfrasis', '[contenido no obtenido', 'por confirmar')
ESTADOS_INV = ('cubierto', 'parcial', 'falta')


class ErrorNormalizacion(ValueError):
    pass


# --------------------------------------------------------------------------------------------------------------------
# Catálogo de líneas (dotación, equipamiento fijo, laboratorio.json y cierre de brechas) para resolver «item_dotacion»
# --------------------------------------------------------------------------------------------------------------------
def catalogo_lineas(dot: dict, lab: dict) -> list[dict]:
    salida = []
    for s in dot.get('servicios', []):
        for lista, letra in (('equipos', 'e'), ('mobiliario', 'm')):
            for i, x in enumerate(s.get(lista, [])):
                salida.append({'id': C.id_linea(s['id'], letra, x['nombre']), 'nombre': x['nombre'], 'servicio': s['id'],
                               'letra': letra, 'ref': (s['id'], lista, i)})
    for i, x in enumerate(dot.get('equipamiento_fijo', [])):
        salida.append({'id': C.id_linea('fijo', 'f', x['nombre']), 'nombre': x['nombre'], 'servicio': 'fijo', 'letra': 'f',
                       'ref': ('fijo', 'equipamiento_fijo', i)})
    for i, x in enumerate(lab.get('equipos', [])):
        salida.append({'id': C.id_linea('laboratorio', 'c', x['nombre']), 'nombre': x['nombre'], 'servicio': 'laboratorio',
                       'letra': 'c', 'ref': ('laboratorio', 'laboratorio.json', i)})
    for i, x in enumerate((dot.get('cierre_brechas_habilitacion') or {}).get('items', [])):
        salida.append({'id': C.id_linea(x['servicio'], 'x', x['nombre']), 'nombre': x['nombre'], 'servicio': x['servicio'],
                       'letra': 'x', 'ref': (x['servicio'], 'cierre_brechas', i)})
    return salida


PISTAS = {'equipamiento_fijo': 'fijo', 'fijo': 'fijo'}
RE_PAREN_FINAL = re.compile(r'\s*\([^()]*\)\s*$')


def _pista(texto: str, j: int, servicios: set[str]) -> str | None:
    """Servicio citado entre paréntesis justo después de un nombre: «… (tic_apoyo, 70)», «… (equipamiento_fijo)»."""
    m = re.match(r'\s*\(([a-z_]+)[,)]', texto[j:])
    if not m:
        return None
    s = m.group(1)
    s = PISTAS.get(s, s)
    return s if s in servicios or s == 'fijo' else None


def resolver_items(texto, servicio: str | None, cat: list[dict], sin_aviso=()) -> tuple[list[dict], list[str]]:
    """Busca en el texto de «item_dotacion» los nombres exactos de líneas (los más largos primero, sin traslapes).
    Devuelve ([{linea, nombre}], [avisos]). Si un nombre está en varios servicios, decide la pista entre paréntesis,
    después el servicio de la exigencia; si sigue ambiguo, lo informa y no lo usa."""
    if not texto or not isinstance(texto, str):
        return [], []
    por_nombre = {}
    propios = {}            # nombre base (sin el paréntesis final) → líneas del servicio de la exigencia: «… (sala de procedimientos)»
    for l in cat:
        if l['letra'] == 'x':
            continue
        por_nombre.setdefault(l['nombre'], []).append(l)
    for l in cat:
        if l['letra'] != 'x' and servicio and l['servicio'] == servicio:
            base = RE_PAREN_FINAL.sub('', l['nombre']).strip()
            # solo reemplaza un nombre exacto que existe en otro servicio (no crea coincidencias nuevas)
            if base and base != l['nombre'] and base in por_nombre and not any(x['servicio'] == servicio for x in por_nombre[base]):
                propios.setdefault(base, []).append(l)
    servicios = {l['servicio'] for l in cat}
    usado = [False] * len(texto)
    hallados, avisos = [], []
    for nombre in sorted(por_nombre, key=lambda n: (-len(n), n)):
        ini = 0
        while True:
            i = texto.find(nombre, ini)
            if i < 0:
                break
            j = i + len(nombre)
            libre = not any(usado[i:j])
            frontera = j == len(texto) or not texto[j].isalnum()
            inicio = i == 0 or not texto[i - 1].isalnum()
            if libre and frontera and inicio:
                for k in range(i, j):
                    usado[k] = True
                hallados.append((i, nombre, _pista(texto, j, servicios)))
            ini = i + 1
    salida, vistos = [], set()
    for _, nombre, pista in sorted(hallados):
        cands = por_nombre[nombre]
        # pista entre paréntesis; si no, la línea del propio servicio (con el mismo nombre o con el mismo nombre y un paréntesis
        # final que dice dónde va); solo si no hay ninguna propia, la única línea de otro servicio
        elegidas = [l for l in cands if pista and l['servicio'] == pista] or \
                   [l for l in cands if l['servicio'] == servicio] or propios.get(nombre, []) or (cands if len(cands) == 1 else [])
        if len(elegidas) == 1 and servicio and elegidas[0]['servicio'] not in (servicio, 'fijo') and not pista \
                and elegidas[0]['id'] not in sin_aviso:
            avisos.append(f'«{nombre}» solo está en {elegidas[0]["servicio"]}: se toma esa línea para una exigencia de {servicio} '
                          '(si el servicio tiene una propia, citarla en reglas_exigencias.json)')
        if len(elegidas) != 1:
            avisos.append(f'«{nombre}» está en {len(cands)} servicios ({", ".join(sorted(l["servicio"] for l in cands))}) '
                          'y el texto no dice cuál')
            continue
        l = elegidas[0]
        if l['id'] not in vistos:
            vistos.add(l['id'])
            salida.append({'tipo': 'linea', 'linea': l['id'], 'nombre': l['nombre']})
    return salida, avisos


# --------------------------------------------------------------------------------------------------------------------
# Ambientes por fila del programa (regla común del 3.4)
# --------------------------------------------------------------------------------------------------------------------


def _variantes(nombre: str):
    """El nombre tal cual y luego sin paréntesis finales, uno a la vez («Consultorio … (8)» → «Consultorio …»)."""
    n = nombre.strip()
    vistos = []
    while n and n not in vistos:
        vistos.append(n)
        m = RE_PAREN_FINAL.search(n)
        if not m:
            break
        n = n[:m.start()].strip()
    return vistos


def resolver_ambiente_texto(nombre: str, servicios_programa: list[str], ambientes: list[dict],
                            servicio_explicito: str | None = None) -> int | None:
    """Fila del programa para un nombre de ambiente de una investigación: primero dentro de los servicios del programa de
    esa investigación (o del servicio que trae la fila), luego en todo el programa si el nombre es único."""
    for n in _variantes(nombre):
        filas = [i for i, a in enumerate(ambientes) if a.get('nombre') == n]
        if not filas:
            continue
        if servicio_explicito:
            f = [i for i in filas if ambientes[i].get('servicio') == servicio_explicito]
            if len(f) == 1:
                return f[0]
        f = [i for i in filas if ambientes[i].get('servicio') in servicios_programa]
        if len(f) == 1:
            return f[0]
        if len(filas) == 1:
            return filas[0]
        if len(f) > 1 or len(filas) > 1:
            raise ErrorNormalizacion(f'el ambiente «{n}» corresponde a varias filas ({filas}) y el servicio no lo desambigua')
    return None


def ambientes_de_fila(e: dict, servicios_programa: list[str], ambientes: list[dict]) -> tuple[list[dict], list[str]]:
    """[{fila, nombre, servicio_programa[, n]}] y los textos que no corresponden a una fila (se conservan aparte)."""
    salida, sin_fila = [], []
    dist = e.get('distribucion_por_ambiente') or []
    if dist:
        fuentes = [(x.get('ambiente'), x.get('servicio_programa'), x.get('cantidad')) for x in dist]
    else:
        crudo = e.get('ambiente_programa')
        if isinstance(crudo, list):
            fuentes = [(x, None, None) for x in crudo]
        elif isinstance(crudo, str) and crudo.strip():
            fuentes = [(x, None, None) for x in crudo.split(' | ')]
        else:
            fuentes = []
    vistos = set()
    for nombre, srv, n in fuentes:
        if not nombre:
            continue
        f = resolver_ambiente_texto(nombre, servicios_programa, ambientes, srv)
        if f is None:
            sin_fila.append(nombre.strip())
            continue
        if f in vistos:
            continue
        vistos.add(f)
        a = {'fila': f, 'nombre': ambientes[f]['nombre'], 'servicio_programa': ambientes[f]['servicio']}
        if isinstance(n, int):
            a['n'] = n
        salida.append(a)
    return salida, sin_fila


# --------------------------------------------------------------------------------------------------------------------
# Campos calculados
# --------------------------------------------------------------------------------------------------------------------
def numeral_confirmado(numeral: str | None, verificacion: str | None = None) -> bool:
    t = (numeral or '').lower()
    if verificacion in VERIF_NUMERAL_NO_CONFIRMADO:
        return False
    return not any(m in t for m in MARCAS_NUMERAL)


def url_oficial(url) -> bool:
    urls = url if isinstance(url, list) else [url]
    return any(isinstance(u, str) and RE_URL_OFICIAL.match(u) for u in urls)


def texto_disponible(texto) -> bool:
    if not isinstance(texto, str) or not texto.strip():
        return False
    t = texto.strip().lower()
    return not any(t.startswith(m) for m in SIN_TEXTO)


def corregir_superados(v, superados: dict, es_comentario: bool = False):
    """Reescribe «Res. 482 de 2018» (salvo en comentarios que ya explican el reemplazo)."""
    if isinstance(v, str):
        r = superados['res_482']
        if r['buscar'] in v and not (es_comentario and '1811' in v):
            v = v.replace(r['buscar'], r['reemplazo'])
        return v
    if isinstance(v, list):
        return [corregir_superados(x, superados, es_comentario) for x in v]
    return v


def es_documental(e: dict) -> bool:
    """¿La fila exige un documento (licencia, certificado, documento firmado, programa, información documentada, contrato)?
    Se mira lo que la fila exige (texto literal y resumen), no los ítems de dotación que la investigación le asocia."""
    texto = ' '.join(str(e.get(k) or '') for k in ('texto_literal', 'que_exige'))
    return bool(RE_DOCUMENTAL.search(texto))


def regla_automatica(e: dict, items: list[dict], ambientes: list[dict]) -> dict:
    """Regla por defecto cuando reglas_exigencias.json no trae una. Primero lo documental (en cualquier estándar y aunque la
    fila traiga ítems: que exista el equipo no cumple una licencia, un certificado o un programa); luego, los ítems resueltos
    deben existir en los recintos del servicio (dotación), los ambientes deben existir en la planta (infraestructura sin
    ítems) o queda sin regla (estado de la investigación)."""
    est = e.get('estandar')
    texto = ' '.join(str(e.get(k) or '') for k in ('item_dotacion', 'cantidad_minima', 'texto_literal')).lower()
    documental_viejo = any(p in texto for p in ('inventario', 'hoja de vida', 'programa de mantenimiento', 'capacitación',
                                                'tecnovigilancia', 'licencia', 'contrato', 'procedimiento', 'protocolo',
                                                'registro de control', 'información documentada'))
    if est == 'procesos_prioritarios' or es_documental(e) or (est == 'todos_los_servicios' and documental_viejo and not items):
        return {'tipo': 'documental', 'origen_regla': 'automatica'}
    if items:
        return {'tipo': 'total_servicio', 'items': [{'linea': x['linea'], 'nombre': x['nombre']} for x in items], 'n': 1,
                'origen_regla': 'automatica', 'nota': 'Cada ítem que cubre la exigencia debe existir al menos una vez en el servicio.'}
    if est == 'infraestructura' and ambientes:
        return {'tipo': 'existe_ambiente', 'origen_regla': 'automatica'}
    return {'tipo': 'sin_regla', 'origen_regla': 'automatica'}


def validar_regla(regla: dict, cat_ids: dict, donde: str, ambientes: list[dict]) -> None:
    if regla.get('tipo') not in TIPOS_REGLA:
        raise ErrorNormalizacion(f'{donde}: regla.tipo {regla.get("tipo")!r} fuera de {TIPOS_REGLA}')
    for it in regla.get('items', []) or []:
        validar_ref_linea(it, cat_ids, f'{donde} → regla.items', obligatoria=False)
    for k, g in enumerate(regla.get('grupos', []) or []):
        if not g.get('lineas') and not g.get('infra'):
            raise ErrorNormalizacion(f'{donde} → regla.grupos[{k}]: un grupo sin líneas ni infraestructura')
        for it in g.get('lineas', []) or []:
            validar_ref_linea(it, cat_ids, f'{donde} → regla.grupos[{k}]')
        # un grupo puede pedir sus propios puestos (por_puesto) o solo algunos ambientes (por_recinto)
        for campo in ('puestos', 'ambientes'):
            for a in g.get(campo, []) or []:
                try:
                    C.resolver_ambiente({kk: v for kk, v in a.items() if kk in ('fila', 'nombre', 'servicio_programa')}, ambientes)
                except C.ErrorAmbiente as err:
                    raise ErrorNormalizacion(f'{donde} → regla.grupos[{k}].{campo}: {err}') from None
    for it in regla.get('compartidas', []) or []:
        validar_ref_linea(it, cat_ids, f'{donde} → regla.compartidas')
        if not it.get('motivo'):
            raise ErrorNormalizacion(f'{donde} → regla.compartidas: {it.get("linea")} sin motivo')
    if 'parte_documental' in regla and not (isinstance(regla['parte_documental'], str) and regla['parte_documental'].strip()):
        raise ErrorNormalizacion(f'{donde} → regla.parte_documental: debe ser el texto del documento que falta')
    if regla.get('dentro_de'):
        validar_ref_linea(regla['dentro_de'], cat_ids, f'{donde} → regla.dentro_de')
    for p in regla.get('puestos', []) or []:
        try:
            C.resolver_ambiente({k: v for k, v in p.items() if k in ('fila', 'nombre', 'servicio_programa')}, ambientes)
        except C.ErrorAmbiente as err:
            raise ErrorNormalizacion(f'{donde} → regla.puestos: {err}') from None


def validar_ref_linea(ref: dict, cat_ids: dict, donde: str, obligatoria: bool = True) -> None:
    if 'linea' not in ref:
        if obligatoria:
            raise ErrorNormalizacion(f'{donde}: falta la línea')
        if not ref.get('nombre'):
            raise ErrorNormalizacion(f'{donde}: un ítem sin línea debe traer al menos su nombre')
        return
    l = cat_ids.get(ref['linea'])
    if l is None:
        raise ErrorNormalizacion(f'{donde}: la línea {ref["linea"]} no existe')
    if ref.get('nombre') != l['nombre']:
        raise ErrorNormalizacion(f'{donde}: {ref["linea"]} se llama «{l["nombre"]}», no «{ref.get("nombre")}»')


# --------------------------------------------------------------------------------------------------------------------
def leer_filas(fuentes: dict, reglas: dict):
    """Filas de origen en el orden del contrato: por archivo, primero las de todos los servicios y luego los servicios."""
    tabla = reglas['servicio_a_programa']
    for arch in reglas['archivos']:
        nombre = arch['archivo']
        d = fuentes[nombre]
        letra = arch.get('todos')
        if letra:
            for i, e in enumerate(d.get('requisitos_todos_los_servicios', [])):
                yield {'id': C.id_exigencia_todos(letra, i + 1), 'origen': f'{nombre}#requisitos_todos_los_servicios[{i}]',
                       'archivo': nombre, 'srv': None, 'cfg': {**reglas['todos_los_servicios'][letra], 'srv': 'TOD',
                                                                 'matriz': None, 'codigo_reps': None},
                       'servicio_inv': None, 'fila': e, 'campo_verif': arch['campo_verificacion']}
        for si, s in enumerate(d.get('servicios', [])):
            cfg = (tabla.get(nombre) or {}).get(s['id'])
            if cfg is None:
                raise ErrorNormalizacion(f'{nombre}: el servicio «{s["id"]}» no está en reglas_exigencias.json → servicio_a_programa')
            for i, e in enumerate(s.get('exigencias', [])):
                yield {'id': C.id_exigencia(cfg['srv'], i + 1), 'origen': f'{nombre}#servicios[{si}].exigencias[{i}]',
                       'archivo': nombre, 'srv': cfg['srv'], 'cfg': cfg, 'servicio_inv': s, 'fila': e,
                       'campo_verif': arch['campo_verificacion']}


def normalizar(fuentes: dict, reglas: dict, programa: dict, dot: dict, lab: dict) -> dict:
    ambientes = programa['ambientes']
    escala = reglas['escala_verificacion']
    superados = reglas['superados']
    marca_914 = reglas['vigencia']['res914']
    cat = catalogo_lineas(dot, lab)
    cat_ids = {l['id']: l for l in cat}
    manual = {}
    for r in reglas.get('reglas', []):
        if r['id'] in manual:
            raise ErrorNormalizacion(f'reglas_exigencias.json: {r["id"]} repetida')
        manual[r['id']] = r
    filas = list(leer_filas(fuentes, reglas))
    por_id = {f['id']: f for f in filas}
    compartidas_globales = (reglas.get('lineas_compartidas') or {}).get('lineas', [])
    for c in compartidas_globales:
        validar_ref_linea(c, cat_ids, 'reglas_exigencias.json → lineas_compartidas')
    for rid, r in manual.items():
        f = por_id.get(rid)
        if f is None:
            raise ErrorNormalizacion(f'reglas_exigencias.json: la exigencia {rid} no existe')
        if r.get('origen') != f['origen']:
            raise ErrorNormalizacion(f'reglas_exigencias.json: {rid} tiene origen {f["origen"]}, no {r.get("origen")}')
    salida, avisos = [], []
    primeros_texto = {}
    for f in filas:
        e, cfg = f['fila'], f['cfg']
        eid = f['id']
        verif_origen = e.get(f['campo_verif'])
        if verif_origen not in escala:
            raise ErrorNormalizacion(f'{eid}: nivel de verificación {verif_origen!r} fuera de la escala')
        verif = escala[verif_origen]
        r = manual.get(eid, {})
        fuente_url = r.get('fuente_url') or e.get('fuente_url')
        ajuste_verif = None
        if verif in VERIF_EXIGIBLE and not url_oficial(fuente_url):
            # «vista en una compilación oficial» pide una URL de compilación oficial (4.2); con un sitio privado baja de nivel
            ajuste_verif = (f'La revisión la marcó «{verif}», pero solo cita {fuente_url} (sitio privado o de consultoría, no una '
                            'compilación oficial): queda como fuente secundaria hasta cotejarla en el normograma de Supersalud o en '
                            'el Diario Oficial.')
            verif = 'fuente_secundaria'
        numeral = corregir_superados(e.get('numeral'), superados)
        texto_crudo = e.get('texto_literal')
        disponible = texto_disponible(texto_crudo)
        servicios_programa = cfg.get('servicios_programa') or []
        try:
            if 'ambientes' in r:
                amb = []
                for a in r['ambientes']:
                    fi = C.resolver_ambiente(a, ambientes)
                    x = {'fila': fi, 'nombre': ambientes[fi]['nombre'], 'servicio_programa': ambientes[fi]['servicio']}
                    if isinstance(a, dict) and isinstance(a.get('n'), int):
                        x['n'] = a['n']
                    amb.append(x)
                sin_fila = r.get('ambientes_sin_fila', [])
            else:
                amb, sin_fila = ambientes_de_fila(e, servicios_programa, ambientes)
        except (C.ErrorAmbiente, ErrorNormalizacion) as err:
            raise ErrorNormalizacion(f'{eid}: {err}') from None
        # líneas de otro servicio que la regla ya decidió (las quita o las declara compartidas): sin aviso
        sin_aviso = set(r.get('quitar_cubre_con', []) or []) | {c.get('linea') for c in (r.get('regla') or {}).get('compartidas', []) or []}
        items, av = resolver_items(e.get('item_dotacion'), cfg.get('servicio'), cat, sin_aviso)
        avisos += [f'{eid}: {a}' for a in av]
        cubre = list(items)
        for c in r.get('cubre_con', []) or []:
            if c.get('tipo', 'linea') == 'linea':
                validar_ref_linea(c, cat_ids, f'{eid} → cubre_con')
                if all(x.get('linea') != c['linea'] for x in cubre):
                    cubre.append({'tipo': 'linea', 'linea': c['linea'], 'nombre': c['nombre']})
            else:
                cubre.append(c)
        for q in r.get('quitar_cubre_con', []) or []:
            cubre = [x for x in cubre if x.get('linea') != q]
        if 'regla' in r:
            regla = dict(r['regla'])
            regla.setdefault('origen_regla', 'reglas_exigencias.json')
        else:
            regla = regla_automatica(e, [x for x in cubre if x.get('tipo') == 'linea'], amb)
        if regla.get('tipo') == 'total_servicio':
            # centrales únicas de la torre (lista explícita de reglas_exigencias.json): cuentan aunque estén fuera del servicio
            usadas = {i.get('linea') for i in regla.get('items', []) or []} | \
                     {i.get('linea') for g in regla.get('grupos', []) or [] for i in g.get('lineas', []) or []}
            if not regla.get('items') and not regla.get('grupos'):
                usadas |= {c.get('linea') for c in cubre if c.get('tipo') == 'linea'}
            ya = {c.get('linea') for c in regla.get('compartidas', []) or []}
            extra = [dict(c) for c in compartidas_globales if c['linea'] in usadas and c['linea'] not in ya]
            if extra:
                regla['compartidas'] = list(regla.get('compartidas', []) or []) + extra
        validar_regla(regla, cat_ids, eid, ambientes)
        texto_norm = corregir_superados(texto_crudo, superados) if disponible else None
        misma_que = None
        if disponible and isinstance(texto_crudo, str) and len(texto_crudo) > 40:
            clave = (f['archivo'], e.get('estandar'), texto_crudo)
            misma_que = primeros_texto.setdefault(clave, eid)
            misma_que = None if misma_que == eid else misma_que
        if r.get('misma_que'):
            if r['misma_que'] not in por_id or r['misma_que'] == eid:
                raise ErrorNormalizacion(f'{eid}: misma_que {r["misma_que"]!r} no es otra exigencia')
            misma_que = r['misma_que']
        derogado = marca_914['marca'] in (e.get('numeral') or '').lower() and cfg.get('srv') == 'EST'
        # requisito propio de la Res. 914 (rige desde el 3-ene-2027): solo las filas de esterilización que la citan como norma
        es_914 = (e.get('numeral') or '').lower().startswith('res. 914') and cfg.get('srv') == 'EST' and not derogado
        referencia = 'por analogía' in (e.get('numeral') or '').lower()
        estado_inv = e.get('estado_en_dotacion')
        if estado_inv not in ESTADOS_INV:
            raise ErrorNormalizacion(f'{eid}: estado_en_dotacion {estado_inv!r} fuera de {ESTADOS_INV}')
        x = {
            'id': eid,
            'origen': f['origen'],
            'servicio': cfg.get('servicio'),
            'servicio_matriz': cfg.get('matriz'),
            'servicio_programa': servicios_programa[0] if servicios_programa else None,
            'servicios_programa': servicios_programa,
            'codigo_reps': ({'valor': cfg['codigo_reps'], 'estado': 'por confirmar en el REPS (tomado de programa.json)'}
                            if cfg.get('codigo_reps') else None),
            'numeral_grupo': cfg.get('numeral_grupo'),
            'estandar': e.get('estandar'),
            'numeral': numeral,
            'numeral_confirmado': numeral_confirmado(e.get('numeral'), verif),
            'texto': texto_norm,
            'texto_disponible': disponible,
            'verificacion_texto': verif,
            'verificacion_origen': verif_origen,
            'exigible': 'si' if verif in VERIF_EXIGIBLE and not es_914 else 'por_confirmar',
            'que_exige': corregir_superados(e.get('que_exige'), superados),
            'ambientes': amb,
            'ambientes_sin_fila': sin_fila,
            'cantidad_texto': corregir_superados(e.get('cantidad_minima'), superados),
            'item_dotacion_texto': corregir_superados(e.get('item_dotacion'), superados),
            'regla': regla,
            'cubre_con': cubre,
            'estado_investigacion': estado_inv,
            'comentario': corregir_superados(e.get('comentario'), superados, es_comentario=True),
            'diferencia': r.get('diferencia'),
            'vigencia_hasta': marca_914['vigencia_hasta'] if derogado else None,
            'vigencia_desde': marca_914['vigencia_desde_914'] if es_914 else None,
            'referencia': referencia,
            'misma_que': misma_que,
            'fuente_url': fuente_url,
            'tipo_dato': 'dato oficial' if verif in VERIF_EXIGIBLE else 'fuente secundaria o paráfrasis',
        }
        if e.get('tipo_dato') and e['tipo_dato'] != x['tipo_dato']:
            x['tipo_dato_origen'] = e['tipo_dato']
        if r.get('fuente_url') and r['fuente_url'] != e.get('fuente_url'):
            x['fuente_url_origen'] = e.get('fuente_url')
            x['nota_fuente_url'] = r.get('nota_fuente_url')
        if ajuste_verif:
            x['ajuste_verificacion'] = ajuste_verif
        if r.get('nota'):
            x['nota_regla'] = r['nota']
        if es_914:
            x['motivo_exigible'] = marca_914.get('nota_exigible') or 'Requisito de la Res. 914 de 2025: por confirmar hasta leer el manual DMER.'
        if x['texto'] is None and x['texto_disponible']:
            raise ErrorNormalizacion(f'{eid}: texto vacío con texto_disponible')
        salida.append(x)
    # citas del cierre de brechas de dotacion.json: id y origen deben coincidir
    por_id_salida = {x['id']: x for x in salida}
    for i, it in enumerate((dot.get('cierre_brechas_habilitacion') or {}).get('items', [])):
        for ex in it.get('exigencias', []) or []:
            x = por_id_salida.get(ex.get('id'))
            if x is None:
                raise ErrorNormalizacion(f'dotacion.json → cierre_brechas_habilitacion.items[{i}]: la exigencia {ex.get("id")} no existe')
            if ex.get('origen') and ex['origen'] != x['origen']:
                raise ErrorNormalizacion(f'dotacion.json → cierre_brechas_habilitacion.items[{i}]: {ex["id"]} tiene origen '
                                         f'{x["origen"]}, no {ex["origen"]}')
    return {'exigencias': salida, 'avisos': avisos}


def conteos(exig: list[dict]) -> dict:
    def contar(campo):
        c = {}
        for x in exig:
            c[x[campo]] = c.get(x[campo], 0) + 1
        return dict(sorted(c.items(), key=lambda kv: str(kv[0])))
    por_archivo = {}
    for x in exig:
        a = x['origen'].split('#')[0]
        clave = 'todos_los_servicios' if x['id'].startswith('EX-TOD-') else 'servicios'
        por_archivo.setdefault(a, {'servicios': 0, 'todos_los_servicios': 0})[clave] += 1
    dot = [x for x in exig if x['estandar'] == 'dotacion']
    auto = [x for x in dot if x['regla']['tipo'] != 'sin_regla']
    pc = {}
    for x in exig:
        if x['exigible'] == 'por_confirmar':
            a = x['origen'].split('#')[0]
            pc[a] = pc.get(a, 0) + 1
    return {
        'filas': len(exig),
        'por_archivo': por_archivo,
        'por_verificacion': contar('verificacion_texto'),
        'por_exigible': contar('exigible'),
        'por_confirmar_por_archivo': pc,
        'por_estandar': contar('estandar'),
        'texto_no_disponible': sum(1 for x in exig if not x['texto_disponible']),
        'numeral_confirmado': sum(1 for x in exig if x['numeral_confirmado']),
        'dotacion_con_regla_automatica': {'filas_dotacion': len(dot), 'con_regla': len(auto),
                                          'porcentaje': round(100 * len(auto) / len(dot), 1) if dot else None},
        'por_tipo_de_regla': {t: sum(1 for x in exig if x['regla']['tipo'] == t) for t in TIPOS_REGLA},
        'vigencia_hasta_2027': [x['id'] for x in exig if x['vigencia_hasta']],
        'desde_res914': [x['id'] for x in exig if x['vigencia_desde']],
        'referencia': [x['id'] for x in exig if x['referencia']],
        'tipo': 'cálculo propio (conteos sobre las filas normalizadas)',
    }


def construir(rutas: dict | None = None) -> dict:
    rutas = rutas or {}
    r_fuentes = {n: rutas.get(n, C.FUENTES_INVESTIGACION / n) for n in (ARCH_URG, ARCH_CON, ARCH_APO)}
    r_reglas = rutas.get('reglas', C.REGLAS_EXIGENCIAS)
    r_prog = rutas.get('programa', C.PROGRAMA)
    r_dot = rutas.get('dotacion', C.DOTACION)
    r_lab = rutas.get('laboratorio', C.LABORATORIO)
    fuentes = {n: C.cargar_json(p) for n, p in r_fuentes.items()}
    reglas = C.cargar_json(r_reglas)
    programa = C.cargar_json(r_prog)
    dot = C.cargar_json(r_dot)
    lab = C.cargar_json(r_lab)
    res = normalizar(fuentes, reglas, programa, dot, lab)
    exig = res['exigencias']
    insumos = [*r_fuentes.values(), r_reglas, r_prog, r_dot, r_lab]
    return {
        'id': 'torre_hospital_exigencias_3100',
        'version': 1,
        'generado_por': 'scripts/torre/normalizar_exigencias.py',
        'fecha': reglas.get('fecha'),
        'insumos_sha1': C.insumos_sha1(insumos),
        'norma_vigente': 'Res. 3100 de 2019 y sus modificaciones (la Res. 1732 de 2026 fue revocada por la Res. 2080 del '
                         '8-sep-2026 antes de regir; se informa y no se aplica)',
        'aviso_textos': 'Textos tomados de compilaciones oficiales vistas por buscador (Cancillería, ICBF, Invima) o de guías '
                        'secundarias; cotejar con el Diario Oficial antes de radicar o de la visita previa.',
        'escala_verificacion': {
            'literal_compilacion': 'Frase vista en una compilación oficial a través del buscador; cotejar con el Diario Oficial.',
            'contenido_compilacion': 'Contenido confirmado en una compilación oficial; redacción o subnumeral por confirmar.',
            'fuente_secundaria': 'Guía o transcripción de terceros: no es texto normativo.',
            'por_confirmar': 'Paráfrasis o dato sin fuente leída: por confirmar.'},
        'reglas_de_calculo': {
            'exigible': '«si» solo con literal_compilacion o contenido_compilacion; «por_confirmar» en los demás casos.',
            'numeral_confirmado': ('false si el numeral contiene «por confirmar», «según guía», «según la guía», «según normas.json», '
                                   '«por analogía», «no se pudo confirmar», «no recuperad», «según una de las copias», «lo numera», '
                                   '«en la copia», «en la Cancillería», «en el ICBF» o «Colegio» (subnumerales que difieren entre copias '
                                   'o que no se recuperaron), y siempre que la fila sea fuente_secundaria o por_confirmar.'),
            'verificacion_por_url': ('Una fila literal_compilacion o contenido_compilacion cuya única URL no es una compilación oficial '
                                     '(sitio .gov.co: Cancillería, ICBF, Invima, normograma de Supersalud) baja a fuente_secundaria y '
                                     'queda exigible por_confirmar (campo ajuste_verificacion), salvo que reglas_exigencias.json cite la '
                                     'compilación oficial donde está el mismo texto.'),
            'tipo_dato': ('«dato oficial» solo con literal_compilacion o contenido_compilacion; «fuente secundaria o paráfrasis» en '
                          'los demás casos. Si la investigación traía otro tipo_dato, queda en tipo_dato_origen.'),
            'documental': ('Regla automática documental, en cualquier estándar y antes de mirar los ítems, si lo que la fila exige es '
                           'una licencia, un certificado, un documento firmado, un programa (mantenimiento, capacitación, tecno-, '
                           'fármaco- o reactivovigilancia), información documentada, hojas de vida o un contrato.'),
            'texto': 'El texto literal de la fila; null (y texto_disponible false) si la investigación no lo trae o es una '
                     'paráfrasis: la web muestra entonces que_exige con la etiqueta «resumen; texto oficial no obtenido».',
            'vigencia': 'Las exigencias de esterilización cuyos numerales deroga la Res. 914 de 2025 llevan vigencia_hasta '
                        '2027-01-02; la fila que ya cita la Res. 914 lleva vigencia_desde 2027-01-03.',
            'referencia': 'Las exigencias «por analogía» (sala de expansión) son referencia: quedan no_aplica y no cuentan.',
            'superados': 'Toda mención de la Res. 482 de 2018 se reescribe como Res. 1811 de 2025; la transición de la '
                         'Res. 1732 de 2026 no se propaga (fue revocada).'},
        'conteos': conteos(exig),
        'servicios_matriz': reglas.get('servicios_matriz', {}),
        'avisos': res['avisos'],
        'exigencias': exig,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description='Normaliza las exigencias de la Res. 3100 (contrato, 4.2).')
    ap.add_argument('--verificar', action='store_true', help='no escribe; sale con 1 si el archivo cambiaría')
    ap.add_argument('--salida', type=Path, default=C.EXIGENCIAS)
    a = ap.parse_args(argv)
    try:
        datos = construir()
    except (ErrorNormalizacion, FileNotFoundError, ValueError) as err:
        sys.stderr.write(f'normalizar_exigencias: {err}\n')
        return 2
    texto = C.texto_json(datos)
    k = datos['conteos']
    resumen = (f'{k["filas"]} filas · exigibles {k["por_exigible"].get("si", 0)} · por confirmar '
               f'{k["por_exigible"].get("por_confirmar", 0)} · dotación con regla automática '
               f'{k["dotacion_con_regla_automatica"]["porcentaje"]} % · avisos {len(datos["avisos"])}')
    if a.verificar:
        actual = a.salida.read_text(encoding='utf-8') if a.salida.exists() else None
        if actual != texto:
            sys.stderr.write(f'normalizar_exigencias: {C.relativa(a.salida)} no está al día ({resumen})\n')
            return 1
        sys.stderr.write(f'normalizar_exigencias: al día ({resumen})\n')
        return 0
    escribio = C.escribir_json(a.salida, datos)
    sys.stderr.write(f'normalizar_exigencias: {"escrito" if escribio else "sin cambios"} {C.relativa(a.salida)} ({resumen})\n')
    for av in datos['avisos']:
        sys.stderr.write(f'  aviso: {av}\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
