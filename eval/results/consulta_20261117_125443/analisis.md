# Análisis de errores de A4 (2026-11-17)

Complementa [resumen.md](resumen.md). Medición con `python -m eval.run_consulta`:
agente completo (prompt v1, validador y revisión de cobertura), modelo
`qwen2.5:7b` en Ollama sobre una RTX 3070 Ti, base de la EC2 por túnel, 20
casos del golden set y 1 repetición.

## Resultado

| Indicador | Valor |
|---|---:|
| Exactitud del SQL (16 casos que esperan SQL) | **75 %** (12 de 16) |
| Acierto global (20 casos) | 80 % |
| Casos `sin_datos` (q11, q12, q14, q20) | 100 % |
| Exactitud por dificultad (fácil / media / difícil) | 100 % / 66.7 % / 66.7 % |
| Tiempo por pregunta (media / mediana / máximo) | 10.4 s / 9.3 s / 21.6 s |

La meta del diseño es 85 %. Se reporta el valor real; las mejoras van en A5.
El máximo de 21.6 s es la primera pregunta, que incluye cargar el modelo en la GPU.

## Los cuatro errores

### q06: interpretó "preliminar" como filtro (`filas_distintas`)

Pregunta: *¿Cómo se distribuyen los tipos preliminares de procedimiento por fuente?*

```sql
-- Generado
SELECT fuente, tipo_procedimiento_norm, COUNT(*) AS procedimientos
FROM clean.v_contratos_agente
WHERE tipo_procedimiento_estado = 'pendiente'
GROUP BY fuente, tipo_procedimiento_norm ORDER BY fuente, tipo_procedimiento_norm LIMIT 100
```

Devolvió 8 filas en lugar de 10: el filtro por `pendiente` dejó fuera los
`sin_dato`. "Preliminar" describe toda la clasificación; no es un valor por
filtrar.

### q07: columna en la vista equivocada (`error_ejecucion`)

Pregunta: *¿Cuántos contratos tienen coincidencia exacta de RFC con el listado 69-B, por fuente?*

```sql
-- Generado
SELECT fuente, COUNT(*) AS coincidencias FROM clean.v_contratos_agente
WHERE fuente IN ('comprasmx', 'historico') AND rfc_exacto = 'S'
GROUP BY fuente ORDER BY coincidencias DESC, fuente LIMIT 50
```

PostgreSQL respondió `column "rfc_exacto" does not exist`. Esa columna está en
`clean.v_coincidencias_69b_agente` (y es booleana); hacía falta unir las dos
vistas por `codigo_contrato`. El validador solo revisa tablas, no columnas, así
que el error llegó hasta la base y no hubo reintento.

### q08: SQL que PostgreSQL no acepta (`error_ejecucion`)

Pregunta: *Lista hasta 20 contratos iniciados en 2024 con coincidencia en el listado 69-B que requiere revisión humana.*

```sql
-- Generado (resumido)
SELECT c.*, COUNT(DISTINCT c.codigo_contrato) AS coincidencias
FROM clean.v_contratos_agente AS c JOIN clean.v_coincidencias_69b_agente AS cc ...
GROUP BY c.codigo_contrato, c.proveedor, ...
```

PostgreSQL respondió `GroupingError`: no se puede seleccionar `c.*` con un
`GROUP BY` parcial. Una lista no necesitaba agregar. Tampoco hubo reintento,
por la misma razón que en q07.

### q16: todas las columnas (`columnas_distintas`)

Pregunta: *Muestra hasta 20 contratos cuya fecha de fin aparece antes de la fecha de inicio.*

```sql
-- Generado
SELECT * FROM clean.v_contratos_agente
WHERE fecha_fin_antes_inicio AND fecha_inicio_valida AND NOT fecha_fin IS NULL AND NOT fecha_inicio IS NULL
LIMIT 20
```

El contrato encontrado es el correcto (1 fila, igual que la respuesta
esperada), pero con las 35 columnas en lugar de 4, incluido el nombre del
proveedor. Además de no coincidir con la respuesta esperada, contradice la
regla de mostrar los campos mínimos.

## Otros hallazgos

- **Los supuestos del modelo no son confiables.** En q04 el modelo escribió
  "El año 2024 está completo" y la revisión de cobertura agregó, en la misma
  respuesta, "Cobertura incompleta en CompraNet histórico para 2024". En otros
  casos escribió supuestos vagos ("El año está incompleto" en q07 y q18) o sin
  sentido (`fecha_inicio_valida` en q16). Los supuestos de la revisión de
  cobertura fueron correctos en todos los casos.
- **q08 espera un resultado vacío.** Después de la corrección del 16 nov, no
  hay contratos de 2024 con coincidencia que requiera revisión. Con una
  respuesta esperada vacía, cualquier SQL equivocado que no devuelva filas
  contaría como acierto.
- **El reintento funcionó** en q13: la primera respuesta del modelo no fue
  válida (por formato o por el validador; el medidor no guarda cuál) y la
  segunda acertó.
- **La revisión de cobertura respondió bien los cuatro `sin_datos`** sin
  depender del modelo.

## Mejoras propuestas para A5

| # | Mejora | Corrige | Dónde |
|---|---|---|---|
| 1 | Reintentar una vez cuando la base rechaza el SQL, pasándole el error al modelo | q07, q08 | `agents/consulta/agent.py` y la ejecución (A3) |
| 2 | Que el validador revise que cada columna exista en la vista donde se usa | q07, antes de llegar a la base | `agents/consulta/validator.py` |
| 3 | Reglas del prompt: nunca `SELECT *`; en listas, columnas mínimas y sin `GROUP BY`; "preliminar" no es un filtro; `rfc_exacto`, `nivel_confianza` y `requiere_revision_humana` solo están en la vista de coincidencias | q06, q08, q16 | `agents/consulta/prompt.py` |
| 4 | Que el modelo no escriba supuestos de cobertura; esos los pone solo la revisión de cobertura | Supuestos contradictorios | `agents/consulta/prompt.py` y `agent.py` |
| 5 | Cambiar q08 a un periodo con coincidencias, para que su respuesta esperada no sea vacía | Evaluación de q08 | `eval/golden_set.yaml` |

Siguiente medición: la misma con `--repeticiones 3`, para reportar la
consistencia, y después de aplicar las mejoras.

**Actualización del mismo día:** la medición con 3 repeticiones
([consulta_20261117_132009](../consulta_20261117_132009/analisis.md)) dio
79.2 %, y los casos de A2 con el modelo real
([consulta_casos_consulta_20261117_133449](../consulta_casos_consulta_20261117_133449/analisis.md))
agregaron tres mejoras más. El plan completo está en
[docs/mejoras_agente_consulta.md](../../../docs/mejoras_agente_consulta.md).
