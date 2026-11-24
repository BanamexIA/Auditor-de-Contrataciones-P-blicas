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
