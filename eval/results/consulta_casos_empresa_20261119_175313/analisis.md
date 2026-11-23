# Análisis de A5: casos de empresa (2026-11-19)

Complementa [resumen.md](resumen.md). Primera medición de
`eval/casos_empresa.yaml` (mejora 8): 6 preguntas sobre un proveedor, como en
la ficha de empresa de la demo. No se usaron para ajustar el prompt, así que
miden si el agente generaliza.

## Resultado

| Tipo | Acierto |
|---|---:|
| SQL | **1 de 5** |
| Sin datos | 1 de 1 |

## Qué hizo el modelo

| Caso | Esperado | Obtenido | Qué pasó |
|---|---:|---:|---|
| e01 | 487 contratos | 0 | Buscó la empresa en `nombre_de_la_uc` |
| e02 | 1 moneda | 0 filas | Igual que e01 |
| e03 | 1 tipo | 0 filas | Unió la vista del 69-B sin que se pidiera, buscó en su `proveedor` y agregó un filtro de licitación que la pregunta no tiene |
| e04 | 0 | 0 | Acierto por suerte: buscó `'Molinos Azteca'` sin la forma normalizada y agregó un filtro de revisión humana; coincide porque la respuesta es cero |
| e05 | 10 filas | 0 | `nombre_de_la_uc` y, además, un `JOIN` con el 69-B que deja fuera todo |
| e06 | sin datos | sin datos | La revisión de cobertura detuvo 2025 |

**El agente no sabe buscar un proveedor.** `nombre_de_la_uc` es la unidad
compradora, quien compra, no el proveedor. Y aunque use `proveedor_normalizado`,
escribe el nombre como lo dice la pregunta, con acentos y en minúsculas, cuando
la columna está en mayúsculas, sin acentos y sin "SA DE CV".

Es el hallazgo más importante de A5: la ficha de empresa de la demo depende de
esta búsqueda, y el golden set no tiene ninguna pregunta por proveedor.

## Qué sigue

Mejora 12: regla del prompt para buscar proveedores por `proveedor_normalizado`
y normalización en código del nombre que escriba el modelo, con la misma regla
que el ETL. Después de ajustar con estos casos ya no sirven como prueba de
generalización: hacen falta casos nuevos (por ejemplo, las empresas con
coincidencia en el 69-B).
