# Mejoras del Agente Consulta (A5)

Plan de mejoras a partir de las mediciones del 2026-11-17. Cada mejora dice qué
error corrige, dónde va y cómo se comprueba que funcionó.

## Punto de partida

| Medición | Resultado | Detalle |
|---|---|---|
| Golden set, 1 repetición | Exactitud del SQL 75 % | [análisis](../eval/results/consulta_20261117_125443/analisis.md) |
| Golden set, 3 repeticiones | Exactitud del SQL 79.2 %; mismo resultado en 19 de 20 casos | [análisis](../eval/results/consulta_20261117_132009/analisis.md) |
| Casos de A2 | Aclaración 2 de 5; sin datos 5 de 6 | [análisis](../eval/results/consulta_casos_consulta_20261117_133449/analisis.md) |

Errores por corregir: q06, q07, q08 y q16 del golden set, y c01, c03, c04, c10
y c13 de A2.

## Mejoras

| # | Mejora | Corrige | Dónde | Cómo se comprueba | Prioridad |
|---|---|---|---|---|---|
| 1 | **Agregar el `LIMIT` en código cuando falte** (200), en lugar de rechazar la consulta. Los demás límites del validador no cambian | c03 (falló dos veces por el `LIMIT`) y los reintentos de q13 | `agents/consulta/validator.py` o `agent.py` | c03 deja de dar `error`; q13 acierta al primer intento | Alta |
| 2 | **Reintentar cuando la base rechaza el SQL**, pasándole al modelo el error de PostgreSQL. Hoy solo se reintenta cuando falla el formato o el validador | q07 (repetición 1) y q08 | `agents/consulta/agent.py` y la ejecución (A3); el medidor debe hacer lo mismo | q07 acierta las 3 veces; q08 deja de dar `error_ejecucion` | Alta |
| 3 | **Que el validador revise las columnas de cada vista**, con la lista que da `schema_context`, y diga en qué vista está una columna mal ubicada | q07 | `agents/consulta/validator.py` | Un SQL con `rfc_exacto` en `v_contratos_agente` se rechaza antes de llegar a la base, con un mensaje que lleva al `JOIN` | Alta |
| 4 | **Reglas nuevas en el prompt:** nunca `SELECT *`; en listas, columnas mínimas y sin `GROUP BY`; "preliminar" describe la clasificación y no es un filtro; `rfc_exacto`, `nivel_confianza` y `requiere_revision_humana` solo están en la vista de coincidencias (con un ejemplo de `JOIN`); incluir todos los filtros que pide la pregunta | q06, q08, q16 y c13 | `agents/consulta/prompt.py` | Los cuatro casos aciertan | Alta |
| 5 | **Conceptos que no existen en las fuentes → "sin datos".** Regla y ejemplo en el prompt: cancelaciones, pagos, sanciones, rescisiones o modificaciones no están en los datos y no se sustituyen con otra columna | c10 (afirmó cancelaciones que no existen) | `agents/consulta/prompt.py`; opcional, una lista de conceptos revisada en código | c10 responde "sin datos" | Alta |
| 6 | **Los supuestos de cobertura los escribe solo el código.** El prompt pide al modelo no escribir supuestos sobre años o cobertura, y `agent.py` descarta los que lo hagan | Supuestos falsos o vagos (q04, c13 y otros) | `agents/consulta/prompt.py` y `agent.py` | Ningún supuesto contradice la revisión de cobertura | Media |
| 7 | **Preguntas con métrica ambigua.** Decisión de equipo: pedir aclaración, o responder declarando la métrica supuesta en `supuestos`. Según lo que se decida, ejemplos en el prompt con palabras como "más", "mucho", "grande" o "gastó" | c01, c03 y c04 | `agents/consulta/prompt.py` y `eval/casos_consulta.yaml` | Los casos se califican con la regla acordada | Media (requiere decisión) |
| 8 | **Golden set:** cambiar q08 a un periodo con coincidencias (hoy su respuesta esperada es vacía) y agregar casos de empresa, como pide A5 | Evaluación de q08 | `eval/golden_set.yaml` | La respuesta esperada de q08 no es vacía | Media |
| 9 | **Medidor:** guardar el error de cada intento y calcular la consistencia entre repeticiones | Saber por qué se reintenta (q13) | `eval/run_consulta.py` | `detalle.csv` incluye el error del primer intento; el resumen muestra la consistencia | Baja |

## Orden sugerido

1. Mejoras 1 a 4: son cambios de código y de prompt, y se pueden medir de inmediato.
2. Mejoras 5 y 6, y volver a medir el golden set y los casos de A2.
3. Mejora 7, después de acordarla con el equipo.
4. Mejoras 8 y 9.

Después de cada paso se repiten las dos mediciones:

```powershell
.venv\Scripts\python -m eval.run_consulta --repeticiones 3
.venv\Scripts\python -m eval.run_consulta --casos eval/casos_consulta.yaml
```

La meta del diseño es 85 % de exactitud del SQL. Si no se alcanza, se reporta
el valor real con sus tipos de error.

## Avance

**2026-11-19 — Mejoras 1 a 6 en el código, sin medir.** La EC2 estaba apagada,
así que no se corrieron las dos mediciones. Además de lo que pedía cada mejora:

- **Regla de booleanos (con la 4):** el modelo comparaba `rfc_exacto` y
  `requiere_revision_humana` con `'S'` o `'si'`. El prompt nombra las 6 columnas
  booleanas y pide usarlas solas en `WHERE`.
- **`DATE_TRUNC` en la revisión de cobertura (con la 6):** si el modelo filtraba
  el año con `DATE_TRUNC('year', fecha_inicio)`, el aviso de año incompleto se
  perdía, porque ya no lo escribe el modelo.
- **Mensaje del validador para un alias inexistente (sobre la 3):** antes decía
  que la columna no existía, cuando lo que no existía era el alias.

**Prueba rápida sin base** (modelo local con los comentarios de las columnas
tomados de `etl/sql/07_fase4b_transform.sql`, sin ejecutar el SQL): c10 responde
"sin datos"; q04, q06, q07, q08 y c13 escriben un SQL que se ve correcto; c12 ya
lleva el aviso de 2024. q16 todavía devuelve una columna de más
(`titulo_contrato`). q04 y q06 necesitaron dos intentos; la mejora 9 diría por
qué.

**Cuidado al leer la próxima medición:** las reglas salieron de los errores del
mismo golden set, así que la exactitud puede verse mejor que con preguntas
nuevas. Los casos de empresa de la mejora 8 sirven para comprobarlo.

**2026-11-19 — Mejoras 8 y 9 en el código, sin medir.**

- **q08** ahora cubre los años completos del histórico (2011–2022), donde están
  las coincidencias por nombre, y la pregunta dice el orden y las columnas,
  porque hay más de 20 contratos que cumplen. Falta confirmar con la base que
  su resultado esperado ya no es vacío.
- **`eval/casos_empresa.yaml`:** 6 casos de empresa (5 con SQL y 1 sin datos)
  con proveedores de ComprasMX 2026. Van aparte para que el golden set siga
  siendo comparable con A4 y porque no se usaron para ajustar el prompt.
  Falta, con la base encendida, una empresa con coincidencia por RFC y otra
  solo por nombre.
- **Medidor:** `detalle.csv` trae `errores_intentos` (etapa y error de cada
  intento fallido); el resumen muestra la consistencia entre repeticiones y
  avisa si algún caso tiene un resultado esperado vacío.

Mediciones con la base encendida:

```powershell
.venv\Scripts\python -m eval.run_consulta --repeticiones 3
.venv\Scripts\python -m eval.run_consulta --casos eval/casos_consulta.yaml
.venv\Scripts\python -m eval.run_consulta --casos eval/casos_empresa.yaml
```
