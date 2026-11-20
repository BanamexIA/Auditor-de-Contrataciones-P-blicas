# Medición del Agente Consulta

Archivo: `golden_set.yaml` · Modelo: `qwen2.5:7b` · Casos: 20 · Repeticiones: 3 · Fecha: 2026-11-17T13:20:09

| Indicador | Valor |
|---|---:|
| Exactitud del SQL (casos que esperan SQL) | 79.2 % |
| Acierto global (incluye aclaración y sin datos) | 83.3 % |
| Exactitud SQL, dificultad dificil | 66.7 % |
| Exactitud SQL, dificultad facil | 100.0 % |
| Exactitud SQL, dificultad media | 74.1 % |
| Acierto en casos `sin_datos` | 100.0 % |
| Acierto en casos `sql` | 79.2 % |

## Tipos de error

| Error | Respuestas |
|---|---:|
| columnas_distintas | 3 |
| error_ejecucion | 4 |
| filas_distintas | 3 |

## Respuestas incorrectas

| Caso | Esperado | Obtenido | Error |
|---|---|---|---|
| q06 | sql | sql | filas_distintas |
| q07 | sql | sql | error_ejecucion |
| q08 | sql | sql | error_ejecucion |
| q16 | sql | sql | columnas_distintas |
| q06 | sql | sql | filas_distintas |
| q08 | sql | sql | error_ejecucion |
| q16 | sql | sql | columnas_distintas |
| q06 | sql | sql | filas_distintas |
| q08 | sql | sql | error_ejecucion |
| q16 | sql | sql | columnas_distintas |
