# Análisis de A5: golden set con 3 repeticiones (2026-11-19)

Complementa [resumen.md](resumen.md). Primera medición después de las mejoras
1 a 6, 8 y 9 de [docs/mejoras_agente_consulta.md](../../../docs/mejoras_agente_consulta.md).
Misma configuración que A4: agente completo, `qwen2.5:7b` en una RTX 3070 Ti,
base de la EC2 y los 20 casos del golden set, 3 veces cada uno (60 respuestas).
Desde A5 el agente ejecuta el SQL él mismo, con el reintento cuando PostgreSQL
lo rechaza.

## Resultado

| Indicador | A4 (3 repeticiones) | A5 (3 repeticiones) |
|---|---:|---:|
| Exactitud del SQL | 79.2 % (38 de 48) | **75.0 %** (36 de 48) |
| Acierto global | 83.3 % | 80.0 % |
| Casos `sin_datos` | 100 % | 100 % |
| Consistencia (mismo SQL y mismo veredicto) | 19 de 20 | 18 de 20 |
| Respuestas con dos intentos | 5 de 60 | 9 de 60 |
| Tiempo por pregunta (media) | 10.2 s | 9.2 s |

La meta de 85 % no se alcanza. **q08 ya no tiene un resultado esperado vacío**
(20 filas), así que esta vez su veredicto sí mide algo.

## Qué cambió por caso

| Caso | A4 | A5 | Causa |
|---|---|---|---|
| q06 | 0 de 3 | **3 de 3** | Ya no lee "preliminar" como filtro (mejora 4) |
| q16 | 0 de 3 | **3 de 3** | Ya no usa `SELECT *` (mejora 4) |
| q07 | 2 de 3 | 0 de 3 | Escribe `c_fuente` en lugar de `c.fuente` |
| q08 | 0 de 3 | 0 de 3 | El mismo `c_fuente`; en A4 fallaba por el `GROUP BY` |
| q15 | 3 de 3 | 0 de 3 | Agrupa por `fecha_inicio_valida` (sí/no) en lugar de `fecha_inicio_estado` |
| q18 | 3 de 3 | 0 de 3 | `LIMIT 20` cuando hay 44 artículos: recorta el resultado |

Los otros 14 casos acertaron las 3 veces en las dos mediciones. q02 y q04
escribieron SQL distinto entre repeticiones (otro `LIMIT`, `EXTRACT` contra
`DATE_TRUNC`), pero acertaron siempre.

## Los errores

- **q07 y q08, `c_fuente`.** Reproducido con el modelo real: el primer SQL de
  q07 tenía el `JOIN` correcto y `m.rfc_exacto` en su vista, y solo fallaba por
  esa errata. El validador respondió "la columna c_fuente no existe", sin decir
  cómo corregirla, y en el reintento el modelo la repitió en todo el SQL. Lo más
  probable es que el ejemplo de `JOIN` con alias de la mejora 4 lo haya llevado
  a usar alias. `intentos_fallidos` (mejora 9) mostró el error de cada intento.
- **q15, estado contra sí/no.** La pregunta pide el "estado de fecha de inicio";
  el modelo eligió `fecha_inicio_valida`. Probablemente lo atrajo la regla de
  booleanos, que nombra esa columna.
- **q18, recorte.** Sin que la pregunta pidiera un número de filas, puso
  `LIMIT 20`. El `LIMIT` es un tope de seguridad y no debe recortar un
  resultado sin avisar.

## Qué sigue

Segunda ronda de mejoras: 10 (pista para `alias_columna`), 11 (`LIMIT` como
tope), 13 (estado contra sí/no). Ver el plan de mejoras.
