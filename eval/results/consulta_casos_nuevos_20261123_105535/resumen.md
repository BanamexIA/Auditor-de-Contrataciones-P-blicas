# Medición del Agente Consulta

Archivo: `casos_nuevos.yaml` · Modelo: `qwen2.5:7b` · Casos: 8 · Repeticiones: 1 · Fecha: 2026-11-23T10:55:35

| Indicador | Valor |
|---|---:|
| Exactitud del SQL (casos que esperan SQL) | 57.1 % |
| Acierto global (incluye aclaración y sin datos) | 62.5 % |
| Exactitud SQL, dificultad dificil | 50.0 % |
| Exactitud SQL, dificultad facil | 66.7 % |
| Exactitud SQL, dificultad media | 50.0 % |
| Acierto en casos `sin_datos` | 100.0 % |
| Acierto en casos `sql` | 57.1 % |

## Tipos de error

| Error | Respuestas |
|---|---:|
| columnas_distintas | 1 |
| filas_distintas | 1 |
| valores_distintos | 1 |

## Respuestas incorrectas

| Caso | Esperado | Obtenido | Error |
|---|---|---|---|
| n02 | sql | sql | valores_distintos |
| n03 | sql | sql | filas_distintas |
| n05 | sql | sql | columnas_distintas |
