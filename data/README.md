# Datos de entrada

Los archivos fuente no se incluyen en Git. Colócalos en `data/raw/` una vez
descargados desde sus portales públicos:

- `contratos_comprasmx_2026.csv`: Datos Abiertos de ComprasMX
  (https://datos.gob.mx/).
- `Listado_completo_69-B.csv`: listado de contribuyentes del artículo 69-B
  publicado por el SAT (https://www.sat.gob.mx/).
- `compranet_historico.csv`: contratos y expedientes del sistema histórico de Compranet. Aunque la descripción del portal señala cobertura hasta 2022, el archivo cargado también contiene 16,896 inicios en 2023 y 1,836 en 2024; esos años son parciales. La revisión de los datos disponibles no encontró inicios en 2025.
(https://www.datos.gob.mx/dataset/contratos_expedientes_sistema_historico_compranet)


Confirma en los portales las URL de descarga, fecha de actualización, licencia,
columnas y codificación del archivo que utilices; pueden cambiar entre
publicaciones. No edites los originales. Los scripts de ingesta deberán
registrar el nombre y la fecha de descarga y reportar la codificación detectada.
