# Medición del Agente Consulta

Archivo: `golden_set.yaml` · Modelo: `qwen2.5:7b` · Casos: 20 · Repeticiones: 3 · Fecha: 2026-11-19T17:50:18

| Indicador | Valor |
|---|---:|
| Exactitud del SQL (casos que esperan SQL) | 75.0 % |
| Acierto global (incluye aclaración y sin datos) | 80.0 % |
| Exactitud SQL, dificultad dificil | 66.7 % |
| Exactitud SQL, dificultad facil | 75.0 % |
| Exactitud SQL, dificultad media | 77.8 % |
| Acierto en casos `sin_datos` | 100.0 % |
| Acierto en casos `sql` | 75.0 % |
| Consistencia entre repeticiones (mismo SQL y mismo veredicto) | 18 de 20 casos (90.0 %) |

Casos que variaron entre repeticiones: q02, q04.

## Tipos de error

| Error | Respuestas |
|---|---:|
| error_modelo | 6 |
| filas_distintas | 6 |

## Respuestas incorrectas

| Caso | Esperado | Obtenido | Error |
|---|---|---|---|
| q07 | sql | error | error_modelo |
| q08 | sql | error | error_modelo |
| q15 | sql | sql | filas_distintas |
| q18 | sql | sql | filas_distintas |
| q07 | sql | error | error_modelo |
| q08 | sql | error | error_modelo |
| q15 | sql | sql | filas_distintas |
| q18 | sql | sql | filas_distintas |
| q07 | sql | error | error_modelo |
| q08 | sql | error | error_modelo |
| q15 | sql | sql | filas_distintas |
| q18 | sql | sql | filas_distintas |
