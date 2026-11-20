# Análisis de A5: casos de empresa (2026-11-20)

Complementa [resumen.md](resumen.md). 6 casos, 1 repetición.

| Indicador | 2026-11-19 | 2026-11-20 |
|---|---:|---:|
| SQL | 1 de 5 | **3 de 5** |
| Sin datos | 1 de 1 | 1 de 1 |

La mejora 12 (buscar por `proveedor_normalizado` con el nombre en la forma del
ETL) arregló e01, e02 y e04. Siguen fallando:

- **e03.** Tomó "Brand and Push" por un tipo de procedimiento y filtró
  `tipo_procedimiento_norm = 'brand_and_push'`, que devuelve cero. Con la
  mejora 16 el validador rechaza ese valor y dice dónde buscar un proveedor;
  en la prueba rápida el modelo respondió con una aclaración en vez de SQL, así
  que sigue sin acertar, pero ya no da un cero falso.
- **e05.** Buscó la empresa en `nombre_de_la_uc` (la unidad compradora). No
  tiene corrección en código: no se puede saber sin la base si un texto es un
  proveedor o una unidad compradora.

Estos casos ya se usaron para ajustar la mejora 12, así que no miden si el
agente generaliza; para eso están los casos del 69-B.
