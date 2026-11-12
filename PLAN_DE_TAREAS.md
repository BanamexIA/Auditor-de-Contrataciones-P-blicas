# Plan de tareas por frente: Entrega 2 y entrega final

> Estado a lunes 9 de noviembre de 2026. Deriva de `AVANCE_2_PLAN.md`; si hay diferencias de fechas, **manda este archivo**.
> **Supuestos por confirmar con el profesor:** Entrega 2 el miércoles 18 de noviembre y entrega final el miércoles 2 de diciembre.
> **La fecha de cada tarea es el día límite para tener la evidencia en el repo** (código, prueba, documento o captura), no el día en que se empieza.
> Marca cada tarea como hecha en cuanto exista la evidencia. Si algo del Sprint 1 ya estaba hecho, se marca y se avanza.

## 1. Hitos

| Fecha | Hito |
|---|---|
| Mar 10 nov | Cierre del Sprint 1: **contratos de interfaz congelados** (T1) |
| Vie 13 nov | Cierre real de las tareas del Sprint 1 (3 días de holgura); respuesta esperada del socio formador; **go / no-go de Tailscale desde la EC2** (Z4) |
| Lun 16 nov | Decisión del alcance del despliegue final (Z6); se avanza con valores provisionales donde el socio no haya respondido |
| **Mié 18 nov** | **ENTREGA 2:** flujo integrado en local con datos reales, 3 agentes, bitácora y revisión humana |
| Mar 24 nov | **Congelamiento de funcionalidades**; después solo se corrigen errores |
| Vie 27 nov | Escenarios 1 a 6 con evidencia; último día recomendado para integrar cambios |
| Dom 29 nov | **Congelamiento de código** (etiqueta de versión) |
| Lun 30 nov y Mar 1 dic | Documentación final y dos ensayos de la demostración |
| **Mié 2 dic** | **ENTREGA FINAL** |

## 2. Tareas por frente

### Transversales
| ID | Tarea | Entregable / evidencia | Quién | Fecha | Depende de |
|---|---|---|---|---|---|
| T1 | Congelar los 7 contratos de interfaz (señal de riesgo, estado del caso, tools, fragmento y cita, evento de bitácora, API, vistas) | `docs/contratos/` con ejemplos reales en JSON | Todos | Mar 10 nov | — |
| T2 | Enviar al socio formador, en un solo mensaje, las decisiones 5 a 12 de `AVANCE_2_PLAN.md` | Mensaje enviado; respuestas en `docs/decisiones.md` | Emiliano | Mar 10 nov (respuesta: Vie 13) | — |
| T3 | Confirmar con el profesor las fechas de Entrega 2 y final y qué se debe entregar | Fechas y formato anotados | Emiliano | Mié 11 nov | — |
| T4 | Seguimiento dos veces por semana (15 min): qué se terminó, qué bloquea, qué decisión falta | Acta de 3 líneas | Todos | Lun y Jue | — |
| T5 | Capa semántica: definición de cada métrica, grano de cada tabla, base de fechas, exclusiones y reglas de agregación | `docs/capa_semantica.md` | Emiliano + Alean | Vie 13 nov | — |
| T6 | Vistas con forma de estrella sobre `clean` (hecho de contrato; dimensiones de proveedor, institución, fecha y procedimiento), con comentarios | Vistas creadas; `check_comentarios.sql` sin filas | Emiliano + Alean | Mar 17 nov | T5 |
| T7 | Línea base: cronometrar 3 a 5 casos hechos a mano | Tabla de tiempos | Mario + Mich | Mar 17 nov | — |
| T8 | **Entrega 2:** demostración del flujo integrado y resumen de avance | Demostración y documento | Todos | Mié 18 nov | O3 |
| T9 | Congelamiento de funcionalidades | Rama estable etiquetada | Todos | Mar 24 nov | — |
| T10 | Escenarios 1 a 6 ejecutados (ver sección 3) | `eval/results/escenarios.md` con capturas | Cada responsable | Vie 27 nov | — |
| T11 | Medir los indicadores: exactitud del SQL, trazabilidad, citas correctas y tiempo por caso | Tabla de resultados con el valor real | Alean + Mich + Emiliano | Vie 27 nov | T7, T10 |
| T12 | Congelamiento de código | Etiqueta de versión | Todos | Dom 29 nov | — |
| T13 | Documentación final: README, arquitectura, diccionario, capa semántica, despliegue y limitaciones | Documentos en `docs/` | Todos (reparto en T4) | Lun 30 nov | — |
| T14 | Dos ensayos cronometrados de la demostración, con el plan B listo | Registro de cada ensayo | Todos | Lun 30 nov y Mar 1 dic | — |
| T15 | **Entrega final** | Entregables del curso | Todos | Mié 2 dic | T13, T14 |

### Front-end (Vio, Emilio)
| ID | Tarea | Entregable / evidencia | Fecha | Depende de |
|---|---|---|---|---|
| F1 | Diseño de pantallas y flujo del auditor | Prototipo navegable | Jue 12 nov | T1 |
| F2 | Pantalla de consulta con el SQL visible, sobre API simulada | Pantalla funcionando | Vie 13 nov | F1 |
| F3 | Consulta y reporte conectados a la API real | Flujo con datos reales | Mié 18 nov | B2 |
| F4 | Decisión sobre cada señal: relevante, descartada o pendiente (HU-07) | Decisión guardada en la bitácora | Mié 18 nov | B4 |
| F5 | Estados del caso (incluido BLOQUEADO), mensajes de error y privacidad (no mostrar nombres de personas físicas sin criterio; mostrar situación y fecha del 69-B) | Capturas de cada estado | Vie 20 nov | B2 |
| F6 | Compilación y contenedor del front para el despliegue | Imagen que levanta | Vie 20 nov | — |
| F7 | Pantalla de **ficha de empresa** | Ficha con contratos, % de adjudicaciones directas, 69-B y normas | Mar 24 nov | D8, R4 |
| F8 | Rastro del caso (HU-06), lista ordenada (HU-08) y resumen ejecutivo (HU-09) | Tres vistas funcionando | Mar 24 nov | B3, D7 |
| F9 | Pruebas de la interfaz | Pruebas ejecutadas | Vie 27 nov | F8 |

### Backend (Emiliano)
| ID | Tarea | Entregable / evidencia | Fecha | Depende de |
|---|---|---|---|---|
| B1 | Rol compartido de solo lectura (`agent_ro`) en la BD de la EC2, guía de acceso y prueba del túnel desde fuera de la EC2 (casa o escuela) | `docs/acceso-bd.md`; un compañero conectado con su llave (tabla "Prueba de acceso") | Mié 11 nov | — |
| B2 | API de casos y estados (crear, transitar, BLOQUEADO con motivo) | Endpoints y pruebas | Vie 13 nov | T1 |
| B3 | Bitácora: cada paso se registra en `audit.bitacora` (solicitud, SQL, reglas, normas, modelo, equipo, tokens, latencia) | Registros de un caso completo | Lun 16 nov | B2 |
| B4 | Decisiones humanas sobre las señales (HU-07) | Endpoint y pruebas | Mar 17 nov | B2 |
| B5 | Almacenamiento de reportes detrás de una interfaz (local primero) | Reporte guardado y recuperado | Mar 17 nov | R1 |
| B6 | API documentada | Documento de endpoints | Mié 18 nov | B2, B4 |
| B7 | Registro de agentes mínimo (alta, estado, verificación periódica) | Tabla y endpoints | Vie 20 nov | T1 |
| B8 | Subida a S3 y URL prefirmada, si el laboratorio lo permite | Reporte descargado desde S3 | Mar 24 nov | Z5, B5 |
| B9 | Telemetría integrada: tokens y latencia por caso | Registros en `telemetry.llm_calls` | Mar 24 nov | B3 |
| B10 | Prueba de carga con 2 o 3 usuarios concurrentes | Resultados | Vie 27 nov | Z9 o Z6 |

### Agente Consulta (Alean)
| ID | Tarea | Entregable / evidencia | Fecha | Depende de |
|---|---|---|---|---|
| A1 | Prompt con las vistas aprobadas y el diccionario; validador de SQL **en el servidor** (solo `SELECT`, vistas permitidas, límite de filas y de tiempo) | Validador con pruebas | Vie 13 nov | T5, T1 |
| A2 | Aclaración ante una solicitud ambigua y respuesta "sin datos" (periodo 2025, dato inexistente) | Casos de prueba | Lun 16 nov | A1 |
| A3 | Agente integrado en el orquestador | Flujo de consulta de punta a punta | Mié 18 nov | O1 |
| A4 | Medir la exactitud del SQL con el golden set | Tabla con el valor real y los tipos de error | Mié 18 nov | A1 |
| A5 | Mejoras según los errores; golden set ampliado con casos de empresa | Nueva medición | Mar 24 nov | A4 |
| A6 | **Escenario 1** con evidencia | Evidencia en `eval/results/` | Vie 27 nov | A5 |

### Agente Detección + Normativo (Mario, Aarón)
| ID | Tarea | Quién | Entregable / evidencia | Fecha | Depende de |
|---|---|---|---|---|---|
| D1 | Tabla `config.umbrales` y reglas con **umbrales provisionales** marcados como tales | Mario | Reglas que leen la tabla; ningún umbral en el código | Vie 13 nov | T1 |
| D2 | Corpus normativo completo cargado: LAASSP vigente y abrogada, reglamento, LOPSRM y art. 69-B del CFF, con metadatos y vigencia | Aarón | `rag.documentos` y `rag.chunks`; registro del corpus | Lun 16 nov | — |
| D3 | Regla del 69-B: por RFC y, por nombre, con baja confianza (HU-04) | Mario | Señales en el formato del contrato | Mar 17 nov | D1 |
| D4 | Reglas de adjudicaciones directas recurrentes y concentración de proveedores (HU-02) | Mario | Señales con criterio, valor y umbral | Mié 18 nov | D1, T6 |
| D5 | RAG: búsqueda híbrida, filtro de vigencia, "sin norma aplicable" y verificación de citas | Aarón | Pruebas con consultas de ejemplo | Mié 18 nov | D2 |
| D6 | **Ficha de empresa:** contratos, % de adjudicaciones directas, 69-B con fecha y limitaciones | Mario | Función que recibe una empresa y devuelve señales | Vie 20 nov | D3, D4 |
| D7 | Casos de referencia para los escenarios 3 y 4 (atípicos conocidos o inyectados a propósito) | Mario + Aarón | Conjunto de referencia con resultados esperados | Vie 20 nov | — |
| D8 | Montos atípicos e inconsistencias (HU-03), con grupo de comparación, mediana y umbral | Mario + Aarón | Señales que muestran contra qué se comparó | Mar 24 nov | D1, D7 |
| D9 | Ranking de casos por nivel de señal (HU-08) | Aarón | Lista ordenada con el criterio visible | Mar 24 nov | D4 |
| D10 | **Escenarios 3 y 4** con evidencia | Mario + Aarón | Evidencia en `eval/results/` | Vie 27 nov | D7, D8 |
| D11 | HU-10, solo si el socio formador la confirma (regla estadística simple sobre 2011 a 2022) | Aarón | Regla y prueba | Vie 27 nov (opcional) | Decisión 7 |

### Agente Reportes (Mich)
| ID | Tarea | Entregable / evidencia | Fecha | Depende de |
|---|---|---|---|---|
| R1 | Decidir el formato del reporte (propuesta: PDF en S3) y definir plantilla y esquema de salida | Plantilla y esquema | Jue 12 nov | T1 |
| R2 | Reporte de una señal de punta a punta con **verificación de citas** (cada norma citada debe estar en lo recuperado) | Reporte de ejemplo; verificador con pruebas | Mié 18 nov | D5 |
| R3 | Lenguaje de señal y no de culpa; aviso de revisión humana; limitaciones declaradas (registros excluidos, baja confianza, sin norma, periodos sin datos) | Reportes revisados | Vie 20 nov | R2 |
| R4 | Reporte de la ficha de empresa | Reporte de ejemplo con 3 empresas | Mar 24 nov | D6 |
| R5 | Resumen ejecutivo para directivos (HU-09) | Resumen con sus limitaciones | Mar 24 nov | D9 |
| R6 | Entrega del reporte al backend para su almacenamiento | Reporte guardado | Mar 24 nov | B5 |
| R7 | **Escenario 2** con evidencia y reportes de ejemplo | Evidencia en `eval/results/` | Vie 27 nov | R4 |

### Orquestación (Ana Pau)
| ID | Tarea | Entregable / evidencia | Fecha | Depende de |
|---|---|---|---|---|
| O1 | Grafo de LangGraph con estados, reintentos y BLOQUEADO; agentes simulados | Grafo que corre con datos fijos | Vie 13 nov | T1 |
| O2 | Conexión con el cliente de modelos (`AGENT_BASE_URL`) y registro de cada llamada en la bitácora | Llamada real a un Ollama registrada | Lun 16 nov | B3 |
| O3 | **Integración con los 3 agentes reales**, de punta a punta en local | Un caso completo, de la pregunta al reporte | Mié 18 nov | A3, D5, R2 |
| O4 | Límite de pasos y de tiempo; resultados parciales marcados | Prueba que lo demuestra | Vie 20 nov | O3 |
| O5 | Agente apagado o sin respuesta: tiempo de espera y caso BLOQUEADO con mensaje claro | Prueba con Ollama apagado | Lun 23 nov | B7 |
| O6 | Contenido recuperado tratado como dato, no como instrucción | Prueba con un texto "malicioso" en un fragmento | Mar 24 nov | O3 |
| O7 | **Escenarios 5 y 6** (información insuficiente y contradictoria) | Evidencia en `eval/results/` | Vie 27 nov | O3 |
| O8 | Pruebas de punta a punta | Informe de pruebas | Vie 27 nov | O7 |

### Despliegue y operación (Emiliano, con apoyo de otra persona)
| ID | Tarea | Entregable / evidencia | Fecha | Depende de |
|---|---|---|---|---|
| Z1 | Probar el túnel SSH desde casa y dar de alta las llaves de los compañeros | Un compañero conectado | Mar 10 nov | — |
| Z2 | Pruebas de aceptación de la BD: puerto cerrado, conteos iguales a la base local, permisos, versiones, `check_comentarios.sql` y **reinicio de la instancia** | Lista de verificación con resultados | Mié 11 nov | Z1 |
| Z3 | Documentar el acceso: cómo conectarse, dónde se publica la IP y quién agrega llaves | `docs/acceso-bd.md` | Mié 11 nov | B1 |
| Z4 | **Probar Tailscale desde la EC2 (y desde un contenedor) hacia un Ollama de laptop**; probar un nodo no autorizado | Resultado go / no-go | Vie 13 nov | — |
| Z5 | Probar S3 en el laboratorio (subir, bajar y URL prefirmada) | Prueba anotada | Vie 13 nov | — |
| Z6 | **Decidir el alcance del despliegue final:** (a) backend, front y BD en la EC2, o (b) solo la BD en la nube | Decisión en `docs/despliegue_decisiones.md` | Lun 16 nov | Z4, Z5 |
| Z7 | Dockerfiles de producción y `docker-compose.prod.yml` (solo si es la opción a) | Imágenes que levantan | Mié 18 nov | Z6, F6 |
| Z8 | Respaldo con `pg_dump` y **restauración probada** en un ambiente aislado, con el tiempo medido | Informe de la prueba | Vie 20 nov | Z2 |
| Z9 | Despliegue de backend y front en la EC2 con secretos fuera del repo (solo opción a) | Sistema accesible por la vía acordada | Vie 20 nov | Z7 |
| Z10 | Lista de seguridad (puertos, roles, secretos), alarma de gasto y saldo de créditos revisado | Lista completa | Mar 24 nov | Z2 |
| Z11 | Prueba de carga con 2 o 3 usuarios | Resultados | Vie 27 nov | Z9 o Z6 |
| Z12 | Versión etiquetada, procedimiento de reversa, guion de la demostración y **plan B** (todo en local, con capturas) | Guion y plan B | Lun 30 nov | T12 |
| Z13 | Ensayo con la laptop designada como agente de la demostración | Registro del ensayo | Mar 1 dic | Z12 |

## 3. Escenarios de prueba: quién y cuándo

| Escenario | Responsable | Primera versión | Con evidencia |
|---|---|---|---|
| 1. Consulta en lenguaje natural | Alean | Mié 18 nov | Vie 27 nov |
| 2. Reporte explicable | Mich + Aarón | Mié 18 nov (una señal) | Vie 27 nov |
| 3. Coincidencia con el 69-B | Mario | Mar 17 nov | Vie 27 nov |
| 4. Monto atípico | Mario + Aarón | Mar 24 nov | Vie 27 nov |
| 5. Información insuficiente | Ana Pau + Mario | Lun 23 nov | Vie 27 nov |
| 6. Información contradictoria | Ana Pau + Mario | Lun 23 nov | Vie 27 nov |

**Demostración final:** la ficha de empresa, con una empresa con coincidencia por RFC en el 69-B, una con coincidencia solo por nombre (baja confianza), una con datos faltantes y una consulta sobre un periodo sin datos (2025).

## 4. Dependencias críticas
- **T1** (contratos) bloquea F1, B2, A1, D1, R1 y O1. Es lo primero.
- **D2** (corpus) bloquea D5 y R2. **B2 y B3** bloquean O2 y O3.
- **T5 y T6** (capa semántica y vistas) bloquean el prompt del agente de consulta (A1).
- **Z4** (Tailscale) decide Z6; **Z6** decide Z7 y Z9.
- Las respuestas del socio formador bloquean D1 y D8 (umbrales), D2 (normas) y D11 (HU-10). Mientras no lleguen, se usan los valores provisionales marcados.

## 5. Alertas del calendario
- El Sprint 1 termina mañana. Si faltan tareas, ya tienen holgura hasta el viernes 13, pero **T1 no puede esperar**: sin contratos, nadie integra.
- El laboratorio limita las instancias a un tamaño pequeño y los créditos; la opción (b) del despliegue es el plan seguro.
- Una persona concentra backend, base de datos y despliegue: repartir Z4, Z5 y Z10 con alguien más.
- La demostración depende de que una laptop esté encendida y conectada: designarla desde ya.
- La meta de 85% de exactitud del SQL se mide, no se promete: se reporta el valor real.

## 6. Prompts de revisión (solo lectura)

Cada integrante copia **el prompt de su frente** y lo ejecuta en Claude Code, en su copia del repo. Sirven para saber qué ya existe y qué falta **antes de programar**. Los archivos `PLAN_DE_TAREAS.md`, `AVANCE_2_PLAN.md` y `ARQUITECTURA.md` deben estar en la raíz del repo.

Para conectarse a la BD compartida, usa tu rol personal por el túnel (`127.0.0.1:15432`). **Nunca escribas contraseñas en el repo ni se las pases al prompt.**

### Front-end (Vio, Emilio)
````text
Contexto: «Agente Auditor de Contrataciones Públicas» (Banamex / Tec, entrega final 2-dic-2026). Un auditor consulta por una empresa o un caso; el sistema usa SQL de solo lectura sobre datos públicos (ComprasMX 2026, CompraNet histórico, listado 69-B), reglas deterministas para señales de riesgo, RAG normativo y reportes con evidencia y limitaciones. Nunca determina fraude. Backend Flask con orquestador LangGraph, 3 agentes, Ollama local en laptops, Postgres + pgvector en una EC2. Dependencia solo existe en ComprasMX 2026; no hay datos de 2025.
Frente: Front-end. Lee PLAN_DE_TAREAS.md (tareas F1 a F9), AVANCE_2_PLAN.md, ARQUITECTURA.md y docs/contratos/.
SOLO REVISA: no modifiques archivos, no hagas commits, no instales nada.
1. Para cada tarea F1 a F9, dime si está hecha, parcial o falta, con la ruta o el comando como evidencia.
2. Verifica: qué pantallas existen (consulta con SQL visible, reporte, decisión de señales, rastro, lista ordenada, resumen); si usan la API real o datos simulados; si la URL de la API sale de una variable de entorno; si se muestra el aviso "señal para revisión, no fraude"; si se muestran la situación y la fecha de las coincidencias del 69-B; si se evita mostrar nombres de personas físicas sin criterio; si existen los estados del caso, incluido BLOQUEADO; si `npm run build` funciona y hay Dockerfile; si hay secretos en el código.
3. Señala contradicciones con los contratos de interfaz y con ARQUITECTURA.md.
Entrega una tabla (ID | Estado | Evidencia | Siguiente paso) y máximo 5 riesgos. Si no puedes verificar algo, escribe "no verificado".
````

### Backend (Emiliano)
````text
Contexto: «Agente Auditor de Contrataciones Públicas» (Banamex / Tec, entrega final 2-dic-2026). Un auditor consulta por una empresa o un caso; el sistema usa SQL de solo lectura sobre datos públicos (ComprasMX 2026, CompraNet histórico, listado 69-B), reglas deterministas para señales de riesgo, RAG normativo y reportes con evidencia y limitaciones. Nunca determina fraude. Backend Flask con orquestador LangGraph, 3 agentes, Ollama local en laptops, Postgres + pgvector en una EC2 (acceso por túnel SSH), reportes en S3. Dependencia solo en ComprasMX 2026; sin datos de 2025.
Frente: Backend. Lee PLAN_DE_TAREAS.md (tareas B1 a B10 y T5, T6), AVANCE_2_PLAN.md, ARQUITECTURA.md y DESPLIEGUE_STAGING.md.
SOLO REVISA: no modifiques archivos, no ejecutes migraciones, no hagas commits.
1. Para cada tarea B1 a B10, dime si está hecha, parcial o falta, con evidencia.
2. Verifica: endpoints de casos, estados, decisiones, reportes y rastro; control de acceso por rol; que la bitácora (audit.bitacora) se escriba en cada paso; que el SQL del agente NO pase por el ORM y use el rol de solo lectura; qué tablas existen en audit y telemetry; si hay Dockerfile de producción y /health; pruebas existentes; cómo se maneja un agente apagado; si la interfaz de almacenamiento de reportes permite cambiar de local a S3 sin tocar a los agentes; si hay secretos en el repo.
3. Señala contradicciones entre el código y los contratos de interfaz.
Entrega una tabla (ID | Estado | Evidencia | Siguiente paso) y máximo 5 riesgos. Si no puedes verificar algo, escribe "no verificado".
````

### Agente Consulta (Alean)
````text
Contexto: «Agente Auditor de Contrataciones Públicas» (Banamex / Tec, entrega final 2-dic-2026). Un auditor consulta por una empresa o un caso; el sistema usa SQL de solo lectura sobre datos públicos (ComprasMX 2026, CompraNet histórico, listado 69-B), reglas deterministas para señales de riesgo, RAG normativo y reportes con evidencia y limitaciones. Nunca determina fraude. Backend Flask con orquestador LangGraph, 3 agentes, Ollama local en laptops, Postgres + pgvector en una EC2. Dependencia solo en ComprasMX 2026; el histórico no trae RFC; sin datos de 2025.
Frente: Agente Consulta. Lee PLAN_DE_TAREAS.md (tareas A1 a A6, T5, T6), AVANCE_2_PLAN.md, ARQUITECTURA.md, docs/diccionario_datos.md y eval/.
SOLO REVISA: no modifiques archivos ni hagas commits.
1. Para cada tarea A1 a A6, dime si está hecha, parcial o falta, con evidencia.
2. Verifica: qué vistas aprobadas y qué comentarios ve el agente; que el validador se ejecute en el servidor y permita solo SELECT, vistas aprobadas, límite de filas y de tiempo; que el agente use el cliente de modelos de llm/ y que ninguna laptop necesite credenciales de la BD; cómo responde ante una pregunta ambigua y ante un periodo sin datos (2025); el golden set (número de preguntas, dificultad, si los SQL esperados se ejecutan) y el último resultado de exactitud.
3. Lista 5 preguntas de un auditor sobre una empresa que el agente hoy no podría responder por falta de vista o columna.
Entrega una tabla (ID | Estado | Evidencia | Siguiente paso) y máximo 5 riesgos. Si no puedes verificar algo, escribe "no verificado".
````

### Agente Detección + Normativo (Mario, Aarón)
````text
Contexto: «Agente Auditor de Contrataciones Públicas» (Banamex / Tec, entrega final 2-dic-2026). Un auditor consulta por una empresa o un caso; el sistema usa SQL de solo lectura sobre datos públicos (ComprasMX 2026, CompraNet histórico, listado 69-B), reglas deterministas para señales de riesgo, RAG normativo y reportes con evidencia y limitaciones. Nunca determina fraude ni violación legal. Backend Flask con orquestador LangGraph; este agente tiene la Tool 1 (detección, determinista) y la Tool 2 (normativo, LLM + RAG). El LLM no calcula montos ni define umbrales. Dependencia solo en ComprasMX 2026; el histórico no trae RFC (cruce con 69-B solo por nombre, baja confianza); sin datos de 2025; el mismo número de artículo puede ser de leyes o versiones distintas.
Frente: Detección + Normativo. Lee PLAN_DE_TAREAS.md (tareas D1 a D11), AVANCE_2_PLAN.md, ARQUITECTURA.md, docs/diccionario_datos.md y docs/contratos/.
SOLO REVISA: no modifiques archivos, no ejecutes migraciones ni hagas commits.
1. Para cada tarea D1 a D11, dime si está hecha, parcial o falta, con evidencia.
2. Detección: qué reglas existen; si los umbrales están en una tabla de configuración o escritos en el código; si cada señal incluye criterio, valor, umbral, contratos y confianza según el contrato de "señal de riesgo"; si respetan fecha_inicio_valida y el tipo_procedimiento_norm; si el 69-B distingue coincidencia por RFC y por nombre.
3. Normativo: qué normas hay en rag.documentos y con qué versión y vigencia; cuántos fragmentos hay; si la búsqueda es híbrida y filtra por la fecha del contrato; si responde "sin norma aplicable" cuando nada supera el umbral; si existe verificación de que cada cita esté en lo recuperado en esa consulta.
4. Dime qué casos de referencia existen para los escenarios 3 y 4.
Entrega una tabla (ID | Estado | Evidencia | Siguiente paso) y máximo 5 riesgos. Si no puedes verificar algo, escribe "no verificado".
````

### Agente Reportes (Mich)
````text
Contexto: «Agente Auditor de Contrataciones Públicas» (Banamex / Tec, entrega final 2-dic-2026). Un auditor consulta por una empresa o un caso; el sistema usa SQL de solo lectura sobre datos públicos (ComprasMX 2026, CompraNet histórico, listado 69-B), reglas deterministas para señales de riesgo, RAG normativo y reportes con evidencia y limitaciones. Nunca determina fraude ni violación legal: usa lenguaje de señal y aclara que requiere revisión humana. Backend Flask con orquestador LangGraph; los reportes se guardan en S3 y la BD guarda la ruta y el hash. El agente de Reportes redacta a partir de resultados ya calculados; no calcula montos ni define umbrales.
Frente: Agente Reportes. Lee PLAN_DE_TAREAS.md (tareas R1 a R7), AVANCE_2_PLAN.md, ARQUITECTURA.md y docs/contratos/.
SOLO REVISA: no modifiques archivos ni hagas commits.
1. Para cada tarea R1 a R7, dime si está hecha, parcial o falta, con evidencia.
2. Verifica: si existe la plantilla y el esquema de salida validado; si hay verificador de citas (cada norma citada debe existir en lo recuperado en esa consulta); si el reporte incluye datos que sustentan la señal, norma con referencia y versión, y limitaciones (registros excluidos, coincidencias de baja confianza, sin norma aplicable, periodos sin datos); si el aviso de "señal para revisión, no fraude" aparece siempre; si el lenguaje evita afirmar violaciones o culpa; qué formato se decidió (PDF o Markdown); cómo entrega el reporte al backend.
3. Dame 3 frases del reporte actual que podrían leerse como una acusación y cómo reescribirlas.
Entrega una tabla (ID | Estado | Evidencia | Siguiente paso) y máximo 5 riesgos. Si no puedes verificar algo, escribe "no verificado".
````

### Orquestación (Ana Pau)
````text
Contexto: «Agente Auditor de Contrataciones Públicas» (Banamex / Tec, entrega final 2-dic-2026). Un auditor consulta por una empresa o un caso; el sistema usa SQL de solo lectura sobre datos públicos (ComprasMX 2026, CompraNet histórico, listado 69-B), reglas deterministas para señales de riesgo, RAG normativo y reportes con evidencia y limitaciones. Nunca determina fraude. El orquestador (LangGraph) vive dentro del backend Flask y llama, en orden fijo, a los 3 agentes (Consulta, Detección + Normativo, Reportes); la inferencia ocurre en Ollama, en la laptop de cada auditor, por Tailscale. Estados del caso: recibido, consultado, detectado, normado, reportado, en_revision, cerrado y BLOQUEADO.
Frente: Orquestación. Lee PLAN_DE_TAREAS.md (tareas O1 a O8), AVANCE_2_PLAN.md, ARQUITECTURA.md y docs/contratos/.
SOLO REVISA: no modifiques archivos ni hagas commits.
1. Para cada tarea O1 a O8, dime si está hecha, parcial o falta, con evidencia.
2. Verifica: nodos y aristas del grafo; que los estados y transiciones coincidan con el contrato; reintentos (una repetición ante SQL inválido y una regeneración ante salida fuera de formato); que BLOQUEADO guarde el motivo; límite de pasos y de tiempo con resultados parciales marcados; qué pasa si Ollama no responde; que cada llamada quede registrada en la bitácora; que el contenido recuperado se trate como dato y no como instrucción; qué pruebas de integración existen y si cubren los escenarios 5 y 6.
3. Dibuja en texto el flujo real que encuentres y marca dónde difiere del esperado.
Entrega una tabla (ID | Estado | Evidencia | Siguiente paso) y máximo 5 riesgos. Si no puedes verificar algo, escribe "no verificado".
````

### Despliegue y operación (Emiliano y quien apoye)
````text
Contexto: «Agente Auditor de Contrataciones Públicas» (Banamex / Tec, entrega final 2-dic-2026). Arquitectura: backend Flask con orquestador LangGraph, front React, Postgres + pgvector, S3 para reportes y Ollama en las laptops de los auditores por Tailscale. Hoy existe una EC2 (AWS Academy Learner Lab) con PostgreSQL en Docker, enlazado a 127.0.0.1 y accesible por túnel SSH; los esquemas clean, rag, audit y telemetry se restauraron desde un dump. Aún no hay backend, front, S3 ni Tailscale en la nube. El laboratorio limita el tamaño de instancia y los créditos.
Frente: Despliegue. Lee PLAN_DE_TAREAS.md (tareas Z1 a Z13), AVANCE_2_PLAN.md (sección 5), DESPLIEGUE_STAGING.md y docs/despliegue.md.
SOLO REVISA: no modifiques archivos, no ejecutes nada contra AWS y no hagas commits.
1. Para cada tarea Z1 a Z13, dime si está hecha, parcial o falta, con evidencia en el repo. Lo que dependa de la consola de AWS escríbelo como "no verificado".
2. Verifica en el repo: Dockerfiles de producción; docker-compose.prod.yml; que el puerto de la BD se publique solo en 127.0.0.1; que haya restart: unless-stopped; scripts en ops/ (dump, restauración, roles, verificación); que .env, llaves y dumps estén en .gitignore; que no haya secretos escritos en archivos; que exista .env.example.
3. Dime qué falta para decidir entre desplegar todo en la EC2 (a) o solo la BD (b), y qué pruebas faltan (Tailscale desde la EC2, S3).
4. Propón el orden de las tareas Z de esta semana.
Entrega una tabla (ID | Estado | Evidencia | Siguiente paso) y máximo 5 riesgos. Si no puedes verificar algo, escribe "no verificado".
````
