# Umbrales de las reglas de detección (D1)

Los umbrales viven en la tabla `config.umbrales` (migración `etl/sql/21_config_umbrales.sql`, ya incluida en `init/00-init.sql`).
Cada fila tiene `valor`, `unidad`, `motivo` y `estado` (`provisional` o `confirmado`). Todos nacen **provisionales**:
son valores propuestos por el equipo hasta que el socio formador los confirme (decisión 5 de `AVANCE_2_PLAN.md`).

## Cómo los usa el agente
- Con `--desde-db` el agente los lee con `agent_ro` (solo lectura). Con `--parametros archivo.json` usa ese archivo (origen `archivo:...`).
- Sin base (pruebas, CSV de demostración) usa los valores de respaldo de `Parametros` y lo declara: `umbrales.origen = "codigo"`.
- Si la base está pero la tabla no se puede leer, usa el respaldo, **lo avisa por consola** y el JSON dice `"codigo (respaldo)"`.
- Una clave en la tabla que el agente no conoce es un error (no se ignora).

## Qué ve el Agente 3 (Mich)
El JSON trae `parametros` (valores planos, igual que antes) y el bloque nuevo `umbrales`:
`{"estado": "provisional" | "confirmado", "origen": ..., "provisionales": [claves], "parametros": {clave: {valor, estado, unidad, motivo}}, "nota": ...}`.
`estado` es `confirmado` solo si **todos** lo están. El reporte debe mostrar la nota cuando sea `provisional`.

## Confirmar un umbral (con el rol administrador, no con `agent_ro`)
```sql
UPDATE config.umbrales SET valor = '3', estado = 'confirmado', confirmado_por = 'Nombre del socio', confirmado_en = NOW(),
       actualizado_en = NOW() WHERE clave = 'adj_umbral_n';
```
La tabla no deja marcar `confirmado` sin `confirmado_por` y `confirmado_en`.

## Fuera de la tabla (siguen en el código, documentados)
- La correspondencia situación del 69-B → nivel (Definitivo alto; Presunto o desconocida medio; Desvirtuado o Sentencia favorable bajo).
- El nivel de `INCONSISTENCIA_FUENTES` (monto o RFC → medio; solo fecha → bajo).
