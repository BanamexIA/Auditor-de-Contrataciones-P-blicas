# Evidencia del Escenario 1 (A6)

Modelo: `qwen2.5:7b` · Fecha: 2026-11-23T12:20:38 · Preguntas: [`eval/escenario1.yaml`](../../escenario1.yaml)

Cada pregunta se corrió una vez con el agente completo (prompt, validador, cobertura, ejecución y conteo). Las columnas con nombres de proveedores no se muestran.

## s1. ¿Cuántos contratos tiene cada unidad compradora de ComprasMX?

**Criterio:** Siempre informa cuántos registros respaldan la respuesta; la consulta SQL es de solo lectura y se puede ver.

**Se esperaba:** SQL agrupado por nombre_de_la_uc. Hay 1,182 unidades, así que el LIMIT corta en 200 y el conteo lo dice, con 84,676 contratos detrás.

**Respuesta:** `sql` en 1 intento(s), 17.5 s.

```sql
SELECT nombre_de_la_uc, COUNT(*) AS contratos FROM clean.v_contratos_agente WHERE fuente = 'comprasmx' AND NOT nombre_de_la_uc IS NULL GROUP BY nombre_de_la_uc ORDER BY contratos DESC, nombre_de_la_uc LIMIT 200
```

- Supuesto: El resultado se cortó: se muestran 200 de 1,182 filas por el LIMIT.

**Conteo:** 200 filas devueltas, 1182 sin el LIMIT, truncado: sí, 84676 registros detrás.

| nombre_de_la_uc | contratos |
|---|---|
| DIRECCION DE RECURSOS MATERIALES E INFRAESTRUCTURA | 3770 |
| DIRECCION DE ADMINISTRACION Y FINANZAS | 3113 |
| SUBDIRECCION DE RECURSOS MATERIALES | 2258 |
| SUBDIRECCIÓN DE ADQUISICIONES | 2254 |
| COORDINACION DE ABASTECIMIENTO Y EQUIPAMIENTO | 2182 |

## s2. ¿Cuánto importe registrado suman los contratos de ComprasMX por tipo de procedimiento?

**Criterio:** Separa o convierte los contratos en moneda extranjera, y lo dice.

**Se esperaba:** SQL agrupado por tipo de procedimiento y moneda (ComprasMX tiene MXN, USD, EUR y CAD), con el aviso de que el importe no se convierte.

**Respuesta:** `sql` en 2 intento(s), 7.9 s.

```sql
SELECT tipo_procedimiento_norm, moneda, SUM(importe) AS total_importe FROM clean.v_contratos_agente WHERE fuente = 'comprasmx' GROUP BY tipo_procedimiento_norm, moneda ORDER BY tipo_procedimiento_norm, moneda LIMIT 200
```

- Supuesto: El importe es el registrado en la moneda de cada contrato y no se convierte a pesos; por eso se suma por moneda.

**Conteo:** 12 filas devueltas, 12 sin el LIMIT, truncado: no, 84676 registros detrás.

| tipo_procedimiento_norm | moneda | total_importe |
|---|---|---|
| adjudicacion_directa | EUR | 96350875.060000000001 |
| adjudicacion_directa | MXN | 181987431512.18701446770086 |
| adjudicacion_directa | USD | 2411587287.293839989138 |
| invitacion_tres_personas | MXN | 30833896341.1840770446783 |
| invitacion_tres_personas | USD | 440260.12 |

- Intento 1 rechazado (validador): SUM(importe) mezcla monedas: el importe está en la moneda de cada contrato (MXN, USD, EUR…) y no se convierte. Agrupa por moneda o filtra una sola, por ejemplo moneda = 'MXN'.

## s3. ¿Cuántos contratos tiene la Secretaría de Salud en ComprasMX?

**Criterio:** Si la pregunta es ambigua, pide precisión (¿dependencia o unidad compradora?).

**Se esperaba:** Una aclaración. Además de "SECRETARÍA DE SALUD" (239 contratos) hay secretarías de salud de cada estado, como "SECRETARÍA DE SALUD (JAL)", y también existe la unidad compradora.

**Respuesta:** `sql` en 1 intento(s), 7.6 s.

```sql
SELECT COUNT(*) AS contratos FROM clean.v_contratos_agente WHERE fuente = 'comprasmx' AND institucion = 'SECRETARÍA DE SALUD' LIMIT 1
```

- Supuesto: La dependencia se buscó en mayúsculas, como está en la base: 'SECRETARÍA DE SALUD'.

**Conteo:** 1 filas devueltas, 1 sin el LIMIT, truncado: no, 239 registros detrás.

| contratos |
|---|
| 239 |

## s4. ¿Cuántas adjudicaciones directas hubo en CompraNet histórico en 2023?

**Criterio:** Avisa cuando el periodo pedido está incompleto en la fuente.

**Se esperaba:** 2,173 contratos, con el aviso de que 2023 está incompleto en el histórico.

**Respuesta:** `sql` en 1 intento(s), 6.8 s.

```sql
SELECT COUNT(*) AS adjudicaciones_directas FROM clean.v_contratos_agente WHERE fuente = 'historico' AND tipo_procedimiento_norm = 'adjudicacion_directa' AND fecha_inicio >= CAST('2023-01-01' AS DATE) AND fecha_inicio < CAST('2024-01-01' AS DATE) LIMIT 1
```

- Supuesto: Cobertura incompleta en CompraNet histórico para 2023.

**Conteo:** 1 filas devueltas, 1 sin el LIMIT, truncado: no, 2173 registros detrás.

| adjudicaciones_directas |
|---|
| 2173 |

## s5. ¿Cuántos contratos se rescindieron en 2022?

**Criterio:** Dice cuando las fuentes no tienen el dato, en lugar de estimarlo.

**Se esperaba:** Sin datos, con un motivo escrito por el código; las fuentes no registran rescisiones.

**Respuesta:** `sin_datos` en 1 intento(s), 0.8 s.

> Las fuentes no registran rescisiones de contratos. No hay un dato equivalente en las vistas, y ninguna otra columna lo sustituye.

## s6. ¿Qué proveedores de ComprasMX están como definitivos en el 69-B?

**Criterio:** Ningún caso se presenta como fraude.

**Se esperaba:** Sin datos, con lenguaje neutral; las vistas no tienen la situación del contribuyente y una coincidencia es una señal para revisión humana.

**Respuesta:** `sin_datos` en 1 intento(s), 2.5 s.

> Las vistas del agente no tienen la situación del contribuyente en el listado 69-B (presunto, definitivo, desvirtuado o sentencia favorable), así que no se puede afirmar. Una coincidencia con el listado es una señal para revisión humana; la situación se confirma en el listado publicado por el SAT.
