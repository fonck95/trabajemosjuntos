"""El asistente del panel: un agente de Claude que conversa con el usuario que ingresó y usa herramientas.

Diseño en `admin/docs/agente.md`. En corto:

* El turno corre en el servidor (`bucle.py`) y llega al navegador como NDJSON (`api/agente.py`). La clave de Anthropic
  y el token de Mnemo nunca salen del servidor.
* Toda herramienta del panel (`herramientas/`) llama por dentro a la API que ya existe, con la sesión del usuario
  (`interno.py`): los permisos, el alcance de planilleros y consultores, el presupuesto diario, las lecturas, la
  proyección por rol, el bloqueo de quien no autorizó y la auditoría son exactamente los de la interfaz.
* Lo que llega al modelo pasa además por `minimizar.py`: datos mínimos, cédulas y teléfonos enmascarados, nunca datos
  sensibles ni listas (Ley 1581: el modelo es un tercero).
* Lo que escribe no se ejecuta hasta que la persona lo aprueba en el panel (tarjeta de confirmación).
* Las herramientas de Mnemo (`herramientas/mnemo.py`) llegan por su servidor MCP con un token del dueño; por eso solo
  las usa el administrador (y los coordinadores, si el administrador lo permite en Ajustes).
"""
