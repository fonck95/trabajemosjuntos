"""Lo que une las piezas del asistente (núcleo, herramientas y Mnemo) y que ninguna prueba de cada pieza ve sola.

Solo datos inventados; la Messages API va simulada (`ayudas_agente`)."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import BaseModel

import ayudas_agente as aa
from ayudas_g3 import persona


def _herramienta_falsa(nombre: str, ejecutar, tipo: str = "lectura"):
    from app.agente.herramientas.base import Herramienta

    class Nada(BaseModel):
        pass

    return Herramienta(nombre=nombre, descripcion="Herramienta de prueba.", entrada=Nada, tipo=tipo,
                       permisos=("personas.buscar",), etiqueta="Probando", ejecutar=ejecutar)


def test_editar_por_el_bucle_no_escribe_si_la_ficha_cambio_entre_la_tarjeta_y_la_aprobacion(sesion):
    """La tarjeta guarda huellas de lo que mostró y el bucle guarda la entrada con ellas: si otra persona cambió el
    dato antes de aprobar, la escritura no se hace y el modelo recibe el conflicto."""
    db = sesion.app.state.db
    pid = persona(db, nombre="RIGOBERTA CAMBIADA INVENTADA", consentimiento="si")
    api = aa.encender(sesion.app,
                      aa.sse(aa.TU("toolu_e", "editar_persona", {"persona_id": pid,
                                                                 "cambios": {"ocupacion": "Pescadora"}}),
                             stop="tool_use"))
    r, ev = aa.enviar(sesion, "Ponga que Rigoberta es pescadora")
    assert r.status_code == 200 and ev[-1]["motivo"] == "confirmacion", r.text
    cid = ev[0]["conversacion"]
    pendiente = json.loads(db.agente_conversaciones.find_one({"_id": cid})["pendiente"])
    guardada = json.loads(pendiente["llamadas"][0]["entrada"])
    assert set(guardada.get("huellas") or {}) == {"ocupacion"}  # la entrada validada, con las huellas de la tarjeta
    db.personas.update_one({"_id": pid}, {"$set": {"ocupacion": "Docente"}})  # otra persona la editó
    api.agregar(aa.sse(aa.T("La ficha cambió: no la toqué.")))
    r, ev = aa.decidir(sesion, cid, toolu_e=True)
    assert r.status_code == 200 and ev[-1]["motivo"] == "listo", r.text
    assert db.personas.find_one({"_id": pid})["ocupacion"] == "Docente"
    resultado = api.peticiones[1]["json"]["messages"][-1]["content"][0]
    assert resultado["tool_use_id"] == "toolu_e" and resultado.get("is_error") is True
    assert json.loads(resultado["content"])["error"]["codigo"] == "cambiada"
    assert db.auditoria.count_documents({"accion": "editar", "entidad_id": pid}) == 0


def test_una_busqueda_por_numero_no_trae_los_digitos_enmascarados(sesion):
    """La API compara la cédula por prefijo: con los últimos dígitos en la fila, unas pocas búsquedas por prefijo
    reconstruirían la cédula enmascarada. Por nombre, la fila sí los trae."""
    from app.agente.herramientas import por_nombre
    db = sesion.app.state.db
    persona(db, nombre="HERMENEGILDA NUMERICA INVENTADA", cedula="1023456789", telefono="3104445566",
            consentimiento="si")
    h = por_nombre()["buscar_personas"]
    ctx = aa.contexto(sesion.app, sesion)
    try:
        por_numero = aa.correr(sesion, aa.ejecutar, h, ctx, {"q": "102345"}).contenido
        por_nombre_ = aa.correr(sesion, aa.ejecutar, h, ctx, {"q": "HERMENEGILDA"}).contenido
        con_filtros = aa.correr(sesion, aa.ejecutar, h, ctx, {"q": "3104445", "filtros": {"con_cedula": 1}}).contenido
    finally:
        aa.correr(sesion, ctx.api.cerrar)
    assert por_numero["filas"] and "nota" in por_numero
    assert all("cedula_ult3" not in f and "telefono_mascara" not in f for f in por_numero["filas"])
    assert con_filtros["filas"] and all("cedula_ult3" not in f for f in con_filtros["filas"]) and "nota" in con_filtros
    assert por_nombre_["filas"][0]["cedula_ult3"] == "···789" and "nota" not in por_nombre_
    assert "1023456789" not in json.dumps([por_numero, por_nombre_, con_filtros])


def test_las_herramientas_de_mnemo_tienen_su_propio_plazo():
    from app.agente import mnemo_cliente as mc
    from app.agente.bucle import PLAZO_HERRAMIENTA_S, _plazo

    async def nada(ctx, args):  # pragma: no cover - no se ejecuta
        raise AssertionError

    async def tarjeta(ctx, args):  # pragma: no cover
        raise AssertionError

    panel = _herramienta_falsa("panel_falsa", nada)
    lectura = _herramienta_falsa("mnemo_falsa", nada)
    lectura.nombre_remoto = "search"
    escritura = _herramienta_falsa("mnemo_escribe", nada)
    escritura.tipo, escritura.confirmar, escritura.nombre_remoto = "escritura", tarjeta, "mnemo_create_event"
    assert _plazo(panel) == PLAZO_HERRAMIENTA_S
    assert _plazo(lectura) == mc.PLAZO_LECTURA_S + mc.PLAZO_CATALOGO_S + 5
    assert _plazo(escritura) == mc.PLAZO_ESCRITURA_S + mc.PLAZO_CATALOGO_S + 5 > _plazo(lectura) > _plazo(panel)


def test_las_imagenes_de_una_ronda_tienen_tope(sesion, monkeypatch):
    """Los resultados de una ronda van en un solo mensaje guardado en MongoDB (16 MB por documento): pasado el tope,
    las imágenes que sobran se omiten y el modelo lo sabe."""
    from app.agente import bucle
    from app.agente.herramientas.base import Resultado
    monkeypatch.setattr(bucle, "TOPE_IMAGENES", 3_000)
    imagen = {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "A" * 2_000}}

    async def con_imagenes(ctx, args):
        return Resultado({"ok": True}, "Dos imágenes", imagenes=[imagen, imagen])

    aa.con_herramientas(monkeypatch, [_herramienta_falsa("imagenes_falsa", con_imagenes)])
    api = aa.encender(sesion.app, aa.sse(aa.TU("toolu_i", "imagenes_falsa", {}), stop="tool_use"),
                      aa.sse(aa.T("Veo una imagen.")))
    r, ev = aa.enviar(sesion, "Muéstrame las imágenes")
    assert r.status_code == 200 and ev[-1]["motivo"] == "listo", r.text
    contenido = api.peticiones[1]["json"]["messages"][-1]["content"][0]["content"]
    assert [b["type"] for b in contenido] == ["text", "image"]
    assert "omitida" in contenido[0]["text"]


def test_bajar_la_retencion_durante_un_turno_vale_para_lo_que_ese_turno_guardo(sesion, monkeypatch):
    """El turno leyó la retención al empezar: si el administrador la baja mientras corre, al terminar se vuelve a
    fijar la fecha de borrado con la vigente (si no, lo de ese turno quedaba con el plazo viejo)."""
    from app.agente.herramientas.base import Resultado
    db = sesion.app.state.db

    async def baja_la_retencion(ctx, args):
        ctx.db.meta.update_one({"_id": "ajustes"}, {"$set": {"agente": {
            "roles": ["admin", "coordinador"], "escritura": True, "mnemo_coordinadores": False,
            "retencion_dias": 1}}}, upsert=True)
        return Resultado({"ok": True}, "Listo")

    aa.con_herramientas(monkeypatch, [_herramienta_falsa("retencion_falsa", baja_la_retencion)])
    aa.encender(sesion.app, aa.sse(aa.TU("toolu_r", "retencion_falsa", {}), stop="tool_use"), aa.sse(aa.T("Hecho.")))
    r, ev = aa.enviar(sesion, "Hola")
    assert r.status_code == 200 and ev[-1]["motivo"] == "listo", r.text
    cid = ev[0]["conversacion"]
    limite = datetime.now(timezone.utc) + timedelta(days=2)

    def utc(d):
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)

    assert utc(db.agente_conversaciones.find_one({"_id": cid})["expira"]) < limite
    assert all(utc(m["expira"]) < limite for m in db.agente_mensajes.find({"conversacion": cid}))


@pytest.mark.parametrize("ruta", ["/api/agente/mensajes", "/api/agente/confirmaciones"])
def test_las_rutas_en_flujo_no_se_comprimen_y_las_demas_si(sesion, ruta):
    """El GZip de Starlette retiene el flujo entero hasta el final: esas dos rutas van sin comprimir."""
    from app.main import RUTAS_EN_FLUJO
    assert ruta in RUTAS_EN_FLUJO
    assert "/api/agente/conversaciones" not in RUTAS_EN_FLUJO and "/api/agente/estado" not in RUTAS_EN_FLUJO
