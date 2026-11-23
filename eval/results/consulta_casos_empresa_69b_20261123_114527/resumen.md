# Medición del Agente Consulta

Archivo: `casos_empresa_69b.yaml` · Modelo: `qwen2.5:7b` · Casos: 6 · Repeticiones: 1 · Fecha: 2026-11-23T11:45:27

| Indicador | Valor |
|---|---:|
| Exactitud del SQL (casos que esperan SQL) | 80.0 % |
| Acierto global (incluye aclaración y sin datos) | 83.3 % |
| Exactitud SQL, dificultad dificil | 100.0 % |
| Exactitud SQL, dificultad facil | 100.0 % |
| Exactitud SQL, dificultad media | 50.0 % |
| Acierto en casos `sin_datos` | 100.0 % |
| Acierto en casos `sql` | 80.0 % |

## Tipos de error

| Error | Respuestas |
|---|---:|
| filas_distintas | 1 |

## Respuestas incorrectas

| Caso | Esperado | Obtenido | Error |
|---|---|---|---|
| f03 | sql | sql | filas_distintas |
