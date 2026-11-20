# Vistas en forma de estrella (T6)

> Borrador del Agente Consulta (2026-11-19) para revisión con Backend. El SQL
> está en [vistas_estrella.sql](./vistas_estrella.sql) y **todavía no está en
> `etl/sql/`**, porque `scripts/init_db.ps1` ejecuta todo lo que hay en esa
> carpeta. Las definiciones vienen de la [capa semántica](./capa_semantica.md)
> (T5). Lo marcado **POR CONFIRMAR** está en la sección 4.

Son vistas sobre `clean`, no un rediseño: no cambian tablas ni el ETL. Las
señales que se calculen con ellas siguen siendo indicios para revisión humana,
nunca determinaciones de fraude.

## 1. Para qué sirven

| Quién | Para qué |
|---|---|
| Agente Detección (Mario, D4 y D6) | Adjudicaciones directas recurrentes y concentración de proveedores por institución y periodo; ficha de empresa |
| Agente Reportes (Mich, R4) y front (F7) | La ficha de empresa: contratos, tipo de procedimiento, 69-B con su situación y limitaciones |
| Contrato 7 (vistas) | Deja por escrito qué vistas existen, su grano y sus llaves |
| Agente Consulta | Por ahora sigue con sus dos vistas; ver la decisión 5 |

## 2. La estrella

```text
                 v_dim_proveedor (proveedor_normalizado)
                            │
v_dim_institucion ── v_hecho_contrato ── v_dim_fecha (fecha)
 (clave_institucion)        │
                 v_dim_procedimiento (tipo_procedimiento_norm)
```

| Vista | Una fila es | Llave | Desde |
|---|---|---|---|
| `v_hecho_contrato` | Un registro de contrato de una fuente | Ninguna garantizada (igual que `v_contratos_agente`) | `clean.contratos` |
| `v_dim_proveedor` | Un `proveedor_normalizado` con contratos | `proveedor_normalizado` | `clean.contratos`, `clean.coincidencias_69b` y `clean.listado_69b` |
| `v_dim_institucion` | Una clave de institución de ComprasMX | `clave_institucion` | `clean.contratos` |
| `v_dim_fecha` | Una fecha de inicio válida que aparece en los contratos | `fecha` | `clean.contratos` |
| `v_dim_procedimiento` | Un valor de `tipo_procedimiento_norm` | `tipo_procedimiento_norm` | Lista fija de los 5 valores de M3 |

**Hecho.** Lleva las cuatro llaves, la medida (`importe` con su `moneda`), las
banderas de calidad de fechas y `tiene_coincidencia_69b`. Las reglas de la capa
semántica no cambian: el importe se suma por fuente y moneda, los periodos se
filtran con `fecha_inicio` y `fecha_inicio_valida`, y los contratos se cuentan
con `COUNT(DISTINCT codigo_contrato)` cuando hay uniones.

**Proveedor.** No expone el RFC (sección 7 de la capa semántica). En su lugar:

- `tipo_persona` (`fisica` o `moral`), deducido del largo del RFC de ComprasMX
  sin contar los RFC genéricos, para que el front no muestre nombres de
  personas físicas sin criterio.
- `en_listado_69b`, `nivel_confianza_69b` y `situacion_69b`. Resuelve la
  decisión 5 de la capa semántica (la situación del 69-B no estaba en ninguna
  vista), pero **sin fecha de publicación**, porque esa no está en `clean`
  (decisión 2).

**Institución.** Solo ComprasMX trae institución. En el histórico la llave es
nula, lo que no significa cero actividad. `nombres_publicados` muestra si una
clave tiene más de un nombre.

**Fecha.** Solo fechas válidas (2010–2026). Los años 2010, 2023 y 2024 del
histórico siguen incompletos y no hay 2025: eso lo dice la cobertura (M9), no
esta dimensión.

**Procedimiento.** Los 5 valores de M3, con un nombre legible y `es_competitivo`
(provisional).

## 3. Ejemplo de uso

Adjudicaciones directas por institución y proveedor en ComprasMX (una base para
D4):

```sql
SELECT i.institucion, p.proveedor_normalizado, COUNT(*) AS adjudicaciones_directas
FROM clean.v_hecho_contrato AS h
JOIN clean.v_dim_institucion AS i ON i.clave_institucion = h.clave_institucion
JOIN clean.v_dim_proveedor AS p ON p.proveedor_normalizado = h.proveedor_normalizado
WHERE h.fuente = 'comprasmx'
  AND h.tipo_procedimiento_norm = 'adjudicacion_directa'
GROUP BY i.institucion, p.proveedor_normalizado
ORDER BY adjudicaciones_directas DESC, i.institucion, p.proveedor_normalizado
LIMIT 20
```

## 4. Decisiones abiertas

| # | Decisión | Propuesta mientras no haya respuesta | Quién |
|---|---|---|---|
| 1 | ¿La dimensión de proveedor lleva el RFC? Mario lo usa para el cruce con el 69-B | No: dato personal. Mario sigue leyendo `clean.contratos`, o se crea una vista aparte con RFC que no se le dé al Agente Consulta | Backend y Mario |
| 2 | Fecha de publicación del 69-B: no está en `clean` (`_loaded_at` es la fecha de carga, no la del SAT) | Cargarla en el ETL desde el listado original; mientras tanto, `situacion_69b` sin fecha y con el aviso de no afirmar la situación vigente | Backend |
| 3 | Coincidencias solo por nombre: `media` en el código, "baja" en el plan | Conservar la etiqueta del ETL (`media`) y aclarar que es un cruce por nombre | Mario y Backend |
| 4 | ¿Vistas normales o materializadas? El hecho revisa `coincidencias_69b` por cada contrato y la dimensión de proveedor agrupa 2.4 millones de filas | Medir el tiempo con la consulta V7. Si es lento: índice en `coincidencias_69b(codigo_contrato)` o vistas materializadas que se refresquen después del ETL | Backend |
| 5 | ¿El Agente Consulta consulta la estrella? | No por ahora: con dos vistas planas el modelo escribe menos uniones, y A4 y A5 se midieron así. Si se decide que sí, hay que actualizar `VIEW_COLUMNS`, el prompt y el golden set, y volver a medir | Equipo |
| 6 | ¿La invitación a cuando menos tres personas es competitiva? | No (`es_competitivo = false`), provisional | Mario |
| 7 | ¿Agregar la situación del 69-B también a `v_coincidencias_69b_agente`? | Sí, una columna `situacion_del_contribuyente`, cuando se resuelva la 2. Cambia una vista del agente, así que habría que actualizar `VIEW_COLUMNS` y quitar la entrada de `VIEW_GAPS` en `agents/consulta/concepts.py`, que hoy responde "sin datos" a esa pregunta | Backend y Agente Consulta |
| 8 | Número del archivo al moverlo a `etl/sql/` | El siguiente libre. `19_` ya lo usa `19_bitacora_calidad.sql` en la rama `mcp` (2026-11-19), así que probablemente `20_` | Backend |
| 9 | `proveedor_normalizado` conserva "S A DE C V" en 420,137 contratos del histórico (verificado el 2026-11-19): `normalize_provider` quita la puntuación antes que el sufijo, así que "S.A. de C.V." queda como "S A DE C V". La dimensión de proveedor separaría a una misma empresa en dos claves | Corregir el orden en `etl/build_clean.py` (quitar el sufijo con y sin puntos) y recalcular `clean`. El agente de Mario y `agents/consulta/providers.py` copian la regla: hay que cambiarlos a la vez. Mientras tanto, el Agente Consulta busca cada proveedor con y sin esos sufijos (A5, mejora 19, 2026-11-20); eso sigue funcionando después de la corrección | Backend, Mario y Agente Consulta |

## 5. Verificación contra la base

Todas son de solo lectura y se pueden correr con `agent_ro`, que puede leer todas
las tablas de `clean`. Los resultados se anotan aquí antes de crear las vistas.

| # | Qué comprueba | Resultado esperado |
|---|---|---|
| V1 | El hecho tiene todos los contratos | 84,676 de ComprasMX y 2,356,609 del histórico |
| V2 | `clave_institucion` tiene un solo nombre | Cero claves con más de un nombre, o la lista para revisar |
| V3 | Contratos sin proveedor (quedan fuera de la dimensión) | Pocos, y se reportan |
| V4 | Valores de la situación del 69-B | Presunto, definitivo, desvirtuado, sentencia favorable u otros por revisar |
| V5 | RFC del 69-B con más de una situación | Ninguno, o la lista para revisar |
| V6 | Largo del RFC en ComprasMX | Casi todos 12 o 13 |
| V7 | Tiempo de la dimensión de proveedor | Unos segundos; si es mucho, decisión 4 |
| V8 | Códigos de contrato repetidos entre fuentes | Ninguno (si los hay, la coincidencia del 69-B se atribuye a ambas fuentes) |

```sql
-- V1
SELECT fuente, COUNT(*) AS contratos FROM clean.contratos GROUP BY fuente ORDER BY fuente;

-- V2
SELECT clave_institucion, COUNT(DISTINCT institucion) AS nombres
FROM clean.contratos WHERE clave_institucion IS NOT NULL
GROUP BY clave_institucion HAVING COUNT(DISTINCT institucion) > 1
ORDER BY nombres DESC, clave_institucion LIMIT 20;

-- V3
SELECT fuente, COUNT(*) AS sin_proveedor FROM clean.contratos
WHERE proveedor_normalizado IS NULL OR proveedor_normalizado = ''
GROUP BY fuente ORDER BY fuente;

-- V4
SELECT situacion_del_contribuyente, COUNT(*) AS registros
FROM clean.listado_69b GROUP BY situacion_del_contribuyente ORDER BY registros DESC;

-- V5
SELECT rfc, COUNT(DISTINCT situacion_del_contribuyente) AS situaciones
FROM clean.listado_69b GROUP BY rfc
HAVING COUNT(DISTINCT situacion_del_contribuyente) > 1 ORDER BY rfc LIMIT 20;

-- V6
SELECT LENGTH(TRIM(rfc)) AS largo, COUNT(*) AS contratos
FROM clean.contratos WHERE fuente = 'comprasmx' GROUP BY 1 ORDER BY 1;

-- V7: correr el SELECT de v_dim_proveedor de vistas_estrella.sql y anotar el tiempo.

-- V8
SELECT codigo_contrato FROM clean.contratos
GROUP BY codigo_contrato HAVING COUNT(DISTINCT fuente) > 1 LIMIT 20;
```

## 6. Pasos para cerrar T6

1. Backend y Mario revisan este borrador y las decisiones de la sección 4.
2. Con la EC2 prendida, el Agente Consulta corre V1 a V8 con `agent_ro` y anota
   los resultados en la sección 5.
3. Backend mueve `vistas_estrella.sql` a `etl/sql/` con su número, lo corre en
   la EC2 y comprueba que `scripts/check_comentarios.sql` no devuelve filas:
   esa es la evidencia que pide el plan.
4. Se actualiza el contrato 7 (`docs/contratos/README.md`).

`tests/test_vistas_estrella.py` revisa sin base que el SQL se lea bien, que cada
columna tenga comentario y que solo use columnas que existen en `clean`.
