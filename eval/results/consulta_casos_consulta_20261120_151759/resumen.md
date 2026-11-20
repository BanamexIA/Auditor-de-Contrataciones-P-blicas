# Medición del Agente Consulta

Archivo: `casos_consulta.yaml` · Modelo: `qwen2.5:7b` · Casos: 13 · Repeticiones: 1 · Fecha: 2026-11-20T15:17:59

| Indicador | Valor |
|---|---:|
| Exactitud del SQL (casos que esperan SQL) | 100.0 % |
| Acierto global (incluye aclaración y sin datos) | 76.9 % |
| Exactitud SQL, dificultad sin_clasificar | 100.0 % |
| Acierto en casos `aclaracion` | 40.0 % |
| Acierto en casos `sin_datos` | 100.0 % |
| Acierto en casos `sql` | 100.0 % |

## Tipos de error

| Error | Respuestas |
|---|---:|
| tipo_incorrecto | 3 |

## Respuestas incorrectas

| Caso | Esperado | Obtenido | Error |
|---|---|---|---|
| c01 | aclaracion | sql | tipo_incorrecto |
| c03 | aclaracion | sql | tipo_incorrecto |
| c05 | aclaracion | sql | tipo_incorrecto |
