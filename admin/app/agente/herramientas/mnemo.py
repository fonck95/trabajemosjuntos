"""Herramientas de Mnemo para el asistente, por su servidor MCP (`mnemo_cliente.py`).

Interfaz que usa el bucle (`bucle.py`):
* `async definiciones(cliente, filtro) -> list[dict]`: las herramientas que ofrece el servidor (`tools/list`), acotadas
  por `MNEMO_HERRAMIENTAS` y limpias, como diccionarios JSON que la conversación guarda congelados.
* `desde_definiciones(definiciones) -> list[Herramienta]`: las herramientas del asistente a partir de lo guardado.
* `disponible_para(quien, ajustes_agente, cfg) -> bool`: si a esta persona se le ofrecen.

Por qué está hecho así:

* Son dinámicas: salen de `tools/list` al crear la conversación, se guardan con ella y en cada turno se rehacen con
  `desde_definiciones`, que es determinista (mismos nombres, descripciones y esquemas): la lista congelada de la
  conversación, la caché del proveedor y el razonamiento conservado dependen de que el prefijo no cambie. Lo guardado
  se vuelve a validar al rehacerlo: viene de un servidor externo y pasó por MongoDB.
* Lista blanca por defecto (`POR_DEFECTO`): las 30 de Mnemo pesan 10–15 k tokens, y estudiar, vender o generar mazos
  no es trabajo del panel. `MNEMO_HERRAMIENTAS` la cambia: nombres separados por comas, o `*` para todas las que
  permita el token.
* Nombres: el remoto si ya empieza por `mnemo_`; si no, `mnemo_<nombre>` (`search` y `fetch` son demasiado genéricos
  junto a las del panel, y el `system` reconoce a las de Mnemo por el prefijo). Sin repetir y con los caracteres que
  acepta la API de Anthropic. La descripción dice que es de Mnemo y cómo se llama allá (sus instrucciones y
  descripciones citan los nombres remotos).
* Esquema: el de Mnemo tal cual, sin `$schema`, con `type: object` y validado en lo básico: uno que la API rechace
  dañaría todas las rondas de la conversación.
* Tipo: con `readOnlyHint` es de lectura (corre en el acto); si no, de escritura: el panel muestra antes una tarjeta
  con el título y los argumentos exactos, y solo corre si la persona la aprueba. Mnemo además puede pedir su propia
  aprobación (`needs_approval`): esa se da en Mnemo, con la sesión de la persona, y el resultado trae el enlace.
* La entrada la valida Mnemo con su esquema (su error vuelve al modelo para que corrija); aquí solo se exige un objeto
  JSON que quepa. `wait_seconds` se acota a `TOPE_ESPERA_S`: si Mnemo espera más que el plazo, la conexión se corta y
  Mnemo cancela el trabajo; con poco, contesta `running` y el modelo sigue con `mnemo_get_job`.
* Las usa el administrador (el token es suyo) y, si él lo permite en Ajustes (`mnemo_coordinadores`), los
  coordinadores. Se decide en cada turno: el ajuste pudo cambiar desde que se creó la conversación.
* El resultado: los datos (`structuredContent` o el texto) recortados sin romper su estructura, las imágenes como
  bloques `image` (validadas: un bloque roto dañaría la conversación entera, porque el historial se reenvía en cada
  ronda), los `resource_link` como texto, y los enlaces relativos de Mnemo (`approval_url`, descargas) con el origen
  de `MNEMO_MCP_URL`, el mismo con que el widget los deja abrir. Nada de esto es de habitantes del panel: no suma a
  `Resultado.personas`.
"""
from __future__ import annotations

import base64
import binascii
import json
import logging
import re
from typing import Any

from pydantic import RootModel, model_validator

from .. import mnemo_cliente as mc
from .base import MAX_CONTENIDO, Confirmacion, Contexto, ErrorHerramienta, Herramienta, Resultado

log = logging.getLogger("panel")

POR_DEFECTO = (
    "search", "fetch", "mnemo_get_briefing", "mnemo_list_items", "mnemo_view_image", "mnemo_list_events",
    "mnemo_create_event", "mnemo_update_event", "mnemo_query_forms", "mnemo_save_form_draft", "mnemo_create_document",
    "mnemo_update_document", "mnemo_export_document", "mnemo_save_memory", "mnemo_list_shared_with_me",
    "mnemo_request_publish", "mnemo_request_share", "mnemo_check_approval", "mnemo_get_job",
)
PREFIJO = "mnemo_"
PERMISOS = ("agente.usar",)  # A y K lo tienen con «*»; quién más, lo decide `disponible_para`
PISTAS = ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint")

NOMBRE_REMOTO = re.compile(r"[A-Za-z0-9_.\-/]{1,128}")
NOMBRE_MAX = 64            # la API de Anthropic: ^[a-zA-Z0-9_-]{1,64}$
MAX_DESCRIPCION = 4_000    # las de Mnemo tienen 600–1 500 caracteres
MAX_TITULO = 120
MAX_ESQUEMA = 30_000
MAX_ENTRADA = 250_000      # `generate_deck` acepta 200 000 de contexto; Mnemo lee hasta 4 MB
TOPE_ESPERA_S = 40         # `wait_seconds` (generate_deck espera 200 s por defecto; get_job, 25)
IMAGEN_MAX_B64 = 2_500_000  # ~1,9 MB: se guarda con la conversación y se reenvía en cada ronda
IMAGENES_MAX = 2
DIMENSION_MAX = 8_000      # la API rechaza imágenes de más de 8000 px de lado
TIPOS_IMAGEN = ("image/png", "image/jpeg", "image/gif", "image/webp")
DETALLE_FILAS = 30
DETALLE_VALOR = 1_500
DETALLE_TOTAL = 12_000
MAX_BLOQUES = 50           # Mnemo da 1–3 bloques por resultado
MAX_EXTRAS = 4_000         # las notas sobre imágenes y enlaces que van tras los datos

# Etiquetas (en gerundio) para la interfaz y títulos de la tarjeta de confirmación de las conocidas
ETIQUETAS = {
    "search": "Buscando en Mnemo",
    "fetch": "Leyendo en Mnemo",
    "mnemo_get_briefing": "Consultando el resumen de Mnemo",
    "mnemo_list_items": "Listando elementos de Mnemo",
    "mnemo_view_image": "Mirando una imagen de Mnemo",
    "mnemo_get_study_overview": "Revisando el estudio en Mnemo",
    "mnemo_get_due_cards": "Buscando tarjetas para repasar en Mnemo",
    "mnemo_grade_answer": "Calificando una respuesta en Mnemo",
    "mnemo_create_deck": "Creando un mazo en Mnemo",
    "mnemo_edit_cards": "Editando tarjetas en Mnemo",
    "mnemo_generate_deck": "Generando un mazo en Mnemo",
    "mnemo_save_memory": "Guardando un recuerdo en Mnemo",
    "mnemo_get_job": "Consultando un trabajo de Mnemo",
    "mnemo_list_events": "Consultando el calendario de Mnemo",
    "mnemo_create_event": "Creando un evento en Mnemo",
    "mnemo_update_event": "Cambiando un evento en Mnemo",
    "mnemo_query_business": "Consultando el negocio en Mnemo",
    "mnemo_record_sale": "Registrando una venta en Mnemo",
    "mnemo_manage_products": "Cambiando productos en Mnemo",
    "mnemo_query_forms": "Consultando formularios de Mnemo",
    "mnemo_save_form_draft": "Guardando un formulario en Mnemo",
    "mnemo_create_document": "Creando un documento en Mnemo",
    "mnemo_update_document": "Cambiando un documento en Mnemo",
    "mnemo_export_document": "Exportando un documento de Mnemo",
    "mnemo_list_shared_with_me": "Consultando lo compartido en Mnemo",
    "mnemo_unshare": "Dejando de compartir en Mnemo",
    "mnemo_request_share": "Pidiendo compartir en Mnemo",
    "mnemo_request_publish": "Pidiendo publicar en Mnemo",
    "mnemo_request_delete": "Pidiendo borrar en Mnemo",
    "mnemo_check_approval": "Revisando una aprobación de Mnemo",
}
TITULOS = {
    "mnemo_grade_answer": "Calificar una respuesta en Mnemo",
    "mnemo_create_deck": "Crear un mazo en Mnemo",
    "mnemo_edit_cards": "Editar tarjetas de un mazo de Mnemo",
    "mnemo_generate_deck": "Generar un mazo con IA en Mnemo",
    "mnemo_save_memory": "Guardar un recuerdo en Mnemo",
    "mnemo_create_event": "Crear un evento en el calendario de Mnemo",
    "mnemo_update_event": "Cambiar un evento del calendario de Mnemo",
    "mnemo_record_sale": "Registrar una venta en Mnemo",
    "mnemo_manage_products": "Cambiar productos en Mnemo",
    "mnemo_save_form_draft": "Guardar un borrador de formulario en Mnemo",
    "mnemo_create_document": "Crear un documento en Mnemo",
    "mnemo_update_document": "Cambiar un documento de Mnemo",
    "mnemo_unshare": "Dejar de compartir en Mnemo",
    "mnemo_request_share": "Pedir en Mnemo que se comparta",
    "mnemo_request_publish": "Pedir en Mnemo que se publique",
    "mnemo_request_delete": "Pedir en Mnemo que se borre",
}
# El resumen para la interfaz según el `status` que devuelve Mnemo (aprobaciones y trabajos largos)
ESTADOS = {
    "needs_approval": "Aprobación pendiente en Mnemo",
    "pending": "Aprobación pendiente en Mnemo",
    "created": "Creado en Mnemo",
    "updated": "Actualizado en Mnemo",
    "saved": "Guardado en Mnemo",
    "proposed": "Propuesto en Mnemo: falta aceptarlo allá",
    "nothing_to_do": "Nada que hacer en Mnemo",
    "approved": "Aprobada en Mnemo",
    "rejected": "Rechazada en Mnemo",
    "expired": "La aprobación venció en Mnemo",
    "running": "Trabajo en curso en Mnemo",
    "done": "Hecho en Mnemo",
    "failed": "Falló en Mnemo",
    "interrupted": "Trabajo interrumpido en Mnemo",
}
LISTAS = (("results", "resultados"), ("items", "elementos"), ("events", "eventos"), ("forms", "formularios"),
          ("documents", "documentos"), ("shared", "compartidos"))

_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_NO_NOMBRE = re.compile(r"[^A-Za-z0-9_-]")
_CLAVE_URL = re.compile(r"(?:^|_)url$")
_URL_EN_TEXTO = re.compile(r'("(?:[a-z]+_)?url"\s*:\s*")(/(?!/)[^"\s]*)"')
_APROBAR_EN_TEXTO = re.compile(r"(?<![\w/:.-])(/aprobar/apr_[A-Za-z0-9_-]+)")
_SIN_ESPACIOS = re.compile(r"\s+")


# ───────────────────────────── Quién y cuáles ─────────────────────────────

def disponible_para(quien: Any, ajustes_agente: dict, cfg: Any) -> bool:
    """¿Se le ofrecen las herramientas de Mnemo? El token es del administrador: él siempre (si está configurado) y los
    coordinadores solo si él lo permite (`agente.mnemo_coordinadores`). Planilleros y consultores, nunca."""
    if not getattr(cfg, "mnemo_configurado", False):
        return False
    if getattr(quien, "es_admin", False) is True:
        return True
    return (getattr(quien, "rol", None) == "coordinador" and isinstance(ajustes_agente, dict)
            and ajustes_agente.get("mnemo_coordinadores") is True)


def _filtro(texto: Any) -> frozenset[str] | None:
    """Los nombres que pide `MNEMO_HERRAMIENTAS` (None = todas, con `*`). Vacío: la lista blanca por defecto."""
    partes = [p.strip() for p in texto.split(",")] if isinstance(texto, str) else []
    partes = [p for p in partes if p]
    if "*" in partes:
        return None
    return frozenset(partes) if partes else frozenset(POR_DEFECTO)


_AVISADOS: set[frozenset[str]] = set()


async def definiciones(cliente: Any, filtro: str) -> list[dict]:
    """Las herramientas que ofrece Mnemo a este token, acotadas por `filtro` y limpias (`_limpia`), en el orden del
    servidor. Lanza `ErrorHerramienta` si Mnemo no responde (el bucle sigue sin Mnemo)."""
    if cliente is None:
        return []
    elegidas = _filtro(filtro)
    out, vistas = [], set()
    for t in await cliente.herramientas():
        d = _limpia(t)
        if d is None:
            log.warning("Mnemo: se descartó una herramienta con una definición que no sirve")
            continue
        vistas |= {d["name"], _nombre_panel(d["name"])}
        if elegidas is None or d["name"] in elegidas or _nombre_panel(d["name"]) in elegidas:
            out.append(d)
    faltan = (elegidas or frozenset()) - vistas
    if faltan and faltan not in _AVISADOS and elegidas != frozenset(POR_DEFECTO):
        _AVISADOS.add(frozenset(faltan))  # una vez por proceso: es configuración, no un fallo de cada conversación
        log.warning("Mnemo: MNEMO_HERRAMIENTAS nombra herramientas que Mnemo no ofrece a este token: %s",
                    ", ".join(sorted(faltan))[:500])
    return out


# ───────────────────────────── Definiciones guardadas → herramientas ─────────────────────────────

def _texto(v: Any, tope: int) -> str | None:
    return _CONTROL.sub("", v).strip()[:tope] if isinstance(v, str) else None


def _esquema(s: Any) -> dict | None:
    """El `inputSchema` como lo acepta la API: un objeto JSON con `type: object`, sin `$schema` ni `$id`, con
    `properties` y `required` bien formados y de tamaño acotado. None si no sirve."""
    if s is None:
        s = {"type": "object", "properties": {}}
    if not isinstance(s, dict) or s.get("type", "object") != "object":
        return None
    s = {k: v for k, v in s.items() if k not in ("$schema", "$id")}
    s["type"] = "object"
    props, req = s.get("properties"), s.get("required")
    if props is not None and not (isinstance(props, dict) and all(isinstance(k, str) and isinstance(v, (dict, bool))
                                                                   for k, v in props.items())):
        return None
    if req is not None and not (isinstance(req, list) and all(isinstance(x, str) for x in req)):
        return None
    try:
        texto = json.dumps(s, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, RecursionError):
        return None
    return json.loads(texto) if len(texto) <= MAX_ESQUEMA else None


def _limpia(t: Any) -> dict | None:
    """Una definición de `tools/list` reducida a lo que se usa y guarda: `name`, `title`, `description`,
    `inputSchema` y las cuatro pistas de `annotations`. None si no tiene un nombre o un esquema que sirvan."""
    if not isinstance(t, dict):
        return None
    nombre = t.get("name")
    if not isinstance(nombre, str) or not NOMBRE_REMOTO.fullmatch(nombre):
        return None
    esquema = _esquema(t.get("inputSchema"))
    if esquema is None:
        return None
    anot = t.get("annotations") if isinstance(t.get("annotations"), dict) else {}
    d: dict[str, Any] = {"name": nombre, "description": _texto(t.get("description"), MAX_DESCRIPCION) or "",
                         "inputSchema": esquema, "annotations": {k: anot[k] for k in PISTAS
                                                                 if isinstance(anot.get(k), bool)}}
    titulo = _texto(t.get("title"), MAX_TITULO) or _texto(anot.get("title"), MAX_TITULO)
    if titulo:
        d["title"] = titulo
    return d


def _nombre_panel(remoto: str) -> str:
    base = remoto if remoto.startswith(PREFIJO) else PREFIJO + remoto
    return _NO_NOMBRE.sub("_", base)[:NOMBRE_MAX]


def _nombres(defs: list[dict]) -> list[str]:
    """Los nombres del panel, en orden y sin repetir (el segundo `x` es `x_2`): deterministas para lo guardado."""
    usados: set[str] = set()
    out = []
    for d in defs:
        n = _nombre_panel(d["name"])
        if n in usados:
            i, base = 2, n[:NOMBRE_MAX - 4]
            while f"{base}_{i}" in usados:
                i += 1
            n = f"{base}_{i}"
        usados.add(n)
        out.append(n)
    return out


def desde_definiciones(definiciones: list[dict]) -> list[Herramienta]:
    """Las herramientas del asistente a partir de las definiciones guardadas con la conversación (o recién pedidas).
    Lo que no sirve se descarta; el resultado depende solo de `definiciones`."""
    defs = [d for d in (_limpia(x) for x in (definiciones if isinstance(definiciones, list) else [])) if d]
    return [_herramienta(d, n) for d, n in zip(defs, _nombres(defs))]


def _lectura(d: dict) -> bool:
    """¿Solo lee? Lo dice `readOnlyHint`, salvo para las escrituras conocidas de Mnemo, que siempre piden la tarjeta
    (las pistas de MCP son del servidor: una que se equivoque no salta la aprobación)."""
    return d["annotations"].get("readOnlyHint") is True and d["name"] not in TITULOS


def _descripcion(d: dict, nombre: str) -> str:
    remoto = d["name"]
    cabeza = "Herramienta de Mnemo" + (f" (allá se llama `{remoto}`)" if nombre != remoto else "")
    cola = "" if _lectura(d) else " Antes de correr, la persona la aprueba en una tarjeta del panel."
    return f"{cabeza}. {d['description'] or d.get('title') or remoto}{cola}"


class EntradaMnemo(RootModel[dict[str, Any]]):
    """La entrada de una herramienta de Mnemo: un objeto JSON cualquiera que quepa. El esquema lo valida Mnemo (su
    error vuelve al modelo para que corrija): duplicarlo aquí exigiría un validador de JSON Schema completo."""

    @model_validator(mode="after")
    def _cabe(self) -> "EntradaMnemo":
        try:
            n = len(json.dumps(self.root, ensure_ascii=False, allow_nan=False))
        except (TypeError, ValueError, RecursionError):
            raise ValueError("la entrada tiene que ser JSON") from None
        if n > MAX_ENTRADA:
            raise ValueError(f"la entrada es demasiado grande ({n} caracteres; el máximo es {MAX_ENTRADA})")
        return self


def _herramienta(d: dict, nombre: str) -> Herramienta:
    lectura = _lectura(d)

    async def ejecutar(ctx: Contexto, args: EntradaMnemo) -> Resultado:
        return await _ejecutar(ctx, args, d)

    async def confirmar(ctx: Contexto, args: EntradaMnemo) -> Confirmacion:
        _cliente(ctx)  # sin Mnemo en este turno no tiene sentido pedir la aprobación
        return confirmacion(d, _argumentos(args.root, d["inputSchema"]))

    etiqueta = ETIQUETAS.get(d["name"]) or ("Consultando Mnemo" if lectura else "Escribiendo en Mnemo")
    return Herramienta(nombre=nombre, descripcion=_descripcion(d, nombre), entrada=EntradaMnemo,
                       tipo="lectura" if lectura else "escritura", permisos=PERMISOS, etiqueta=etiqueta,
                       ejecutar=ejecutar, confirmar=None if lectura else confirmar, disponible=disponible_para,
                       esquema=d["inputSchema"], nombre_remoto=d["name"])


# ───────────────────────────── Escrituras: la tarjeta ─────────────────────────────

def _valor(v: Any) -> str:
    if isinstance(v, str):
        t = v
    elif isinstance(v, bool):
        t = "sí" if v else "no"
    elif v is None:
        t = "(vacío)"
    else:
        t = json.dumps(v, ensure_ascii=False)
    t = _CONTROL.sub(" ", t)
    return t if len(t) <= DETALLE_VALOR else f"{t[:DETALLE_VALOR]}… ({len(t)} caracteres en total)"


def confirmacion(d: dict, argumentos: dict) -> Confirmacion:
    """La tarjeta de una escritura de Mnemo: qué herramienta y los argumentos exactos que se mandarán, en el orden del
    esquema (los largos, recortados con su tamaño total)."""
    remoto, anot = d["name"], d["annotations"]
    props = d["inputSchema"].get("properties") or {}
    claves = [k for k in props if k in argumentos] + sorted(k for k in argumentos if k not in props)
    detalle: list[tuple[str, str]] = []
    total = 0
    for k in claves:
        if len(detalle) >= DETALLE_FILAS or total >= DETALLE_TOTAL:
            detalle.append(("…", f"y {len(claves) - len(detalle)} argumentos más"))
            break
        v = _valor(argumentos[k])
        detalle.append((str(k)[:80], v))
        total += len(v)
    if not detalle:
        detalle.append(("Argumentos", "(ninguno)"))
    aviso = ["Lo hace Mnemo con el token del administrador."]
    if remoto.startswith("mnemo_request_"):
        aviso.append("Aquí solo se pide: Mnemo devuelve un enlace y la acción se aprueba allá.")
    elif anot.get("destructiveHint") is True:
        aviso.append("Puede cambiar o reemplazar lo que ya hay en Mnemo.")
    if anot.get("openWorldHint") is True:
        aviso.append("Puede dejar el contenido a la vista de otras personas.")
    titulo = TITULOS.get(remoto) or f"Mnemo: {d.get('title') or remoto}"
    return Confirmacion(titulo, detalle, " ".join(aviso))


# ───────────────────────────── Ejecución ─────────────────────────────

def _cliente(ctx: Contexto) -> Any:
    cliente = getattr(ctx, "mnemo", None)
    if cliente is None or not callable(getattr(cliente, "llamar", None)):
        raise ErrorHerramienta("Mnemo no está disponible en este turno (no está configurado o el rol ya no lo usa).",
                               mc.COD_NO_DISPONIBLE)
    return cliente


def _argumentos(argumentos: dict, esquema: dict) -> dict:
    """Los argumentos que se mandan: los del modelo, con `wait_seconds` acotado si la herramienta lo tiene (si no se
    dio y el valor por defecto del esquema pasa el tope, se manda el tope)."""
    out = dict(argumentos)
    prop = (esquema.get("properties") or {}).get("wait_seconds")
    if isinstance(prop, dict):
        tope = TOPE_ESPERA_S
        maximo = prop.get("maximum")
        if isinstance(maximo, (int, float)) and not isinstance(maximo, bool):
            tope = min(tope, int(maximo))
        dado = out.get("wait_seconds", prop.get("default"))
        if isinstance(dado, (int, float)) and not isinstance(dado, bool) and dado > tope:
            out["wait_seconds"] = max(tope, 0)
    return out


def _origen(ctx: Contexto, cliente: Any) -> str | None:
    """El origen de Mnemo para volver absolutos sus enlaces: el de `MNEMO_MCP_URL`, el mismo que el widget deja
    abrir (`politica.origen_mnemo`)."""
    try:
        from .. import politica
        origen = politica.origen_mnemo(ctx.cfg)
    except Exception:  # noqa: BLE001 - sin la política se usa la dirección del cliente
        origen = None
    return origen or getattr(cliente, "origen", None)


async def _ejecutar(ctx: Contexto, args: EntradaMnemo, d: dict) -> Resultado:
    cliente = _cliente(ctx)
    escritura = not _lectura(d)
    plazo = mc.PLAZO_ESCRITURA_S if escritura else mc.PLAZO_LECTURA_S
    try:
        res = await cliente.llamar(d["name"], _argumentos(args.root, d["inputSchema"]), plazo)
    except ErrorHerramienta as e:
        if escritura and e.codigo in (mc.COD_PLAZO, mc.COD_RED):
            # Cortada a mitad de camino una escritura pudo quedar hecha: repetirla a ciegas la duplicaría
            raise ErrorHerramienta(f"{e.mensaje} No se sabe si alcanzó a hacerse en Mnemo: revíselo allá antes de "
                                   "repetirla.", e.codigo, estado=e.estado, detalle=e.detalle) from None
        raise
    return resultado_de(res, _origen(ctx, cliente))


# ───────────────────────────── El resultado ─────────────────────────────

def _relativa(x: Any) -> bool:
    return (isinstance(x, str) and x.startswith("/") and not x.startswith("//") and len(x) <= 2_000
            and not _SIN_ESPACIOS.search(x))


def _absolutas(v: Any, origen: str | None, prof: int = 0) -> Any:
    """Los enlaces relativos de Mnemo (`approval_url`, `url` de una exportación…) con su origen: sin
    `PUBLIC_BASE_URL`, Mnemo los da relativos a su servidor y la persona no los podría abrir."""
    if not origen or prof > 30:
        return v
    if isinstance(v, dict):
        return {k: (origen + x if isinstance(k, str) and _CLAVE_URL.search(k) and _relativa(x)
                    else _absolutas(x, origen, prof + 1)) for k, x in v.items()}
    if isinstance(v, list):
        return [_absolutas(x, origen, prof + 1) for x in v]
    return v


def _absolutas_texto(texto: str, origen: str | None) -> str:
    if not origen:
        return texto
    texto = _URL_EN_TEXTO.sub(lambda m: f'{m.group(1)}{origen}{m.group(2)}"', texto)
    return _APROBAR_EN_TEXTO.sub(lambda m: origen + m.group(1), texto)


def _podar(v: Any, cadena: int, lista: int, prof: int = 0) -> Any:
    if isinstance(v, str):
        return v if len(v) <= cadena else f"{v[:cadena]}… [recortado: {len(v)} caracteres en total]"
    if prof > 40:
        return "… [recortado]"
    if isinstance(v, dict):
        return {k: _podar(x, cadena, lista, prof + 1) for k, x in v.items()}
    if isinstance(v, list):
        cola = [f"… y {len(v) - lista} más (recortado)"] if len(v) > lista else []
        return [_podar(x, cadena, lista, prof + 1) for x in v[:lista]] + cola
    return v


def _ajustar(datos: Any, tope: int) -> str:
    """Los datos en JSON dentro de `tope` caracteres, recortando primero los textos largos y luego las listas: así
    sobreviven las claves que dicen cómo seguir (`next_cursor`, `metadata.next_offset`, `approval_url`)."""
    texto = json.dumps(datos, ensure_ascii=False, default=str)
    if len(texto) <= tope:
        return texto
    for cadena, lista in ((20_000, 200), (8_000, 100), (3_000, 50), (1_000, 20), (300, 10), (100, 5)):
        texto = json.dumps(_podar(datos, cadena, lista), ensure_ascii=False, default=str)
        if len(texto) <= tope:
            return texto
    return texto[:tope] + "… [recortado]"


def _firma(crudo: bytes) -> str | None:
    """El tipo real de la imagen por sus primeros bytes (la API rechaza un `media_type` que no coincide)."""
    if crudo.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if crudo.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if crudo[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if crudo[:4] == b"RIFF" and crudo[8:12] == b"WEBP":
        return "image/webp"
    return None


def _dimensiones(b: bytes, tipo: str) -> tuple[int, int] | None:
    """Ancho y alto leídos de la cabecera (None si no se pudo): la API rechaza las de más de 8000 px de lado."""
    try:
        if tipo == "image/png" and len(b) >= 24:
            return int.from_bytes(b[16:20], "big"), int.from_bytes(b[20:24], "big")
        if tipo == "image/gif" and len(b) >= 10:
            return int.from_bytes(b[6:8], "little"), int.from_bytes(b[8:10], "little")
        if tipo == "image/webp" and len(b) >= 30:
            trozo = b[12:16]
            if trozo == b"VP8X":
                return int.from_bytes(b[24:27], "little") + 1, int.from_bytes(b[27:30], "little") + 1
            if trozo == b"VP8L" and b[20] == 0x2F:
                bits = int.from_bytes(b[21:25], "little")
                return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
            if trozo == b"VP8 " and b[23:26] == b"\x9d\x01\x2a":
                return int.from_bytes(b[26:28], "little") & 0x3FFF, int.from_bytes(b[28:30], "little") & 0x3FFF
            return None
        if tipo == "image/jpeg":
            i = 2
            while i + 9 < len(b):
                if b[i] != 0xFF:
                    return None
                marca = b[i + 1]
                if marca == 0xFF:
                    i += 1
                    continue
                if marca in (0xD8, 0x01) or 0xD0 <= marca <= 0xD7:
                    i += 2
                    continue
                if 0xC0 <= marca <= 0xCF and marca not in (0xC4, 0xC8, 0xCC):
                    return int.from_bytes(b[i + 7:i + 9], "big"), int.from_bytes(b[i + 5:i + 7], "big")
                i += 2 + int.from_bytes(b[i + 2:i + 4], "big")
    except IndexError:
        return None
    return None


def _imagen(b: dict) -> tuple[dict | None, str | None]:
    """Un bloque `image` de MCP como bloque `image` de la API, o (None, por qué no)."""
    datos = b.get("data")
    if not isinstance(datos, str) or not datos:
        return None, "una imagen vacía"
    if _SIN_ESPACIOS.search(datos):
        datos = _SIN_ESPACIOS.sub("", datos)
    if len(datos) > IMAGEN_MAX_B64:
        return None, f"una imagen demasiado pesada para el modelo (más de {IMAGEN_MAX_B64 * 3 // 4 // 1000} KB)"
    try:
        crudo = base64.b64decode(datos, validate=True)
    except (binascii.Error, ValueError):
        return None, "una imagen que no venía bien codificada"
    tipo = _firma(crudo)
    if tipo is None:
        return None, "una imagen en un formato que el modelo no lee"
    dims = _dimensiones(crudo, tipo)
    if dims and (max(dims) > DIMENSION_MAX or min(dims) < 1):
        return None, "una imagen de más de 8000 píxeles de lado"
    return {"type": "image", "source": {"type": "base64", "media_type": tipo, "data": datos}}, None


def _enlace(b: dict, origen: str | None) -> str | None:
    uri = b.get("uri")
    if not isinstance(uri, str) or len(uri) > 2_000:
        return None
    if _relativa(uri) and origen:
        uri = origen + uri
    elif not re.match(r"^(https?|mnemo)://", uri, re.IGNORECASE):
        return None
    nombre = _texto(b.get("name"), 200) or "archivo"
    tipo = _texto(b.get("mimeType"), 100)
    desc = _texto(b.get("description"), 300)
    return f"Enlace: {nombre}{f' ({tipo})' if tipo else ''}: {uri}{f' — {desc}' if desc else ''}"


def _resumen(datos: Any, imagenes: list[dict]) -> str:
    """Una línea para la interfaz, sin datos: el estado de una aprobación o un trabajo, o cuántos resultados."""
    if isinstance(datos, dict):
        estado = datos.get("status")
        if isinstance(estado, str) and estado in ESTADOS:
            return ESTADOS[estado]
    if imagenes:
        return "Imagen de Mnemo"
    if isinstance(datos, dict):
        for clave, nombre in LISTAS:
            if isinstance(datos.get(clave), list):
                n = len(datos[clave])
                return f"{n} {nombre}" if n != 1 else f"1 {nombre[:-1] if nombre.endswith('s') else nombre}"
    return "Respuesta de Mnemo"


def resultado_de(res: dict, origen: str | None) -> Resultado:
    """El `result` de un `tools/call` correcto como `Resultado` del asistente."""
    textos: list[str] = []
    imagenes: list[dict] = []
    extras: list[str] = []
    bloques = res.get("content") if isinstance(res.get("content"), list) else []
    for b in bloques[:MAX_BLOQUES]:
        if not isinstance(b, dict):
            continue
        tipo = b.get("type")
        if tipo == "text" and isinstance(b.get("text"), str):
            textos.append(b["text"])
        elif tipo == "image":
            img, motivo = _imagen(b) if len(imagenes) < IMAGENES_MAX else (None, "otra imagen (solo van dos)")
            if img is not None:
                imagenes.append(img)
                extras.append("[Imagen adjunta]")
            else:
                extras.append(f"[No se adjuntó {motivo}]")
        elif tipo == "resource_link":
            enlace = _enlace(b, origen)
            extras.append(enlace or "[Se omitió un enlace con una dirección que no es de Mnemo]")
        elif tipo == "resource" and isinstance(b.get("resource"), dict):
            r = b["resource"]
            if isinstance(r.get("text"), str):
                textos.append(r["text"])
            else:
                extras.append("[Se omitió un archivo adjunto]")
        else:
            extras.append(f"[Se omitió contenido de tipo {_texto(tipo, 30) or 'desconocido'}]")
    texto = "\n".join(textos)
    datos: Any = res.get("structuredContent") if isinstance(res.get("structuredContent"), dict) else None
    if datos is None and texto.strip()[:1] in ("{", "["):
        try:
            datos = json.loads(texto)
        except (ValueError, RecursionError):
            datos = None
    cola = ("\n" + "\n".join(extras))[:MAX_EXTRAS] if extras else ""
    tope = MAX_CONTENIDO - len(cola) - 200
    if isinstance(datos, (dict, list)):
        datos = _absolutas(datos, origen)
        cuerpo = _ajustar(datos, tope)
    else:
        cuerpo = _absolutas_texto(texto, origen)
        if len(cuerpo) > tope:
            cuerpo = f"{cuerpo[:tope]}… [recortado: {len(texto)} caracteres en total]"
    return Resultado(contenido=(cuerpo or "(Mnemo no devolvió texto)") + cola, resumen=_resumen(datos, imagenes),
                     imagenes=imagenes)
