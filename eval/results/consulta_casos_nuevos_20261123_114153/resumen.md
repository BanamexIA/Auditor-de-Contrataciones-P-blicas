# Medición del Agente Consulta

Archivo: `casos_nuevos.yaml` · Modelo: `qwen2.5:7b` · Casos: 8 · Repeticiones: 1 · Fecha: 2026-11-23T11:41:53

| Indicador | Valor |
|---|---:|
| Exactitud del SQL (casos que esperan SQL) | 85.7 % |
| Acierto global (incluye aclaración y sin datos) | 87.5 % |
| Exactitud SQL, dificultad dificil | 50.0 % |
| Exactitud SQL, dificultad facil | 100.0 % |
| Exactitud SQL, dificultad media | 100.0 % |
| Acierto en casos `sin_datos` | 100.0 % |
| Acierto en casos `sql` | 85.7 % |

## Tipos de error

| Error | Respuestas |
|---|---:|
| columnas_distintas | 1 |

## Respuestas incorrectas

| Caso | Esperado | Obtenido | Error |
|---|---|---|---|
| n05 | sql | sql | columnas_distintas |
