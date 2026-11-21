# Análisis de A5: golden set con 3 repeticiones, tercera ronda (2026-11-20)

Complementa [resumen.md](resumen.md). Medición después de las mejoras 15 a 19 y
del cambio al esperado de q10 ([plan de mejoras](../../../docs/mejoras_agente_consulta.md)).
Misma configuración que las anteriores: `qwen2.5:7b` en una RTX 3070 Ti, base de
la EC2, 20 casos y 3 repeticiones (60 respuestas).

## Resultado

| Indicador | A4 | A5, 11-19 | A5, 11-20 (14:20) | A5, 11-20 (15:16) |
|---|---:|---:|---:|---:|
| Exactitud del SQL | 79.2 % | 75.0 % | 75.0 % | **93.8 %** (45 de 48) |
| Acierto global | 83.3 % | 80.0 % | 80.0 % | **95.0 %** |
| Casos `sin_datos` | 100 % | 100 % | 100 % | 100 % |
| Consistencia | 19 de 20 | 18 de 20 | 20 de 20 | 20 de 20 |
| Respuestas con dos intentos | 5 de 60 | 9 de 60 | 6 de 60 | 3 de 60 |
| Tiempo por pregunta (media) | 10.2 s | 9.2 s | 6.1 s | 4.9 s |

**Pasa la meta de 85 %.** Sin el cambio al esperado de q10, que es de la
evaluación y no del agente, sería 87.5 % (42 de 48): también arriba de la meta.

## Qué cambió por caso

| Caso | 11-20 (14:20) | 11-20 (15:16) | Por qué |
|---|---|---|---|
| q08 | 0 de 3 | **3 de 3** | Mejora 15: `c_fuente` se corrige en código y el primer intento ya pasa |
| q10 | 0 de 3 | **3 de 3** | El esperado pasó a `LIMIT 200` |
| q17 | 0 de 3 | **3 de 3** | Mejora 17: las 3 veces dijo "sin datos" de 2024, el código lo rechazó y el reintento dio el SQL correcto |
| q18 | 0 de 3 | 0 de 3 | Sigue agrupando por `descripcion_excepcion` en lugar de `articulo_de_excepcion` |

Los otros 16 casos acertaron las 3 veces. Las 3 respuestas con dos intentos son
las de q17.

## Qué tan confiable es el 93.8 %

- Las mejoras 15 y 17 salieron de errores de este mismo golden set, y q10 se
  corrigió en la evaluación. Es probable que con preguntas nuevas la exactitud
  sea menor.
- q17 depende de un reintento: el modelo sigue afirmando que no hay 2024 y es el
  código el que lo detiene.
- El modelo no es del todo determinista entre corridas, aunque sí lo fue dentro
  de esta (20 de 20).

## Qué queda

- **q18:** elección de columna. No se corrige en el prompt para no ajustarlo a
  un caso del golden set.
- Preguntas nuevas que no se hayan usado para ajustar el agente, para medir si
  generaliza.
