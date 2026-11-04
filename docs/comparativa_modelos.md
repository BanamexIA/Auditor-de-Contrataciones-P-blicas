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

La muestra normativa contiene diez fragmentos literales, cinco por versión:

- Nueva ley, publicada en DOF el 16-04-2025:
  [PDF oficial](https://www.diputados.gob.mx/LeyesBiblio/pdf/LAASSP.pdf),
  SHA-256 local `883f6e9c3139d0961de302de7bddcf3262c69884008bb3b2324d57e5d67009fc`.
- Texto anterior, última reforma DOF 20-05-2021:
  [PDF del archivo oficial](https://www.diputados.gob.mx/LeyesBiblio/abro/laassp_2000/LAASSP_2000_abro.pdf),
  copia local `rag/LAASSP_2000_abrogada.pdf`, SHA-256
  `b4d82848f5feb93412b34c4c5d80ac4891da7e7095d09da4cbd2b4c47f26b23b`.

Los diez contenidos se cotejaron con su página citada y ambos SHA-256 coinciden
con los PDFs locales. El PDF anterior indica publicación original el
04-01-2000 y última reforma el 20-05-2021. La vigencia de la versión anterior
se registró desde el 05-03-2000; la nueva ley entra en vigor y abroga la
anterior el 17-04-2025.

La ingestión cargó 10 fragmentos con `nomic-embed-text` (dimensión 768):
6,032 ms en total, 603 ms promedio por fragmento. La última ejecución del
benchmark de cinco consultas devolvió 15 resultados, con una latencia media de
embedding de 493 ms por consulta y 5.32 ms de consulta a PostgreSQL. Son
mediciones puntuales sobre diez fragmentos; no representan rendimiento ni
calidad a escala.
El CSV incluye versión, intervalo de vigencia, hash, PDF local y artículo/página
para que la cita pueda verificarse.

### Revisión manual de la muestra

| Consulta | Resultado relevante | Cita/fuente verificada | Observaciones |
|---|---|---|---|
| Principios de contratación pública | Parcial | LAASSP anterior, arts. 26 y 41, pp. 12 y 25 | Recupera procedimientos y supuestos de excepción, pero no desarrolla todos los principios solicitados. |
| Requisitos de adjudicación directa | Sí | LAASSP anterior, arts. 26, 40 y 41, pp. 12, 24 y 25 | Recupera selección del procedimiento y motivación de excepciones. |
| Justificación de excepción a licitación | Sí | LAASSP anterior, arts. 40 y 41, pp. 24 y 25 | El art. 43 también aparece entre los tres primeros, pero trata la invitación a cuando menos tres personas. |
| Obligaciones del área contratante | Parcial | LAASSP anterior, arts. 26, 41 y 43, pp. 12, 25 y 28 | El art. 43 aporta una obligación del procedimiento de invitación; la muestra no cubre de forma suficiente las obligaciones del área contratante. |
| Investigación de mercado y selección | Sí | LAASSP vigente, arts. 3, 35 y 54, pp. 2, 14 y 25 | Recupera investigación de mercado, procedimientos de contratación y supuestos de excepción. |

El filtro temporal devolvió solo la versión abrogada para las cuatro fechas
anteriores al 17-04-2025 y solo la nueva ley para la consulta del 01-06-2025.
La muestra sirve para probar vigencia y trazabilidad, no para medir calidad
general. La revisión de pertinencia es manual y exploratoria; requiere revisión
jurídica profesional antes de usar los resultados como criterio legal.

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

## Comparativa de generación y decisión (Fase 8, preliminar)

### Alcance y metodología

La comparación final debe usar la misma versión del golden set, vistas,
configuración de seguridad, temperatura y repeticiones para cada modelo. El
runner de `eval/run_benchmark.py` ejecuta cada caso tres veces, valida el SQL,
compara los resultados de la consulta con los esperados y registra latencia,
tokens, cumplimiento de seguridad y telemetría disponible. También incluye
pruebas de concurrencia de 1, 2, 4 y 8 solicitudes. Los resultados reproducibles
se generan en `eval/results/`.

Al momento de esta actualización no hay resultados del benchmark text-to-SQL
en `eval/results/`. La ejecución comparativa de la Fase 7 está pendiente de un
compañero; por ello, esta sección separa la evidencia exploratoria disponible
de las conclusiones que todavía no se pueden obtener.

### Evidencia disponible (no comparable)

El CSV local registra cinco pruebas breves de disponibilidad de
`qwen2.5:0.5b`, cuantización `Q4_K_M`, con la misma solicitud de respuesta
breve. No son preguntas del golden set ni permiten medir exactitud SQL,
seguridad, concurrencia o calidad de respuesta.

| Modelo / proveedor | Muestra | Latencia observada | Tokens/s observados | Calidad SQL / seguridad | GPU / VRAM |
|---|---:|---:|---:|---|---|
| `qwen2.5:0.5b` (`Q4_K_M`) / Ollama local | 5 pruebas de disponibilidad | media 3,983 ms; mín. 2,407 ms; máx. 5,340 ms | media 57.34; mín. 43.62; máx. 81.34 | No medida | No disponible; `nvidia-smi` no está instalado |
| Segundo modelo local | — | Pendiente | Pendiente | Pendiente | Pendiente |
| Referencia cloud | — | Pendiente | Pendiente | Pendiente | No aplica |

Las cinco observaciones abarcan Ollama `0.40.12` y `0.40.13` en un equipo
Windows 11 con CPU Intel (identificador reportado: `Intel64 Family 6 Model 186
Stepping 3`) y 13.73 GiB de RAM. Son mediciones puntuales de una tarea corta,
no una caracterización del hardware ni un benchmark reproducible de modelos.
Los valores de latencia no deben usarse como p50/p95 del sistema.

### Decisión y límites actuales

Se mantiene como decisión de arquitectura ejecutar los agentes localmente,
conforme al alcance del proyecto. La razón operativa es evitar enviar datos de
contrataciones a un proveedor externo y conservar control sobre el entorno de
ejecución. Esta decisión no demuestra que un modelo local tenga mayor exactitud
o menor latencia/costo que la referencia cloud: esos aspectos requieren los
resultados comparables de la Fase 7. Tampoco se selecciona todavía un modelo
final para producción.

El equipo medido es únicamente una referencia observada; no se recomienda como
hardware mínimo. La recomendación y los modelos permitidos quedan pendientes de
comparar al menos dos modelos locales y una referencia cloud con el benchmark
completo, incluyendo calidad por dificultad, p50/p95, concurrencia, memoria,
VRAM y errores. El costo por 1,000 consultas cloud se calculará con el consumo
medido y los precios vigentes configurados para esa ejecución; no se estima aquí
porque todavía no hay una corrida cloud ni precios verificados.

Para que las métricas sean reproducibles, se usarán estas fórmulas:

- **Costo cloud por 1,000 consultas:** `1,000 × costo total estimado / número
  total de consultas`. El costo total se calcula con los tokens medidos de
  entrada y salida y las tarifas vigentes por millón de tokens.
- **Costo por consulta correcta:** `costo total estimado / número de consultas
  cuyo resultado coincide con el esperado`. Si no hay respuestas correctas, se
  reporta como no definido.
- **Tokens/s por GiB de VRAM pico:** `tokens de salida / segundos de generación /
  VRAM pico en GiB`. Se reporta solo si la VRAM fue medida; no se infiere cuando
  la telemetría es `null`.

### Riesgos y siguiente actualización

- La prueba de recuperación normativa evalúa embeddings, no generación de SQL.
- Cinco pruebas breves de un solo modelo no representan el workload real.
- No se midió GPU/VRAM; los valores `null` significan que el host no ofreció
  medición NVIDIA, no que el uso de GPU haya sido cero.
- Los resultados de la Fase 7 deben incluir el golden set usado, fecha,
  versiones/modelos, cuantización, hardware y configuración para que la
  comparación sea interpretable.
- La revisión jurídica profesional de la muestra RAG sigue pendiente y no se
  sustituye por métricas de recuperación o generación.

Cuando estén disponibles los resultados de `eval/results/`, actualizar esta
sección con las tablas por modelo, errores observados, fórmula de eficiencia,
hardware mínimo recomendado y decisión final. No usar la evidencia exploratoria
anterior como sustituto del benchmark.
