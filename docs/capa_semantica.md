# Capa semántica

> Borrador de la tarea T5 para revisión con el backend. Define qué significa cada
> número que el sistema puede calcular sobre las vistas aprobadas: grano, base de
> fechas, exclusiones, métricas y reglas de agregación. No cambia `clean`; se
> deriva del [diccionario de datos](./diccionario_datos.md) y del ETL. Lo marcado
> como **POR CONFIRMAR** es una decisión abierta (sección 8).

Los resultados son señales para revisión humana, nunca determinaciones de fraude,
corrupción o responsabilidad legal.

## 1. Alcance

El SQL generado por el Agente Consulta solo puede leer dos vistas, porque el
validador (`validate_sql` en `eval/run_benchmark.py`) rechaza cualquier otra:

- `clean.v_contratos_agente`
- `clean.v_coincidencias_69b_agente`

`agent_ro` también puede leer otros objetos de `clean`, como
`clean.v_cobertura_fuentes` o `clean.config_calidad`. Sirven como referencia del
sistema, no para el SQL que genera el modelo.

Este documento lo usan el prompt del Agente Consulta (A1), el golden set
(`eval/golden_set.yaml`), las vistas en forma de estrella (T6) y los reportes.

## 2. Fuentes y cobertura

| Fuente | Valor en `fuente` | Filas en `clean` | Cobertura temporal |
|---|---|---:|---|
| ComprasMX 2026 | `comprasmx` | 84,676 | Archivo de 2026; rango real de `fecha_inicio` **POR VERIFICAR** |
| CompraNet histórico | `historico` | 2,356,609 | Inicios válidos desde 2010-01-01, el límite de calidad; 2023 (16,896) y 2024 (1,836) son parciales |
| Listado 69-B del SAT | — | 14,837 | Fecha de publicación no disponible en `clean` |

Fecha de descarga registrada en `clean.config_calidad`: 2026-10-16.

**No hay contratos con inicio en 2025.** Una pregunta sobre un periodo sin
cobertura se responde "sin datos para ese periodo", nunca con un cero. Una
pregunta sobre 2023 o 2024 se responde con el aviso de que el año está
incompleto.

**Campos que solo existen en ComprasMX.** En el histórico quedan nulos porque la
fuente no los trae: `institucion`, `clave_institucion`,
`siglas_de_la_institucion`, `tipo_de_institucion`, `clave_ramo`,
`descripcion_ramo`, `clave_de_la_uc`, `nombre_de_la_uc`,
`numero_de_procedimiento`, `caracter_del_procedimiento`, `articulo_de_excepcion`,
`descripcion_excepcion` y `tipo_procedimiento`. El RFC del proveedor también
existe solo en ComprasMX y no está en la vista. A la inversa, `tipo_expediente`
solo existe en el histórico. Las preguntas por dependencia o
unidad compradora solo cubren ComprasMX; en el histórico se responde "dato no
disponible en la fuente", no "cero contratos".

## 3. Grano

| Vista | Una fila es | Llave | Advertencia |
|---|---|---|---|
| `v_contratos_agente` | Un registro de contrato de una fuente | No hay llave única garantizada | `codigo_contrato` puede faltar o repetirse; unicidad **POR CONFIRMAR** |
| `v_coincidencias_69b_agente` | Un registro de contrato cuyo proveedor coincide con un registro del 69-B | Ninguna declarada; se une por `codigo_contrato` | Es un contrato, no una empresa: una empresa con 20 contratos aparece 20 veces |

**Unir las dos vistas.** Se unen por `codigo_contrato`. Como el código no es
único garantizado, la unión puede repetir filas: los conteos se hacen con
`COUNT(DISTINCT c.codigo_contrato)`. La vista de coincidencias no guarda la
fuente; si el mismo código existiera en ambas fuentes, la coincidencia se
atribuiría a las dos.

**Niveles de confianza del 69-B.** `alta` significa RFC exacto y solo ocurre en
ComprasMX. `media` significa nombre normalizado exacto; es el único cruce posible
en el histórico. Por construcción (`etl/build_clean.py`), una coincidencia por
RFC tiene `requiere_revision_humana = false` y una por nombre tiene `true`; nunca
se cumplen `rfc_exacto` y `requiere_revision_humana` al mismo tiempo.

## 4. Base de fechas

- **Fecha de referencia:** `fecha_inicio`, el inicio del contrato. `fecha_fin` no
  define periodos.
- **Periodos:** rango semiabierto, por ejemplo
  `fecha_inicio >= DATE '2024-01-01' AND fecha_inicio < DATE '2025-01-01'`. Un
  filtro de rango dentro de 2010–2026 deja fuera, sin más condiciones, las fechas
  nulas y las que están fuera de rango.
- **Agrupar por año sin filtro de periodo:** agregar `fecha_inicio_valida` para
  no mezclar fechas nulas o fuera de rango. El año se obtiene con
  `EXTRACT(YEAR FROM fecha_inicio)::integer`; sin la conversión, PostgreSQL
  devuelve un número decimal.
- **Rango válido:** de 2010-01-01 a 2026-12-31, inclusivo (`clean.config_calidad`).

| `fecha_inicio_estado` | Contratos | Entra en análisis por periodo |
|---|---:|---|
| `valida` | 2,435,971 | Sí |
| `nula` | 5,307 | No |
| `fuera_de_rango` | 7 | No |
| `no_parseable` | 0 | No |

Conteos del informe del 2026-10-28, que suman los 2,441,285 contratos; el cero de
`no_parseable` se obtiene por diferencia.

Banderas informativas que no excluyen: `fecha_inicio_futura` (inicio posterior a
la fecha de descarga) y `fecha_fin_antes_inicio` (fechas invertidas, una señal de
calidad de datos).

## 5. Exclusiones

| Caso | Se queda en la vista | Entra al cálculo |
|---|---|---|
| Fecha de inicio nula, ilegible o fuera de rango | Sí | No en análisis por periodo; sí en totales sin periodo |
| `tipo_procedimiento_norm = 'sin_dato'` (3,050 en ComprasMX) | Sí | Sí en conteos; se reporta aparte en porcentajes (M4) |
| `importe` nulo | Sí | No en sumas; se informa cuántos registros no tienen importe |
| Monedas distintas | Sí | Nunca se suman entre sí |
| Contratos excluidos por el ETL | No (`clean.contratos_excluidos`, hoy 0 filas) | No |
| Campos de ComprasMX en el histórico | Sí, nulos | Nunca se interpretan como falta de actividad |

## 6. Métricas

Todos los SQL de esta sección pasan el validador actual. No se ejecutaron contra
la base para este borrador.

### M1. Contratos

Número de registros de contrato. Se cuenta con `COUNT(*)` y se separa o filtra
por `fuente`. Mientras la unicidad de `codigo_contrato` esté **POR CONFIRMAR**, se
nombra "registros de contrato".

```sql
SELECT fuente, COUNT(*) AS contratos
FROM clean.v_contratos_agente
GROUP BY fuente
ORDER BY fuente
LIMIT 20
```

### M2. Importe registrado

Suma de `importe` por fuente y moneda. En el histórico viene de `importe`; en
ComprasMX, de `importe_drc`, cuyo significado está **POR CONFIRMAR**. No se
presenta como gasto pagado ni ejercido. Se acompaña del número de registros con
importe.

```sql
SELECT fuente, moneda,
       SUM(importe) AS importe_registrado,
       COUNT(*) AS contratos,
       COUNT(importe) AS contratos_con_importe
FROM clean.v_contratos_agente
WHERE fecha_inicio >= DATE '2024-01-01'
  AND fecha_inicio < DATE '2025-01-01'
GROUP BY fuente, moneda
ORDER BY fuente, moneda
LIMIT 50
```

### M3. Contratos por tipo de procedimiento

Conteo por `tipo_procedimiento_norm`: `adjudicacion_directa`,
`invitacion_tres_personas`, `licitacion_publica`, `otro` o `sin_dato`. Es una
**clasificación preliminar**: todas las reglas del seed están `pendiente`.

```sql
SELECT fuente, tipo_procedimiento_norm, COUNT(*) AS contratos
FROM clean.v_contratos_agente
GROUP BY fuente, tipo_procedimiento_norm
ORDER BY fuente, contratos DESC
LIMIT 50
```

### M4. Porcentaje de adjudicación directa

Adjudicaciones directas entre los contratos clasificados del mismo grupo (fuente,
periodo e institución, según la pregunta). Propuesta: el denominador excluye
`sin_dato` y su número se reporta aparte (**POR CONFIRMAR**). El porcentaje se
recalcula a partir de los conteos; nunca se suman ni se promedian porcentajes.

```sql
SELECT fuente,
       COUNT(*) FILTER (WHERE tipo_procedimiento_norm = 'adjudicacion_directa') AS adjudicaciones_directas,
       COUNT(*) FILTER (WHERE tipo_procedimiento_norm <> 'sin_dato') AS contratos_clasificados,
       COUNT(*) FILTER (WHERE tipo_procedimiento_norm = 'sin_dato') AS contratos_sin_dato,
       ROUND(100.0 * COUNT(*) FILTER (WHERE tipo_procedimiento_norm = 'adjudicacion_directa')
             / NULLIF(COUNT(*) FILTER (WHERE tipo_procedimiento_norm <> 'sin_dato'), 0), 2)
           AS pct_adjudicacion_directa
FROM clean.v_contratos_agente
WHERE fuente = 'comprasmx'
GROUP BY fuente
LIMIT 10
```

### M5. Contratos por institución

Solo ComprasMX. Se excluyen las instituciones nulas.

```sql
SELECT institucion, COUNT(*) AS contratos
FROM clean.v_contratos_agente
WHERE fuente = 'comprasmx'
  AND institucion IS NOT NULL
GROUP BY institucion
ORDER BY contratos DESC, institucion
LIMIT 20
```

### M6. Contratos con coincidencia en el 69-B

Contratos distintos con coincidencia, por nivel de confianza. El informe del
2026-10-28 reporta 817 filas de coincidencia. Para separar por fuente se une con
la vista de contratos (ver sección 3).

```sql
SELECT c.fuente, m.nivel_confianza,
       COUNT(DISTINCT c.codigo_contrato) AS contratos
FROM clean.v_coincidencias_69b_agente AS m
JOIN clean.v_contratos_agente AS c
  ON c.codigo_contrato = m.codigo_contrato
GROUP BY c.fuente, m.nivel_confianza
ORDER BY c.fuente, m.nivel_confianza
LIMIT 20
```

La vista no incluye la situación del contribuyente (presunto, definitivo,
desvirtuado o sentencia favorable) ni su fecha de publicación. Ninguna respuesta
puede afirmar la situación vigente.

### M7. Registros del 69-B con coincidencia

Registros distintos del listado que coinciden con al menos un contrato. Se
cuentan por el RFC del registro 69-B.

```sql
SELECT nivel_confianza, COUNT(DISTINCT rfc) AS registros_69b
FROM clean.v_coincidencias_69b_agente
GROUP BY nivel_confianza
ORDER BY nivel_confianza
LIMIT 10
```

### M8. Proveedores distintos

Conteo de `proveedor_normalizado` distinto. Es una clave textual: puede unir
entidades diferentes o separar variantes de la misma. No es un identificador
legal.

```sql
SELECT fuente, COUNT(DISTINCT proveedor_normalizado) AS proveedores
FROM clean.v_contratos_agente
WHERE proveedor_normalizado <> ''
GROUP BY fuente
ORDER BY fuente
LIMIT 20
```

### M9. Cobertura por año

Contratos por año de inicio y fuente. Se calcula sobre la vista de contratos
porque `clean.v_cobertura_fuentes` no está permitida para el SQL generado.

```sql
SELECT EXTRACT(YEAR FROM fecha_inicio)::integer AS anio, fuente,
       COUNT(*) AS contratos
FROM clean.v_contratos_agente
WHERE fecha_inicio_valida
GROUP BY EXTRACT(YEAR FROM fecha_inicio), fuente
ORDER BY anio, fuente
LIMIT 50
```

### M10. Calidad de fechas

Contratos por estado de la fecha de inicio. Sirve para explicar cuántos registros
quedan fuera de un análisis por periodo.

```sql
SELECT fuente, fecha_inicio_estado, COUNT(*) AS contratos
FROM clean.v_contratos_agente
GROUP BY fuente, fecha_inicio_estado
ORDER BY fuente, fecha_inicio_estado
LIMIT 30
```

## 7. Reglas de agregación

- **Fuentes:** no se suman importes entre ComprasMX y el histórico; son
  poblaciones y medidas distintas. Los conteos se presentan por fuente o filtrados
  por una.
- **Monedas:** siempre se agrupa por `moneda`; no se convierte ni se suma entre
  monedas.
- **Porcentajes y promedios:** se recalculan desde los conteos del nivel pedido.
  No se suman porcentajes ni se promedian promedios.
- **Nulos:** `NULL` no es cero. `COUNT(*)` cuenta registros y `COUNT(columna)`
  solo los que tienen valor.
- **Uniones:** con la vista de coincidencias, contar `DISTINCT codigo_contrato`.
- **Rankings y empates:** ordenar por la métrica y después por la etiqueta, para
  que el resultado sea reproducible. El validador rechaza `RANK()` y
  `DENSE_RANK()`; para saber si hay empate en el corte se pide un registro más de
  los necesarios (`LIMIT n + 1`) y se compara fuera de la base.
- **Límite de filas:** como máximo 200. Si un resultado llega al límite, la
  respuesta lo dice.
- **Datos personales:** la vista de contratos no incluye RFC. Los nombres de
  proveedores pueden corresponder a personas físicas: se muestran solo cuando la
  pregunta los necesita.

Restricciones actuales del validador que afectan cómo se escribe el SQL: rechaza
`WITH` (CTE), `UNION`, `RANK()`, `DENSE_RANK()`, `NTILE()`, `unaccent()` y
cualquier tabla distinta de las dos vistas. Acepta `ROW_NUMBER()`, `FILTER`,
`NULLIF` y uniones entre las dos vistas. La búsqueda por nombre de institución
usa `ILIKE`, que ignora mayúsculas pero no acentos.

## 8. Decisiones abiertas

| # | Decisión | Propuesta mientras no haya respuesta | Quién |
|---|---|---|---|
| 1 | ¿`codigo_contrato` es único por fuente o entre fuentes? | Contar registros con `COUNT(*)` | Socio formador (pregunta 3 de [preguntas_socio_formador.md](./preguntas_socio_formador.md)) |
| 2 | ¿Qué medida de ComprasMX representa `importe`? | Reportar como "importe registrado", nunca como gasto | Socio formador (pregunta 1) |
| 3 | ¿El denominador de M4 incluye `sin_dato`? | Excluirlo y reportarlo aparte | Equipo |
| 4 | Las coincidencias solo por nombre son `media` en el código y "baja confianza" en el plan de trabajo | Usar la etiqueta de la vista y aclarar que es un cruce por nombre | Agente 2 y backend |
| 5 | Situación y fecha del 69-B fuera de las vistas | Agregarlas en T6; mientras tanto, no afirmar la situación vigente | Backend |
| 6 | ¿Se permiten CTE, `UNION`, `RANK()`, `DENSE_RANK()`, `unaccent()` y `v_cobertura_fuentes`? | Mantener el validador estricto | Agente Consulta y backend |
| 7 | Rango real de `fecha_inicio` en ComprasMX | Verificarlo con M9 | Agente Consulta |
| 8 | Los casos q08 y q19 del golden set combinan `rfc_exacto` con `requiere_revision_humana`, que nunca coinciden | Corregirlos antes de medir la exactitud (A4) | Agente Consulta |
