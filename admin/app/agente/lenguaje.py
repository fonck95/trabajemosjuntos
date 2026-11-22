"""Cómo habla el asistente cuando le explica la propuesta a la sala, y el glosario de las siglas del guion.

Por qué existe. La presentación técnica se le muestra a la comunidad, no a ingenieros: lo que se dice (los pasos del
plan guiado, la explicación suelta, la respuesta inmediata, las respuestas habladas) tiene que entenderse a la primera,
con palabras de todos los días y con el léxico que la gente ya le conoce al candidato («le apostamos», «podamos», «el
casco urbano», «recursos económicos», «empleo»). El guion, en cambio, sale de documentos técnicos y trae siglas (PTAR,
NSR-10, BIM…) y tecnicismos («impulsión», «frontera de inyección»). Por eso:

* `COMO_SE_EXPLICA` son las reglas de esa voz. Van enteras en las instrucciones de quien escribe lo que oye la sala:
  el redactor del plan en flujo (`redactor.INSTRUCCIONES`) y el asistente del panel cuando tiene la presentación
  (`sistema.texto`). `EN_CORTO` es la misma idea en una frase, para lo que no tiene lugar para más: la respuesta
  inmediata (`sistema.SISTEMA_ADELANTO`), las respuestas habladas (`sistema.RESPUESTA_HABLADA`), la nota del guion y
  del paso (`herramientas/interfaz.py`) y las instrucciones del servidor MCP (`api/mcp.py`).
* `SIGLAS` dice, de cada sigla, abreviatura o unidad que trae el guion, su nombre completo y qué es en palabras
  sencillas. Al modelo le llegan solo las de lo que va a explicar (`siglas_en`: las del capítulo, con su guion; las del
  paso, con `ir`), así dice el nombre completo y, si hace falta, para qué sirve. Una prueba (test_lenguaje.py) revisa
  que toda sigla del guion esté aquí: la que llegue con una propuesta nueva hay que explicarla.
* Las palabras cambian; los datos no: las cifras, los nombres y los plazos siguen saliendo solo del guion, tal como
  vienen, y la voz no agrega ideas ni promesas. La primera persona del plural es la de la propuesta y la comunidad
  («le apostamos», «juntos»): nunca un «yo» ni una cita del candidato (la voz puede ser la clonada del administrador).
* La presentación automática no tiene modelo: dice la narración escrita a mano de cada paso (`tecnica.narracion` de
  data/propuesta/general.json, que `guion.derivar` deja en el paso), escrita con estas mismas reglas; la prueba también
  la revisa (`problemas_de_voz`: sin siglas, sin lo que salió de la propuesta, «casco urbano» completo).
* Solo la biblioteca estándar: lo importan el redactor, el sistema, la herramienta y las pruebas, sin el panel.
"""
from __future__ import annotations

import re
from typing import Any

# Lo que salió de la propuesta y la voz no nombra (el registro de cambios de la campaña)
RETIRADO = ("puestos de salud", "puesto de salud", "malecón")
# Los nombres que se dicen como los conoce la gente, sin variantes
NOMBRES = ("Yondó", "el hospital Héctor Abad Gómez", "la ruta chelera", "la 15", "la cancha de sóftbol",
           "el parque principal", "la Casa de la Cultura", "la iglesia", "el centro agroindustrial",
           "la planta de tratamiento de aguas residuales", "vivienda joven")

COMO_SE_EXPLICA = "\n".join([
    "CÓMO HABLAS: le explicas la propuesta a la gente de Yondó, no a ingenieros. Que se entienda a la primera.",
    "- Sencillo y cercano, como en una reunión del barrio o de la vereda: frases cortas, palabras de todos los días y "
    "una idea por frase, con respeto (a la sala, «ustedes»: «Aquí ven…», «Fíjense en…»).",
    "- Explica cada parte: qué es, para qué sirve y a quién le sirve, antes que los detalles. Pocas cifras: la que "
    "ayuda a entender, tal como viene, con la unidad dicha entera (metros cuadrados, hectáreas, kilómetros, litros por "
    "segundo).",
    "- Sin siglas: di siempre el nombre completo («la planta de tratamiento de aguas residuales», nunca «la PTAR»); lo "
    "que quiere decir cada sigla del guion viene en «siglas». De una norma o una entidad, di para qué sirve («la norma "
    "colombiana para construir resistente a los sismos»).",
    "- Sin tecnicismos: cambia la palabra técnica por lo que hace o lo que logra («la torre aguanta un terremoto y "
    "sigue atendiendo», no «edificación indispensable del grupo de uso IV»; «el agua sube con bombas hasta el tanque», "
    "no «impulsión»). Si no hay cómo evitarla, explícala en la misma frase.",
    "- Con el léxico del candidato: la primera persona del plural de la propuesta y la comunidad («le apostamos a…», "
    "«que podamos…», «juntos») y, de vez en cuando, un «¿sí?» al final de una frase para ver si la sala va entendiendo "
    "(no en cada frase). «El casco urbano», completo, nunca «el casco» solo; «recursos económicos», nunca «plata»; "
    "«empleo», no «trabajo», cuando se habla de puestos de empleo («trabajo de parto» y «¡Trabajemos juntos!» no se "
    "tocan).",
    "- Los nombres, como los conoce la gente y sin variantes: " + ", ".join(NOMBRES[:-1]) + " y " + NOMBRES[-1] +
    ". El hospital es siempre el hospital Héctor Abad Gómez. Úsalos donde el guion habla de ellos: no se los pongas a "
    "obras que no los traen.",
    "- Nunca hablas de puestos de salud ni de malecón: salieron de la propuesta.",
    "- Las palabras cambian; los datos no: cifras, nombres y plazos solo del guion, sin ideas, promesas ni datos que no "
    "estén en él. Nada de «yo» ni de citas o promesas a nombre del candidato.",
])

EN_CORTO = ("en palabras sencillas: sin siglas (di el nombre completo) ni tecnicismos, «el casco urbano» completo y "
            "«recursos económicos», nunca «plata»")

# Cada sigla, abreviatura o unidad del guion: su nombre completo y qué es, en palabras sencillas. La clave es como se
# escribe en el guion (la búsqueda distingue mayúsculas: «ART» no es «arte»)
SIGLAS: dict[str, str] = {
    "PTAR": "planta de tratamiento de aguas residuales: donde se limpian las aguas negras antes de devolverlas al caño o al río",
    "PTAP": "planta de tratamiento de agua potable (la potabilizadora): donde el agua se limpia para que se pueda tomar",
    "EBAR": "estación de bombeo de aguas residuales: bombas que empujan las aguas negras por la red",
    "ECA": "estación de clasificación y aprovechamiento: donde se separa el reciclaje para aprovecharlo y no enterrarlo",
    "NSR-10": "Reglamento Colombiano de Construcción Sismo Resistente: la norma para construir resistente a los sismos",
    "DMO": "capacidad moderada de disipación de energía: cuánto movimiento de un sismo absorbe la estructura sin caerse",
    "BIM": "modelado de información de la construcción: la obra hecha completa en el computador, pieza por pieza, "
           "antes de construirla",
    "IFC": "formato abierto para compartir el modelo de la obra en el computador entre los diseñadores",
    "IFC4": "la versión 4 del formato abierto para compartir el modelo de la obra en el computador",
    "LOIN": "nivel de información que se le exige a cada parte del modelo de la obra en el computador",
    "4D": "el modelo de la obra con el tiempo: qué se construye en cada momento",
    "5D": "el modelo de la obra con las cantidades de cada material",
    "DNP": "Departamento Nacional de Planeación: la entidad nacional de los proyectos tipo",
    "DANE": "Departamento Administrativo Nacional de Estadística: el que hace el censo",
    "EOT": "Esquema de Ordenamiento Territorial: el plan que dice qué se puede construir y dónde en el municipio",
    "PDET": "Programas de Desarrollo con Enfoque Territorial: los de los municipios más golpeados por el conflicto",
    "ZOMAC": "Zonas Más Afectadas por el Conflicto Armado",
    "OCAD": "Órgano Colegiado de Administración y Decisión: el que aprueba los proyectos de regalías",
    "ANH": "Agencia Nacional de Hidrocarburos: la que administra el petróleo y el gas del país",
    "ART": "Agencia de Renovación del Territorio",
    "IPM": "índice de pobreza multidimensional: mide la pobreza por lo que le falta a un hogar, no solo por lo que gana",
    "NBI": "necesidades básicas insatisfechas: hogares sin lo básico (vivienda, servicios, escuela)",
    "REPS": "Registro Especial de Prestadores de Servicios de Salud: la lista oficial de lo que cada sede puede atender",
    "TPR": "habitación de trabajo de parto, parto y recuperación: la mamá pasa todo el parto en el mismo cuarto",
    "VIVA": "Empresa de Vivienda de Antioquia",
    "TIC": "tecnologías de la información y las comunicaciones: internet, telefonía y redes",
    "MinTIC": "Ministerio de Tecnologías de la Información y las Comunicaciones",
    "EPM": "Empresas Públicas de Medellín",
    "CREG": "Comisión de Regulación de Energía y Gas",
    "E.S.E.": "Empresa Social del Estado: así se llama un hospital público",
    "ESE": "Empresa Social del Estado: así se llama un hospital público",
    "VIS": "vivienda de interés social: la vivienda para las familias de menos ingresos, con subsidio",
    "EPS": "entidad promotora de salud: la aseguradora de salud de cada persona",
    "IPS": "institución prestadora de servicios de salud: el hospital, la clínica o el centro donde atienden",
    "SECOP": "Sistema Electrónico de Contratación Pública: donde se publican los contratos del Estado",
    "PSMV": "Plan de Saneamiento y Manejo de Vertimientos: el plan para dejar de echar aguas negras sin tratar",
    "PGIRS": "Plan de Gestión Integral de Residuos Sólidos: el plan de la basura del municipio",
    "LED": "luces de bajo consumo",
    "CO2": "dióxido de carbono: el gas que calienta el planeta",
    "Res.": "Resolución (una norma)",
    "kWp": "kilovatios pico: lo más que dan los paneles solares a pleno sol",
    "Wp": "vatios pico: lo más que da un panel solar a pleno sol",
    "MWp": "megavatios pico: mil kilovatios pico",
    "kWh": "kilovatios hora: la energía que se cobra en el recibo",
    "GWh": "gigavatios hora: un millón de kilovatios hora",
    "kV": "kilovoltios: el voltaje de una línea eléctrica",
    "kVA": "kilovoltiamperios: la capacidad de un transformador",
    "m²": "metros cuadrados",
    "m³": "metros cúbicos",
    "ha": "hectáreas (una hectárea son 10.000 metros cuadrados)",
    "km": "kilómetros",
    "km²": "kilómetros cuadrados",
}
# Lo que se escribe en mayúsculas en el guion y no es una sigla que haya que explicar: nombres propios en letras
# grandes, números romanos y palabras que la gente ya dice así
NO_SON_SIGLAS = frozenset({"YONDÓ", "CASABE", "II", "III", "IV", "Sisbén", "SISBÉN", "OpenStreetMap"})


def _patron(sigla: str) -> re.Pattern:
    # Sin letras ni dígitos pegados antes o después; una unidad («m²», «ha», «km»), solo detrás de un número
    if sigla in ("m²", "m³", "ha", "km", "km²", "kWp", "Wp", "MWp", "kWh", "GWh", "kV", "kVA"):
        return re.compile(r"(?<=\d)\s?" + re.escape(sigla) + r"(?![\w²³])")
    return re.compile(r"(?<![\w.])" + re.escape(sigla) + r"(?![\w²³])")


_PATRONES = {s: _patron(s) for s in SIGLAS}


def _textos(v: Any):
    if isinstance(v, str):
        yield v
    elif isinstance(v, dict):
        for x in v.values():
            yield from _textos(x)
    elif isinstance(v, (list, tuple)):
        for x in v:
            yield from _textos(x)


def siglas_en(contenido: Any) -> dict[str, str]:
    """Las entradas de `SIGLAS` que aparecen en los textos de `contenido` (texto, o un objeto o una lista con textos:
    el capítulo del guion, un paso), en el orden del glosario. Vacío si no trae ninguna."""
    texto = "\n".join(_textos(contenido))
    return {s: d for s, d in SIGLAS.items() if _PATRONES[s].search(texto)}


# Para revisar lo que se dice ya escrito (la narración de la presentación automática): las siglas que se oyen como
# letras sueltas, lo retirado y «el casco» sin «urbano»
_SIGLA_SUELTA = re.compile(r"(?<![\w.])[A-ZÁÉÍÓÚÑ]{2,}[0-9]*(?:-[0-9]+)?(?![\w])")
_CASCO_SOLO = re.compile(r"\bcasco\b(?!\s+urbano)", re.I)
_PLATA = re.compile(r"\bplata\b", re.I)


def problemas_de_voz(texto: Any) -> list[str]:
    """Lo que no cumple la voz en un texto para decir (vacío si cumple): una sigla (salvo `NO_SON_SIGLAS`), una
    abreviatura del glosario («Res.»), algo retirado de la propuesta, «el casco» sin «urbano» o «plata»."""
    if not isinstance(texto, str):
        return []
    out = [f"sigla «{m.group(0)}»" for m in _SIGLA_SUELTA.finditer(texto) if m.group(0) not in NO_SON_SIGLAS]
    out += [f"abreviatura «{s}»" for s in ("Res.",) if _PATRONES[s].search(texto)]
    bajo = texto.lower()
    out += [f"«{x}» salió de la propuesta" for x in RETIRADO if x in bajo]
    if _CASCO_SOLO.search(texto):
        out.append("«casco» sin «urbano»")
    if _PLATA.search(texto):
        out.append("«plata» en vez de «recursos económicos»")
    return out
