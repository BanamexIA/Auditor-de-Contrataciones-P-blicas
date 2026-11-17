# Análisis de los casos de A2 con el modelo real (2026-11-17)

Complementa [resumen.md](resumen.md). Primera vez que los 13 casos de
`eval/casos_consulta.yaml` se corren con un modelo de verdad (`qwen2.5:7b`) en
lugar del modelo falso de las pruebas: 5 preguntas ambiguas, 6 sin datos y 2 de
control con SQL. Una repetición.

## Resultado

| Tipo de caso | Acierto |
|---|---|
| Aclaración | **2 de 5** (40 %) |
| Sin datos | **5 de 6** (83 %) |
| SQL de control | 1 de 2 |
| Global | 8 de 13 (61.5 %) |

## Caso por caso

| Caso | Pregunta | Esperado | Obtenido | Qué pasó |
|---|---|---|---|---|
| c01 | ¿Cuál es la institución que más contrata? | aclaración | SQL | Supuso "por número de contratos en ComprasMX" sin avisarlo |
| c02 | Dame los contratos sospechosos. | aclaración | aclaración | ✅ |
| c03 | ¿Cuánto se gastó en adjudicaciones directas? | aclaración | error | Intentó SQL dos veces y las dos olvidó el `LIMIT`; además, "gasto" no es "importe registrado" |
| c04 | ¿Qué proveedores aparecen mucho? | aclaración | SQL | Supuso "top 10 por número de contratos en ComprasMX" sin avisarlo |
| c05 | ¿Cómo le fue a la Secretaría de Salud? | aclaración | aclaración | ✅ |
| c06 | Licitaciones que iniciaron en 2025 | sin datos | sin datos | ✅ Lo detectó el modelo |
| c07 | Unidades compradoras en 2016 | sin datos | sin datos | ✅ El modelo escribió SQL; lo detuvo la revisión de cobertura |
| c08 | Histórico en 2026 | sin datos | sin datos | ✅ Lo detectó el modelo |
| c09 | ComprasMX en 2020 | sin datos | sin datos | ✅ Lo detuvo la revisión de cobertura |
| c10 | ¿Qué contratos se cancelaron antes de terminar? | sin datos | SQL | **Inventó un sustituto**: listó contratos con fecha de fin antes del inicio como si fueran cancelaciones |
| c11 | Contratos por ramo en 2019 | sin datos | sin datos | ✅ Lo detuvo la revisión de cobertura |
| c12 | Contratos del histórico en 2024 | SQL | SQL | ✅ Con el aviso de año incompleto |
| c13 | Licitaciones de ComprasMX en 2026 | SQL | SQL | Olvidó el filtro `licitacion_publica`: contó todos los contratos de 2026 (84,676 en lugar de 17,307) |

## Hallazgos

1. **El modelo prefiere responder antes que preguntar.** En c01 y c04 sus
   interpretaciones son razonables, pero no declaró la métrica que supuso. Hay
   que decidir en equipo qué es mejor: pedir aclaración (más seguro, pero puede
   cansar al auditor) o responder declarando el supuesto en `supuestos`.
2. **c10 es el error más delicado.** Las fuentes no registran cancelaciones y
   el modelo sustituyó el concepto por otra columna, lo que equivale a afirmar
   algo falso sobre contratos reales. La revisión de cobertura no lo detecta,
   porque no es un problema de años ni de campos, sino de conceptos.
3. **La revisión de cobertura fue la red de seguridad** en c07, c09 y c11: el
   modelo escribió SQL para años sin datos en ComprasMX y el código lo convirtió
   en "sin datos" antes de ejecutar.
4. **El `LIMIT` faltante es un error recurrente.** En c03 el modelo lo omitió
   incluso después de que el reintento se lo pidió; probablemente también
   explica los reintentos de q13 en el golden set.
5. **Omitir un filtro produce un resultado plausible pero falso** (c13). El
   alias "licitaciones" hacía que pareciera correcto.
6. **Los supuestos del modelo siguen sin ser confiables**: escribió "año 2026
   está incompleto" (falso) y "El año está incompleto" sin decir cuál.

Las mejoras para A5 están en
[docs/mejoras_agente_consulta.md](../../../docs/mejoras_agente_consulta.md).
