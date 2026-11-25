"""La documentación del asistente (docs/agente.md y README.md) dice lo que el código hace: que nombre cada herramienta
con su tipo y quién la recibe, los nombres exactos que salen por cada alcance de MCP, los ajustes nuevos con sus
valores por defecto, los archivos que existen y enlaces internos que llevan a una sección que existe; y que ya no diga
que el asistente nunca importa ni une, ni que la clave MCP no ve datos de personas. Sin MongoDB ni modelo.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app import acceso
from app.agente import herramientas as H
from app.agente import politica

RAIZ = Path(__file__).resolve().parents[1]
DOC = (RAIZ / "docs" / "agente.md").read_text(encoding="utf-8")
README = (RAIZ / "README.md").read_text(encoding="utf-8")
LETRA = {"admin": "A", "coordinador": "K", "planillero": "P", "consultor": "C"}


def _sin_codigo(texto: str) -> list[str]:
    """Las líneas fuera de los bloques de código."""
    fuera, codigo = [], False
    for linea in texto.split("\n"):
        if linea.startswith("```"):
            codigo = not codigo
        elif not codigo:
            fuera.append(linea)
    return fuera


def _seccion(texto: str, titulo: str) -> str:
    """El texto de una sección `## titulo` hasta la siguiente del mismo nivel."""
    i = texto.index(f"\n## {titulo}\n")
    j = texto.find("\n## ", i + 1)
    return texto[i: j if j > 0 else len(texto)]


def _plano(texto: str) -> str:
    """El texto con los saltos de línea y los espacios seguidos en uno: las frases se buscan sin depender del ajuste."""
    return " ".join(texto.split())


def _slug(titulo: str) -> str:
    """El ancla que GitHub le da a un título: minúsculas, sin puntuación, espacios a guiones."""
    return re.sub(r"[^\w\- ]", "", titulo.strip().lower()).replace(" ", "-")


def _filas_de_herramientas() -> dict[str, tuple[str, str]]:
    """{herramienta: (tipo, quién)} de las tablas `| Herramienta | Tipo | Quién | Qué hace |` de «Qué puede hacer»."""
    filas: dict[str, tuple[str, str]] = {}
    for linea in _seccion(DOC, "Qué puede hacer").split("\n"):
        celdas = [c.strip() for c in linea.strip().strip("|").split("|")]
        if len(celdas) < 4 or not celdas[0].startswith("`"):
            continue
        for nombre in re.findall(r"`([a-z_]+)`", celdas[0]):
            assert nombre not in filas, f"{nombre} está dos veces en las tablas"
            filas[nombre] = (celdas[1], celdas[2])
    return filas


def _roles_que_la_reciben(h) -> set[str]:
    ajustes = {"agente_planillas": politica.ajustes_planillas(
        {"agente_planillas": {"roles": list(politica.ROLES_PLANILLAS)}})}
    agente = politica.ajustes_agente({"agente": {"roles": list(politica.ROLES)}})
    return {LETRA[rol] for rol in politica.ROLES
            if politica.ofrecida(h, acceso.Quien(uid=7, usuario="u", nombre="U", rol=rol,
                                                 permisos=acceso.PERMISOS[rol]), agente, None, ajustes=ajustes)}


# ───────────────────────────── Las herramientas ─────────────────────────────

def test_cada_herramienta_del_catalogo_esta_en_las_tablas_con_su_tipo_y_quien_la_recibe():
    filas = _filas_de_herramientas()
    catalogo = {h.nombre: h for h in H.fijas()}
    assert set(catalogo) <= set(filas), sorted(set(catalogo) - set(filas))
    assert set(filas) <= set(catalogo), sorted(set(filas) - set(catalogo))   # ninguna que ya no existe
    for nombre, h in catalogo.items():
        tipo, quien = filas[nombre]
        assert tipo.startswith(h.tipo), (nombre, tipo, h.tipo)
        letras = {"A", "K", "P", "C"} if quien.startswith("todos") else set(re.findall(r"\b([AKPC])\b",
                                                                                        quien.split("(")[0]))
        assert letras == _roles_que_la_reciben(h), (nombre, quien, _roles_que_la_reciben(h))


def test_los_plazos_propios_estan_en_limites_y_costos():
    limites = " ".join(_seccion(DOC, "Límites y costos").split())
    for h in H.fijas():
        if h.plazo:
            assert re.search(rf"`{h.nombre}`[^;]*?{int(h.plazo)}\b", limites), h.nombre


# ───────────────────────────── MCP ─────────────────────────────

def _nombres_del_alcance(texto: str, alcance: str) -> set[str]:
    m = re.search(rf"^- \*\*{alcance}:\*\*(.*?)(?=^- \*\*|\n\n)", texto, re.S | re.M)
    assert m, alcance
    # fuera del conjunto: el parámetro de toda propuesta, la herramienta que solo existe por MCP y el nombre del alcance
    return set(re.findall(r"`([a-z_]+)`", m.group(1))) - {"motivo_propuesta", "estado_propuesta", alcance}


@pytest.mark.parametrize("alcance", ["lectura", "analitica", "escritura"])
def test_los_nombres_por_alcance_de_mcp_son_los_del_catalogo(alcance):
    texto = _seccion(DOC, "Agentes por MCP con datos")
    assert _nombres_del_alcance(texto, alcance) == {h.nombre for h in H.fijas() if h.mcp == alcance}


def test_lo_que_nunca_sale_por_mcp_no_tiene_marca():
    texto = _seccion(DOC, "Agentes por MCP con datos")
    m = re.search(r"^- \*\*Nunca por MCP:\*\*(.*?)\n\n", texto, re.S | re.M)
    catalogo = {h.nombre: h for h in H.fijas()}
    nunca = set(re.findall(r"`([a-z_]+)`", m.group(1)))
    assert {"registrar_autorizacion", "equipo", "mi_trabajo", "mapa", "abrir_vista", "presentacion"} <= nunca
    for nombre in nunca:
        assert catalogo[nombre].mcp is None, nombre
    for h in catalogo.values():   # las de planillas, aunque el texto las nombre en grupo
        if h.nombre in {"planillas", "leer_planilla", "cotejar_planilla", "cargar_planilla"}:
            assert h.mcp is None


def test_la_clave_de_la_presentacion_y_la_de_datos_no_se_confunden():
    pantalla = _plano(_seccion(DOC, "Pantalla en off y agentes por MCP"))
    assert "Con la clave de la presentación no se lee ni se escribe ningún dato de personas" in pantalla
    assert "Una por persona: crear otra reemplaza la anterior" not in _plano(DOC)
    datos = _plano(_seccion(DOC, "Agentes por MCP con datos"))
    for parte in ("`ypm_`", "`ypd_`", "30 días", "**Solo** `Authorization: Bearer`", "**Solo el administrador**",
                  "motivo_propuesta", "/cuenta?propuesta=<id>", "48 h", "`propuestas_mcp`", "INSIGNIAS.cuenta",
                  "una por una", "yondo-datos"):
        assert parte in datos, parte
    assert "MCP (clave en Mi cuenta)" not in README and "clave de la presentación" in README


# ───────────────────────────── Ajustes ─────────────────────────────

def test_los_ajustes_nuevos_estan_con_su_valor_por_defecto():
    ajustes = _seccion(DOC, "Ajustes")
    for clave in politica.PLANILLAS_POR_DEFECTO:
        assert f"`agente_planillas.{clave}`" in ajustes, clave
    for clave in politica.MCP_POR_DEFECTO:
        assert f"`agente_mcp.{clave}`" in ajustes, clave
    fila = lambda clave: next(x for x in ajustes.split("\n") if clave in x and x.startswith("|"))  # noqa: E731
    assert f"| {politica.PLANILLAS_POR_DEFECTO['retencion_horas']} |" in fila("agente_planillas.retencion_horas")
    assert "| No |" in fila("agente_planillas.otros_formatos") and not politica.PLANILLAS_POR_DEFECTO["otros_formatos"]
    assert "| Sí |" in fila("agente_mcp.escritura") and politica.MCP_POR_DEFECTO["escritura"] is True
    assert "| 2.000 |" in fila("agente_mcp.llamadas_diarias") and politica.MCP_POR_DEFECTO["llamadas_diarias"] == 2000
    assert "| 300 |" in fila("agente_mcp.personas_diarias") and politica.MCP_POR_DEFECTO["personas_diarias"] == 300
    assert "| Administrador y coordinadores |" in fila("agente_planillas.roles")
    assert politica.PLANILLAS_POR_DEFECTO["roles"] == ["admin", "coordinador"]
    assert "| Administrador |" in fila("agente_mcp.roles") and politica.MCP_POR_DEFECTO["roles"] == ["admin"]


# ───────────────────────────── Lo que cambió de «nunca» y la privacidad ─────────────────────────────

def test_ya_no_dice_que_nunca_importa_ni_une_y_sigue_diciendo_lo_que_nunca_hace():
    nunca = _plano(DOC[DOC.index("Nunca, para nadie:"):DOC.index("Dos «nunca» cambiaron")])
    assert "importar" not in nunca and "unir" not in nunca
    for parte in ("exportar", "suprimir datos", "usuarios", "ajustes", "confirmar las autorizaciones declaradas",
                  "datos sensibles"):
        assert parte in nunca, parte
    fin = DOC.index("Las herramientas del panel (`app/agente/herramientas/`)")
    cambios = _plano(DOC[DOC.index("Dos «nunca» cambiaron"):fin])
    assert "**Importar**" in cambios and "**Unir fichas**" in cambios and "planillas físicas fotografiadas" in cambios
    seguridad = _plano(_seccion(DOC, "Seguridad"))
    assert "exportar, importar, unir, suprimir" not in seguridad
    assert "Importar y unir existen solo de una forma" in seguridad
    assert "No hay herramientas para exportar, importar, unir" not in _plano(README)


def test_la_excepcion_de_las_fotos_esta_documentada():
    privacidad = _plano(_seccion(DOC, "Privacidad y protección de datos (Ley 1581 de 2012)"))
    excepcion = privacidad[privacidad.index("### La excepción de las fotos de planillas"):]
    for parte in ("**va entera al proveedor del modelo**", "llamada de lectura aparte", "Revisión jurídica antes de "
                  "encenderlo", "`acceso.COMPROMISOS`", "AES-GCM", "`agente_planillas.retencion_horas`",
                  "SHA-256", "`declarado_planilla`", "dato", "Auditoría sin datos de personas"):
        assert parte in excepcion, parte
    for parte in ("`planillas_subidas`", "`mcp_propuestas`", "`mcp_entregas`", "`db.vaciar_planillas`",
                  "`db.borrar_propuestas_mcp`", "**fotos de planillas** son una transmisión más amplia"):
        assert parte in privacidad, parte
    assert "excepción documentada" in README and "planilla física" in README
    assert "versión nueva del compromiso de confidencialidad" in _plano(README)


def test_las_secciones_nuevas_y_lo_que_dicen():
    planillas = _plano(_seccion(DOC, "Planillas físicas por foto"))
    for parte in ("leer → preguntar lo dudoso → cotejar → cargar", "`<fotos_adjuntas>`", "(Envié fotos sin texto.)",
                  "**El modelo nunca recibe la imagen.**", "`/importar?planilla=<id>`", "**en su propia tarjeta**",
                  "`cambiada`", "2 lecturas por foto", "`POST /api/planillas/fotos?nota=&formato=`"):
        assert parte in planillas, parte
    analisis = _plano(_seccion(DOC, "Análisis avanzados"))
    from app import analitica
    assert len(analitica.ANALISIS) >= 16
    for tipo in analitica.ANALISIS:   # cada tipo del motor tiene su fila en la tabla
        assert f"| `{tipo}` |" in analisis, tipo
    for parte in ('`{"pocas": true, "personas": "<10"}`', "«<5»", "«oculta»", "`dispersas`", "`analitica.fijadas`",
                  "**Límite conocido**", "`grafico`"):
        assert parte in analisis, parte
    calidad = _plano(_seccion(DOC, "Registros de cada persona y calidad de datos"))
    assert "`POST /api/lugares/{lid}/alias`" in calidad and "nunca su texto" in calidad


# ───────────────────────────── Archivos y enlaces ─────────────────────────────

def test_los_archivos_que_nombra_existen():
    raiz_repo = RAIZ.parent
    texto = "\n".join(_sin_codigo(DOC)) + "\n" + README
    rutas = set(re.findall(r"`((?:app|web|tests|docs|scripts)/[\w./-]+\.(?:py|js|css|md|json|html))`", texto))
    faltan = sorted(r for r in rutas if not (RAIZ / r).exists() and not (raiz_repo / r).exists())
    assert faltan == [], faltan
    arquitectura = _seccion(DOC, "Arquitectura")
    for nuevo in ("app/analitica.py", "app/api/analitica.py", "app/planillas.py", "app/api/planillas.py",
                  "app/agente/lector_planillas.py", "app/agente/grafico.py", "app/sesion_interna.py",
                  "web/js/agente-graficos.js", "web/js/vistas/importar.js", "web/css/planillas.css", "web/js/app.js",
                  "fichas.py", "calidad.py", "planillas.py", "analisis.py"):
        assert nuevo in arquitectura, nuevo


def test_los_enlaces_internos_llevan_a_una_seccion_que_existe():
    anclas: dict[str, int] = {}
    for linea in _sin_codigo(DOC):
        m = re.match(r"^(#{1,6})\s+(.*)$", linea)
        if m:
            s = _slug(m.group(2))
            anclas[s] = anclas.get(s, 0) + 1
    validas = {s for s in anclas} | {f"{s}-{i}" for s, n in anclas.items() for i in range(1, n)}
    del_doc = set(re.findall(r"\]\(#([^)]+)\)", DOC))
    del_readme = set(re.findall(r"docs/agente\.md#([^)]+)\)", README))
    assert del_doc - validas == set() and del_readme - validas == set()
    for nueva in ("planillas-físicas-por-foto", "análisis-avanzados", "agentes-por-mcp-con-datos",
                  "registros-de-cada-persona-y-calidad-de-datos", "la-excepción-de-las-fotos-de-planillas"):
        assert nueva in validas and nueva in del_doc, nueva


def test_el_readme_presenta_lo_nuevo():
    modulos = README[README.index("| Módulo | Qué ofrece |"):README.index("**Nueva persona y Completar.**")]
    importar = next(x for x in modulos.split("\n") if x.startswith("| **Importar y exportar**"))
    asistente = next(x for x in modulos.split("\n") if x.startswith("| **Asistente**"))
    assert "**Planillas por foto**" in importar and "folio" in importar and "declaradas" in importar
    asistente = _plano(asistente)
    for parte in ("**análisis avanzados**", "**diagnóstico**", "**Calidad de datos**", "**planillas físicas por foto**",
                  "**clave de datos**", "Mi cuenta → Agentes por MCP", "el menú cuenta"):
        assert parte in asistente, parte
