"""El plan en flujo (docs/agente.md, «El plan en flujo»; docs/velocidad.md): el panel escribe el plan guiado de la
presentación y la pantalla lo empieza a narrar con su PRIMER paso, mientras el resto se sigue escribiendo.

Por qué existe. Antes, para explicar algo, el modelo del asistente pedía el guion del capítulo (una ronda), lo leía
entero (de 6.000 a 11.000 tokens), razonaba y escribía el plan completo (de 1.500 a 3.000 tokens) dentro de la llamada
`recorrido`; con Mnemo esa llamada no llega por partes (`mnemo_model_complete` solo manda el texto a trozos), así que
la sala esperaba en silencio todo eso, de 40 segundos a más de un minuto, antes del primer paso. Ahora:

1. El modelo del asistente llama `presentacion` op `plan` con el capítulo y un `encargo` corto (qué mostrar y contar).
   No necesita el guion: no lo lee ni lo deja en la conversación (que así sigue liviana en las rondas siguientes).
2. Esta herramienta le pide la redacción al mismo proveedor (`Proveedor.generar(..., rapido=True)`: sin herramientas
   y sin razonar, o lo mínimo) con instrucciones fijas y el guion del capítulo en el `system` (el mismo texto para el
   mismo capítulo: el proveedor lo saca de su caché la próxima vez) y el encargo en el mensaje. El plan llega como
   TEXTO en JSON Lines, que Mnemo sí manda a trozos: una línea con el título, una por paso, una con el cierre.
3. `Lector` saca de ese texto cada objeto JSON en cuanto se cierra y `PlanEnFlujo` lo compone igual que la op
   `recorrido` (`interfaz._componer`, tolerante, y `recorrido.validar`, que no se relaja). Con el primer paso el plan
   se guarda (`pantalla.guardar_recorrido` con `abierto`) y se publica: la acción de la presentación y la tarjeta del
   chat. Cada paso nuevo lo hace crecer (`pantalla.crecer_recorrido`, y la misma acción con `sigue`): el reproductor
   del navegador lo agrega sin cortar lo que suena y, si llega al último antes que el siguiente, lo espera.
4. Al terminar queda entero (`abierto` en False, con su cierre), y el turno termina sin otra ronda del modelo
   (`Resultado.termina_turno`): la tarjeta ya trae las sugerencias para seguir.

Lo que no cambia: las frases, el título y el cierre pasan las mismas reglas de lo que se proyecta (sin costos, sin datos
de personas, sin «@» ni números largos), el plan no pasa de 12 pasos ni de su duración máxima (lo que se pasa se
descarta con un aviso) y nada se guarda si no hay al menos un paso que valga. Si la redacción falla antes del primer
paso, la herramienta devuelve un error y el modelo arma el plan como antes (`guion` y `recorrido`). Si la persona lo
detiene (o llega otra orden u otro plan) mientras se escribe, la redacción se corta en el acto: no se gasta en lo que
nadie va a oír.

Cómo habla. Las instrucciones llevan la voz de la presentación (`lenguaje.COMO_SE_EXPLICA`: sencilla y cercana, con el
léxico del candidato, sin siglas ni tecnicismos y explicando cada parte), y el guion del capítulo va con su glosario
(`siglas`: el nombre completo y qué es cada sigla que trae ese capítulo, `lenguaje.siglas_en`). Cambian las palabras,
no los datos: las cifras, los nombres y los plazos siguen saliendo solo del guion.

Solo para el asistente del panel: por MCP no hay modelo del panel que lo escriba (el agente externo arma su plan con
`recorrido`). Nada del contenido va al registro: solo tipos y códigos.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from fastapi.concurrency import run_in_threadpool
from pydantic import ValidationError

from .. import pantalla as pantalla_off
from .. import recorrido as rec
from . import conversaciones as conv_db
from . import guion as guion_presentacion
from . import lenguaje
from .herramientas.base import ErrorHerramienta, Resultado

log = logging.getLogger("panel")

TOKENS = 6_000             # lo que puede escribir la redacción (12 pasos largos caben de sobra)
PLAZO_S = 150.0            # la redacción entera
PRIMER_PASO_S = 60.0       # sin un paso que valga en esto, no hay plan en flujo: el modelo lo arma como antes
TEXTO_MAX = 80_000         # lo que se lee de la redacción, en caracteres: lo que sobra se ignora
MAX_ENCARGO = 600
LARGOS = {"corto": (3, 5), "normal": (6, 10)}
TITULO_MIN = 3

INSTRUCCIONES = """Escribes el plan guiado de la presentación técnica de la propuesta 2028–2031 de Yondó (Antioquia): \
lo que se construye, dónde, cómo funciona y cómo se mide, SIN COSTOS. El plan se proyecta en una sala y se lee en voz \
alta MIENTRAS lo escribes: cada línea que terminas ya está en pantalla. Escribe en orden, sin volver atrás.

FORMATO: SOLO líneas JSON (JSON Lines): un objeto por línea, sin Markdown, sin ``` y sin nada fuera de ellos.
1. Primera línea: {"titulo": "…"} (de 3 a 80 caracteres: lo que se va a mostrar).
2. Después, los pasos del plan, uno por línea y en el orden en que se dicen (cuántos, lo dice el encargo). El primero \
lleva "capitulo" (el id del capítulo) y "paso"; los demás, solo lo que cambia.
3. Última línea: {"cierre": {"puntos": ["…", "…"]}, "sugerencias": ["…", "…"]}: de 1 a 3 ideas que quedan en la sala, \
dichas en sencillo (hasta 80 caracteres cada una, 200 entre todas), y hasta 3 sugerencias para seguir, de hasta 60 \
caracteres, como las diría la persona («Muéstrame el agua potable»).

Cada paso es UNA frase hablada ("dice": corta, en presente, en palabras sencillas, sin listas ni paréntesis, hasta 220 \
caracteres: «Aquí ven…», «Fíjense en…») y lo que ocurre en pantalla MIENTRAS se dice. Claves de un paso (solo "dice" \
es obligatoria):
- "capitulo" (id) y "paso" (el id o el número del paso del capítulo; sin él, el mismo). Al cambiar de paso, lo visual \
vuelve a lo de ese paso.
- La cámara: "camara" (paso, aerea, oblicua, rasante, cerca o lejos), "rumbo" (grados desde el norte; 180 deja el \
norte arriba), "elevacion" (8 a 85), "zoom" (0.3 a 3; 1 es el encuadre del paso), "mirar" (una pieza o un componente \
con lugar) y "mover" {"giro": grados, "zoom": n, "elevacion": n}: el viaje de la cámara durante la frase (rodear la \
obra, acercarse, subir).
- Las piezas de «maqueta»: "aislar" (una), "mostrar" y "ocultar" (listas de piezas) y "sin" (partes quitadas, \
«pieza.parte»: "torre.cubierta" deja ver las losas).
- "enfoque" (la cámara va a un componente con lugar), "detalle" (abre la ficha técnica de un componente) con \
"resaltar": {"especificacion": "<nombre>"}, {"cifra": n}, {"punto": n}, {"leyenda": n} o {"componente": "<id>"} (de lo \
«resaltable» del paso), y "comparar" (hoy: el sitio como está; proyecto lo devuelve).
- "inmersion" (un modelo del atlas del catálogo) y "simular": [{"control": "<id>", "valor": …}], hasta 4 en orden, de \
los «controles» de ese modelo (la magnitud del simulador sísmico y después "calcular", que hace temblar la torre; \
cambiar un valor no recalcula); sin modelo del atlas, los de «controles_maqueta» (hora: manana, tarde, atardecer o \
noche; reproducir_dia; luces; partido). Al cambiar de paso vuelven a lo del paso: repítelos si deben seguir.
- "animar": true (la obra crece), "gesto" del presentador (de «gestos»: saludar al comenzar, comparar hoy y \
proyecto, invitar al final) y "sostener" (segundos que la imagen se queda después de la frase, de 0 a 8).
Cada paso parte del anterior: di solo lo que cambia. Un arco que sirve: ubicar con una vista amplia; cómo está hoy; \
qué se construye, pieza por pieza (aislar la obra, quitarle la cubierta, rodearla con mover); el dato clave (la ficha \
con la especificación resaltada, un modelo del atlas); qué cambia y cuándo (la meta o la cifra resaltada); y el \
cierre con 2 o 3 ideas. La frase nombra lo que se ve en ese momento y explica qué es y para qué sirve.

""" + lenguaje.COMO_SE_EXPLICA + """

Reglas que no se relajan: cifras, nombres y plazos solo del guion y tal como vienen; nunca costos, plata, precios, \
pesos ni financiación; nunca datos de personas, «@» ni números de 7 o más dígitos. Usa los ids del guion (pasos, \
componentes, piezas, partes, modelos, controles): lo que no exista se descarta y el plan sigue con lo demás. Las \
siglas del capítulo, con su nombre completo, están en «siglas»: en la frase va el nombre, nunca la sigla.

El guion del capítulo, lo único que sabes de él:
"""


def sistema_de(g: guion_presentacion.Guion, ci: int) -> str:
    """Las instrucciones de la redacción con el guion del capítulo `ci` (los gestos del presentador y el glosario de
    las siglas que trae el capítulo): el mismo texto para el mismo capítulo, así el proveedor lo saca de su caché la
    próxima vez que se presenta."""
    leer = g.capitulo_para_leer(ci)
    guion = {**leer, "gestos": dict(rec.GESTOS), **({"siglas": s} if (s := lenguaje.siglas_en(leer)) else {})}
    return INSTRUCCIONES + json.dumps(guion, ensure_ascii=False, separators=(",", ":"))


def mensaje_de(g: guion_presentacion.Guion, ci: int, encargo: str, largo: str, en_pantalla: str = "") -> str:
    """El mensaje de la redacción: el encargo del asistente, cuántos pasos y lo que la sala ve ahora (si se sabe)."""
    lo, hi = LARGOS.get(largo, LARGOS["normal"])
    c = g.capitulos[ci]
    lineas = [f"Encargo del asistente: {encargo.strip()}",
              f"Capítulo: {c['id']} ({c['nombre']}). De {lo} a {hi} pasos, y el cierre."]
    if en_pantalla:
        lineas.append(f"En pantalla ahora: {en_pantalla}")
    lineas.append("Escribe ya la primera línea.")
    return "\n".join(lineas)


# ───────────────────────────── El texto que llega ─────────────────────────────

class Lector:
    """Saca los objetos JSON de primer nivel de un texto que llega a trozos, en cuanto se cierra cada uno, sin importar
    los saltos de línea (un objeto partido en varias líneas también vale) ni lo que haya entre ellos (```, una frase
    suelta: se ignora). Lleva la cuenta de los que ya entregó: si el texto final de la ronda no es la continuación de
    lo que llegó (`reemplazar`), lo vuelve a leer entero y entrega solo los que faltaban."""

    def __init__(self) -> None:
        self.texto = ""
        self.entregados = 0
        self._i = 0
        self._prof = 0
        self._cadena = False
        self._escape = False
        self._ini = -1

    def agregar(self, trozo: str) -> list[dict]:
        if not isinstance(trozo, str) or not trozo:
            return []
        self.texto += trozo[:max(0, TEXTO_MAX - len(self.texto))]
        out: list[dict] = []
        s = self.texto
        while self._i < len(s):
            ch = s[self._i]
            if self._cadena:
                if self._escape:
                    self._escape = False
                elif ch == "\\":
                    self._escape = True
                elif ch == '"':
                    self._cadena = False
            elif ch == '"':
                self._cadena = self._prof > 0   # fuera de un objeto, una comilla no abre nada
            elif ch == "{":
                if self._prof == 0:
                    self._ini = self._i
                self._prof += 1
            elif ch == "}" and self._prof > 0:
                self._prof -= 1
                if self._prof == 0:
                    try:
                        o = json.loads(s[self._ini:self._i + 1])
                    except (ValueError, RecursionError):
                        o = None
                    if isinstance(o, dict):
                        out.append(o)
            self._i += 1
        self.entregados += len(out)
        return out

    def reemplazar(self, todo: str) -> list[dict]:
        """El texto final de la ronda: si sigue lo que llegó, lo que falta; si no, los objetos que no se entregaron."""
        if not isinstance(todo, str):
            return []
        if todo.startswith(self.texto):
            return self.agregar(todo[len(self.texto):])
        ya = self.entregados
        nuevo = Lector()
        objetos = nuevo.agregar(todo)
        self.__dict__.update(nuevo.__dict__)
        self.entregados = max(ya, len(objetos))
        return objetos[ya:]


# ───────────────────────────── El plan que crece ─────────────────────────────

def _es_paso(o: dict) -> bool:
    return "dice" in o or "narracion" in o


class PlanEnFlujo:
    """Los pasos que llegan, compuestos como la op `recorrido`. `agregar` devuelve qué fue: «titulo», «paso» (el plan
    creció: `r` es el recorrido absoluto con todos sus pasos), «cierre» o «nada» (no valía, o ya no cabía: queda un
    aviso). El id es el del primer paso que valió y no cambia."""

    def __init__(self, g: guion_presentacion.Guion, ci: int, largo: str = "normal"):
        self.g, self.ci = g, ci
        self.maximo = min(rec.MAX_ESCENAS, LARGOS.get(largo, LARGOS["normal"])[1] + 2)
        self.titulo: str | None = None
        self.pasos: list[dict] = []
        self.cierre: dict | None = None
        self.sugerencias: list[str] = []
        self.descartes: list[str] = []
        self.avisos: list[str] = []      # los de la última composición (de todos los pasos)
        self.suaves: set[int] = set()
        self.r: dict | None = None
        self.ms = 0
        self.lleno = False

    def _componer(self, pasos: list[dict], cierre: dict | None) -> tuple[dict, list[str], set[int], int]:
        from .herramientas import interfaz   # aquí: interfaz importa este módulo al correr la op `plan`
        crudo: dict[str, Any] = {"op": "recorrido", "pasos": pasos}
        if self.titulo:
            crudo["titulo"] = self.titulo
        if cierre:
            crudo["cierre"] = cierre
        try:
            a = interfaz.PresentacionEntrada.model_validate(crudo)
        except ValidationError as e:
            raise ErrorHerramienta("no tiene la forma de un paso del plan", "invalido",
                                   detalle={"errores": [x.get("msg") for x in e.errors()][:3]}) from None
        r, avisos, suaves = interfaz._componer(self.g, a)
        problemas = rec.validar(r, self.g)
        if problemas:
            raise ErrorHerramienta("; ".join(problemas[:2]), "bytes" if "pesa" in problemas[0] else "invalido")
        ms = rec.duracion_ms(r, self.g)
        if ms > rec.MAX_DURACION_MS:
            raise ErrorHerramienta("el plan ya dura lo más que puede durar", "duracion")
        return r, avisos, suaves, ms

    def _fijar(self, r: dict, avisos: list[str], suaves: set[int], ms: int) -> None:
        if self.r is not None:
            r = {**r, "id": self.r["id"]}
        self.r, self.avisos, self.suaves, self.ms = r, avisos, suaves, ms

    def agregar(self, o: Any) -> str:
        if not isinstance(o, dict):
            return "nada"
        if _es_paso(o):
            return self._paso(o)
        if "cierre" in o or "sugerencias" in o or "puntos" in o:
            self._cierre(o)
            return "cierre"
        if "titulo" in o and self.r is None:
            t = o.get("titulo")
            if isinstance(t, str) and TITULO_MIN <= len(t.strip()) <= rec.MAX_TITULO:
                self.titulo = t.strip()
                return "titulo"
        return "nada"

    def _paso(self, o: dict) -> str:
        n = len(self.pasos) + 1
        if self.lleno or len(self.pasos) >= self.maximo:
            if not self.lleno:
                self.descartes.append(f"Paso {n} y siguientes: el plan ya tenía {len(self.pasos)} pasos; se omitieron")
            self.lleno = True
            return "nada"
        if not self.pasos and not o.get("capitulo"):
            o = {"capitulo": self.g.capitulos[self.ci]["id"], **o}
        try:
            compuesto = self._componer([*self.pasos, o], None)
        except ErrorHerramienta as e:
            if e.codigo in ("duracion", "bytes"):
                self.lleno = True
                self.descartes.append(f"Paso {n} y siguientes: {e.mensaje}; se omitieron")
                return "nada"
            if not self.pasos and self.titulo:
                # quizá es el título el que no se puede proyectar: sin él, el del capítulo
                titulo, self.titulo = self.titulo, None
                try:
                    compuesto = self._componer([o], None)
                except ErrorHerramienta:
                    self.titulo = titulo
                else:
                    self.descartes.append("El título no se podía proyectar: va el del capítulo")
                    self.pasos.append(o)
                    self._fijar(*compuesto)
                    return "paso"
            self.descartes.append(f"Paso {n}: {e.mensaje}; se omitió")
            return "nada"
        self.pasos.append(o)
        self._fijar(*compuesto)
        return "paso"

    def _cierre(self, o: dict) -> None:
        from .herramientas import interfaz
        c = o.get("cierre", {"puntos": o["puntos"]} if isinstance(o.get("puntos"), list) else None)
        if isinstance(c, list):
            c = {"puntos": c}
        if isinstance(c, dict) and isinstance(c.get("puntos"), list):
            self.cierre = {"puntos": [x for x in c["puntos"] if isinstance(x, str)][:rec.MAX_PUNTOS]}
        try:
            self.sugerencias = list(interfaz._sugerencias_a_su_manera(o.get("sugerencias")) or [])
        except Exception:  # noqa: BLE001 - las sugerencias son solo para el chat: sin ellas, nada
            self.sugerencias = []

    def terminar(self) -> None:
        """Con el cierre, si vale (si no, sin él y con un aviso)."""
        if self.r is None or not self.cierre:
            return
        try:
            self._fijar(*self._componer(self.pasos, self.cierre))
        except ErrorHerramienta as e:
            self.descartes.append(f"El cierre no se pudo proyectar ({e.mensaje}): el plan termina sin él")
            self.cierre = None


# ───────────────────────────── La herramienta ─────────────────────────────

class _Detenido(Exception):
    """La persona detuvo el plan, otra orden lo cerró o llegó otro mientras se escribía."""


NOTA_PLAN = (
    "El plan se escribió en flujo y la sala lo vio y lo oyó mientras se escribía: la tarjeta del chat lo muestra con sus "
    "sugerencias y el turno terminó ahí (no hacía falta otra respuesta). La explicación ES la narración: no la repitas. "
    "Si la persona escribe, el plan se pausa: responde breve y sigue con control_recorrido (continuar), o arma otro "
    "plan. Si vienen «avisos», el plan corrió con lo que sí valía: tenlos en cuenta en el próximo.")
NOTA_DETENIDO = (
    "El plan se detuvo mientras se escribía (la persona lo detuvo, otra orden cambió la pantalla o llegó otro plan): "
    "quedó con los pasos que alcanzaron a escribirse.")


async def escribir(ctx: Any, a: Any, g: guion_presentacion.Guion) -> Resultado:
    """La op `plan` del asistente: escribe el plan en flujo y lo publica paso a paso (ver el docstring del módulo)."""
    from .herramientas import interfaz
    if ctx.proveedor is None or ctx.emitir is None:
        raise ErrorHerramienta("El plan en flujo solo lo escribe el asistente del panel: arme el plan con guion y "
                               "recorrido.", "sin_redactor", estado=409)
    ci = interfaz._resolver_capitulo(g, a.capitulo)
    db, uid = ctx.db, ctx.quien.uid
    doc = await run_in_threadpool(pantalla_off.leer, db, uid)
    abierta = pantalla_off.conectada(doc)
    destino = "pantalla_off" if abierta else "vista"
    previo = pantalla_off.recorrido_de(doc, g)
    auto = pantalla_off.auto_de(doc, g)
    e = pantalla_off.estado(pantalla_off.a_la_vista(doc, g), g) if doc else None
    en_pantalla = pantalla_off.describir(e, g) if e and abierta else ""
    largo = a.largo or ("corto" if auto and auto["activa"] else "normal")
    plan = PlanEnFlujo(g, ci, largo)
    sistema = sistema_de(g, ci)
    mensajes = [{"role": "user", "content": [{"type": "text", "text": mensaje_de(g, ci, a.encargo, largo, en_pantalla)}]}]
    if destino == "vista":   # «El asistente prepara la explicación…» en la presentación, hasta el primer paso
        ctx.emitir({"tipo": "accion", "accion": {"tipo": "presentacion", "op": "preparando", "activar": True}})

    cola: asyncio.Queue = asyncio.Queue()

    def al_evento(ev: dict) -> None:
        tipo = ev.get("tipo") if isinstance(ev, dict) else None
        if tipo == "texto" and isinstance(ev.get("texto"), str):
            cola.put_nowait(("texto", ev["texto"]))
        elif tipo == "texto_ronda" and isinstance(ev.get("texto"), str):
            cola.put_nowait(("todo", ev["texto"]))

    t0 = time.monotonic()
    tarea = asyncio.ensure_future(ctx.proveedor.generar(sistema, mensajes, [], max_tokens=TOKENS, esfuerzo="low",
                                                        al_evento=al_evento, rapido=True))
    tarea.add_done_callback(lambda _t: cola.put_nowait(("fin", None)))
    lector = Lector()
    publicado = 0          # los pasos que ya están en la pantalla
    detenido = False
    fallo: BaseException | None = None

    async def publicar(abierto: bool) -> None:
        nonlocal publicado
        r = plan.r
        if publicado == 0:
            await run_in_threadpool(pantalla_off.guardar_recorrido, db, uid, r, destino, "asistente", abierto)
            if destino == "pantalla_off" and previo and not previo["cerrado"] and previo["destino"] == "vista":
                ctx.emitir({"tipo": "accion", "accion": {"tipo": "presentacion", "op": "control_recorrido",
                                                         "rid": previo["id"], "accion": "detener",
                                                         "motivo": "otra_orden"}})
        elif await run_in_threadpool(pantalla_off.crecer_recorrido, db, uid, r, abierto) is None:
            raise _Detenido()
        if destino == "vista":
            ctx.emitir({"tipo": "accion", "accion": {"tipo": "presentacion", "op": "recorrido", "recorrido": r,
                                                     **({"sigue": True} if publicado else {}),
                                                     **({"abierto": True} if abierto else {})}})
        ctx.emitir({"tipo": "accion", "accion": {**interfaz._tarjeta(g, r, destino, plan.ms, plan.sugerencias),
                                                 **({"abierto": True} if abierto else {})}})
        publicado = len(r["escenas"])

    try:
        while True:
            espera = PLAZO_S - (time.monotonic() - t0) if publicado else PRIMER_PASO_S - (time.monotonic() - t0)
            try:
                tipo, x = await asyncio.wait_for(cola.get(), max(0.05, espera))
            except TimeoutError:
                raise TimeoutError("la redacción no llegó a tiempo") from None
            if tipo == "texto":
                objetos = lector.agregar(x)
            elif tipo == "todo":
                objetos = lector.reemplazar(x)
            else:
                respuesta = tarea.result()   # (lanza si la redacción falló)
                final = "".join(b.get("text", "") for b in respuesta.contenido or []
                                if isinstance(b, dict) and b.get("type") == "text")
                objetos = lector.reemplazar(final) if final else []
                u = respuesta.uso
                await run_in_threadpool(conv_db.sumar_uso, db, uid, u.entrada, u.salida, u.cache_lectura,
                                        u.cache_escritura, u.creditos)
            for o in objetos:
                if plan.agregar(o) == "paso":
                    await publicar(True)
            if tipo == "fin":
                break
    except _Detenido:
        detenido = True
    except asyncio.CancelledError:
        raise
    except Exception as ex:  # noqa: BLE001 - se decide abajo: con pasos publicados, el plan termina con ellos
        fallo = ex
        log.warning("Asistente: la redacción del plan falló (%s)", type(ex).__name__)
    finally:
        if not tarea.done():
            tarea.cancel()
    if plan.r is None:
        if destino == "vista":
            ctx.emitir({"tipo": "accion", "accion": {"tipo": "presentacion", "op": "preparando", "activar": False}})
        raise ErrorHerramienta(
            "No se pudo escribir el plan en flujo" + (" a tiempo" if isinstance(fallo, TimeoutError) else "") +
            ": arme el plan como siempre, con guion (los datos del capítulo) y recorrido.", "plan_fallo", estado=502)
    if not detenido:
        plan.terminar()
        try:
            await publicar(False)
        except _Detenido:
            detenido = True
    r = plan.r
    avisos = [*plan.descartes, *plan.avisos, *interfaz._avisos(g, r, plan.suaves)]
    if fallo is not None:
        avisos.insert(0, "La redacción se cortó a mitad: el plan quedó con los pasos que alcanzaron a escribirse")
    minutos, segundos = divmod(round(plan.ms / 1000), 60)
    dura = f"{minutos} min {segundos} s" if minutos else f"{segundos} s"
    contenido: dict[str, Any] = {
        "plan": {"id": r["id"], "titulo": r["titulo"], "pasos": len(r["escenas"]), "cierre": bool(r["cierre"]),
                 "duracion_estimada_s": round(plan.ms / 1000), "se_reproduce_en": interfaz.DONDE_SUENA[destino],
                 "en_flujo": True},
        "pasos": [{"n": n, "dice": " ".join(esc["frases"]),
                   "muestra": interfaz._muestra(g, esc, n in plan.suaves, r["escenas"][n - 2] if n > 1 else None)}
                  for n, esc in enumerate(r["escenas"], 1)],
        "nota": NOTA_DETENIDO if detenido else NOTA_PLAN}
    if plan.sugerencias:
        contenido["sugerencias"] = plan.sugerencias
    if avisos:
        contenido["avisos"] = avisos[:interfaz.MAX_AVISOS] + (
            [f"y {len(avisos) - interfaz.MAX_AVISOS} avisos más"] if len(avisos) > interfaz.MAX_AVISOS else [])
    if auto and auto["activa"]:
        c = g.capitulos[g.por_id(auto["capitulo"])]
        contenido["automatica"] = (
            "La presentación automática está encendida: este plan la interrumpe y, cuando termine, sigue sola en "
            f"{c['nombre']}, paso {auto['paso']} de {len(c['pasos'])}. No hace falta reiniciarla.")
    resumen = f"Plan «{r['titulo']}» · {len(r['escenas'])} pasos · ≈{dura}" + (" · detenido" if detenido else "")
    return Resultado(contenido, resumen, termina_turno=not detenido)
