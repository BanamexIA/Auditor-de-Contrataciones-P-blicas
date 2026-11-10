# PLAN 2: Del prototipo de datos al sistema integrado y desplegado

> Cubre desde hoy (miércoles 4 de noviembre de 2026) hasta la entrega final (miércoles 2 de diciembre de 2026).
> Está escrito para el equipo y también para Claude Code. Complementa a `AVANCE_1_PLAN.md`, `ARQUITECTURA.md`, `docs/despliegue.md` y el plan de trabajo por frente.
> Todo lo marcado **PENDIENTE** es una decisión que aún no está confirmada. Las fechas de entrega (18 de noviembre y 2 de diciembre) son **supuestos a confirmar**.

## 1. Resumen

- **Entrega 2 (≈ 18 nov):** el flujo completo funciona de punta a punta **en local** con datos reales, con los 3 agentes, la bitácora y la revisión humana, y existe un **ambiente de pruebas en AWS** con la base del despliegue.
- **Entrega final (2 dic):** el sistema está **desplegado y se puede demostrar**, los 6 escenarios de prueba tienen evidencia, las métricas están medidas y la documentación está cerrada.
- **Lo que no está en el plan de trabajo:** el despliegue aparece solo como una línea dentro del frente de Backend. El documento `docs/despliegue.md` describe mucho más trabajo (red, TLS, secretos, respaldos y restauración, Tailscale desde el contenedor, registro de agentes, operación). Este plan lo convierte en un **frente propio (Frente 7)**.
- **Alcance confirmado:** el caso de uso es **auditar una empresa con datos públicos** (contratos, 69-B y normativa). La BD sintética financiera del socio formador queda **fuera del MVP**, pendiente de que el socio confirme su uso esperado (decisión 12).
- **El mayor riesgo del calendario no es técnico:** son las decisiones pendientes con el socio formador (umbrales, normas, alcance de HU-10, roles) y el acceso a una cuenta de AWS. Ambos tienen fecha límite y un valor provisional en la sección 6, para que no bloqueen.

## 2. Calendario

| Sprint | Fechas | Cierra con |
|---|---|---|
| Sprint 1 | mié 4 nov – mar 10 nov | **M1:** contratos de interfaz congelados; cada agente se puede llamar solo, con datos simulados |
| Sprint 2 | mié 11 nov – mar 17 nov | **M2 (Entrega 2, mié 18 nov):** flujo integrado en local y staging en AWS iniciado |
| Sprint 3 | mié 18 nov – mar 24 nov | **M3:** funcionalidades completas (congelamiento de funcionalidades el 24 nov); despliegue funcionando |
| Sprint 4 | mié 25 nov – mar 1 dic | **M4 (Entrega final, mié 2 dic):** pruebas, documentación, ensayo y demostración |

Reglas del calendario:
- **Congelamiento de funcionalidades: 24 de noviembre.** Después solo se corrigen errores.
- **Congelamiento de código: 29 de noviembre.** El 30 de noviembre y el 1 de diciembre son ensayo de la demostración y no se cambia nada nuevo.
- Reunión de seguimiento **dos veces por semana** (15 minutos): qué se terminó, qué bloquea y qué decisión falta.
- **Supuesto de capacidad:** unas 8 a 10 horas por persona y semana. Si es menos, el recorte se hace en las prioridades de la sección 4, no en las pruebas ni en el despliegue mínimo.

## 3. Puerta de entrada (hoy y mañana)

Antes de empezar el Sprint 1, confirmar que el Avance 1 realmente cerró. Una sola persona corre esto desde un clon limpio del repo:

- [ ] `docker compose up -d --build` levanta `db` y `backend` siguiendo solo el README.
- [ ] Las 3 fuentes están cargadas; `raw = clean + excluidos` para cada una.
- [ ] `check_comentarios.sql` devuelve cero filas y `verify_fase5.py` no reporta discrepancias.
- [ ] `agent_ro` lee `clean` y `rag`, y falla ante `INSERT` y `DROP`.
- [ ] El golden set y los resultados del benchmark existen en `eval/results/`, y `docs/comparativa_modelos.md` nombra el **modelo elegido** y el **hardware mínimo**.
- [ ] `docs/despliegue.md` y `ARQUITECTURA.md` están en el repo.

Lo que falle se corrige primero; el Plan 2 se apoya en eso. Para obtener el estado real del repo, usar el prompt de revisión de solo lectura (sección 10).

## 4. Qué se espera de cada frente

Responsables según el plan de trabajo vigente. **El Frente 7 es propuesta**; ajústalo según disponibilidad.

### Contratos de interfaz (primeros dos días del Sprint 1, todos)
Congelar antes de programar, con ejemplos reales en `docs/contratos/`:
1. Señal de riesgo (JSON): tipo, criterio, valor, umbral, contratos, periodo, nivel, confianza.
2. Estado del caso y transiciones, con el motivo de `BLOQUEADO`.
3. Vistas aprobadas y diccionario (ya existen del Avance 1).
4. Entrada, salida y errores de cada tool.
5. Fragmento normativo y cita (ley, artículo, versión, vigencia, fuente).
6. Evento de bitácora.
7. API del backend (endpoints, formatos, roles).

### Resumen por sprint

| Frente | Sprint 1 | Sprint 2 (→ Entrega 2) | Sprint 3 | Sprint 4 (→ Entrega final) |
|---|---|---|---|---|
| **1. Front-end** (Vio, Emilio) | Diseño de pantallas; consulta con el SQL visible, sobre API simulada | Consulta y reporte conectados a la API real; decisión sobre señales (HU-07) | Rastro (HU-06), lista ordenada (HU-08), resumen ejecutivo (HU-09), estados y errores | Pruebas de la interfaz, ajustes con retroalimentación, imagen del front para el despliegue |
| **2. Backend** (Emiliano) | API de casos y estados; bitácora escribiendo; rol y control de acceso | Decisiones humanas; entrega de reportes (almacenamiento local detrás de una interfaz); registro de agentes mínimo | Subida a S3 y URLs prefirmadas; telemetría integrada; API documentada | Pruebas de carga con concurrencia; correcciones |
| **3. Agente Consulta** (Alean) | Prompt con las vistas aprobadas; validador de SQL en el servidor; aclaración ante solicitud ambigua | Agente completo sobre el orquestador; exactitud de SQL medida con el golden set | Mejoras según los fallos; casos de información inexistente (2025) | Escenario 1 con evidencia |
| **4. Agente Detección + Normativo** (Mario, Aarón) | Reglas de detección con umbrales **configurables y provisionales**; corpus normativo completo cargado | 69-B por RFC (HU-04), adjudicaciones directas y concentración (HU-02); RAG con filtro de vigencia y verificación de citas | Montos atípicos e inconsistencias (HU-03); ranking (HU-08); HU-10 solo si se confirma | Escenarios 3 y 4 con evidencia |
| **5. Agente Reportes** (Mich) | Plantilla y esquema de salida; formato del reporte decidido | Reporte de una señal de punta a punta, con verificación de citas | Resumen ejecutivo (HU-09); límites y lenguaje de señal; entrega a S3 | Escenario 2 con evidencia; reportes de ejemplo |
| **6. Orquestación** (Ana Pau) | Grafo de LangGraph con estados, reintentos y bloqueos; agentes simulados | Integración con los 3 agentes reales y la bitácora; conexión con el modelo local | Escenarios 5 y 6; agente apagado y tiempos de espera; límite de pasos | Pruebas de punta a punta; ensayo |
| **7. Despliegue y operación** (Emiliano, con apoyo de otra persona) | Decisiones y accesos (ver sección 5) | Staging mínimo en AWS | Respaldos y restauración probada; Tailscale desde el contenedor; seguridad; alarmas | Congelamiento, reversa, guion de demostración y plan B |

### Notas por frente
- **Normalización:** el plan de trabajo la asigna al Agente 2, pero ya se resolvió en el ETL (SQL) durante el Avance 1. El trabajo de Mario y Aarón se concentra ahora en las reglas, el corpus y el ranking.
- **Detección:** los umbrales no deben quedar en el código sino en una tabla de configuración (`config.umbrales`), con el valor, el motivo y el estado `provisional`. Montos atípicos: comparar contra un grupo (misma ley, tipo de procedimiento y año) con una medida robusta, como la mediana y el rango intercuartil, y mostrar siempre contra qué se comparó.
- **Cobertura de datos:** las reglas que usan periodos o series deben respetar que **no hay datos de 2025** y que 2023 y 2024 son parciales. La dependencia solo existe en ComprasMX (2026).
- **Backend:** el registro de agentes (`audit.agentes`) pasa de tabla a servicio mínimo: alta autenticada, estado, verificación periódica y selección del agente por usuario. No se aceptan direcciones arbitrarias del cliente.
- **Carga de trabajo:** Backend, base de datos y despliegue están hoy en una sola persona. Es el punto con mayor riesgo del plan; conviene que otro integrante tome Tailscale, S3 e IAM.
- **Capa semántica y vistas con forma de estrella (Backend y Agente Consulta, Sprints 1 y 2):** `docs/capa_semantica.md` con la definición de cada métrica de contratación (por ejemplo, adjudicación directa), el grano de cada tabla (un contrato por fila), la base de fechas, los registros que se excluyen (`fecha_inicio_valida = false`) y las reglas de agregación (los importes de ComprasMX y del histórico no son la misma población; los porcentajes se recalculan, no se suman). Sobre `clean`, vistas con un hecho de contrato y dimensiones de proveedor, institución, fecha y procedimiento. Son vistas, no un rediseño de `clean`.
- **Ficha de empresa (Agente Detección + Normativo, Agente Reportes y Front-end, Sprints 2 y 3):** flujo en el que el auditor pide la información de una empresa y el sistema reúne sus contratos (cuántos, montos, años), su proporción de adjudicaciones directas, su situación en el 69-B con fecha, las normas recuperadas por señal y las limitaciones. Es el flujo de la demostración final. El agente nunca afirma que hay una violación ni un fraude: presenta hallazgos que podrían requerir revisión.

## 5. Frente 7: Despliegue y operación (nuevo)

### 5.1 Qué falta en el plan de trabajo
El plan vigente solo tiene una línea ("Docker Compose y publicación en EC2") y otra para S3. `docs/despliegue.md` describe además: balanceador y TLS, VPC y grupos de seguridad, secretos y roles IAM, respaldos con restauración probada, Tailscale desde el contenedor, registro de agentes, observabilidad y criterios de aceptación. Nada de eso tiene responsable ni fecha.

### 5.2 Alcance por niveles

| Nivel | Contenido |
|---|---|
| **Obligatorio para el 2 de diciembre** | EC2 con Docker Compose de producción (front, backend, BD); solo HTTPS expuesto; PostgreSQL sin puerto publicado; S3 privado con subida y descarga prefirmada probadas; secretos fuera del repo; Tailscale funcionando desde el contenedor hacia un agente y rechazando uno no autorizado; **un respaldo y una restauración probados**; alarma de gasto |
| **Deseable** | Imágenes en ECR y despliegue desde CI; métricas y alarmas básicas (disco, CPU, antigüedad del respaldo); prueba de carga con 2 o 3 usuarios concurrentes |
| **Solo documentado** | Migración a RDS, Object Lock, simulacros periódicos, SSO, varios agentes por usuario |

### 5.3 Etapas

**D0. Decisiones y accesos (Sprint 1, hasta el 6 de noviembre)**
- Cuenta de AWS, región, presupuesto y alarma de gasto. **Es el bloqueo número uno:** sin cuenta no hay despliegue.
- Dominio y certificado, o una alternativa para tener HTTPS. Una opción a evaluar es acceder solo por la red privada de Tailscale, que evita el dominio público; hay que verificarla con el administrador de la tailnet.
- Quién administra la tailnet y con qué plan; quién custodia los secretos.
- Entregable: `docs/despliegue_decisiones.md`.

**D1. Staging mínimo (Sprints 1 y 2, hasta el 17 de noviembre)**
- Guía paso a paso, con comandos, verificaciones y prompts: `DESPLIEGUE_STAGING.md`.
- Dockerfile de producción para backend y front, y `docker-compose.prod.yml`: sin puertos de la BD en el host, sin montajes de desarrollo, reinicio automático, verificaciones de salud y registros.
- EC2 con un volumen EBS de datos separado; administración con Session Manager, sin SSH público.
- Secretos en Secrets Manager (o el almacén que se apruebe), con rol de instancia y sin claves estáticas.
- **Qué cargar:** medición por esquema en la BD local: `clean` 3,842 MB, `raw` 1,220 MB, `staging` 1,127 MB; `rag`, `audit` y `telemetry` menos de 1 MB. **Propuesta:** en staging restaurar solo `clean`, `rag`, `audit` y `telemetry` (unos 3.8 GB, el 62 % del total) y volver a generar `raw` y `staging` con el ETL si hiciera falta. Es una decisión del equipo.
- Bucket de reportes con su rol mínimo; Tailscale en el host; ACL con etiquetas.

**D2. Seguridad y recuperación (Sprint 3, hasta el 24 de noviembre)**
- `pg_dump` en formato custom a un bucket de respaldos separado; **restauración completa probada en un ambiente aislado**, con tiempo medido.
- Prueba de que un agente no autorizado es rechazado y de que la API de Ollama no es alcanzable desde Internet.
- Verificaciones del `docs/despliegue.md` (puertos, acceso público, URL prefirmadas, hash).
- Pruebas de carga con la carga de la Fase 7.

**D3. Congelamiento y demostración (Sprint 4, hasta el 1 de diciembre)**
- Versión etiquetada y procedimiento de reversa.
- Guion de demostración y **plan B**: el mismo flujo con `docker compose` local y capturas, por si falla la nube o la red.
- Definir qué laptop actúa como agente de la demostración, y que esté encendida y conectada.

### 5.4 Qué queda pendiente aunque se despliegue
Concurrencia objetivo, retención, RPO y RTO, costo máximo y la decisión entre PostgreSQL en la EC2 y RDS. Se declaran como **limitaciones**, no se inventan cifras.

## 6. Decisiones pendientes, con fecha y valor provisional

| # | Decisión | Quién | Fecha límite | Valor provisional si no hay respuesta |
|---|---|---|---|---|
| 1 | Cuenta de AWS, región, presupuesto, dominio | Equipo y profesor | 6 nov | Si no hay cuenta el 10 de nov, la demostración corre en `docker compose` local y el despliegue queda documentado (plan B) |
| 2 | Formato del reporte (Markdown o PDF) | Equipo | 6 nov | PDF en S3 (`reportes/{caso_id}/{version}.pdf`), con vista previa en el front |
| 3 | Modelo y hardware mínimo | Equipo, según `comparativa_modelos.md` | 6 nov | El modelo mejor evaluado que quepa en el hardware menos potente |
| 4 | Administrador y plan de la tailnet | Equipo | 6 nov | El dueño del repo, hasta que se acuerde otra cosa |
| 5 | Umbrales y criterio de "comparable" | Socio formador | 11 nov | Valores propuestos por el equipo, en `config.umbrales`, marcados `provisional` en cada reporte |
| 6 | Normas prioritarias y validación legal | Socio formador (área legal) | 11 nov | Corpus del Avance 1, marcado `pendiente_validacion_legal` |
| 7 | Alcance de HU-10 | Socio formador | 11 nov | Fuera del MVP. Si se pide, una regla estadística simple sobre 2011–2022, no una LSTM, por los huecos de datos |
| 8 | Accesos por rol y auditorías externas | Socio formador | 13 nov | Roles auditor, analista de datos, legal y directivo; sin acceso externo |
| 9 | Línea base del tiempo manual por caso | Socio formador o el equipo | 13 nov | El equipo cronometra 3 a 5 casos hechos a mano |
| 10 | RPO y RTO, retención de respaldos | Socio formador | 18 nov | Respaldo diario y restauración probada; valores propuestos y documentados |
| 11 | Dependencia para el histórico, clasificación de etiquetas "otro" | Socio formador | 11 nov | Preguntas por dependencia solo sobre 2026; la clasificación sigue `pendiente` |
| 12 | Uso esperado de la BD sintética financiera y flujo del auditor: (A) evaluar a un cliente del banco que pide un crédito, o (B) investigar a una empresa asignada a auditoría con datos públicos. Si es A: llave de cruce y criterios de evaluación | Socio formador | 11 nov | Se avanza con B (es lo documentado); la BD sintética queda aparte, fuera de `clean` y de las vistas del agente |

**Mandar las preguntas del 5 al 12 juntas, esta semana, en un solo mensaje.**

## 7. Escenarios y métricas por entrega

| Escenario | Entrega 2 (≈ 18 nov) | Entrega final (2 dic) |
|---|---|---|
| 1. Consulta en lenguaje natural | Pasa, con SQL y conteo visibles | Pasa, con evidencia |
| 2. Reporte explicable | Una señal de punta a punta | Pasa, con citas verificadas |
| 3. Coincidencia con el 69-B | Pasa por RFC | Pasa, con la baja confianza por nombre |
| 4. Monto atípico | En desarrollo | Pasa; marca solo los atípicos del conjunto de referencia |
| 5. Información insuficiente | Diseñado | Pasa: excluye y cuenta los registros sin dato |
| 6. Información contradictoria | Diseñado | Pasa: muestra ambos valores y deja el caso en revisión |

**Flujo de la demostración final:** la "ficha de empresa" (ver notas del frente 4). Debe cubrir una empresa con coincidencia por RFC en el 69-B, una con solo coincidencia por nombre (baja confianza), una con datos faltantes y una consulta sobre un periodo sin datos (2025).

| Indicador | Meta del diseño | En la Entrega 2 | En la final |
|---|---|---|---|
| Exactitud del SQL | 85 % o más | Medir y reportar **el valor real** | Valor final, con las mejoras |
| Trazabilidad (reportes con rastro completo) | 100 % | Medir | 100 % en los casos de prueba |
| Citas correctas | 90 % o más, cero inventadas | Medir sobre una muestra | Medir con revisión humana |
| Tasa de confirmación de señales | Por definir | Primera revisión interna | Con la revisión disponible |
| Tiempo por caso | Reducir al menos 50 % | No se mide | Comparar con la línea base de la decisión 9 |

La meta de 85 % de exactitud es un objetivo a medir. Si no se alcanza, se presenta el valor real, los tipos de error y las mejoras aplicadas.

## 8. Riesgos del Plan 2

| Riesgo | Mitigación |
|---|---|
| Una persona concentra backend, base de datos y despliegue | Repartir Tailscale, S3 e IAM; revisión cruzada de cada cambio |
| No hay cuenta de AWS a tiempo | Decisión 1 con plan B; el despliegue se documenta con evidencia local |
| Integración tardía entre agentes | Contratos congelados en el Sprint 1, agentes simulados, integración en el Sprint 2 |
| Tailscale no alcanza desde el contenedor | Probarlo en el Sprint 2, no en el 4; usar la alternativa aprobada del diseño |
| La laptop-agente está apagada en la demostración | Una laptop designada, guion de encendido, plan B local |
| Exactitud del SQL por debajo de la meta | Vistas simples con comentarios, ejemplos en el prompt, revisión por tipo de error |
| Umbrales sin confirmar | Configurables y marcados `provisional` en el reporte |
| Se interpretan mal los vacíos de datos | El agente responde "sin datos para ese periodo"; la cobertura va en el diccionario |
| Exposición de personas físicas | Campos mínimos, lenguaje de señal y no de culpa, revisión del área legal |
| Crecimiento del alcance (HU-10, resumen ejecutivo) | Prioridad: HU-01, 02, 04, 05, 06, 07 primero; el resto si hay tiempo |

## 9. Cambios al plan de trabajo por frente

1. Agente 2: quitar "Normalización en Python" (ya está en el ETL) y reasignar: Mario lleva las reglas de detección y los casos 3 y 4; Aarón, el corpus y el RAG, el ranking y el caso 2 (parte normativa).
2. Backend: mover el despliegue (actividad 8 de su lista) al Frente 7 y agregar el servicio de registro de agentes y los reintentos con idempotencia.
3. Agregar el **Frente 7** de la sección 5 con responsable y fechas.
4. Agregar el calendario de la sección 2 y las decisiones de la sección 6.
5. Telemetría: la implementación ya existe; falta integrarla en los agentes y medir tokens y latencia por caso.
6. Aclarar que HU-10 queda fuera del MVP salvo confirmación.

## 10. Cómo trabajar con Claude Code

**Reglas:**
- Un frente por persona y una tarea por vez; cambios pequeños, con pruebas y revisión de otro integrante.
- Pedir siempre primero la revisión y el plan, y luego ejecutar.
- Todo cambio de esquema va en `etl/sql/`; todo secreto fuera del repo.
- Nada se declara hecho sin una verificación que se pueda repetir.

**Prompt de arranque del Plan 2 (solo lectura):**

````text
Lee completos AVANCE_2_PLAN.md, AVANCE_1_PLAN.md, ARQUITECTURA.md, docs/despliegue.md y DESPLIEGUE_STAGING.md. Hoy es el inicio del Plan 2.
TU TAREA ES SOLO REVISAR: no modifiques archivos, no ejecutes migraciones ni hagas commits.
1. Verifica la "Puerta de entrada" de la sección 3 de AVANCE_2_PLAN.md y dime qué pasa y qué falla, con evidencia.
2. Compara el estado del repo y de la BD contra la sección 4 (frentes) y señala qué ya existe de cada frente.
3. Lista los contratos de interfaz de la sección 4 que ya existen en el repo y los que faltan.
4. Entrega: una tabla (Frente | Ya existe | Falta | Riesgo), las contradicciones que encuentres, y el orden que propones para el Sprint 1.
No inventes: si algo no lo pudiste verificar, escribe "no verificado".
````

**Plantilla de prompt por frente:**

````text
Frente: <nombre>. Lee AVANCE_2_PLAN.md (sección 4, mi fila), ARQUITECTURA.md y los contratos de docs/contratos/.
Dime qué ya existe y qué ajustarías; no cambies nada todavía. Después ejecuta solo la tarea <X>, con pruebas, y muéstrame los cambios y cómo verificarlos.
````
