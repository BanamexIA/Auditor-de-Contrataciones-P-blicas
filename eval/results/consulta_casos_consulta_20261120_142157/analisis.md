# Análisis de A5: casos de A2 (2026-11-20)

Complementa [resumen.md](resumen.md). 13 casos, 1 repetición.

| Indicador | 2026-11-19 | 2026-11-20 |
|---|---:|---:|
| Aciertos | 10 de 13 | 10 de 13 |
| Aclaración | 2 de 5 | 2 de 5 |
| Sin datos | 6 de 6 | 6 de 6 |
| SQL | 2 de 2 | 2 de 2 |

Fallan c01, c03 y c05: preguntas con métrica ambigua ("la que más contrata",
"cuánto se gastó", "cómo le fue") a las que el agente responde con SQL en lugar
de pedir aclaración. c04 ahora acierta y c05 ahora falla; los dos son del mismo
tipo. Además, en c05 buscó la Secretaría de Salud en `nombre_de_la_uc` y no en
`institucion`.

Los tres dependen de la mejora 7, que es una decisión de equipo: pedir
aclaración o responder declarando la métrica supuesta. No se tocaron.
