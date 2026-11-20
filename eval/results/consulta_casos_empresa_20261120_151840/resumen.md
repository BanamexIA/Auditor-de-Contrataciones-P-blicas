# Medición del Agente Consulta

Archivo: `casos_empresa.yaml` · Modelo: `qwen2.5:7b` · Casos: 6 · Repeticiones: 1 · Fecha: 2026-11-20T15:18:40

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
| filas_distintas | 1 |
| tipo_incorrecto | 1 |

## Respuestas incorrectas

| Caso | Esperado | Obtenido | Error |
|---|---|---|---|
| e03 | sql | aclaracion | tipo_incorrecto |
| e05 | sql | sql | filas_distintas |
