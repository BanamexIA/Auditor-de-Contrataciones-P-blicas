# Muestra de normatividad para Fase 5B

No se incluye texto legal de ejemplo. Descarga una fuente normativa pública y
prepara `normas.jsonl` con entre 5 y 10 fragmentos literales de esa fuente.
Conserva el texto tal como aparece publicado; no uses resúmenes ni texto
generado como si fuera normatividad.

Cada línea del JSONL representa un fragmento y debe incluir:

```json
{"fuente":"DOF","tipo":"normas","titulo":"Título publicado","url_o_ruta":"https://URL-oficial","posicion":0,"contenido":"Fragmento literal...","document_metadata":{"fecha_publicacion":"AAAA-MM-DD"},"metadata":{"articulo":"Artículo X","pagina":1}}
```

Registra la URL oficial, título, versión/fecha y artículo o página para poder
revisar la pertinencia y devolver citas trazables. El texto y los metadatos del
ejemplo anterior son solo una plantilla; reemplázalos con los datos verificados
de la fuente que descargue el equipo.

Valida e ingiere la muestra desde la raíz del repositorio:

```powershell
python -m rag.cli ingest --jsonl rag\samples\normas.jsonl --sample
```
