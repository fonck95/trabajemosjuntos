"""Permisos por endpoint (3.6 y 3.7): cada ruta de la API declara sus permisos y coinciden con la tabla; planilleros y
consultores reciben 403 `permiso` en todo lo exclusivo del administrador; importar se rechaza sin leer la subida.

Las rutas que todavía no existen, y las actuales cuyos permisos cambia otro grupo, se comprueban cuando su grupo llega
(lo dice la existencia de una ruta suya, no un fallo)."""
import asyncio
import re

import pytest
from fastapi.routing import APIRoute

from app import acceso
from app import seguridad as seg

A = "solo A"  # solo el administrador: ningún permiso que tengan P o C
P = acceso.PERMISOS["planillero"]
C = acceso.PERMISOS["consultor"]
# El servidor MCP de la presentación (app/api/mcp.py) no usa la sesión: lo autentica su clave, que la ruta comprueba
# antes de leer el cuerpo (tests/test_pantalla_mcp.py)
SIN_SESION_MCP = {("POST", "/api/mcp"), ("GET", "/api/mcp"), ("DELETE", "/api/mcp")}
SIN_PERMISOS = {("POST", "/api/login"), ("GET", "/api/yo")} | SIN_SESION_MCP

# (método, ruta, permisos esperados o A, grupo dueño). Las rutas van con {} en lugar del nombre del parámetro.
# Endpoints actuales (3.7, filas 1 a 45)
ACTUALES = [
    ("POST", "/api/logout", {"cuenta"}, "G2"),
    ("POST", "/api/importar", {"importar"}, "G2"),
    ("GET", "/api/importaciones", {"importar"}, "G2"),
    ("GET", "/api/exportar.xlsx", {"exportar"}, "G2"),
    ("GET", "/api/catalogos", {"catalogos.ver"}, "G2"),
    ("POST", "/api/campos", A, "G2"), ("PATCH", "/api/campos/{}", A, "G2"),
    ("POST", "/api/etiquetas", A, "G2"), ("DELETE", "/api/etiquetas/{}", A, "G2"),
    ("GET", "/api/auditoria", A, "G2"),
    ("GET", "/api/indicadores", {"tablero.ver"}, "G3"),
    ("GET", "/api/mapa/puntos", {"mapa.ver"}, "G3"), ("GET", "/api/mapa/capas", {"mapa.ver"}, "G3"),
    ("GET", "/api/mapa/grilla.json", {"mapa.ver"}, "G3"),
    ("GET", "/api/personas", {"personas.listar"}, "G3"),
    ("GET", "/api/buscar", {"personas.buscar"}, "G3"),
    ("GET", "/api/personas/{}", {"personas.ver"}, "G3"),
    ("PATCH", "/api/personas/{}", {"personas.editar"}, "G3"),
    ("POST", "/api/personas", {"personas.crear"}, "G3"),
    ("GET", "/api/personas/{}/parecidas", {"personas.parecidas"}, "G3"),
    ("POST", "/api/personas/{}/notas", {"personas.notas"}, "G3"),
    ("DELETE", "/api/personas/{}/notas/{}", {"personas.notas"}, "G3"),
    ("PUT", "/api/personas/{}/ubicacion", {"personas.ubicar"}, "G3"),
    ("DELETE", "/api/personas/{}/ubicacion", {"personas.ubicar"}, "G3"),
    ("POST", "/api/personas/{}/fusionar", A, "G3"),
    ("DELETE", "/api/personas/{}", A, "G3"),
    ("GET", "/api/reuniones", {"reuniones.ver"}, "G3"),
    ("POST", "/api/reuniones", {"reuniones.crear"}, "G3"),
    ("GET", "/api/reuniones/{}", {"reuniones.ver"}, "G3"),
    ("PATCH", "/api/reuniones/{}", [{"reuniones.crear"}, {"reuniones.ver"}, {"reuniones.asistentes"}], "G3"),
    ("DELETE", "/api/reuniones/{}", A, "G3"),
    ("POST", "/api/reuniones/{}/asistentes", {"reuniones.asistentes"}, "G3"),
    ("DELETE", "/api/reuniones/{}/asistentes/{}", {"reuniones.asistentes"}, "G3"),
    ("GET", "/api/reuniones/{}/asistentes.csv", {"exportar"}, "G3"),
    ("GET", "/api/coincidencias", A, "G1"), ("POST", "/api/coincidencias/{}", A, "G1"),
    ("GET", "/api/lugares", A, "G1"), ("POST", "/api/lugares", A, "G1"), ("PATCH", "/api/lugares/{}", A, "G1"),
    ("GET", "/api/lugares/sin-reconocer", A, "G1"), ("POST", "/api/georreferenciar", A, "G1"),
]
# Endpoints nuevos (3.7)
NUEVAS = [
    ("GET", "/api/usuarios", {"usuarios.gestionar"}, "G2"), ("POST", "/api/usuarios", {"usuarios.gestionar"}, "G2"),
    ("GET", "/api/usuarios/{}", {"usuarios.gestionar"}, "G2"), ("PATCH", "/api/usuarios/{}", {"usuarios.gestionar"}, "G2"),
    ("POST", "/api/usuarios/{}/clave", {"usuarios.gestionar"}, "G2"),
    ("DELETE", "/api/usuarios/{}/sesiones", {"usuarios.gestionar"}, "G2"),
    ("DELETE", "/api/usuarios/{}/bloqueo", {"usuarios.gestionar"}, "G2"),
    ("GET", "/api/usuarios/indicadores", {"usuarios.gestionar"}, "G2"),
    ("GET", "/api/usuarios/{}/indicadores", {"usuarios.gestionar"}, "G2"),
    ("GET", "/api/usuarios/avance", {"usuarios.gestionar"}, "G2"),
    ("POST", "/api/yo/clave", {"cuenta"}, "G2"), ("POST", "/api/yo/compromiso", {"cuenta"}, "G2"),
    ("GET", "/api/yo/indicadores", {"cuenta"}, "G2"),
    ("GET", "/api/parecidas", {"personas.parecidas"}, "G3"),
    ("POST", "/api/personas/{}/telefonos", {"personas.telefonos"}, "G3"),
    ("PATCH", "/api/personas/{}/telefonos/{}", {"personas.telefonos"}, "G3"),
    ("POST", "/api/personas/{}/telefonos/{}/principal", {"personas.editar"}, "G3"),
    ("DELETE", "/api/personas/{}/telefonos/{}", A, "G3"),
    ("POST", "/api/personas/{}/autorizacion", {"personas.autorizacion"}, "G3"),
    ("GET", "/api/personas/{}/autorizaciones", A, "G3"), ("GET", "/api/personas/{}/sensibles", A, "G3"),
    ("POST", "/api/personas/{}/duplicado", {"personas.duplicado"}, "G3"),
    ("POST", "/api/personas/{}/actualizacion", {"personas.editar"}, "G3"),
    ("POST", "/api/personas/{}/situacion", {"personas.situacion"}, "G3"),
    ("POST", "/api/personas/{}/no-disponible", {"personas.no_disponible"}, "G3"),
    ("POST", "/api/personas/{}/acercamientos", {"acercamientos.registrar"}, "G3"),
    ("GET", "/api/personas/{}/acercamientos", {"acercamientos.ver"}, "G3"),
    ("POST", "/api/acercamientos/{}/anular", {"acercamientos.registrar"}, "G3"),
    ("GET", "/api/acercamientos", A, "G3"),
    ("GET", "/api/trabajo", {"trabajo.ver"}, "G3"),
    ("GET", "/api/trabajo/cola", {"trabajo.cola"}, "G3"), ("POST", "/api/trabajo/siguiente", {"trabajo.cola"}, "G3"),
    ("POST", "/api/trabajo/tomar/{}", {"trabajo.cola"}, "G3"), ("DELETE", "/api/trabajo/tomar/{}", {"trabajo.cola"}, "G3"),
    ("GET", "/api/insignias", {"insignias"}, "G3"),
    ("GET", "/api/conflictos", A, "G1"), ("POST", "/api/conflictos/{}", A, "G1"),
    ("POST", "/api/importaciones/{}/confirmar-autorizaciones", A, "G1"),
    ("GET", "/api/solicitudes", A, "G1"), ("PATCH", "/api/solicitudes/{}", A, "G1"),
    ("POST", "/api/solicitudes", {"solicitudes.crear"}, "G1"),
    ("GET", "/api/puestos", {"puestos.ver"}, "G1"), ("POST", "/api/puestos", A, "G1"), ("PATCH", "/api/puestos/{}", A, "G1"),
    ("GET", "/api/ajustes", A, "G1"), ("PUT", "/api/ajustes", A, "G1"),
    ("GET", "/api/plantillas/planilla.xlsx", {"plantillas"}, "G1"),
    ("GET", "/api/areas", A, "G5"), ("POST", "/api/areas", A, "G5"), ("GET", "/api/areas/{}", A, "G5"),
    ("PATCH", "/api/areas/{}", A, "G5"), ("DELETE", "/api/areas/{}", A, "G5"),
    # Unificación en bloque: grupos de coincidencias y resolución en lote (como las coincidencias: A y K)
    ("GET", "/api/coincidencias/grupos", A, "unificacion"), ("POST", "/api/coincidencias/lote", A, "unificacion"),
    # El asistente: conectar y desconectar la cuenta de Mnemo del administrador (ni el coordinador)
    ("POST", "/api/agente/mnemo/conectar", {"agente.conectar"}, "agente"),
    ("POST", "/api/agente/mnemo/volver", {"agente.conectar"}, "agente"),
    ("DELETE", "/api/agente/mnemo", {"agente.conectar"}, "agente"),
]
TABLA = ACTUALES + NUEVAS
# Rutas que ya existían antes de la ampliación: las de otros grupos se comparan cuando su grupo llega
_ACTUALES = {(m, r) for m, r, _, _ in ACTUALES}
# Una ruta de cada grupo que llega después: si existe, ese grupo ya cambió los permisos de sus rutas actuales
MARCAS = {"G1": ("GET", "/api/ajustes"), "G3": ("GET", "/api/trabajo"), "G5": ("GET", "/api/areas")}


def _forma(ruta: str) -> str:
    return re.sub(r"\{[^}]+\}", "{}", ruta)


def _permisos_de(ruta: APIRoute) -> frozenset | None:
    """Los permisos que declara la dependencia `requiere` de la ruta (busca también en las dependencias anidadas)."""
    pendientes = list(ruta.dependant.dependencies)
    while pendientes:
        d = pendientes.pop()
        if d.call is not None and hasattr(d.call, "permisos"):
            return frozenset(d.call.permisos)
        pendientes.extend(d.dependencies)
    return None


def _rutas(app) -> dict[tuple[str, str], APIRoute]:
    return {(m, _forma(r.path)): r for r in app.routes if isinstance(r, APIRoute) and r.path.startswith("/api/")
            for m in r.methods}


def _solo_admin(permisos: frozenset) -> bool:
    return bool(permisos) and not permisos <= P and not permisos <= C


def test_toda_ruta_de_la_api_tiene_los_permisos_de_la_tabla(cliente):
    rutas = _rutas(cliente.app)
    # 1. Toda ruta bajo /api (salvo login y yo) declara permisos
    sin = [k for k, r in rutas.items() if k not in SIN_PERMISOS and _permisos_de(r) is None]
    assert not sin, f"Rutas sin permisos declarados: {sin}"
    assert all(_permisos_de(rutas[k]) is None for k in SIN_PERMISOS)
    llegados = {g for g, k in MARCAS.items() if k in rutas}
    comprobadas = 0
    for metodo, ruta, esperado, grupo in TABLA:
        r = rutas.get((metodo, ruta))
        if r is None:
            continue  # la ruta llega con su grupo
        tiene = _permisos_de(r)
        if esperado == A:
            assert _solo_admin(tiene), (metodo, ruta, tiene)
        else:
            validos = [frozenset(x) for x in (esperado if isinstance(esperado, list) else [esperado])]
            if all(_solo_admin(v) for v in validos):
                assert _solo_admin(tiene), (metodo, ruta, tiene)  # exclusiva de A desde ya
            if grupo == "G2" or grupo in llegados or (metodo, ruta) not in _ACTUALES:
                assert tiene in validos, (metodo, ruta, tiene, validos)
        comprobadas += 1
    assert comprobadas >= 45
    # Toda ruta del grupo 2 está en la tabla
    propias = {(m, _forma(r.path)) for r in cliente.app.routes if isinstance(r, APIRoute)
               and r.endpoint.__module__ in ("app.api.sistema", "app.api.usuarios") for m in r.methods}
    assert propias - SIN_PERMISOS <= {(m, r) for m, r, _, _ in TABLA}


def _ruta_concreta(ruta: str) -> str:
    return re.sub(r"\{[^}]+\}", "1", ruta)


@pytest.mark.parametrize("rol", ["planillero", "consultor"])
def test_planillero_y_consultor_reciben_403_en_lo_exclusivo_del_administrador(cliente, como, rol):
    c = como(rol)
    propios = acceso.PERMISOS[rol]
    probadas = 0
    for r in cliente.app.routes:
        if not isinstance(r, APIRoute) or not r.path.startswith("/api/"):
            continue
        permisos = _permisos_de(r)
        if permisos is None or permisos <= propios:
            continue
        for metodo in r.methods:
            ruta = _ruta_concreta(r.path)
            cuerpo = {} if metodo in ("POST", "PATCH", "PUT") else None
            x = c.request(metodo, ruta, json=cuerpo) if cuerpo is not None else c.request(metodo, ruta)
            assert x.status_code == 403, (metodo, ruta, x.status_code, x.text[:200])
            assert x.json()["detail"]["codigo"] == "permiso", (metodo, ruta)
            probadas += 1
    assert probadas >= 40
    # Su cuenta sí la puede usar
    assert c.get("/api/yo/indicadores").status_code == 200
    assert c.get("/api/catalogos").status_code == 200


def _asgi(app, metodo, ruta, headers, partes):
    """Llama a la aplicación ASGI y cuenta cuántas partes del cuerpo leyó antes de responder (como en
    tests/test_seguridad.py)."""
    partes, leidas, res = list(partes), [], {}

    async def receive():
        leidas.append(1)
        if partes:
            return {"type": "http.request", "body": partes.pop(0), "more_body": bool(partes)}
        return {"type": "http.disconnect"}

    async def send(msg):
        if msg["type"] == "http.response.start":
            res.setdefault("estado", msg["status"])
            res.setdefault("leidas", len(leidas))
        if msg["type"] == "http.response.body" and "cuerpo" not in res:
            res["cuerpo"] = msg.get("body", b"")

    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": metodo, "scheme": "http",
             "path": ruta, "raw_path": ruta.encode(), "query_string": b"", "root_path": "", "client": ("203.0.113.50", 1),
             "server": ("testserver", 80), "headers": [(k.encode(), v.encode()) for k, v in headers.items()]}
    asyncio.run(app(scope, receive, send))
    return res["estado"], res["leidas"], res.get("cuerpo", b"")


@pytest.mark.parametrize("rol", ["planillero", "consultor"])
def test_importar_como_usuario_da_403_sin_leer_el_cuerpo(cliente, como, rol):
    c = como(rol)
    cuerpo = (b'--xx\r\nContent-Disposition: form-data; name="archivos"; filename="a.xlsx"\r\n\r\n' + b"0" * 4000
              + b"\r\n--xx--\r\n")
    partes = [cuerpo[i:i + 1000] for i in range(0, len(cuerpo), 1000)]
    h = {"content-type": "multipart/form-data; boundary=xx", "content-length": str(len(cuerpo)),
         "cookie": f"{seg.COOKIE}={c.cookies.get(seg.COOKIE)}", "x-csrf-token": c.headers["X-CSRF-Token"]}
    estado, leidas, respuesta = _asgi(cliente.app, "POST", "/api/importar", h, partes)
    assert (estado, leidas) == (403, 0)
    assert b'"permiso"' in respuesta
