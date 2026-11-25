# Agente Auditor de Contrataciones Públicas: resumen para el pitch

Reto Banamex × Tec de Monterrey (TC3009C), Opción 2. Estado al 25 de noviembre de 2026, víspera de la presentación.

## 1. El problema
Revisar contrataciones públicas es lento y manual. Los datos están repartidos en varias fuentes:

- ComprasMX (2026)
- CompraNet histórico (2010–2024)
- El listado 69-B del SAT, que reúne a los contribuyentes con operaciones presuntamente inexistentes

Además, los datos tienen problemas de calidad: fechas inválidas, montos en otras monedas, contratos sin ley registrada y fuentes que se contradicen.

Un analista tiene que hacer cuatro cosas a mano: cruzar las fuentes, detectar patrones de riesgo, encontrar la norma aplicable y documentar todo para una auditoría. Hacerlo con un LLM "de chat" no sirve en un banco, porque inventa datos y citas y no deja rastro.

## 2. La solución
El proyecto es un **Data Steward agéntico**: un sistema de agentes que convierte una pregunta en lenguaje natural en un **caso auditable**. El caso reúne cinco cosas:

1. **Consulta:** la pregunta se traduce a un SQL validado y se ejecuta con un rol de **solo lectura**.
2. **Calidad de datos:** se revisan los contratos del caso y se informa lo que falta o se contradice.
3. **Señales de riesgo:** reglas explicables con umbral, por ejemplo adjudicaciones directas recurrentes al mismo proveedor, montos atípicos frente a contratos comparables, proveedor en el listado 69-B o inconsistencias entre fuentes.
4. **Norma aplicable:** RAG sobre leyes oficiales, filtrado por la **vigencia a la fecha del contrato** y por la **ley del contrato**.
5. **Reporte PDF verificado:** cada cita se comprueba contra el texto recuperado y el archivo se guarda con su huella SHA-256.

Después, **el auditor decide** cada señal (relevante, descartada o pendiente) y cierra el caso. Cada paso queda en una **bitácora** que solo crece y no se puede editar.

> El sistema no acusa a nadie: las señales son indicios para revisión humana, no determinaciones de fraude.

## 3. Arquitectura final

```
 Navegador (auditor)
   │  HTTPS, URL pública por Tailscale Funnel
   ▼
 EC2 (AWS, cuenta del equipo) ── Docker Compose ─────────────────────────────┐
 │  Flask: API + front React compilado (mismo origen)                         │
 │   ├─ Autenticación: Cognito (OIDC, correo verificado) + rol desde la base  │
 │   ├─ Orquestador LangGraph: consulta → calidad → detección → normativo →   │
 │   │                         reporte → en revisión (con límites y bloqueos) │
 │   ├─ Agente Consulta     (LLM → SQL validado; rol agent_ro)                │
 │   ├─ Agente Detección    (reglas, umbrales en config.umbrales)             │
 │   ├─ Agente Normativo    (RAG híbrido: vectores + texto, pgvector)         │
 │   ├─ Agente Reportes     (PDF con verificador de citas)                    │
 │   └─ Servidor MCP        (herramientas con caso_id y registro en bitácora) │
 │  PostgreSQL + pgvector: clean.* (datos), audit.* (casos, bitácora,         │
 │                         señales, decisiones), rag.* (normas), config.*    │
 └────────────────────────────────────────────────────────────────────────────┘
   │ Tailscale (red privada)                       │
   ▼                                               ▼
 Laptops del equipo = motores de inferencia      S3: reportes PDF (SHA-256)
 (Ollama: qwen2.5:7b + nomic-embed-text)         Cognito: identidades
```

**Decisiones clave de diseño**

| Decisión | Por qué |
|---|---|
| **Los agentes viven junto a los datos**, en la EC2. Las laptops solo prestan el modelo | Los datos no salen del entorno controlado. Si una laptop falla, otra toma el caso |
| **Modelos locales** (Ollama) en vez de una API externa | Ningún dato sale a un proveedor de IA. El costo de inferencia es cero |
| **El LLM solo redacta el SQL**. La detección y las citas no las inventa el modelo | Lo crítico es determinista y explicable |
| **SQL con rol de solo lectura** y validador (vistas permitidas, `LIMIT`, sin escrituras) | Ningún prompt puede modificar ni borrar datos |
| **Bloquear antes que adivinar** | Si falta información, el caso se bloquea con un motivo claro en lugar de responder algo falso |
| **Todo pasa por la bitácora**, que solo agrega filas | Trazabilidad completa para auditoría (HU-06) |

## 4. Los agentes y sus salvaguardas

| Agente | Qué hace | Salvaguardas |
|---|---|---|
| **Orquestador** (LangGraph) | Coordina las etapas, elige la laptop y aplica límites de tiempo | Bloquea con motivo; un caso ya reportado no se pierde por tiempo |
| **Consulta** | Pregunta → SQL. Pide aclaración o dice "sin datos" | Validador de SQL; reintento con el error. Rechaza un cruce con el 69-B que nadie pidió. Agrega el código del contrato a las listas. Detecta conceptos que no existen en las fuentes (pagos, sanciones, rescisiones) |
| **Calidad** | Revisa los contratos del caso | Informa los problemas por motivo; no imputa valores |
| **Detección** | 4 reglas de riesgo con umbral, nivel y confianza | Los umbrales viven en la base y están marcados como *provisionales* hasta que el socio formador los confirme |
| **Normativo** | Recupera la norma vigente a la fecha del contrato | Solo cita la ley que corresponde a la señal: LAASSP o LOPSRM según el contrato, y el CFF para el 69-B. Umbral de similitud calibrado (0.28). Si no hay norma, lo declara |
| **Reportes** | PDF con resumen, señales, normas y limitaciones | Verificador de citas ("APROBADO" si 100% de las citas son correctas). SHA-256 en S3 |

## 5. Datos y corpus

- **Contratos:** 84,676 de ComprasMX 2026 y 2,356,609 de CompraNet histórico, más el cruce con el listado 69-B del SAT.
- **Corpus normativo oficial** (diputados.gob.mx), 1,227 fragmentos con vigencia:
  - LAASSP vigente (2025) y abrogada (2000–2025)
  - Reglamento de la LAASSP (2025)
  - LOPSRM y su reglamento
  - Artículo 69-B del CFF

## 6. Qué se puede mostrar hoy (demo)

1. **Login** con la cuenta del equipo (Cognito).
2. **Pregunta** en lenguaje natural. Se ve el avance por etapas.
3. **Tabla de resultados**, el SQL generado y sus **supuestos**: es transparente y no es una caja negra.
4. **Reporte PDF** con la verificación automática de citas.
5. **Señales y decisión:** el auditor marca cada señal y cierra el caso (humano en el ciclo).
6. **Bitácora:** qué se pidió, qué SQL corrió, qué modelo respondió y en qué equipo, qué SQL se rechazó y por qué, qué normas se citaron y qué decidió el auditor. Se descarga en JSON.
7. **Casos:** historial para reabrir cualquier caso.
8. **Guardarraíles en vivo:**
   - Una pregunta ambigua → pide aclaración.
   - Una pregunta fuera de alcance → "las fuentes no registran pagos".
   - Una laptop apagada → otra toma el caso.

## 7. Beneficios para el banco

- **Productividad:** de días de cruce manual a minutos por caso, con el expediente ya armado.
- **Auditabilidad:** cada respuesta es reproducible (SQL, modelo, equipo, normas, decisión y usuario).
- **Cumplimiento y riesgo:** se identifican proveedores en el listado 69-B y patrones de adjudicación directa antes de una relación comercial o un financiamiento.
- **Seguridad de datos:**
  - Los modelos son locales y los datos no salen.
  - El acceso a la base es de solo lectura.
  - La identidad es corporativa (Cognito) y el rol se controla desde la base.
- **Confianza:** el sistema dice "no sé" o "no hay norma" en lugar de inventar.
- **Escalable y barato:** más motores = más casos en paralelo, sin pagar por cada consulta a un proveedor externo.

## 8. Limitaciones honestas (y siguiente paso)

- **Umbrales:** los de detección son provisionales y falta validarlos con expertos del socio formador.
- **Fuentes:** no registran pagos, sanciones ni modificaciones de contratos. El sistema lo declara.
- **Corpus:** falta el reglamento de la LAASSP de 2010. El texto de la LOPSRM es el consolidado vigente.
- **Listas grandes:** se cortan en 200 filas, y el sistema avisa cuántas había en total (p. ej. 200 de 58,868).
- **Infraestructura:** es académica (AWS Academy). En producción, el equipo de TI del banco operaría los motores de inferencia y la URL.
- **Siguiente paso:** más reglas (fraccionamiento, concentración por dependencia), un modelo secuencial (LSTM) para patrones en el tiempo y un tablero de casos.

## 9. Equipo

| Integrante | Rol |
|---|---|
| Alean | Agente Consulta |
| Mario y Aarón | Agente Detección / Normativo y corpus (RAG) |
| Michelle | Agente Reportes |
| Ana Pau | Orquestador (LangGraph) |
| Emiliano | Backend, front, despliegue e integración |

## 10. Números útiles para el pitch

| Dato | Valor |
|---|---|
| Contratos analizables | ~2.44 millones (ComprasMX 2026 + histórico 2010–2024) |
| Adjudicaciones directas en ComprasMX 2026 | 58,868 |
| Fragmentos de normas con vigencia | 1,227 (5 ordenamientos + art. 69-B del CFF) |
| Pruebas automatizadas | 610 |
| Tiempo típico de un caso | ~25–60 s con el modelo en una laptop (caso de prueba: 24 s de la pregunta al reporte) |
| Verificación de citas en el reporte de prueba | 3/3 (100%) |
