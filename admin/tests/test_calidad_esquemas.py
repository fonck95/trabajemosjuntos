"""Las herramientas de datos y calidad del asistente (`herramientas/fichas.py` y `herramientas/calidad.py`) en el
catálogo: su lugar en `fijas()`, qué rol recibe cada una (los permisos de la API), su marca para MCP, sus plazos y las
reglas del esquema que la Messages API entiende (las mismas de test_agente_personas y test_agente_gestion). Sin
datos de personas."""
from __future__ import annotations

import json
import re

import pytest
from pydantic import ValidationError

from ayudas_calidad import H, roles
from app.agente import herramientas
from app.agente.herramientas import calidad as hc
from app.agente.herramientas import fichas as hf
from app.agente.herramientas import gestion as hg
from app.agente.herramientas import personas as hp

MIAS = set(H)
LECTURAS = {"historial_acercamientos", "autorizaciones_de", "coincidencias", "conflictos_cedula", "situaciones",
            "solicitudes", "importaciones", "puestos", "lugares_sin_reconocer"}
ESCRITURAS = MIAS - LECTURAS
DE_TODOS = {"historial_acercamientos", "reportar_situacion", "registrar_solicitud", "marcar_no_disponible",
            "estado_telefono", "anular_acercamiento", "puestos"}
DEL_ROL = {
    "admin": MIAS, "coordinador": MIAS,
    "planillero": DE_TODOS | {"reportar_duplicado", "pedir_actualizacion", "editar_reunion", "quitar_asistente"},
    "consultor": DE_TODOS,
}
PALABRAS_ESQUEMA = {"type", "properties", "required", "additionalProperties", "description", "enum", "items",
                    "minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems", "default", "anyOf"}


def _palabras(s, ruta=""):
    if isinstance(s, dict):
        for k, v in s.items():
            if k == "properties":
                for nombre, sub in v.items():
                    yield from _palabras(sub, f"{ruta}.{nombre}")
            else:
                yield ruta, k
                yield from _palabras(v, f"{ruta}.{k}")
    elif isinstance(s, list):
        for v in s:
            yield from _palabras(v, ruta)


def _objetos(s):
    if isinstance(s, dict):
        if s.get("type") == "object":
            yield s
        for v in s.values():
            yield from _objetos(v)
    elif isinstance(s, list):
        for v in s:
            yield from _objetos(v)


def test_las_dos_listas_tienen_las_herramientas_de_su_modulo():
    assert [h.nombre for h in hf.HERRAMIENTAS] == [
        "historial_acercamientos", "autorizaciones_de", "reportar_situacion", "registrar_solicitud",
        "reportar_duplicado", "marcar_no_disponible", "pedir_actualizacion", "estado_telefono", "anular_acercamiento",
        "editar_reunion", "quitar_asistente"]
    assert [h.nombre for h in hc.HERRAMIENTAS] == [
        "coincidencias", "resolver_coincidencias", "conflictos_cedula", "resolver_conflicto", "situaciones",
        "confirmar_situacion", "solicitudes", "actualizar_solicitud", "importaciones", "puestos",
        "lugares_sin_reconocer", "agregar_alias_lugar"]
    assert len(MIAS) == 23


def test_van_entre_las_de_personas_y_las_de_gestion_sin_nombres_repetidos():
    nombres = [h.nombre for h in herramientas.fijas()]
    assert len(nombres) == len(set(nombres))
    n = len(hp.HERRAMIENTAS)
    assert nombres[:n] == [h.nombre for h in hp.HERRAMIENTAS]
    assert nombres[n:n + len(hf.HERRAMIENTAS)] == [h.nombre for h in hf.HERRAMIENTAS]
    assert nombres[n + len(hf.HERRAMIENTAS):n + len(hf.HERRAMIENTAS) + len(hc.HERRAMIENTAS)] == \
        [h.nombre for h in hc.HERRAMIENTAS]
    assert nombres.index("indicadores") > max(nombres.index(x) for x in MIAS)
    assert set(herramientas.por_nombre()) >= MIAS


def test_definiciones_son_json_schema_validos_para_la_messages_api():
    for h in hf.HERRAMIENTAS + hc.HERRAMIENTAS:
        d = h.definicion()
        assert set(d) == {"name", "description", "input_schema", "eager_input_streaming"}, h.nombre
        assert re.fullmatch(r"[a-z_]{3,64}", d["name"]) and d["eager_input_streaming"] is True
        assert 200 < len(d["description"]) < 1500, (h.nombre, len(d["description"]))
        assert re.match(r"^\w+(ando|endo|iendo)\b", h.etiqueta), h.etiqueta  # en gerundio
        s = d["input_schema"]
        texto = json.dumps(s, ensure_ascii=False)
        assert "$ref" not in texto and "$defs" not in texto and '"title"' not in texto and "\\n" not in texto
        assert s["type"] == "object" and isinstance(s["properties"], dict) and s["properties"], h.nombre
        for obj in _objetos(s):  # todo objeto, también los anidados: cerrado y con sus obligatorias declaradas
            assert obj.get("additionalProperties") is False, h.nombre
            assert set(obj.get("required", [])) <= set(obj.get("properties", {})), h.nombre
        for ruta, k in _palabras(s):
            assert k in PALABRAS_ESQUEMA, (h.nombre, ruta, k)
        for nombre, prop in s["properties"].items():
            assert "type" in prop or "anyOf" in prop or "enum" in prop, (h.nombre, nombre)
        # Lo que pone `confirmar` (huellas, la vista previa de la unión) nunca se le muestra al modelo
        assert not {"huellas", "previas", "base"} & set(s["properties"]), h.nombre
        assert (h.tipo == "escritura") == (h.confirmar is not None) == (h.nombre in ESCRITURAS), h.nombre
        assert h.tipo == ("lectura" if h.nombre in LECTURAS else "escritura"), h.nombre
        assert h.esquema == hg.esquema(h.entrada)  # el esquema plano de gestión


def test_marcas_para_mcp_lecturas_y_escrituras():
    """Por MCP salen solo las marcadas: las lecturas con «lectura» (también `solicitudes`, que no trae personas) y las
    escrituras con «escritura» (allá quedan como propuestas que la persona aprueba en el panel)."""
    for h in hf.HERRAMIENTAS + hc.HERRAMIENTAS:
        assert h.mcp == ("lectura" if h.nombre in LECTURAS else "escritura"), h.nombre
        assert h.alcance_mcp() == h.mcp, h.nombre


def test_el_plazo_para_anular_es_el_de_la_api():
    from app.api import acercamientos
    assert hf.HORAS_ANULAR == acercamientos.HORAS_ANULAR
    assert hf.POR_PAGINA_API == 50


def test_plazos_de_las_escrituras_largas():
    assert 150 <= H["resolver_coincidencias"].plazo <= 170
    assert 150 <= H["agregar_alias_lugar"].plazo <= 170
    assert all(H[n].plazo is None for n in MIAS - {"resolver_coincidencias", "agregar_alias_lugar"})


def test_cada_rol_recibe_solo_las_herramientas_de_sus_permisos(sesion, como):
    cfg = sesion.app.state.cfg
    for rol, (_, quien) in roles(sesion, como).items():
        nombres = {h.nombre for h in herramientas.para(quien, {"escritura": True}, cfg)}
        assert nombres & MIAS == DEL_ROL[rol], (rol, sorted(nombres & MIAS ^ DEL_ROL[rol]))
        # Sin escritura en Ajustes, solo las de lectura
        sin = {h.nombre for h in herramientas.para(quien, {"escritura": False}, cfg)} & MIAS
        assert sin == DEL_ROL[rol] - ESCRITURAS, rol
    # Las de Calidad (A y K) piden los permisos de sus rutas
    assert H["coincidencias"].permisos == H["resolver_coincidencias"].permisos == ("admin",)
    assert H["conflictos_cedula"].permisos == H["situaciones"].permisos == H["solicitudes"].permisos == \
        ("calidad.ver",)
    assert H["resolver_conflicto"].permisos == H["confirmar_situacion"].permisos == \
        H["actualizar_solicitud"].permisos == ("calidad.resolver",)
    assert H["importaciones"].permisos == ("importar",)


@pytest.mark.parametrize("nombre, entrada", [
    ("historial_acercamientos", {"persona_id": True}),
    ("historial_acercamientos", {"persona_id": 1, "pagina": 99}),
    ("autorizaciones_de", {"persona_id": 1, "sensibles": True}),
    ("reportar_situacion", {"persona_id": 1, "situacion": "activa"}),
    ("registrar_solicitud", {"tipo": "supresion", "canal": "visita", "descripcion": "Que borren mis datos"}),
    ("registrar_solicitud", {"persona_id": 1, "tipo": "consulta", "canal": "paloma", "descripcion": "Qué tienen"}),
    ("reportar_duplicado", {"persona_id": 4, "con_id": 4}),
    ("marcar_no_disponible", {"persona_id": 1, "campo": "cedula"}),
    ("marcar_no_disponible", {"persona_id": 1, "campo": "cedula", "motivo": "no_tiene", "quitar": True}),
    ("marcar_no_disponible", {"persona_id": 1, "campo": "correo", "motivo": "no_tiene"}),
    ("pedir_actualizacion", {"persona_id": 1, "accion": "borrar"}),
    ("estado_telefono", {"persona_id": 1, "estado": "confirmado"}),
    ("estado_telefono", {"persona_id": 1, "telefono_indice": 0, "telefono_posicion": 0, "estado": "confirmado"}),
    ("estado_telefono", {"persona_id": 1, "telefono_indice": 0}),
    ("estado_telefono", {"persona_id": 1, "telefono_indice": 0, "estado": "equivocado", "principal": True}),
    ("estado_telefono", {"persona_id": 1, "telefono_indice": 0, "numero": "3001112233", "estado": "confirmado"}),
    ("anular_acercamiento", {"persona_id": 1, "acercamiento_id": 2, "motivo": ""}),
    ("editar_reunion", {"reunion_id": 1}),
    ("editar_reunion", {"reunion_id": 1, "lugar": "La Paz", "lugar_id": 3}),
    ("editar_reunion", {"reunion_id": 1, "titulo": ""}),
    ("editar_reunion", {"reunion_id": 1, "fecha": "2026-02-30"}),
    ("resolver_coincidencias", {"grupos": []}),
    ("resolver_coincidencias", {"grupos": [{"clave": "1-2; borrar", "decision": "unir"}]}),
    ("resolver_coincidencias", {"grupos": [{"clave": "1-2", "decision": "separar", "conservar": 3}]}),
    ("resolver_coincidencias", {"grupos": [{"clave": "1-2", "decision": "unir", "conservar": 3, "excluir": [3]}]}),
    ("resolver_coincidencias", {"grupos": [{"clave": "1-2", "decision": "unir"}, {"clave": "2", "decision": "unir"}]}),
    ("resolver_coincidencias", {"grupos": [{"clave": str(i), "decision": "unir"} for i in range(1, 7)]}),
    ("resolver_coincidencias", {"grupos": [{"clave": "1", "decision": "unir"}],
                                "previas": {"1": {"huella": "x", "destino": 1}}}),
    ("resolver_conflicto", {"conflicto_id": 1, "decision": "corregir"}),
    ("resolver_conflicto", {"conflicto_id": 1, "decision": "corregir", "cedula_correcta": "12AB345"}),
    ("resolver_conflicto", {"conflicto_id": 1, "decision": "descartar", "cedula_correcta": "1234567"}),
    ("confirmar_situacion", {"persona_id": 1, "decision": "borrar"}),
    ("actualizar_solicitud", {"solicitud_id": 1}),
    ("solicitudes", {"estado": "abiertas", "persona_id": 4}),
    ("agregar_alias_lugar", {"lugar_id": 1, "texto": "x"}),
])
def test_entradas_invalidas_se_rechazan(nombre, entrada):
    with pytest.raises(ValidationError):
        H[nombre].validar(entrada)


def test_huellas_ocultas_que_no_cumplen_se_rechazan():
    for nombre, entrada in (("estado_telefono", {"persona_id": 1, "telefono_indice": 0, "estado": "confirmado"}),
                            ("editar_reunion", {"reunion_id": 1, "titulo": "Reunión inventada"})):
        with pytest.raises(ValidationError):
            H[nombre].validar({**entrada, "huellas": {"telefono": "no-es-hexa"}})
    with pytest.raises(ValidationError):  # una huella de un campo que la tarjeta no muestra
        H["editar_reunion"].validar({"reunion_id": 1, "titulo": "Reunión inventada", "huellas": {"cedula": "a" * 24}})
