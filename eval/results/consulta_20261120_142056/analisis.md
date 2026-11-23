# Análisis de A5: golden set con 3 repeticiones (2026-11-20)

Complementa [resumen.md](resumen.md). Segunda medición de A5, después de las
mejoras 10 a 14 de [docs/mejoras_agente_consulta.md](../../../docs/mejoras_agente_consulta.md).
Misma configuración que la primera: agente completo, `qwen2.5:7b` en una RTX
3070 Ti, base de la EC2 y los 20 casos, 3 veces cada uno (60 respuestas).

## Resultado

| Indicador | A4 | A5, 2026-11-19 | A5, 2026-11-20 |
|---|---:|---:|---:|
| Exactitud del SQL | 79.2 % | 75.0 % | **75.0 %** (36 de 48) |
| Acierto global | 83.3 % | 80.0 % | 80.0 % |
| Casos `sin_datos` | 100 % | 100 % | 100 % |
| Consistencia | 19 de 20 | 18 de 20 | **20 de 20** |
| Respuestas con dos intentos | 5 de 60 | 9 de 60 | 6 de 60 |
| Tiempo por pregunta (media) | 10.2 s | 9.2 s | 6.1 s |

Mismo porcentaje que el 19, pero con otros casos fallando.

## Qué cambió por caso

| Caso | 2026-11-19 | 2026-11-20 | Causa |
|---|---|---|---|
| q07 | 0 de 3 | **3 de 3** | Mejora 10: el reintento ya corrige `c_fuente` |
| q15 | 0 de 3 | **3 de 3** | Mejora 13: usa `fecha_inicio_estado` |
| q08 | 0 de 3 | 0 de 3 | Gasta los dos intentos: `c_fuente` en el primero y un `JOIN` por `m.proveedor_normalizado`, que no existe, en el segundo |
| q10 | 3 de 3 | 0 de 3 | Devuelve 200 instituciones; el esperado recortaba a 50 |
| q17 | 3 de 3 | 0 de 3 | Responde "sin datos": dice que el histórico no tiene contratos de 2024 (tiene 1,836) |
| q18 | 0 de 3 | 0 de 3 | Ya no recorta, pero agrupa por `descripcion_excepcion` (41 valores) en lugar de `articulo_de_excepcion` (44) |

Los otros 14 casos acertaron las 3 veces.

## Los errores

- **q08.** Se reprodujo con la base. Antes del 20 se pensó que fallaba por un
  empate de fechas en el lugar 20 (mejora 14), pero la base muestra que no hay
  empate en ese corte. Falla porque el primer intento, correcto salvo por
  `c_fuente`, se pierde y el segundo trae otro error.
- **q10.** No es un error del agente. La pregunta pide los contratos por
  institución, sin número de filas, y hay 784 instituciones. Desde la mejora 11
  el `LIMIT` es un tope (200) y no un recorte; el esperado con `LIMIT 50` era
  el que recortaba. Los demás filtros del esperado (2026 y sin institución
  nula) no cambian el resultado: los 84,676 contratos de ComprasMX son de 2026
  y todos tienen institución.
- **q17.** Afirmación falsa del modelo. El prompt dice que el histórico va de
  2010 a 2024, con 2024 incompleto, y aun así responde que no hay 2024.
- **q18.** Elección de columna del modelo. Los comentarios de las dos columnas
  están bien; no se corrige para no ajustar el prompt a un caso del golden set.

## Mejoras que salieron de esta medición

| # | Qué hace | Caso |
|---|---|---|
| 15 | El código cambia `alias_columna` por `alias.columna` antes de validar, así que el reintento queda para errores reales | q08 |
| 17 | Si el modelo dice "sin datos" para años que sí tienen contratos, se le reintenta con lo que dice la cobertura | q17 |
| — | El esperado de q10 pasa a `LIMIT 200` (cambio de evaluación, no del agente) | q10 |

**Prueba rápida después de los cambios** (1 repetición, con la base): 19 de 20.
Solo falla q18. q17 pasó por el reintento de la mejora 17. Falta la medición
completa con 3 repeticiones.

**Cuidado.** El cambio de q10 sube la exactitud sin que el agente cambie, y las
mejoras 15 y 17 salieron de este mismo golden set. Además, el modelo no es del
todo determinista entre corridas aunque la temperatura sea 0: q17 respondió
"sin datos" en la medición y SQL en una de las pruebas rápidas. La consistencia
de 20 de 20 es dentro de una corrida.
