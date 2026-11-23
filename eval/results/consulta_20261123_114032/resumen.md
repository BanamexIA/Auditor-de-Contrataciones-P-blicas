# Medición del Agente Consulta

Archivo: `golden_set.yaml` · Modelo: `qwen2.5:7b` · Casos: 20 · Repeticiones: 3 · Fecha: 2026-11-23T11:40:32

| Indicador | Valor |
|---|---:|
| Exactitud del SQL (casos que esperan SQL) | 93.8 % |
| Acierto global (incluye aclaración y sin datos) | 95.0 % |
| Exactitud SQL, dificultad dificil | 100.0 % |
| Exactitud SQL, dificultad facil | 100.0 % |
| Exactitud SQL, dificultad media | 88.9 % |
| Acierto en casos `sin_datos` | 100.0 % |
| Acierto en casos `sql` | 93.8 % |
| Consistencia entre repeticiones (mismo SQL y mismo veredicto) | 20 de 20 casos (100.0 %) |

## Tipos de error

| Error | Respuestas |
|---|---:|
| filas_distintas | 3 |

## Respuestas incorrectas

| Caso | Esperado | Obtenido | Error |
|---|---|---|---|
| q18 | sql | sql | filas_distintas |
| q18 | sql | sql | filas_distintas |
| q18 | sql | sql | filas_distintas |
