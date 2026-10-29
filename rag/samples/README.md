# Muestra normativa de Fase 5B

`normas.jsonl` contiene seis fragmentos literales de la LAASSP: tres de la
nueva ley publicada el 16-04-2025 y tres del texto anterior, cuya última
reforma fue publicada el 20-05-2021 y que quedó abrogado el 16-04-2025. Cada
fragmento incluye artículo, página, versión, vigencia y SHA-256 del PDF local.

## Fuentes

- Nueva ley: [PDF oficial de la Cámara de Diputados](https://www.diputados.gob.mx/LeyesBiblio/pdf/LAASSP.pdf);
  copia local `rag/LAASSP.pdf`.
- Texto anterior: [PDF del archivo oficial de la Cámara de Diputados](https://www.diputados.gob.mx/LeyesBiblio/abro/laassp_2000/LAASSP_2000_abro.pdf);
  copia local `rag/LAASSP_2000_abrogada.pdf`. La portada identifica la publicación
  original del 04-01-2000, última reforma DOF 20-05-2021 y abrogación DOF
  16-04-2025.

La nueva ley y la abrogación de la anterior entran en vigor el 17-04-2025,
conforme al transitorio del decreto nuevo. La fecha inicial de vigencia de la
ley anterior se registró como 05-03-2000, sesenta días después de su publicación.
Revisa el texto y las citas contra el PDF antes de usar los fragmentos como
criterio legal; la selección de esta muestra no constituye una validación jurídica.

## Validar e ingerir

Desde la raíz del repositorio:

```powershell
python -m rag.cli ingest --jsonl rag\samples\normas.jsonl --sample
python -m rag.cli benchmark
```

La evaluación escribe citas con versión, artículo, página, SHA-256 y ruta del
PDF local en `rag/results/embedding_retrieval.csv`. Cada consulta normativa
necesita fecha del contrato; se aplica `fecha_entrada_vigor <= fecha_contrato <
fecha_abrogacion` para excluir versiones no vigentes.
