# Medición del Agente Consulta

Archivo: `golden_set.yaml` · Modelo: `qwen2.5:7b` · Casos: 20 · Repeticiones: 3 · Fecha: 2026-11-20T14:20:56

| Indicador | Valor |
|---|---:|
| Exactitud del SQL (casos que esperan SQL) | 75.0 % |
| Acierto global (incluye aclaración y sin datos) | 80.0 % |
| Exactitud SQL, dificultad dificil | 66.7 % |
| Exactitud SQL, dificultad facil | 100.0 % |
| Exactitud SQL, dificultad media | 66.7 % |
| Acierto en casos `sin_datos` | 100.0 % |
| Acierto en casos `sql` | 75.0 % |
| Consistencia entre repeticiones (mismo SQL y mismo veredicto) | 20 de 20 casos (100.0 %) |

## Tipos de error

| Error | Respuestas |
|---|---:|
| error_modelo | 3 |
| filas_distintas | 6 |
| tipo_incorrecto | 3 |

## Respuestas incorrectas

| Caso | Esperado | Obtenido | Error |
|---|---|---|---|
| q08 | sql | error | error_modelo |
| q10 | sql | sql | filas_distintas |
| q17 | sql | sin_datos | tipo_incorrecto |
| q18 | sql | sql | filas_distintas |
| q08 | sql | error | error_modelo |
| q10 | sql | sql | filas_distintas |
| q17 | sql | sin_datos | tipo_incorrecto |
| q18 | sql | sql | filas_distintas |
| q08 | sql | error | error_modelo |
| q10 | sql | sql | filas_distintas |
| q17 | sql | sin_datos | tipo_incorrecto |
| q18 | sql | sql | filas_distintas |
