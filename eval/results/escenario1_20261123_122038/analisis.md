# Análisis del Escenario 1 (A6, 2026-11-23, segunda corrida)

Complementa [evidencia.md](evidencia.md). Mismas seis preguntas que la
[primera corrida](../escenario1_20261123_121015/analisis.md) de las 12:10, ahora
con la mejora 26 (nombres de dependencias en mayúsculas). Es la evidencia que
vale para A6.

## Resultado

| # | Criterio | 12:10 | 12:20 |
|---|---|---|---|
| s1 | Informa cuántos registros respaldan la respuesta; el SQL se puede ver | Sí | **Sí**: "se muestran 200 de 1,182 filas por el LIMIT", 84,676 contratos detrás |
| s2 | Separa las monedas y lo dice | Sí, en el reintento | **Sí, en el reintento**: la mejora 25 rechaza el primer SQL; el segundo agrupa por moneda y avisa que el importe no se convierte |
| s3 | Si es ambigua, pide precisión | No: 0 contratos | **En parte**: 239 contratos de "SECRETARÍA DE SALUD", con el supuesto "La dependencia se buscó en mayúsculas, como está en la base"; no pidió aclaración |
| s4 | Avisa cuando el periodo está incompleto | Sí | **Sí**: 2,173, con "Cobertura incompleta en CompraNet histórico para 2023" |
| s5 | Dice cuando las fuentes no tienen el dato | Sí | **Sí**: "sin datos" escrito por el código |
| s6 | Ningún caso se presenta como fraude | Sí | **Sí**: "sin datos" con lenguaje neutral |

**5 de 6 criterios se cumplen y el sexto en parte.** El criterio de mantener el
contexto entre turnos no se corrió: el agente no guarda conversación.

## s3

La mejora 26 quitó el resultado falso: antes decía 0 contratos sin error, ahora
dice 239 y cómo buscó. Lo que falta es la aclaración: además de la Secretaría de
Salud federal hay secretarías estatales (como "SECRETARÍA DE SALUD (JAL)", con 26
contratos) y la pregunta no dice cuál. Responder con la federal es una lectura
razonable, pero el criterio pide preguntar, y eso depende de la mejora 7, que el
equipo no ha decidido.

## Limitaciones que hay que declarar en A6

- **Sin contexto entre turnos.** Cada pregunta es una llamada nueva al modelo; solo
  las aclaraciones se pasan de forma explícita.
- **Aclaraciones.** Ante métricas o nombres ambiguos el agente suele responder en
  lugar de preguntar (s3, c01, c03, c05). Pendiente la mejora 7.
- **Generalización.** Con preguntas nuevas el agente acertó 57.1 % antes de
  corregir (golden set: 93.8 %).
- **Reintentos.** El reintento por un error del validador rehace la consulta desde
  la pregunta y puede perder o agregar condiciones.
- **Elección de columnas** que el código no puede revisar: q18, n05 y e05.
- **Nombres de dependencias:** la mejora 26 corrige mayúsculas, no acentos ni
  abreviaturas ("DIRECCION" y "DIRECCIÓN" conviven en `nombre_de_la_uc`).
