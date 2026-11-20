# Análisis de A5: casos de A2 con el modelo real (2026-11-19)

Complementa [resumen.md](resumen.md). Los 13 casos de `eval/casos_consulta.yaml`
con el agente después de las mejoras 1 a 6, 8 y 9, una repetición.

## Resultado

| Tipo | A4 (17 nov) | A5 (19 nov) |
|---|---:|---:|
| Aclaración | 2 de 5 | 2 de 5 |
| Sin datos | 5 de 6 | **6 de 6** |
| SQL | 1 de 2 | **2 de 2** |
| **Total** | 8 de 13 (61.5 %) | **10 de 13 (76.9 %)** |

## Qué cambió

- **c10 responde "sin datos"** (mejora 5). En A4 el modelo presentó como
  "cancelados" los contratos con fecha de fin antes de la de inicio. Ahora la
  revisión de conceptos responde con un motivo escrito por el código.
- **c13 filtra las licitaciones** (mejora 4): cuenta 17,307 y no 84,676.
- **c03 ya no da `error`**: el `LIMIT` lo agrega el código (mejora 1). Sigue
  mal calificado porque responde con SQL en lugar de pedir aclaración.

## Lo que falta

c01, c03 y c04 responden con SQL cuando se espera una aclaración: el modelo
elige una métrica ("por número de contratos") en lugar de preguntar. Es la
mejora 7, que espera la decisión del equipo: pedir aclaración o responder
declarando la métrica en `supuestos`.
