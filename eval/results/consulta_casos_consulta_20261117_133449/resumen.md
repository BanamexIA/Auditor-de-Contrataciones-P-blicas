# Medición del Agente Consulta

Archivo: `casos_consulta.yaml` · Modelo: `qwen2.5:7b` · Casos: 13 · Repeticiones: 1 · Fecha: 2026-11-17T13:34:49

| Indicador | Valor |
|---|---:|
| Exactitud del SQL (casos que esperan SQL) | 50.0 % |
| Acierto global (incluye aclaración y sin datos) | 61.5 % |
| Exactitud SQL, dificultad sin_clasificar | 50.0 % |
| Acierto en casos `aclaracion` | 40.0 % |
| Acierto en casos `sin_datos` | 83.3 % |
| Acierto en casos `sql` | 50.0 % |

## Tipos de error

| Error | Respuestas |
|---|---:|
| error_modelo | 1 |
| tipo_incorrecto | 3 |
| valores_distintos | 1 |

## Respuestas incorrectas

| Caso | Esperado | Obtenido | Error |
|---|---|---|---|
| c01 | aclaracion | sql | tipo_incorrecto |
| c03 | aclaracion | error | error_modelo |
| c04 | aclaracion | sql | tipo_incorrecto |
| c10 | sin_datos | sql | tipo_incorrecto |
| c13 | sql | sql | valores_distintos |
