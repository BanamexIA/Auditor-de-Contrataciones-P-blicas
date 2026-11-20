# Medición del Agente Consulta

Archivo: `casos_empresa_69b.yaml` · Modelo: `qwen2.5:7b` · Casos: 6 · Repeticiones: 1 · Fecha: 2026-11-20T14:24:27

| Indicador | Valor |
|---|---:|
| Exactitud del SQL (casos que esperan SQL) | 60.0 % |
| Acierto global (incluye aclaración y sin datos) | 50.0 % |
| Exactitud SQL, dificultad dificil | 50.0 % |
| Exactitud SQL, dificultad facil | 100.0 % |
| Exactitud SQL, dificultad media | 50.0 % |
| Acierto en casos `sin_datos` | 0.0 % |
| Acierto en casos `sql` | 60.0 % |

## Tipos de error

| Error | Respuestas |
|---|---:|
| filas_distintas | 1 |
| tipo_incorrecto | 1 |
| valores_distintos | 1 |

## Respuestas incorrectas

| Caso | Esperado | Obtenido | Error |
|---|---|---|---|
| f04 | sin_datos | sql | tipo_incorrecto |
| f05 | sql | sql | filas_distintas |
| f06 | sql | sql | valores_distintos |
