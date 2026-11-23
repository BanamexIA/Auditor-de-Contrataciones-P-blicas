# Análisis de A5: preguntas nuevas (2026-11-23)

Complementa [resumen.md](resumen.md). Es la primera medición con
`eval/casos_nuevos.yaml`: 8 preguntas que escribió Alean sin ver cómo responde
el agente y que no se usaron para ajustarlo. Misma configuración que el golden
set (`qwen2.5:7b`, base de la EC2), pero con 1 repetición y con el agente después
de la mejora 19 y del conteo de registros (`count_records=False` en el medidor).

Antes de medir se corrió solo el SQL esperado para comprobar que ningún resultado
saliera vacío. n05 daba 0 y se cambió por la tabla por fuente y tipo de
coincidencia (ver el encabezado del `.yaml`). Eso fue antes de correr el agente.

## Resultado

| Indicador | Golden set (11-20, 15:16) | Preguntas nuevas |
|---|---:|---:|
| Exactitud del SQL | 93.8 % (45 de 48) | **57.1 %** (4 de 7) |
| Acierto global | 95.0 % | 62.5 % (5 de 8) |
| Casos `sin_datos` | 100 % | 100 % (1 de 1) |
| Respuestas con dos intentos | 3 de 60 | 0 de 8 |
| Tiempo por pregunta (media) | 4.9 s | 5.2 s (17 s la primera, mientras carga el modelo) |

**Con preguntas que no vio, el agente baja de 93.8 % a 57.1 %.** Es la cifra que
dice cuánto generaliza. Son solo 7 casos con SQL y 1 repetición, así que cada
caso mueve 14 puntos: sirve para ver qué tipo de error aparece, no como
porcentaje fino.

## Por caso

| Caso | Resultado | Qué hizo el agente |
|---|---|---|
| n01 | Acierta | Agrupa por `tipo_contratacion` |
| n02 | **Falla** | Cuenta contratos y los llama "expedientes" |
| n03 | **Falla** | Toma "importe nulo" como `importe = 0` |
| n04 | Acierta | Pero agrega un filtro que nadie pidió |
| n05 | **Falla** | Omite la columna `rfc_exacto` |
| n06 | Acierta | Pero sin el aviso de que 2010 está incompleto |
| n07 | Acierta | Agrupa por `ley` |
| n08 | Acierta | "Sin datos" desde el código (mejora 5) |

## Por qué falla

**n02, unidad de conteo (modelo).** La pregunta pide expedientes; el agente usó
`COUNT(*)`, que cuenta contratos. El histórico tiene 2,356,609 contratos en
1,768,189 expedientes, así que las cifras salen infladas en 33 % en total
(1,234,750 en lugar de 952,501 en la primera fila) con la columna llamada
`expedientes`. Es el error más grave: el resultado se ve correcto y no lo es.
La nota del caso ya lo anticipaba: el prompt tiene un ejemplo que cuenta
contratos por tipo de expediente, y el modelo lo copió.

**n03, término ambiguo y supuesto callado (modelo y pregunta).** "Importe nulo"
en la base es `NULL` (5,182 contratos, sin dato de importe); el agente lo leyó
como importe en cero (1,473 contratos en 4 monedas). En el habla común "nulo"
también es "cero", así que la pregunta admite las dos lecturas. Lo que sí está
mal es que el agente eligió una sin decirlo: `supuestos` salió vacío. No se
cambia el esperado después de medir.

**n05, columna omitida (modelo).** Agrupó por fuente y `nombre_normalizado_exacto`
y dejó fuera `rfc_exacto`, que la pregunta pide. Las cifras (27 y 790) son las
correctas y, como en estos datos los dos indicadores son opuestos, la tabla dice
lo mismo. Es el fallo menos grave, pero con otros datos faltaría información.
Esta pregunta la reescribió Claude el mismo día, no Alean.

## Lo que el medidor no ve

El medidor compara filas. Tres respuestas que acertaron tienen problemas que no
cuentan como fallo:

- **n06, falta el aviso de cobertura (código).** El resultado trae 2010, que la
  cobertura marca como incompleto en el histórico (junto con 2023 y 2024), pero
  `supuestos` sale vacío. `check_coverage` solo avisa cuando el `WHERE` limita
  los años; una consulta que agrupa por año sin filtrarlos muestra los años
  incompletos sin aviso. Es una falla del código, no del modelo, y la encontró
  una pregunta nueva.
- **n04, filtro inventado (modelo).** Agregó `fecha_inicio < CURRENT_DATE +
  INTERVAL '10 YEARS'` sin que la pregunta lo pidiera ni lo anotara en
  `supuestos`. No cambió el resultado (ningún contrato pasa de 10 años), pero
  pudo haberlo hecho, y depende del día en que se corre.
- **`COUNT(*)` en uniones (modelo).** n05 y n06 cuentan filas de la unión con el
  69-B en lugar de contratos distintos. Da lo mismo porque hoy cada contrato tiene
  una sola coincidencia; con dos, contaría doble. Es el mismo patrón de n02.

## Qué se podría hacer (no aplicado)

- **Aviso de cobertura al agrupar por año (código).** Que `check_coverage`
  también avise cuando la consulta agrupa por año de inicio y el resultado puede
  traer años incompletos. Es determinista y se prueba con pruebas unitarias.
- **Expedientes y contratos (prompt).** Una regla para contar expedientes con
  `COUNT(DISTINCT codigo_expediente)` y contratos distintos en uniones.
- **`NULL` frente a cero (prompt).** Decir que "sin importe" o "importe nulo" es
  `importe IS NULL` y que, si se elige otra lectura, se anote en `supuestos`.

Si se aplica alguno, estas 8 preguntas dejan de ser nuevas para ese
comportamiento: para medirlo haría falta otro conjunto sin usar.
