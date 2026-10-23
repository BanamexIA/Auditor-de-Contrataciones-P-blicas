# Datos de entrada

Los archivos fuente no se incluyen en Git. Colócalos en `data/raw/` una vez
descargados desde sus portales públicos:

- `contratos_comprasmx_2026.csv`: Datos Abiertos de ComprasMX
  (https://datos.gob.mx/).
- `Listado_completo_69-B.csv`: listado de contribuyentes del artículo 69-B
  publicado por el SAT (https://www.sat.gob.mx/).

Confirma en los portales las URL de descarga, fecha de actualización, licencia,
columnas y codificación del archivo que utilices; pueden cambiar entre
publicaciones. No edites los originales. Los scripts de ingesta deberán
registrar el nombre y la fecha de descarga y reportar la codificación detectada.
