# Análisis de A4 con 3 repeticiones (2026-11-17)

Complementa [resumen.md](resumen.md). Misma configuración que la primera
medición ([consulta_20261117_125443](../consulta_20261117_125443/analisis.md)):
agente completo, `qwen2.5:7b` en una RTX 3070 Ti, base de la EC2 y los 20
casos del golden set, esta vez 3 veces cada uno (60 respuestas).

## Resultado

| Indicador | 1 repetición | 3 repeticiones |
|---|---:|---:|
| Exactitud del SQL | 75 % (12 de 16) | **79.2 %** (38 de 48) |
| Acierto global | 80 % | 83.3 % |
| Casos `sin_datos` | 100 % | 100 % |
| Tiempo por pregunta (media / mediana / máximo) | 10.4 / 9.3 / 21.6 s | 10.2 / 9.4 / 19.5 s |

## Consistencia

| Caso | Repetición 1 | Repetición 2 | Repetición 3 | SQL distintos | Intentos |
|---|---|---|---|---:|---|
| q06 | filas_distintas | filas_distintas | filas_distintas | 1 | 1, 1, 1 |
| q07 | error_ejecucion | ok | ok | 2 | 1, 2, 2 |
| q08 | error_ejecucion | error_ejecucion | error_ejecucion | 1 | 1, 1, 1 |
| q13 | ok | ok | ok | 1 | 2, 2, 2 |
| q16 | columnas_distintas | columnas_distintas | columnas_distintas | 1 | 1, 1, 1 |
| Los otros 15 | ok | ok | ok | 1 | 1, 1, 1 |

- **19 de 20 casos** dieron el mismo SQL y el mismo resultado en las tres
  vueltas: con temperatura 0 el modelo es casi determinista.
- **q07 fue el único que varió.** En la repetición 1 usó `rfc_exacto` en la
  vista de contratos y falló en la base. En la 2 y la 3 su primera respuesta no
  fue válida, reintentó y escribió el `JOIN` correcto entre las dos vistas. El
  reintento rescata casos.
- **q06, q08 y q16 fallaron las tres veces con el mismo SQL**: son errores
  sistemáticos (descritos en el primer análisis), así que se corrigen con
  cambios al prompt y al validador, no repitiendo.
- **q13 necesitó dos intentos las tres veces.** El medidor no guarda el error
  del primer intento; por el caso c03 de A2, lo más probable es que falte el
  `LIMIT`.

## Qué cambia respecto a la primera medición

La exactitud real del agente está entre 75 % y 81 % según si q07 acierta al
primer intento. Las mejoras de A5 están en
[docs/mejoras_agente_consulta.md](../../../docs/mejoras_agente_consulta.md).
