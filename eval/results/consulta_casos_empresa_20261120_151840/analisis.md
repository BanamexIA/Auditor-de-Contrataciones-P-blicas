# Análisis de A5: casos de empresa, tercera ronda (2026-11-20)

Complementa [resumen.md](resumen.md). 6 casos, 1 repetición: 4 de 6, igual que
a las 14:23, pero e03 falla distinto.

- **e03:** el validador rechazó `tipo_procedimiento_norm = 'brand_and_push'`
  (mejora 16) y en el reintento el modelo pidió una aclaración en lugar de
  buscar al proveedor. Ya no devuelve un cero falso, pero no acierta.
- **e05:** sigue buscando la empresa en `nombre_de_la_uc`.
- **e04** acertó en el segundo intento: el primero comparó `rfc_exacto` con
  `'S'` y PostgreSQL lo rechazó, a pesar de la regla de booleanos del prompt.
