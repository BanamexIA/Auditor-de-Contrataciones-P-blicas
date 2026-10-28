# Comparativa de modelos

## Embeddings (Fase 5B)

### Configuración

- Modelo predeterminado: `nomic-embed-text` en Ollama (`OLLAMA_EMBEDDING_MODEL`).
- Dimensión: `768`, medida desde la respuesta real de `/api/embed` el
  2026-10-26 y guardada en `rag.embedding_config`; no se fija en el código.
- Métrica: distancia coseno de pgvector (`<=>`).
- Índice: HNSW con `vector_cosine_ops`. Se elige porque no requiere fase de
  entrenamiento y permite agregar fragmentos incrementalmente. En una muestra
  de solo 5 a 10 fragmentos, el índice puede no reducir la latencia; la prueba
  sirve para validar el flujo y no para afirmar rendimiento a escala.

### Resultados de recuperación

La conexión a Ollama, la generación de embeddings y la consulta pgvector se
probaron con un fragmento temporal no normativo que se revirtió al terminar.
La recuperación de normatividad y su revisión manual siguen pendientes de
cargar 5 a 10 fragmentos literales de una fuente pública verificada. No se
inventan fragmentos ni se presentan resultados legales sin revisar las citas.

Después de cargar la fuente, corre:

```powershell
python -m rag.cli benchmark
```

El comando guarda las distancias, contenido recuperado, latencia promedio de
embedding por consulta y latencia de consulta a PostgreSQL en
`rag/results/embedding_retrieval.csv`. Revisa manualmente los primeros
resultados de cada consulta y registra aquí si son pertinentes y si la cita
corresponde a la fuente indicada.

| Consulta | Resultado relevante (sí/no) | Cita/fuente verificada | Observaciones |
|---|---|---|---|
| Principios de contratación pública | Pendiente | Pendiente | Pendiente |
| Requisitos de adjudicación directa | Pendiente | Pendiente | Pendiente |
| Justificación de excepción a licitación | Pendiente | Pendiente | Pendiente |
| Obligaciones del área contratante | Pendiente | Pendiente | Pendiente |
| Investigación de mercado y selección | Pendiente | Pendiente | Pendiente |
