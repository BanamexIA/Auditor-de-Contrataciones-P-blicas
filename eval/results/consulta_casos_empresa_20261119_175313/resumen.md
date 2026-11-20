# Medición del Agente Consulta

Archivo: `casos_empresa.yaml` · Modelo: `qwen2.5:7b` · Casos: 6 · Repeticiones: 1 · Fecha: 2026-11-19T17:53:13

| Indicador | Valor |
|---|---:|
| Exactitud del SQL (casos que esperan SQL) | 20.0 % |
| Acierto global (incluye aclaración y sin datos) | 33.3 % |
| Exactitud SQL, dificultad dificil | 100.0 % |
| Exactitud SQL, dificultad facil | 0.0 % |
| Exactitud SQL, dificultad media | 0.0 % |
| Acierto en casos `sin_datos` | 100.0 % |
| Acierto en casos `sql` | 20.0 % |

## Tipos de error

| Error | Respuestas |
|---|---:|
| filas_distintas | 3 |
| valores_distintos | 1 |

## Respuestas incorrectas

| Caso | Esperado | Obtenido | Error |
|---|---|---|---|
| e01 | sql | sql | valores_distintos |
| e02 | sql | sql | filas_distintas |
| e03 | sql | sql | filas_distintas |
| e05 | sql | sql | filas_distintas |
