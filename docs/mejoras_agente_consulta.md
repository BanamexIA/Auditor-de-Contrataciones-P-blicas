# Mejoras del Agente Consulta (A5)

Plan de mejoras a partir de las mediciones del 2026-11-17. Cada mejora dice qué
error corrige, dónde va y cómo se comprueba que funcionó.

## Punto de partida

| Medición | Resultado | Detalle |
|---|---|---|
| Golden set, 1 repetición | Exactitud del SQL 75 % | [análisis](../eval/results/consulta_20261117_125443/analisis.md) |
| Golden set, 3 repeticiones | Exactitud del SQL 79.2 %; mismo resultado en 19 de 20 casos | [análisis](../eval/results/consulta_20261117_132009/analisis.md) |
| Casos de A2 | Aclaración 2 de 5; sin datos 5 de 6 | [análisis](../eval/results/consulta_casos_consulta_20261117_133449/analisis.md) |

Errores por corregir: q06, q07, q08 y q16 del golden set, y c01, c03, c04, c10
y c13 de A2.

## Mejoras

| # | Mejora | Corrige | Dónde | Cómo se comprueba | Prioridad |
|---|---|---|---|---|---|
| 1 | **Agregar el `LIMIT` en código cuando falte** (200), en lugar de rechazar la consulta. Los demás límites del validador no cambian | c03 (falló dos veces por el `LIMIT`) y los reintentos de q13 | `agents/consulta/validator.py` o `agent.py` | c03 deja de dar `error`; q13 acierta al primer intento | Alta |
| 2 | **Reintentar cuando la base rechaza el SQL**, pasándole al modelo el error de PostgreSQL. Hoy solo se reintenta cuando falla el formato o el validador | q07 (repetición 1) y q08 | `agents/consulta/agent.py` y la ejecución (A3); el medidor debe hacer lo mismo | q07 acierta las 3 veces; q08 deja de dar `error_ejecucion` | Alta |
| 3 | **Que el validador revise las columnas de cada vista**, con la lista que da `schema_context`, y diga en qué vista está una columna mal ubicada | q07 | `agents/consulta/validator.py` | Un SQL con `rfc_exacto` en `v_contratos_agente` se rechaza antes de llegar a la base, con un mensaje que lleva al `JOIN` | Alta |
| 4 | **Reglas nuevas en el prompt:** nunca `SELECT *`; en listas, columnas mínimas y sin `GROUP BY`; "preliminar" describe la clasificación y no es un filtro; `rfc_exacto`, `nivel_confianza` y `requiere_revision_humana` solo están en la vista de coincidencias (con un ejemplo de `JOIN`); incluir todos los filtros que pide la pregunta | q06, q08, q16 y c13 | `agents/consulta/prompt.py` | Los cuatro casos aciertan | Alta |
| 5 | **Conceptos que no existen en las fuentes → "sin datos".** Regla y ejemplo en el prompt: cancelaciones, pagos, sanciones, rescisiones o modificaciones no están en los datos y no se sustituyen con otra columna | c10 (afirmó cancelaciones que no existen) | `agents/consulta/prompt.py`; opcional, una lista de conceptos revisada en código | c10 responde "sin datos" | Alta |
| 6 | **Los supuestos de cobertura los escribe solo el código.** El prompt pide al modelo no escribir supuestos sobre años o cobertura, y `agent.py` descarta los que lo hagan | Supuestos falsos o vagos (q04, c13 y otros) | `agents/consulta/prompt.py` y `agent.py` | Ningún supuesto contradice la revisión de cobertura | Media |
| 7 | **Preguntas con métrica ambigua.** Decisión de equipo: pedir aclaración, o responder declarando la métrica supuesta en `supuestos`. Según lo que se decida, ejemplos en el prompt con palabras como "más", "mucho", "grande" o "gastó" | c01, c03 y c04 | `agents/consulta/prompt.py` y `eval/casos_consulta.yaml` | Los casos se califican con la regla acordada | Media (requiere decisión) |
| 8 | **Golden set:** cambiar q08 a un periodo con coincidencias (hoy su respuesta esperada es vacía) y agregar casos de empresa, como pide A5 | Evaluación de q08 | `eval/golden_set.yaml` | La respuesta esperada de q08 no es vacía | Media |
| 9 | **Medidor:** guardar el error de cada intento y calcular la consistencia entre repeticiones | Saber por qué se reintenta (q13) | `eval/run_consulta.py` | `detalle.csv` incluye el error del primer intento; el resumen muestra la consistencia | Baja |

## Orden sugerido

1. Mejoras 1 a 4: son cambios de código y de prompt, y se pueden medir de inmediato.
2. Mejoras 5 y 6, y volver a medir el golden set y los casos de A2.
3. Mejora 7, después de acordarla con el equipo.
4. Mejoras 8 y 9.

Después de cada paso se repiten las dos mediciones:

```powershell
.venv\Scripts\python -m eval.run_consulta --repeticiones 3
.venv\Scripts\python -m eval.run_consulta --casos eval/casos_consulta.yaml
```

La meta del diseño es 85 % de exactitud del SQL. Si no se alcanza, se reporta
el valor real con sus tipos de error.

## Avance

**2026-11-19 — Mejoras 1 a 6 en el código, sin medir.** La EC2 estaba apagada,
así que no se corrieron las dos mediciones. Además de lo que pedía cada mejora:

- **Regla de booleanos (con la 4):** el modelo comparaba `rfc_exacto` y
  `requiere_revision_humana` con `'S'` o `'si'`. El prompt nombra las 6 columnas
  booleanas y pide usarlas solas en `WHERE`.
- **`DATE_TRUNC` en la revisión de cobertura (con la 6):** si el modelo filtraba
  el año con `DATE_TRUNC('year', fecha_inicio)`, el aviso de año incompleto se
  perdía, porque ya no lo escribe el modelo.
- **Mensaje del validador para un alias inexistente (sobre la 3):** antes decía
  que la columna no existía, cuando lo que no existía era el alias.

**Prueba rápida sin base** (modelo local con los comentarios de las columnas
tomados de `etl/sql/07_fase4b_transform.sql`, sin ejecutar el SQL): c10 responde
"sin datos"; q04, q06, q07, q08 y c13 escriben un SQL que se ve correcto; c12 ya
lleva el aviso de 2024. q16 todavía devuelve una columna de más
(`titulo_contrato`). q04 y q06 necesitaron dos intentos; la mejora 9 diría por
qué.

**Cuidado al leer la próxima medición:** las reglas salieron de los errores del
mismo golden set, así que la exactitud puede verse mejor que con preguntas
nuevas. Los casos de empresa de la mejora 8 sirven para comprobarlo.

**2026-11-19 — Mejoras 8 y 9 en el código, sin medir.**

- **q08** ahora cubre los años completos del histórico (2011–2022), donde están
  las coincidencias por nombre, y la pregunta dice el orden y las columnas,
  porque hay más de 20 contratos que cumplen. Falta confirmar con la base que
  su resultado esperado ya no es vacío.
- **`eval/casos_empresa.yaml`:** 6 casos de empresa (5 con SQL y 1 sin datos)
  con proveedores de ComprasMX 2026. Van aparte para que el golden set siga
  siendo comparable con A4 y porque no se usaron para ajustar el prompt.
  Falta, con la base encendida, una empresa con coincidencia por RFC y otra
  solo por nombre.
- **Medidor:** `detalle.csv` trae `errores_intentos` (etapa y error de cada
  intento fallido); el resumen muestra la consistencia entre repeticiones y
  avisa si algún caso tiene un resultado esperado vacío.

Mediciones con la base encendida:

```powershell
.venv\Scripts\python -m eval.run_consulta --repeticiones 3
.venv\Scripts\python -m eval.run_consulta --casos eval/casos_consulta.yaml
.venv\Scripts\python -m eval.run_consulta --casos eval/casos_empresa.yaml
```

**2026-11-19 — Primera medición de A5.** Análisis en cada carpeta:

| Medición | A4 | A5 | Análisis |
|---|---|---|---|
| Golden set, 3 repeticiones | 79.2 % | **75.0 %** | [consulta_20261119_175018](../eval/results/consulta_20261119_175018/analisis.md) |
| Casos de A2 | 8 de 13 | **10 de 13** | [consulta_casos_consulta_20261119_175207](../eval/results/consulta_casos_consulta_20261119_175207/analisis.md) |
| Casos de empresa | — | **SQL 1 de 5** | [consulta_casos_empresa_20261119_175313](../eval/results/consulta_casos_empresa_20261119_175313/analisis.md) |

Se arreglaron q06, q16, c10 y c13. Fallaron q07 y q08 (`c_fuente` por
`c.fuente`), q15 (eligió `fecha_inicio_valida`) y q18 (`LIMIT 20` sobre 44
filas). Los casos de empresa mostraron que el agente buscaba la empresa en
`nombre_de_la_uc`, la unidad compradora.

## Segunda ronda (2026-11-19)

| # | Mejora | Corrige | Dónde |
|---|---|---|---|
| 10 | Si el modelo escribe `alias_columna` (por ejemplo `c_fuente`), el validador responde "escribe `c.fuente`, con punto" | q07, q08 | `validator.py` |
| 11 | `LIMIT 200` salvo que la pregunta pida un número de filas: es un tope, no un recorte | q18 | `prompt.py` |
| 12 | Proveedores: regla y ejemplo resuelto (empresa ficticia) para buscar por `proveedor_normalizado`, y `providers.py` pasa el nombre que escriba el modelo a la forma del ETL (mayúsculas, sin acentos ni "SA DE CV"), con un supuesto que lo dice | e01 a e05 | `prompt.py`, `providers.py` |
| 13 | La regla de booleanos aclara que `fecha_inicio_estado` es el estado y `fecha_inicio_valida` solo sí o no | q15 | `prompt.py` |
| 14 | Si una lista selecciona `codigo_contrato` y tiene `ORDER BY` y `LIMIT`, el código agrega `codigo_contrato` al final del `ORDER BY` como desempate (2026-11-20) | q08 | `validator.py` (`add_order_tiebreaker`), `prompt.py` |

**Por qué la 14:** el SQL que escribe el modelo para q08 ordena solo por
`fecha_inicio`. Si varios contratos comparten la fecha del lugar 20, PostgreSQL
puede devolver cualquiera de ellos. La base mostró después que en q08 no hay
empate en ese corte (el 20 es del 2019-03-01 y el 21 del 2019-01-01), así que
q08 fallaba por otra razón (ver la tercera ronda). La regla se queda porque
hace que la misma pregunta devuelva siempre los mismos contratos. Ningún SQL
esperado cambia con ella: todos ya desempatan.

**Prueba rápida con la base (sin repetir):** q07, q08, q15 y q18 aciertan (q08
con la pista de la mejora 10 en el reintento). En los casos de empresa aciertan
e01, e02 y e04; e03 confundió el nombre con un tipo de procedimiento y e05
siguió buscando en `nombre_de_la_uc`. Falta la medición completa.

**Los casos de empresa ya no son preguntas nuevas:** la mejora 12 se ajustó con
ellos. Para medir si el agente generaliza está `eval/casos_empresa_69b.yaml`:
6 casos con dos empresas con coincidencia en el 69-B, una por RFC (Grupo
Elibza, ComprasMX) y otra solo por nombre (Distribuidora Universal Tobosa,
histórico), más una pregunta por la situación del 69-B, que debe dar "sin
datos".

**Hallazgo de datos:** en 420,137 contratos del histórico,
`proveedor_normalizado` conserva "S A DE C V" porque la regla del ETL quita la
puntuación antes que el sufijo. Una búsqueda exacta por el nombre de la empresa
no los encuentra (f05 y f06 lo van a mostrar). Está como decisión 9 en
[vistas_estrella.md](vistas_estrella.md).

## Segunda medición (2026-11-20)

| Medición | 2026-11-19 | 2026-11-20 | Análisis |
|---|---|---|---|
| Golden set, 3 repeticiones | 75.0 % | **75.0 %**, consistencia 20 de 20 | [consulta_20261120_142056](../eval/results/consulta_20261120_142056/analisis.md) |
| Casos de A2 | 10 de 13 | **10 de 13** | [consulta_casos_consulta_20261120_142157](../eval/results/consulta_casos_consulta_20261120_142157/analisis.md) |
| Casos de empresa | SQL 1 de 5 | **SQL 3 de 5** | [consulta_casos_empresa_20261120_142349](../eval/results/consulta_casos_empresa_20261120_142349/analisis.md) |
| Casos del 69-B | — | **3 de 6** | [consulta_casos_empresa_69b_20261120_142427](../eval/results/consulta_casos_empresa_69b_20261120_142427/analisis.md) |

Se arreglaron q07 y q15. Siguen fallando q08 (gasta los dos intentos) y q18
(elige `descripcion_excepcion`), y aparecieron q10 (el esperado recortaba a 50)
y q17 (dijo que no hay 2024). En los casos del 69-B fallaron f04 (afirmó la
situación con las coincidencias) y f05 y f06 (el sufijo "S A DE C V").

## Tercera ronda (2026-11-20)

| # | Mejora | Corrige | Dónde |
|---|---|---|---|
| 15 | El código cambia `alias_columna` por `alias.columna` antes de validar, solo si así se resuelve la columna. El reintento queda para errores reales | q08 | `validator.py` (`fix_alias_typos`), `prompt.py` |
| 16 | El validador rechaza un texto que una columna categórica nunca tiene (`fuente`, `tipo_procedimiento_norm`, `fecha_inicio_estado`, `nivel_confianza`) y lista sus valores; si parece un nombre, dice que se busque en `proveedor_normalizado` o `institucion` | e03 | `validator.py` |
| 17 | Si el modelo responde "sin datos" para años que sí tienen contratos, se reintenta con lo que dice la cobertura (etapa `cobertura` en `intentos_fallidos`) | q17 | `coverage.py` (`contradicted_no_data`), `agent.py` |
| 18 | La situación del contribuyente en el 69-B (presunto, definitivo, desvirtuado) responde "sin datos" desde el código: las vistas no la tienen | f04 | `concepts.py` (`VIEW_GAPS`) |
| 19 | El proveedor se busca con y sin su tipo de sociedad al final (`S A DE C V`, `S DE R L DE C V` y otros que el ETL conserva), con un supuesto que lo dice. Sigue sirviendo cuando se corrija el ETL | f05, f06 | `providers.py` (`add_suffix_variants`), `prompt.py` |

**Cambio de evaluación:** el esperado de q10 pasa de `LIMIT 50` a `LIMIT 200`.
La pregunta pide todas las instituciones (hay 784) y, desde la mejora 11, el
`LIMIT` es un tope y no un recorte. Sube la exactitud sin que el agente cambie.

**Prueba rápida con la base (1 repetición):** golden set 19 de 20 (solo falla
q18), casos de A2 10 de 13 (c01, c03 y c05, de la mejora 7), casos de empresa
4 de 6 (e03 ahora pide aclaración y e05 sigue en `nombre_de_la_uc`) y casos del
69-B 6 de 6. Falta la medición completa.

**Cuidado:** las cinco mejoras salieron de errores de los casos que se miden,
incluidos los del 69-B, que eran los que no se habían usado. Para saber si el
agente generaliza hacen falta preguntas nuevas. Además, `qwen2.5:7b` no es del
todo determinista entre corridas aunque la temperatura sea 0 (q17 dio "sin
datos" en la medición y SQL en una prueba rápida), así que una prueba rápida
puede acertar y la medición fallar.

Pendientes: q18 (elección de columna, sin corrección para no ajustar el prompt
a un caso), e05 (empresa buscada como unidad compradora) y la mejora 7.

## Tercera medición (2026-11-20, 15:16)

| Medición | 11-20 (14:20) | 11-20 (15:16) | Análisis |
|---|---|---|---|
| Golden set, 3 repeticiones | 75.0 % | **93.8 %**, consistencia 20 de 20 | [consulta_20261120_151617](../eval/results/consulta_20261120_151617/analisis.md) |
| Casos de A2 | 10 de 13 | 10 de 13 | [consulta_casos_consulta_20261120_151759](../eval/results/consulta_casos_consulta_20261120_151759/analisis.md) |
| Casos de empresa | 4 de 6 | 4 de 6 | [consulta_casos_empresa_20261120_151840](../eval/results/consulta_casos_empresa_20261120_151840/analisis.md) |
| Casos del 69-B | 3 de 6 | **6 de 6** | [consulta_casos_empresa_69b_20261120_151914](../eval/results/consulta_casos_empresa_69b_20261120_151914/analisis.md) |

**El golden set pasa la meta de 85 %.** Sin el cambio al esperado de q10 sería
87.5 %. En el golden set solo falla q18. q17 acierta gracias al reintento de la
mejora 17: el modelo sigue diciendo que no hay 2024.

Antes de reportarlo como resultado de A5: las mejoras 15 a 19 salieron de los
mismos casos que se miden, así que hace falta un conjunto de preguntas nuevas,
sin usar, para saber cuánto generaliza el agente.

**2026-11-21 — Preguntas nuevas:** `eval/casos_nuevos.yaml`, 8 casos (7 con SQL
y 1 sin datos) escritos sin ver cómo responde el agente. No se deben usar para
ajustar el agente antes de medirlas:

```powershell
.venv\Scripts\python -m eval.run_consulta --casos eval/casos_nuevos.yaml
```

## Medición con preguntas nuevas (2026-11-23)

El 2026-11-23 se verificó el SQL esperado con la base (sin el agente). n05 daba
0 y se cambió antes de medir. Después se corrió el agente una vez.

| Medición | Resultado | Análisis |
|---|---|---|
| Preguntas nuevas, 1 repetición | **57.1 %** del SQL (4 de 7); 62.5 % global | [consulta_casos_nuevos_20261123_105535](../eval/results/consulta_casos_nuevos_20261123_105535/analisis.md) |

**Con preguntas que no vio, el agente baja de 93.8 % a 57.1 %.** El 93.8 % del
golden set es con casos que sirvieron para ajustarlo; el 57.1 % es el que dice
cuánto generaliza, con la advertencia de que son 7 casos.

- Fallan n02 (cuenta contratos cuando se piden expedientes), n03 ("importe nulo"
  leído como cero, sin anotarlo) y n05 (omite una columna pedida; las cifras son
  correctas).
- Tres que aciertan tienen problemas que el medidor no ve: n06 muestra 2010, año
  incompleto, sin aviso (falla del código de cobertura); n04 agrega un filtro que
  nadie pidió; n05 y n06 usan `COUNT(*)` en una unión donde hacen falta
  contratos distintos.
- La medición se guardó tal como salió (commit 842b295) antes de corregir nada.

## Cuarta ronda (2026-11-23)

Sale de los errores de las preguntas nuevas. Son reglas generales, no hechas a la
medida de esas 8 preguntas, pero después de aplicarlas `casos_nuevos.yaml` ya no
sirve para medir generalización: una nueva medición con ese archivo se reporta
como "después de corregir".

| # | Mejora | Dónde | Caso que la mostró |
|---|---|---|---|
| 20 | Aviso de años incompletos también cuando la consulta agrupa por año o mes de inicio, aunque no filtre años | `coverage.py` (código) | n06: mostró 2010 sin aviso |
| 21 | Rechazar `COUNT(*)` cuya columna dice `expedientes`, `proveedores` o `instituciones`; el mensaje dice qué `COUNT(DISTINCT …)` usar y se gasta el reintento | `validator.py` (código) | n02: 2,356,609 contratos llamados "expedientes" (son 1,768,189) |
| 22 | Reglas del prompt: `COUNT(*)` cuenta contratos y cómo contar expedientes; "nulo" o "sin dato" es `IS NULL`, no cero, y una lectura dudosa va en `supuestos`; no agregar condiciones que la pregunta no pide | `prompt.py` | n02, n03 ("importe nulo" leído como cero) y n04 (tope de 10 años inventado) |
| 23 | Pedir a Ollama un contexto de 8192 tokens; con el de 4096 el prompt se cortaba sin error | `llm/ollama_client.py`, `.env.example` | q01, q03 y q05 del golden set (ver abajo) |

No se corrigió n05 (omitió una columna pedida): una regla para eso sería a la
medida de la pregunta. Tampoco el `COUNT(*)` en las uniones con el 69-B: la vista
tiene una fila por contrato y da lo mismo que `COUNT(DISTINCT codigo_contrato)`.

Las mejoras 20, 21 y 23 son deterministas y tienen pruebas (408 en total). La 22
depende de que el modelo siga el prompt; con q18 una regla así no bastó.

Para medir:

```powershell
.venv\Scripts\python -m eval.run_consulta --repeticiones 3
```

```powershell
.venv\Scripts\python -m eval.run_consulta --casos eval/casos_nuevos.yaml
```

El golden set comprueba que nada se rompió (tiene que seguir arriba de 85 %).
Los casos nuevos dicen si las correcciones funcionan en n02, n03 y n06.

**2026-11-23 — El contexto de Ollama cortaba el prompt (mejora 23).** La primera
corrida del golden set tras las mejoras 20 a 22 falló en q01, q03 y q05, que
llevaban días acertando, y se detuvo en q07 por el límite de 120 s. La causa no
fueron las mejoras sino el contexto: `llm/ollama_client.py` no pedía tamaño, y
Ollama usa 4096 tokens. El prompt de sistema del agente ya tenía unos 4,000; con
las reglas de la mejora 22 la entrada llegó a 4,094 y no quedaba lugar para la
respuesta. Cuando la entrada no cabe, Ollama la corta por el principio, sin
error, y el modelo pierde las reglas. Con `num_ctx` en 8192 (`OLLAMA_NUM_CTX`),
q01, q03 y q05 vuelven a dar el resultado esperado y la entrada llega a 4,100
tokens.

La telemetría (`telemetry/results/llm_calls.csv`) muestra que esto ya pasaba en
algunos reintentos, que llevan el SQL y el error anterior: 14 llamadas del
2026-11-19 y 3 del 2026-11-20 quedaron en unos 2,050 tokens, la mitad del
prompt. Las mediciones de esos días pueden haber perdido algún reintento por
eso. La de preguntas nuevas del 2026-11-23 (10:55) no: sus 8 llamadas tuvieron
entre 3,945 y 3,970 tokens, así que el 57.1 % no está afectado.

**2026-11-23 — Primera medición con el contexto de 8192 (11:28).** Golden set
87.5 % (q08 0 de 3, q18 0 de 3); casos nuevos 6 de 7; casos de A2 9 de 13;
empresa 4 de 6; 69-B 6 de 6. Dos retrocesos los causó la mejora 22, que también
decía "para contar proveedores, `COUNT(DISTINCT proveedor_normalizado)`": q08
pasó a mostrar `proveedor_normalizado` en lugar del nombre publicado y c04 ("¿Qué
proveedores aparecen mucho?") dejó de pedir aclaración. Se quitó esa parte de la
regla; contar proveedores con `COUNT(*)` lo sigue deteniendo la mejora 21. Con el
cambio, q08 y c04 vuelven a acertar. Esas carpetas de resultados no se suben: la
medición que cuenta es la que sigue.

## Cuarta medición (2026-11-23, 11:40)

| Medición | 11-20 (15:16) | 11-23 (11:40) | Análisis |
|---|---|---|---|
| Golden set, 3 repeticiones | 93.8 %, consistencia 20 de 20 | **93.8 %**, consistencia 20 de 20 | [consulta_20261123_114032](../eval/results/consulta_20261123_114032/analisis.md) |
| Preguntas nuevas | 57.1 % (antes de corregir) | **85.7 %**, después de corregir | el mismo |
| Casos de A2 | 10 de 13 | 10 de 13 | el mismo |
| Casos de empresa | 4 de 6 | 4 de 6 | el mismo |
| Casos del 69-B | 6 de 6 | **5 de 6** | el mismo |

**El golden set sigue arriba de la meta de 85 %**, solo falla q18. Las mejoras
20 a 22 arreglaron n02, n03, n04 y n06 en el primer intento. El 85.7 % de las
preguntas nuevas ya no mide generalización; esa cifra sigue siendo el 57.1 %.

f03 falló: unió la vista del 69-B sin que se pidiera y comparó el nombre
publicado (`m.proveedor`) con `'GRUPO ELIBZA'`, que da 0 filas. Candidata, no
aplicada: que el validador rechace comparar `proveedor` con un texto (mejora 24).
