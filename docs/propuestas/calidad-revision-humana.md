# Propuesta: ¿la mala calidad de datos debe detener un caso?

**Estado:** abierta, para decidir en equipo. **Afecta a:** Ana Pau (orquestador), Mario (reglas
de calidad), Michelle (reporte), Emiliano (backend).

## Qué hay hoy

- La herramienta `evaluar_calidad` ([mcp.md](../mcp.md)) revisa los contratos de un caso:
  monto, moneda, fecha, proveedor, RFC y contradicciones entre fuentes. Reutiliza las reglas de
  Mario (`agente_deteccion/normalizacion.py` y `construir_excluidos`); no hay reglas nuevas.
- El orquestador de demo la llama antes de Detección y deja el evento `calidad_evaluada` en la
  bitácora. **No detiene el caso.**
- Detección ya marca como `no_evaluable` las señales que no se pueden calcular, y el reporte las
  lista en "Limitaciones".

Ejemplo real (base local): una consulta de 20 contratos con coincidencia en el 69-B devolvió
**20 de 20 sin RFC**. Esas coincidencias se hicieron solo por nombre. El reporte lo menciona,
pero el auditor podría no notarlo.

## Lo que hay que decidir

**1. ¿Detener o solo declarar?**

| Opción | A favor | En contra |
|---|---|---|
| **A. Solo declarar** (como hoy) | Sin fricción; nada cambia en el grafo | El aviso puede pasar desapercibido |
| **B. Detener si pasa un umbral** | Una persona confirma antes de ver señales sobre datos malos; es el comportamiento esperado de un Data Steward | Un paso más para el auditor; hay que definir el umbral |

**2. Si es B, ¿qué umbral?** Propuesta para discutir: detener si más del **50 %** de los contratos
del caso tiene un problema que impide **todas** las reglas que aplicarían (p. ej., sin RFC cuando
la pregunta es sobre el 69-B), o si hay **cualquier** contradicción de monto entre fuentes.

**3. ¿Dónde vive el umbral?** Propuesta: en `clean.config_calidad` (ya existe), no en el código.
Así cambiarlo es un cambio de configuración auditable, no un despliegue.

**4. ¿Cómo entra al grafo?** (Ana Pau) Propuesta: un nodo `calidad` entre `consulta` y
`deteccion`. Si se detiene, usar el estado `bloqueado` que ya existe, con el motivo en lenguaje
claro; el auditor desbloquea para continuar. **No hace falta un estado nuevo** ni cambiar el
contrato «Estado del caso».

## Si se aprueba B, quién hace qué

| Trabajo | Quién |
|---|---|
| Umbral en `clean.config_calidad` | Mario |
| Nodo `calidad` y bloqueo en el grafo | Ana Pau |
| Mostrar el resumen de calidad en el reporte (sección propia, no solo en limitaciones) | Michelle |
| Endpoint para que el front muestre la calidad del caso | Emiliano |
