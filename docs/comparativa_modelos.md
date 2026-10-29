# Comparativa de modelos

## Embeddings (Fase 5B)

### Configuración

- Modelo predeterminado: `nomic-embed-text` en Ollama (`OLLAMA_EMBEDDING_MODEL`).
- Dimensión: `768`, medida desde la respuesta real de `/api/embed` el
  2026-10-28 y guardada en `rag.embedding_config`; no se fija en el código.
- Estado al 2026-10-28: se instaló `nomic-embed-text` en el Ollama local y se
  volvió a medir una dimensión real de `768`. La API `/api/embed` respondió en
  3,244 ms para dos probes de texto; este tiempo es una medición puntual, no un
  benchmark de rendimiento.
- Métrica: distancia coseno de pgvector (`<=>`).
- Índice: HNSW con `vector_cosine_ops`. Se elige porque no requiere fase de
  entrenamiento y permite agregar fragmentos incrementalmente. En una muestra
  de solo 5 a 10 fragmentos, el índice puede no reducir la latencia; la prueba
  sirve para validar el flujo y no para afirmar rendimiento a escala.

### Resultados de recuperación

El esquema, el índice HNSW y el flujo de búsqueda se validaron con un fragmento
temporal no normativo y consultas de vigencia con fixtures sintéticos; todos
los registros de prueba se revirtieron. Un probe de embedding + consulta
pgvector encontró el fixture con distancia coseno 0.1445; tiempo DB observado:
7.66 ms. Estas métricas solo verifican conectividad funcional, no rendimiento
a escala.

La muestra normativa contiene seis fragmentos literales, tres por versión:

- Nueva ley, publicada en DOF el 16-04-2025:
  [PDF oficial](https://www.diputados.gob.mx/LeyesBiblio/pdf/LAASSP.pdf),
  SHA-256 local `883f6e9c3139d0961de302de7bddcf3262c69884008bb3b2324d57e5d67009fc`.
- Texto anterior, última reforma DOF 20-05-2021:
  [PDF del archivo oficial](https://www.diputados.gob.mx/LeyesBiblio/abro/laassp_2000/LAASSP_2000_abro.pdf),
  copia local `rag/LAASSP_2000_abrogada.pdf`, SHA-256
  `b4d82848f5feb93412b34c4c5d80ac4891da7e7095d09da4cbd2b4c47f26b23b`.

Los seis contenidos se cotejaron con su página citada y ambos SHA-256 coinciden
con los PDFs locales. El PDF anterior indica publicación original el
04-01-2000 y última reforma el 20-05-2021. La vigencia de la versión anterior
se registró desde el 05-03-2000; la nueva ley entra en vigor y abroga la
anterior el 17-04-2025.

La ingestión cargó 6 fragmentos con `nomic-embed-text` (dimensión 768):
5,623 ms en total, 937 ms promedio por fragmento. La última ejecución del
benchmark de cinco consultas devolvió 15 resultados, con una latencia media de
embedding de 1,076 ms por consulta y 6.17 ms de consulta a PostgreSQL. Son
mediciones puntuales sobre seis fragmentos; no representan rendimiento ni
calidad a escala.
El CSV incluye versión, intervalo de vigencia, hash, PDF local y artículo/página
para que la cita pueda verificarse.

### Revisión manual de la muestra

| Consulta | Resultado relevante | Cita/fuente verificada | Observaciones |
|---|---|---|---|
| Principios de contratación pública | Parcial | LAASSP anterior, art. 26, p. 12 | Recupera procedimientos y mejores condiciones, pero no desarrolla todos los principios solicitados. |
| Requisitos de adjudicación directa | Sí | LAASSP anterior, arts. 26 y 40, pp. 12 y 24 | Recupera selección del procedimiento y motivación de excepciones. |
| Justificación de excepción a licitación | Sí | LAASSP anterior, arts. 40 y 41, pp. 24 y 25 | Recupera motivación y supuestos de excepción. |
| Obligaciones del área contratante | No | LAASSP anterior, arts. 26, 40 y 41, pp. 12, 24 y 25 | La muestra pequeña no cubre obligaciones específicas del área. |
| Investigación de mercado y selección | Sí | LAASSP vigente, arts. 3 y 35, pp. 2 y 14 | Recupera investigación de mercado y lista de procedimientos. |

El filtro temporal devolvió solo la versión abrogada para las cuatro fechas
anteriores al 17-04-2025 y solo la nueva ley para la consulta del 01-06-2025.
La muestra sirve para probar vigencia y trazabilidad, no para medir calidad
general: amplía el corpus y repite la evaluación antes de fijar conclusiones
sobre relevancia normativa.

Para repetir la evaluación:

```powershell
python -m rag.cli benchmark
```

El comando guarda distancias, fragmentos, versión, vigencia, hash, PDF local y
artículo/página, además de las latencias, en
`rag/results/embedding_retrieval.csv`.

Cada pregunta del benchmark incluye la fecha del contrato. La recuperación
filtra por `fecha_entrada_vigor` inclusiva y `fecha_abrogacion` exclusiva; sin
fecha de contrato no devuelve fragmentos normativos.
