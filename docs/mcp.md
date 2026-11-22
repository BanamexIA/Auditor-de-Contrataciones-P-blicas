# Servidor MCP: herramientas gobernadas

Los agentes no tocan la base de datos directamente: usan estas herramientas, que aplican las
reglas de gobierno y dejan rastro en la bitácora del caso. Código: [backend/herramientas/](../backend/herramientas/).

## Herramientas

| Herramienta | Qué hace | Bitácora |
|---|---|---|
| `describir_datos()` | Vistas permitidas, significado de cada columna (capa semántica) y cobertura por año y fuente | — (solo metadatos) |
| `consultar_contratos(caso_id, sql)` | Valida el SQL (un solo `SELECT`, vistas `clean.v_*_agente`, `LIMIT`) y lo ejecuta con `agent_ro` | `sql_ejecutado` o `sql_rechazado` |
| `evaluar_calidad(caso_id, contratos_ids)` | Montos, moneda, fechas, proveedor, RFC y contradicciones entre fuentes; dice qué reglas no aplican a cada contrato | `calidad_evaluada` |
| `detectar_senales(caso_id, contratos_ids)` | Reglas deterministas: adjudicación directa recurrente, monto atípico, proveedor en el 69-B | `reglas_evaluadas` |
| `buscar_norma(caso_id, texto, fecha, top_k)` | Fragmentos de norma vigentes a la fecha (RAG) | `normas_recuperadas` (o `error` si el RAG no está disponible) |

Todos los eventos llevan `"origen": "mcp"`.

## Reglas de gobierno

1. **Sin caso no hay datos.** Toda herramienta que lee datos exige un `caso_id` existente y no cerrado.
2. **Solo lectura.** Los datos se leen con `agent_ro` (sesión de solo lectura, tiempo límite);
   `DELETE`, varias sentencias o tablas fuera de las vistas permitidas se rechazan *antes* de llegar a la base.
3. **Las personas deciden.** No hay herramienta para decidir señales ni cambiar el estado del caso.
   `detectar_senales` solo *propone*: no guarda señales.
4. **Límites fijos:** 200 filas por respuesta, 500 contratos por llamada, 500 caracteres de texto, `top_k` ≤ 10.
5. **Errores claros:** una petición rechazada devuelve el motivo al agente (sin datos sensibles) y queda registrada.

## Cómo conectarse

**stdio (recomendado).** El cliente lanza el servidor como proceso; no se abre ningún puerto.

```bash
docker compose exec -T backend python -m backend.herramientas
```

Desde Python (por ejemplo, el orquestador en LangGraph), dentro del contenedor del backend.
El cliente stdio del SDK lanza el proceso con un entorno mínimo, así que hay que pasarle el entorno
(ahí están las credenciales de `agent_ro` y `backend_app`):

```python
import os, sys
from mcp.client import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

params = StdioServerParameters(command=sys.executable, args=["-m", "backend.herramientas"],
                               env=dict(os.environ))
async with stdio_client(params) as (r, w), ClientSession(r, w) as sesion:
    await sesion.initialize()
    r = await sesion.call_tool("consultar_contratos", {"caso_id": caso_id, "sql": "SELECT ..."})
```

Para LangGraph, `langchain-mcp-adapters` convierte estas herramientas en tools de LangChain.

**HTTP.** `python -m backend.herramientas --http` escucha en `127.0.0.1:8765/mcp`. No tiene
autenticación propia: no lo expongas fuera del contenedor.

## Requisitos

- Migración `etl/sql/19_bitacora_calidad.sql` (agrega el evento `calidad_evaluada`).
- `buscar_norma` necesita una laptop disponible con `nomic-embed-text` (o `OLLAMA_EMBED_BASE_URL`).
