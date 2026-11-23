# Medición del Agente Consulta

Archivo: `casos_empresa.yaml` · Modelo: `qwen2.5:7b` · Casos: 6 · Repeticiones: 1 · Fecha: 2026-11-23T11:44:07

| Indicador | Valor |
|---|---:|
| Exactitud del SQL (casos que esperan SQL) | 60.0 % |
| Acierto global (incluye aclaración y sin datos) | 66.7 % |
| Exactitud SQL, dificultad dificil | 100.0 % |
| Exactitud SQL, dificultad facil | 100.0 % |
| Exactitud SQL, dificultad media | 33.3 % |
| Acierto en casos `sin_datos` | 100.0 % |
| Acierto en casos `sql` | 60.0 % |

## Tipos de error

| Error | Respuestas |
|---|---:|
| columnas_distintas | 1 |
| filas_distintas | 1 |

## Respuestas incorrectas

| Caso | Esperado | Obtenido | Error |
|---|---|---|---|
| e03 | sql | sql | columnas_distintas |
| e05 | sql | sql | filas_distintas |
