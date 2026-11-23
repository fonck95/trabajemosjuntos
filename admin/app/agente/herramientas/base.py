"""Lo común a todas las herramientas del asistente: la definición, el contexto con el que corren, el resultado y los
errores.

* Una `Herramienta` es de `lectura` (corre en el acto), de `escritura` (no corre hasta que la persona la aprueba en el
  panel: antes se arma su `Confirmacion`) o de `interfaz` (no toca la base: mueve el mapa o abre una vista en el
  navegador con `Resultado.acciones`).
* `permisos` son los del panel (`acceso.PERMISOS`): la herramienta solo se ofrece a quien los tiene todos, y de todas
  formas la API interna vuelve a decidir en cada llamada (`interno.ApiInterna`).
* La entrada se valida con su modelo pydantic antes de ejecutar: con `eager_input_streaming` la API de Anthropic no
  valida la entrada y el analizador tolerante del SDK puede entregar un objeto truncado.
* `ejecutar` y `confirmar` son asíncronas y nunca bloquean el bucle: lo síncrono (pymongo) va con `run_in_threadpool`.
* Una escritura del panel tiene su propio plazo (`Contexto.plazo_escritura`), algo menor que el de la herramienta en
  el bucle: si vence, la herramienta avisa que no se sabe si alcanzó a guardarse antes de que el bucle la corte con
  un «tardó demasiado» que no lo dice (la ruta sigue en su hilo y puede terminar la escritura).
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Literal

from pydantic import BaseModel, ValidationError

if TYPE_CHECKING:  # solo para los tipos: evita importar la app al cargar el módulo
    from pymongo.database import Database

    from ...acceso import Quien
    from ...config import Config
    from ..interno import ApiInterna

Tipo = Literal["lectura", "escritura", "interfaz"]
# Lo que el modelo recibe de una herramienta se recorta a esto (en caracteres del JSON)
MAX_CONTENIDO = 40_000
# El plazo de una herramienta del panel en el bucle (`bucle.PLAZO_HERRAMIENTA_S`: una prueba los compara) y lo que se
# le deja al aviso de una escritura que vence para llegar antes de que el bucle corte la herramienta
PLAZO_HERRAMIENTA_S = 60.0
MARGEN_PLAZO_S = 5.0


class ErrorHerramienta(Exception):
    """Un fallo que vuelve al modelo como `tool_result` con `is_error` (y a la interfaz como estado «error»).

    `codigo` es estable (`permiso`, `volumen`, `frecuencia`, `no_existe`, `no_contactable`, `invalido`, `sesion`,
    `base`, `mnemo`, …) y `mensaje` va en español, para que el modelo se lo explique a la persona. `fatal` termina el
    turno: la sesión cerró, MongoDB no responde o el usuario llegó a su tope diario."""

    def __init__(self, mensaje: str, codigo: str = "error", *, estado: int | None = None, detalle: Any = None,
                 fatal: bool = False):
        super().__init__(mensaje)
        self.mensaje, self.codigo, self.estado, self.detalle, self.fatal = mensaje, codigo, estado, detalle, fatal

    def para_modelo(self) -> str:
        cuerpo: dict[str, Any] = {"codigo": self.codigo, "mensaje": self.mensaje}
        if self.detalle is not None:
            cuerpo["detalle"] = self.detalle
        return json.dumps({"error": cuerpo}, ensure_ascii=False, default=str)


@dataclass
class Resultado:
    """Lo que devuelve una herramienta.

    * `contenido`: lo que ve el modelo (dict, list o str; se serializa a JSON y se recorta a `MAX_CONTENIDO`).
    * `resumen`: una línea para la interfaz («12 personas», «Nota guardada»). No va al modelo.
    * `acciones`: acciones para el navegador (`{"tipo": "navegar", "ruta": …}`, `{"tipo": "mapa", "acciones": […]}`,
      `{"tipo": "recargar"}`, `{"tipo": "insignias"}`). No van al modelo: pueden llevar coordenadas y nombres.
    * `personas`: ids de las personas cuyos datos se le sirvieron al modelo. La conversación los guarda para borrarla
      si alguna se suprime (derecho de supresión).
    * `imagenes`: bloques `image` para el modelo (solo Mnemo: `mnemo_view_image`).
    * `termina_turno`: lo que pidió la persona ya quedó hecho y a la vista (el plan en flujo de la presentación, que la
      sala ya oyó): si todo lo de la ronda salió bien, el turno termina sin otra ronda del modelo (`bucle.Turno`). El
      resultado queda en el historial y el modelo lo lee en el mensaje siguiente.
    """
    contenido: Any
    resumen: str = ""
    acciones: list[dict] = field(default_factory=list)
    personas: set[int] = field(default_factory=set)
    imagenes: list[dict] = field(default_factory=list)
    termina_turno: bool = False

    def texto_para_modelo(self) -> str:
        t = self.contenido if isinstance(self.contenido, str) else json.dumps(self.contenido, ensure_ascii=False,
                                                                                default=str)
        if len(t) > MAX_CONTENIDO:
            t = t[:MAX_CONTENIDO] + "… [recortado: pida menos resultados o una página siguiente]"
        return t


@dataclass
class Confirmacion:
    """La tarjeta que el panel muestra antes de una escritura: qué se va a hacer, con los valores exactos."""
    titulo: str
    detalle: list[tuple[str, str]] = field(default_factory=list)
    aviso: str | None = None

    def para_interfaz(self) -> dict:
        return {"titulo": self.titulo, "detalle": [[str(k), str(v)] for k, v in self.detalle], "aviso": self.aviso}


@dataclass
class Contexto:
    """Con qué corre una herramienta: la identidad del usuario del turno y sus medios.

    `api` llama a la API del panel con la sesión del usuario: es la vía preferida para todo lo que toca personas,
    porque aplica sola los permisos, el alcance, el presupuesto, las lecturas, la proyección y la auditoría. `db` es
    para lo que no tiene ruta y no es de personas (el nomenclátor de lugares, por ejemplo)."""
    quien: "Quien"
    db: "Database"
    cfg: "Config"
    app: Any
    api: "ApiInterna"
    ajustes: dict
    conversacion_id: int
    tool_use_id: str = ""
    mnemo: Any = None  # mnemo.ClienteMnemo | None
    # El modelo de la conversación (`proveedores.Proveedor`): el plan en flujo le pide su redacción (`redactor.py`)
    proveedor: Any = None
    # Emite un evento del turno mientras la herramienta corre (`{"tipo": "accion", "accion": …}`): el plan en flujo
    # publica cada paso en cuanto está escrito. None fuera de un turno (por MCP)
    emitir: Callable[[dict], None] | None = None
    # Cuándo empezó la herramienta: el bucle arma el contexto justo antes de correrla
    inicio: float = field(default_factory=time.monotonic)

    def plazo_escritura(self) -> float:
        """Los segundos que le quedan a una escritura del panel para terminar antes de que el bucle corte la
        herramienta, con margen para avisar que pudo quedar hecha (`interno.ApiInterna.pedir`)."""
        return self.inicio + PLAZO_HERRAMIENTA_S - MARGEN_PLAZO_S - time.monotonic()


Ejecutar = Callable[[Contexto, Any], Awaitable[Resultado]]
Confirmar = Callable[[Contexto, Any], Awaitable[Confirmacion]]


@dataclass
class Herramienta:
    nombre: str
    descripcion: str
    entrada: type[BaseModel]
    tipo: Tipo
    permisos: tuple[str, ...]
    etiqueta: str  # en gerundio, para la interfaz: «Buscando habitantes»
    ejecutar: Ejecutar
    confirmar: Confirmar | None = None  # obligatoria en las de escritura
    # Condición extra además de los permisos (un ajuste, una variable de entorno): (quien, ajustes_agente, cfg) -> bool
    disponible: Callable[[Any, dict, Any], bool] | None = None
    # JSON Schema explícito (las de Mnemo traen el suyo); si no, sale de `entrada`
    esquema: dict | None = None
    # Solo Mnemo: el nombre con que el servidor MCP la conoce
    nombre_remoto: str | None = None
    # Su plazo en el bucle, si no es el de siempre (`PLAZO_HERRAMIENTA_S`): la presentación escribe un plan en flujo
    plazo: float | None = None
    # Por MCP (`api/mcp.py`): el alcance de la clave que la ofrece. None = sale del tipo (lectura → «lectura»,
    # escritura → «escritura»; las de interfaz nunca); «» = nunca por MCP (necesita el chat: una foto, el navegador);
    # o un alcance explícito («analitica»)
    mcp: str | None = None

    def __post_init__(self) -> None:
        if self.tipo == "escritura" and self.confirmar is None:
            raise ValueError(f"La herramienta de escritura {self.nombre} necesita `confirmar`")

    def alcance_mcp(self) -> str | None:
        """El alcance de clave MCP que ofrece esta herramienta, o None si no se ofrece por MCP."""
        if self.nombre_remoto or self.mcp == "":
            return None
        if self.mcp:
            return self.mcp
        return {"lectura": "lectura", "escritura": "escritura"}.get(self.tipo)

    def permitida(self, quien: Any) -> bool:
        return all(quien.puede(p) for p in self.permisos)

    def input_schema(self) -> dict:
        if self.esquema is not None:
            return self.esquema
        s = self.entrada.model_json_schema()
        s.pop("title", None)
        return s

    def definicion(self) -> dict:
        """La definición para la Messages API. Sin `strict`: la entrada se valida aquí (`validar`)."""
        return {"name": self.nombre, "description": self.descripcion, "input_schema": self.input_schema(),
                "eager_input_streaming": True}

    def validar(self, crudo: Any) -> Any:
        """La entrada del modelo como instancia de `entrada`; lanza `ValidationError` si no cumple (también si no es un
        objeto)."""
        return self.entrada.model_validate(crudo)


def errores_de_validacion(e: ValidationError) -> list[str]:
    return [f"{x['msg']} en {'.'.join(map(str, x['loc'])) or 'la entrada'}" for x in e.errors()]
