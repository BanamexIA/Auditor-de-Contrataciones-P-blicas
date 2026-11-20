# Análisis de A5: casos de empresa con coincidencia en el 69-B (2026-11-20)

Complementa [resumen.md](resumen.md). Primera medición de estos 6 casos, que no
se usaron para ajustar el agente antes de medirlos. 1 repetición.

| Indicador | Resultado |
|---|---:|
| SQL | 3 de 5 |
| Sin datos | 0 de 1 |

Acertaron f01, f02 y f03 (Grupo Elibza, ComprasMX, coincidencia por RFC): la
regla de proveedores de la mejora 12 sí generalizó a una empresa nueva.

Fallaron:

- **f04** ("¿Qué situación tiene Grupo Elibza en el listado 69-B?"). Las vistas
  no tienen la situación del contribuyente, y el prompt lo dice, pero el modelo
  listó las coincidencias de la empresa como si respondieran la pregunta.
- **f05 y f06** (Distribuidora Universal Tobosa, histórico). El agente buscó
  `'DISTRIBUIDORA UNIVERSAL TOBOSA'` y en la base está como
  `'DISTRIBUIDORA UNIVERSAL TOBOSA S A DE C V'`, por el orden de la regla del
  ETL (decisión 9 de [docs/vistas_estrella.md](../../../docs/vistas_estrella.md)).
  Cero contratos en los dos.

## Mejoras que salieron de esta medición

| # | Qué hace | Caso |
|---|---|---|
| 18 | Una pregunta por la situación en el 69-B (presunto, definitivo, desvirtuado) responde "sin datos" desde el código | f04 |
| 19 | El proveedor se busca con y sin su tipo de sociedad al final (`S A DE C V` y otros que el ETL conserva) | f05, f06 |

**Prueba rápida después de los cambios** (con la base): 6 de 6. Con esto, estos
casos también quedan usados para ajustar el agente; para volver a medir si
generaliza hacen falta preguntas nuevas.
