# Análisis de A5: cuarta ronda (2026-11-23)

Cubre las cinco mediciones de las 11:40 a las 11:45, después de las mejoras 20 a
23 ([plan de mejoras](../../../docs/mejoras_agente_consulta.md)):

| Archivo | Carpeta |
|---|---|
| Golden set, 3 repeticiones | [consulta_20261123_114032](resumen.md) |
| Preguntas nuevas | [consulta_casos_nuevos_20261123_114153](../consulta_casos_nuevos_20261123_114153/resumen.md) |
| Casos de A2 | [consulta_casos_consulta_20261123_114246](../consulta_casos_consulta_20261123_114246/resumen.md) |
| Casos de empresa | [consulta_casos_empresa_20261123_114407](../consulta_casos_empresa_20261123_114407/resumen.md) |
| Casos del 69-B | [consulta_casos_empresa_69b_20261123_114527](../consulta_casos_empresa_69b_20261123_114527/resumen.md) |

Misma configuración que las anteriores (`qwen2.5:7b` en una RTX 3070 Ti, base de
la EC2), salvo el contexto de Ollama, que pasó de 4096 a 8192 tokens (mejora 23).
Ninguna llamada se cortó: la entrada fue de 4,061 a 4,168 tokens, más de lo que
cabía antes.

## Resultado

| Medición | 11-20 (15:16) | 11-23, antes de corregir | 11-23, final |
|---|---|---|---|
| Golden set | 93.8 %, consistencia 20 de 20 | — | **93.8 %**, consistencia 20 de 20 |
| Preguntas nuevas | — | 57.1 % (4 de 7) | **85.7 %** (6 de 7), después de corregir |
| Casos de A2 | 10 de 13 | — | 10 de 13 |
| Casos de empresa | 4 de 6 | — | 4 de 6 |
| Casos del 69-B | 6 de 6 | — | **5 de 6** |
| Tiempo por pregunta (golden) | 4.9 s | — | 4.0 s |

**El golden set se mantiene arriba de la meta de 85 %** y solo falla q18, como
el 2026-11-20. Las 3 respuestas con dos intentos son de q17, igual que antes.

**El 85.7 % de las preguntas nuevas no mide generalización.** Las mejoras 20 a 22
salieron de esas mismas 8 preguntas. La cifra de generalización sigue siendo el
57.1 % de las 10:55. Para medir de nuevo cuánto generaliza hace falta otro
conjunto sin usar.

## Por archivo

**Golden set.** Solo falla q18 (agrupa por `descripcion_excepcion` en lugar de
`articulo_de_excepcion`), sin cambios.

**Preguntas nuevas.** Las correcciones funcionaron en el primer intento, sin el
reintento:

- n02 cuenta `COUNT(DISTINCT codigo_expediente)`.
- n03 usa `importe IS NULL` y lo anota en `supuestos`.
- n04 ya no agrega el tope de 10 años.
- n06 trae el aviso "Cobertura incompleta en CompraNet histórico para 2010 y
  2023–2024".

Sigue fallando n05: omite la columna `rfc_exacto`. No se corrigió a propósito.

**Casos de A2.** Fallan c01, c03 y c05, que esperan una aclaración y el agente
responde con SQL. Es lo de la mejora 7, que sigue pendiente de decidir con el
equipo.

**Casos de empresa.** Fallan e03 y e05, como antes, pero e03 cambió de error.
El 2026-11-20 pedía aclaración; ahora responde con SQL (después del reintento del
validador por `'brand_and_push'`), pero filtra `licitacion_publica` en lugar de
agrupar por tipo de procedimiento. e05 sigue buscando a la empresa como unidad
compradora.

**Casos del 69-B.** f03 ("Lista los contratos de Grupo Elibza…") falló: unió la
vista del 69-B sin que la pregunta lo pidiera y comparó `m.proveedor`, el nombre
publicado, con `'GRUPO ELIBZA'`. No hay ningún contrato con ese nombre exacto,
así que salieron 0 filas en lugar de 16. El 2026-11-20 y en la corrida de las
11:32 acertó.

## Lo que deja esta ronda

- **Cada cambio al prompt mueve casos que no tienen que ver.** En la corrida
  intermedia de las 11:28, la frase "para contar proveedores, `COUNT(DISTINCT
  proveedor_normalizado)`" hizo que q08 mostrara `proveedor_normalizado` y que c04
  dejara de pedir aclaración. Al quitarla, esos dos volvieron, y ahora falló f03.
  Con un modelo de 7B, una regla del prompt no es una garantía.
- **Las reglas en código no tienen ese problema**: solo actúan cuando aparece el
  patrón. La mejora 21 no rechazó ninguna de las 300 respuestas pasadas salvo el
  n02 que estaba mal.
- **Para f03 se agregó después la mejora 24:** el validador rechaza comparar
  `proveedor` (el nombre publicado) con un texto por `=`, `<>` o `IN`, y pide
  `proveedor_normalizado`. En todas las mediciones guardadas solo dos respuestas
  lo hicieron (e03 del 2026-11-19 y f03 de hoy) y las dos estaban mal. No se
  volvió a medir; la prueba del reintento está en el plan de mejoras.
