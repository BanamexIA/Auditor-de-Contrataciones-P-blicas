# Corpus normativo (D2) y búsqueda híbrida (D5)

## Qué hay aquí
| Archivo | Contenido | Fragmentos |
|---|---|---|
| `laassp_vigente.jsonl` | LAASSP, Nueva Ley DOF 16-04-2025 (vigente desde 17-04-2025), artículos 1 a 120 | 185 |
| `laassp_abrogada.jsonl` | LAASSP anterior, última reforma DOF 20-05-2021 (vigente 05-03-2000, abrogada 17-04-2025), artículos 1 a 86 y sus Bis | 146 |

Se generaron con `rag/chunk_normas.py` a partir de los PDF que ya están en el repo (`rag/LAASSP.pdf`, `rag/LAASSP_2000_abrogada.pdf`).
El texto es literal: solo se quitan encabezados, pies y números de página y se unen los renglones cortados de cada párrafo.
Los transitorios no se cargan. Las diez piezas de `rag/samples/normas.jsonl` (las que se cotejaron a mano) se encuentran completas en estos
archivos; la única diferencia es que la muestra trae una mayúscula inicial en "Siempre que…" (art. 42 abrogada), donde el PDF continúa
una oración. `ruta_normativa` (Título > Capítulo) es informativa; no se cotejó una por una.

## Cargar a la base
```powershell
python -m rag.cli ingest --jsonl rag\corpus\laassp_vigente.jsonl
python -m rag.cli ingest --jsonl rag\corpus\laassp_abrogada.jsonl
python -m rag.cli benchmark
```
Necesita Ollama para los embeddings. La búsqueda híbrida usa un índice de texto completo: `python -m rag.cli setup` ya lo crea en una base nueva.
En la base que ya existe (donde `setup` corrió antes), créalo una vez con el rol administrador:
```sql
CREATE INDEX IF NOT EXISTS idx_chunks_texto_es ON rag.chunks USING gin (to_tsvector('spanish', contenido));
```
(Sin el índice la búsqueda funciona igual, solo más lenta; el corpus es chico.)
Si ya cargaste la muestra de 10 fragmentos, bórrala antes para no duplicar los artículos (la muestra y el corpus completo son el mismo PDF).

## Lo que falta (D2): reglamento, LOPSRM y art. 69-B del CFF
No pude descargarlos desde mi entorno (sin acceso a diputados.gob.mx). Descarga los PDF oficiales (Cámara de Diputados, sección de leyes
federales y de reglamentos) y corre, con los datos que trae la portada de cada PDF (fecha de publicación, de entrada en vigor y de abrogación):
```powershell
python -m rag.chunk_normas --pdf rag\LOPSRM.pdf --ley LOPSRM --titulo "Ley de Obras Públicas y Servicios Relacionados con las Mismas (...)" `
    --version "..." --publicacion AAAA-MM-DD --vigor AAAA-MM-DD --url https://www.diputados.gob.mx/LeyesBiblio/pdf/LOPSRM.pdf `
    --archivo-local rag\LOPSRM.pdf --salida rag\corpus\lopsrm.jsonl
python -m rag.chunk_normas --pdf rag\CFF.pdf --ley CFF --solo-articulos "69,69-A,69-B,69-B Bis" ... --salida rag\corpus\cff_69b.jsonl
```
Revisa el control de calidad que imprime (artículos encontrados, saltos o repetidos en la numeración, artículos sin texto) y compara 3 o 4
artículos contra el PDF antes de ingerir. Aviso: el reglamento (`Reglamento de la LAASSP`) lleva numeración propia; ponle `--ley REGLAMENTO_LAASSP`
(o el nombre que prefiera el equipo) para que no se confunda con la ley. Cada ley necesita su par de versiones si hubo reformas con otra vigencia.
`_validate_normative_metadata` solo acepta URLs de diputados.gob.mx o dof.gob.mx.

## Búsqueda híbrida (D5)
`rag.core.retrieve_hybrid` combina la búsqueda por vectores con una búsqueda por palabras clave (texto completo en español de Postgres) y
fusiona las dos listas con Reciprocal Rank Fusion (1/(60 + posición) por lista). Las dos aplican el mismo filtro de vigencia a la fecha del contrato.
- Las palabras clave de cada señal están en `MAPA_SENAL_NORMA` (`agente_deteccion/normativo.py`); sin ellas se usan los términos de la consulta.
- Cada fragmento trae `puntaje_rrf`, `rank_vector`, `rank_texto`, `coincide_texto` y `metodo_busqueda`.
- El umbral de similitud sigue siendo sobre la distancia coseno: una coincidencia de palabras no basta para citar una norma.
- `RecuperadorPgvector(hibrida=False)` regresa a la búsqueda solo vectorial.

Verificación hecha: contra un Postgres 16 con pgvector y un corpus de juguete de 5 fragmentos (vectores escritos a mano) se comprobó que
(a) en 2024 excluye el artículo abrogado y en 2005 solo devuelve el abrogado, (b) sin fecha no devuelve normas, (c) un fragmento que los
vectores dejaban tercero sube al primer lugar de la lista de texto, y (d) "69-B" funciona como palabra clave. **Falta** medir con embeddings
reales (Ollama) y las consultas de `rag/` si la híbrida mejora la recuperación, y calibrar el umbral de distancia.

## Actualización 2026-11-24 (prueba con el orquestador)

**CFF art. 69-B agregado** (`cff_69b.jsonl`, 4 fragmentos) desde el PDF oficial `rag/CFF.pdf` (texto vigente, última reforma
DOF 09-04-2026). Vigencia: desde 2022-01-01, por la última reforma del artículo (párrafo adicionado DOF 12-11-2021). Los
contratos anteriores a 2022 quedan sin norma del 69-B, porque el texto anterior no está en el corpus. Si se agrega, va como
otra versión con su propia vigencia.
```powershell
python -m rag.chunk_normas --pdf rag/CFF.pdf --ley CFF --titulo "Código Fiscal de la Federación (texto vigente, última reforma DOF 09-04-2026), artículo 69-B" `
    --version "Art. 69-B, última reforma del artículo DOF 12-11-2021" --publicacion 2021-11-12 --vigor 2022-01-01 `
    --url https://www.diputados.gob.mx/LeyesBiblio/pdf/CFF.pdf --archivo-local rag/CFF.pdf --solo-articulos "69-B" --salida rag/corpus/cff_69b.jsonl
```

**Por qué el orquestador no encontraba normas.** `rag.core.retrieve` armaba cada fila con `dict(zip(columnas, fila))`; la
conexión del orquestador usa `dict_row`, así que cada valor era el nombre de una columna, el filtro `tipo == "normas"` lo
descartaba todo y la búsqueda devolvía 0 fragmentos sin error. Corregido en `rag.core._fila`. Además `retrieve`,
`retrieve_text` y `retrieve_hybrid` aceptan `tipos=("normas",)`, que se aplica antes del `LIMIT`.

**Umbral de distancia: 0.28** (en el orquestador; `RAG_UMBRAL_DISTANCIA` lo cambia y `ninguno` lo desactiva). Medido con
`nomic-embed-text` sobre este corpus:

| Consulta de la señal | Normas que aplican | Lo más cercano que no aplica |
|---|---|---|
| ADJ_DIRECTA_RECURRENTE | LAASSP arts. 54/55 (vigente) y 41/42 (abrogada): 0.20 a 0.27 | CFF: 0.375 o más |
| PROVEEDOR_LISTA_69B | CFF 69-B: 0.253 y 0.270 | LAASSP: 0.287 en adelante |

Sin umbral, un contrato de 2015 con la señal del 69-B citaba los arts. 11, 1 y 60 de la LAASSP. El margen en el 69-B es corto
(0.270 contra 0.287): si se agregan leyes, conviene volver a medir, o filtrar por ley en `MAPA_SENAL_NORMA`.

**`chunk_normas.py` en Windows:** `pdftotext` usa Latin-1 por defecto; ahora se le pide `-enc UTF-8`.
