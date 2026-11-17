# Exactitud del Agente Consulta (A4)

Modelo: `qwen2.5:7b` · Casos: 20 · Repeticiones: 1 · Fecha: 2026-11-17T12:54:43

| Indicador | Valor |
|---|---:|
| Exactitud del SQL (casos que esperan SQL) | 75.0 % |
| Acierto global (incluye aclaración y sin datos) | 80.0 % |
| Exactitud SQL, dificultad dificil | 66.7 % |
| Exactitud SQL, dificultad facil | 100.0 % |
| Exactitud SQL, dificultad media | 66.7 % |
| Acierto en casos `sin_datos` | 100.0 % |
| Acierto en casos `sql` | 75.0 % |

## Tipos de error

| Error | Respuestas |
|---|---:|
| columnas_distintas | 1 |
| error_ejecucion | 2 |
| filas_distintas | 1 |

## Respuestas incorrectas

| Caso | Esperado | Obtenido | Error |
|---|---|---|---|
| q06 | sql | sql | filas_distintas |
| q07 | sql | sql | error_ejecucion |
| q08 | sql | sql | error_ejecucion |
| q16 | sql | sql | columnas_distintas |
