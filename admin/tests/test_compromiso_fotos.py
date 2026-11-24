"""El compromiso de confidencialidad 2026-11-v2 y las planillas por foto solo para el administrador y los coordinadores
(app/acceso.py, app/agente/politica.py, app/api/planillas.py, app/api/agente.py, web/js/vistas/ajustes.js e
importar.js).

* La versión 2026-11-v2 (la de defecto) conserva los puntos de la 2026-11-v1 salvo el segundo, que deja fotografiar
  planillas físicas solo para subirlas por el panel (nunca cédulas ni otros documentos) y pide borrar la foto del
  teléfono. `compromiso_permite_fotos` sigue la regla de `texto_compromiso` (una versión sin texto propio rige con el
  de la más reciente).
* Con un compromiso vigente que no lo permite: POST /api/planillas/fotos responde 409 `compromiso_fotos` sin leer el
  cuerpo, el estado del asistente no ofrece la cámara (`adjuntos` null) y Ajustes lo advierte y ofrece la versión que
  lo permite; al cambiarla, cada persona la acepta de nuevo.
* Planilleros y consultores nunca: ni los ajustes guardados de antes los habilitan, ni la API los deja pasar (403
  `permiso` en cada ruta de la bandeja, antes del compromiso), ni la vista ni el chat se los ofrecen.
Solo datos inventados; las imágenes se generan en la prueba."""
import re
from pathlib import Path

import pytest
from fastapi.routing import APIRoute

import ayudas_agente as aa
from app import acceso, modelo
from app.agente import politica
from ayudas_g3 import coordinador
from ayudas_planillas import ProveedorFalso, asgi, cabeceras_de, encender, fila, jpeg, lectura_json, subir

WEB = Path(__file__).resolve().parents[1] / "web" / "js"
AJUSTES_JS = (WEB / "vistas" / "ajustes.js").read_text(encoding="utf-8")
IMPORTAR_JS = (WEB / "vistas" / "importar.js").read_text(encoding="utf-8")
AGENTE_JS = (WEB / "agente.js").read_text(encoding="utf-8")
V1, V2 = "2026-11-v1", "2026-11-v2"


def _sin_comentarios(texto: str) -> str:
    return "\n".join("" if l.lstrip().startswith(("//", "*", "/*")) else l for l in texto.splitlines())


def _proveedor():
    return ProveedorFalso(lectura_json([fila(1, cedula="90007001", nombre="ROSA INVENTADA FOTO", celular="3107770001",
                                             autorizacion="si", medio="escrito", mayor_18="si")]))


def _vigente(db, version: str) -> None:
    db.meta.update_one({"_id": "ajustes"}, {"$set": {"compromiso_version": version}}, upsert=True)


# ───────────────────────────── El texto y la regla ─────────────────────────────

def test_la_version_nueva_cambia_solo_el_segundo_punto_y_es_la_de_defecto():
    v1, v2 = acceso.COMPROMISOS[V1], acceso.COMPROMISOS[V2]
    assert len(v1) == len(v2) == 4
    assert [v1[0], v1[2], v1[3]] == [v2[0], v2[2], v2[3]]
    assert "fotografiaré" in v1[1] and "capturas de pantalla" in v1[1]
    segundo = v2[1]
    for frase in ("No los copiaré, exportaré ni compartiré, ni haré capturas de pantalla.",
                  "Solo fotografiaré planillas físicas", "para subirlas por el panel",
                  "Importar y exportar → Planillas por foto", "nunca cédulas ni otros documentos",
                  "Borraré la foto del teléfono después de subirla."):
        assert frase in segundo, frase
    assert modelo.AJUSTES_POR_DEFECTO["compromiso_version"] == V2
    assert acceso.texto_compromiso(None) == v2 and acceso.texto_compromiso(V1) == v1
    assert acceso.compromiso_con_fotos() == V2


def test_compromiso_permite_fotos_sigue_al_texto_que_rige(monkeypatch):
    assert acceso.compromiso_permite_fotos(V2) is True and acceso.compromiso_permite_fotos(V1) is False
    # Sin texto propio rige el de la más reciente (como `texto_compromiso`)
    assert acceso.compromiso_permite_fotos(None) is True and acceso.compromiso_permite_fotos("2027-01-v9") is True
    assert politica.fotos_permitidas({}) is True and politica.fotos_permitidas(None) is True
    monkeypatch.setitem(acceso.COMPROMISOS, "2027-02-v3", ["Uno", "Sin fotos", "Tres", "Cuatro"])
    assert acceso.texto_compromiso("2027-01-v9") == ["Uno", "Sin fotos", "Tres", "Cuatro"]
    assert acceso.compromiso_permite_fotos("2027-01-v9") is False and acceso.compromiso_permite_fotos(V2) is True
    assert politica.fotos_permitidas({"compromiso_version": V1}) is False
    assert politica.fotos_permitidas({"compromiso_version": V2}) is True
    assert politica.fotos_permitidas({}) is False  # la versión más reciente (la inventada) ya no lo permite


# ───────────────────────────── Con un compromiso que no deja fotografiar ─────────────────────────────

def test_sin_compromiso_que_lo_permita_no_se_sube_ni_se_ofrece_la_camara(cliente, sesion, monkeypatch):
    app, db = cliente.app, cliente.app.state.db
    aa.encender(app)
    encender(monkeypatch, app, _proveedor(), roles=("admin", "coordinador"))
    assert sesion.get("/api/agente/estado").json()["adjuntos"] is not None
    a = sesion.get("/api/ajustes").json()
    assert a["compromiso_permite_fotos"] is True and a["compromiso_con_fotos"] == V2
    _vigente(db, V1)
    # La subida: 409 sin leer el cuerpo
    cuerpo = jpeg()
    partes = [cuerpo[i:i + 4000] for i in range(0, len(cuerpo), 4000)]
    h = cabeceras_de(sesion, **{"content-type": "image/jpeg", "content-length": str(len(cuerpo))})
    estado, leidas, resp = asgi(app, "POST", "/api/planillas/fotos", h, partes)
    assert (estado, leidas) == (409, 0) and b'"compromiso_fotos"' in resp and "2026-11-v2" in resp.decode()
    assert db.planillas.count_documents({}) == 0 and db.planillas_subidas.count_documents({}) == 0
    # El chat no ofrece la cámara; Ajustes lo advierte y ofrece la versión que lo permite
    assert sesion.get("/api/agente/estado").json()["adjuntos"] is None
    a = sesion.get("/api/ajustes").json()
    assert a["compromiso_version"] == V1 and a["compromiso_permite_fotos"] is False and a["compromiso_con_fotos"] == V2
    # El administrador la cambia (lo que manda el botón de Ajustes): vuelve la subida
    r = sesion.put("/api/ajustes", json={"compromiso_version": V2})
    assert r.status_code == 200 and r.json()["compromiso_permite_fotos"] is True
    assert subir(sesion, cuerpo).status_code == 201
    assert sesion.get("/api/agente/estado").json()["adjuntos"] is not None


def test_cambiar_a_la_version_nueva_la_pide_aceptar_otra_vez(cliente, sesion, monkeypatch):
    app, db = cliente.app, cliente.app.state.db
    _vigente(db, V1)
    k = coordinador(app, db)  # aceptó la 2026-11-v1
    assert k.get("/api/yo").json()["compromiso"]["puntos"] == acceso.COMPROMISOS[V1]
    # El coordinador no la cambia (es un ajuste de permisos)
    r = k.put("/api/ajustes", json={"compromiso_version": V2})
    assert r.status_code == 403 and r.json()["detail"]["campos"] == ["compromiso_version"]
    assert sesion.put("/api/ajustes", json={"compromiso_version": V2}).status_code == 200
    r = k.get("/api/planillas")
    assert r.status_code == 403 and r.json()["detail"]["codigo"] == "compromiso"
    yo = k.get("/api/yo").json()
    assert yo["compromiso_pendiente"] is True and yo["compromiso"]["version"] == V2
    assert yo["compromiso"]["puntos"] == acceso.COMPROMISOS[V2]
    assert k.post("/api/yo/compromiso", json={"version": V2}).status_code == 200
    encender(monkeypatch, app, _proveedor(), roles=("admin", "coordinador"))
    assert subir(k, jpeg()).status_code == 201
    k.close()


# ───────────────────────────── Solo A y K ─────────────────────────────

def test_los_roles_de_las_fotos_son_solo_a_y_k():
    assert politica.ROLES_PLANILLAS == ("admin", "coordinador")
    guardado = {"agente_planillas": {"roles": ["planillero", "admin", "consultor"]}}
    assert politica.ajustes_planillas(guardado)["roles"] == ["admin"]
    for rol in ("planillero", "consultor"):
        q = acceso.Quien(uid=5, usuario="u5", rol=rol, permisos=acceso.PERMISOS[rol])
        assert not politica.usa_planillas(q, {"agente_planillas": {"roles": [rol]}})
        assert not q.puede("importar")
    k = acceso.Quien(uid=6, usuario="k6", rol="coordinador", permisos=acceso.PERMISOS["coordinador"])
    assert politica.usa_planillas(k, {}) and not politica.usa_planillas(k, {"agente_planillas": {"roles": ["admin"]}})


def test_cada_ruta_de_la_bandeja_exige_importar(cliente):
    rutas = [r for r in cliente.app.routes if isinstance(r, APIRoute) and r.path.startswith("/api/planillas")]
    assert len(rutas) >= 9
    for r in rutas:
        deps = [d.call for d in r.dependant.dependencies if hasattr(d.call, "permisos")]
        assert [set(d.permisos) for d in deps] == [{"importar"}], r.path


def test_el_planillero_recibe_permiso_antes_que_el_compromiso(cliente, como, monkeypatch):
    app, db = cliente.app, cliente.app.state.db
    encender(monkeypatch, app, _proveedor(), roles=("admin", "coordinador", "planillero"))
    p = como("planillero")
    _vigente(db, V1)
    db.usuarios.update_one({"_id": p.uid}, {"$set": {"compromiso_version": V1}})
    cuerpo = jpeg()
    h = cabeceras_de(p, **{"content-type": "image/jpeg", "content-length": str(len(cuerpo))})
    estado, leidas, resp = asgi(app, "POST", "/api/planillas/fotos", h, [cuerpo])
    assert (estado, leidas) == (403, 0) and b'"permiso"' in resp


# ───────────────────────────── La interfaz ─────────────────────────────

def test_ajustes_advierte_y_ofrece_la_version_que_permite_fotos():
    codigo = _sin_comentarios(AJUSTES_JS)
    assert "const ROLES_PLANILLAS = [['admin', 'Administrador'], ['coordinador', 'Coordinadores']];" in codigo
    assert "planillero" not in re.search(r"const ROLES_PLANILLAS = \[(.*?)\];", codigo, re.S).group(1)
    bloque = codigo[codigo.index('<form id="f-planillas"'):codigo.index("Guardar planillas por foto")]
    assert "${aj.compromiso_permite_fotos === false ? html`" in bloque and 'id="pf-compromiso"' in bloque
    assert 'id="compromiso-fotos" data-version="${aj.compromiso_con_fotos}"' in bloque
    assert "soloLectura ? 'Solo el administrador cambia la versión del compromiso.'" in bloque
    texto = re.sub(r"\s+", " ", bloque)
    assert "nunca cédulas ni otros documentos" in texto and "borrar la foto del teléfono" in texto
    # El botón: confirma, guarda la versión y avisa al asistente (la cámara depende del compromiso)
    usar = codigo[codigo.index("async function usarCompromisoConFotos(boton) {"):codigo.index("function horario(f)")]
    assert "await confirmar(" in usar and "aceptarlo de nuevo" in usar
    assert usar.index("await guardar({ compromiso_version: version },") < usar.index("avisarAlAsistente();")
    assert "const cf = e.target.closest('#compromiso-fotos');" in codigo
    assert "if (cf) { await usarCompromisoConFotos(cf); return; }" in codigo


def test_importar_solo_para_a_y_k_y_con_el_aviso_nuevo():
    codigo = _sin_comentarios(IMPORTAR_JS)
    assert "const conImportar = puede('importar'), conFotos = conImportar;" in codigo
    for viejo in ("pf-enmascarada", "tablaEnmascarada", "Un coordinador la revisa y la carga",
                  "un coordinador las revisa y las carga", "puede('plantillas')", "'Planillas por foto';"):
        assert viejo not in codigo, viejo
    # El compromiso: el ajuste lo dice al entrar, y el 409 de la subida también
    assert "ajustes?.compromiso_permite_fotos === false ? 'compromiso'" in codigo
    assert "['planillas_apagado', 'sin_configurar', 'compromiso_fotos'].includes(e.codigo)" in codigo
    assert "{ sin_configurar: 'modelo', compromiso_fotos: 'compromiso' }[e.codigo] || 'rol'" in codigo
    assert "compromiso: puede('permisos.modificar')" in codigo
    # El aviso fijo: las columnas sensibles y las políticas se tapan (el lector no transcribe las políticas: en la
    # foto solo llegarían al proveedor; test_aviso_fotos_politicas.py)
    aviso = re.search(r"const AVISO_FOTOS = ('[^']*'\s*\+\s*'[^']*');", IMPORTAR_JS).group(1)
    plano = re.sub(r"'\s*\+\s*'", "", aviso)
    assert plano == ("'Solo planillas o listas. No fotografíe cédulas. Tape columnas de salud, etnia, víctima o "
                     "políticas. Borre la foto del teléfono.'")
    assert aviso in AGENTE_JS


def test_el_widget_vuelve_a_leer_el_estado_si_ya_no_puede_subir():
    codigo = _sin_comentarios(AGENTE_JS)
    assert "const FOTOS_APAGADAS = new Set(['planillas_apagado', 'compromiso_fotos', 'permiso']);" in codigo
    inicio = codigo.index("async function subirAhora(f) {")
    subir_ = codigo[inicio:codigo.index("function explicarFoto(e) {", inicio)]
    assert "if (e instanceof ErrorApi && FOTOS_APAGADAS.has(e.codigo)) releerEstado();" in subir_


@pytest.mark.parametrize("rol", ["planillero", "consultor"])
def test_ni_con_el_asistente_encendido_se_les_ofrece_la_camara(sesion, como, rol):
    app, db = sesion.app, sesion.app.state.db
    aa.encender(app)
    db.meta.update_one({"_id": "ajustes"}, {"$set": {
        "agente": {"roles": ["admin", "coordinador", "planillero", "consultor"]},
        "agente_planillas": {"roles": ["admin", "coordinador", "planillero", "consultor"]}}}, upsert=True)
    c = como(rol)
    e = c.get("/api/agente/estado").json()
    assert e["disponible"] is True and e["adjuntos"] is None
    r = c.get("/api/planillas")
    assert r.status_code == 403 and r.json()["detail"]["codigo"] == "permiso"
