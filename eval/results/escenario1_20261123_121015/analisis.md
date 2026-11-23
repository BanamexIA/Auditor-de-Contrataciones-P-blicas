# Análisis del Escenario 1 (A6, 2026-11-23)

Complementa [evidencia.md](evidencia.md). Seis preguntas, una por criterio de
aceptación de la épica "Preguntas en lenguaje natural", corridas una vez con el
agente completo después de la mejora 25 (`qwen2.5:7b`, contexto de 8192, base de
la EC2). Es una demostración, no una medición: las preguntas las escribió Claude
conociendo el agente.

## Resultado

| # | Criterio | ¿Se cumplió? | Lo que pasó |
|---|---|---|---|
| s1 | Informa cuántos registros respaldan la respuesta; el SQL se puede ver | **Sí** | "Se muestran 200 de 1,182 filas por el LIMIT", con 84,676 contratos detrás |
| s2 | Separa las monedas y lo dice | **Sí, en el reintento** | El primer SQL sumaba todas las monedas; el validador lo rechazó (mejora 25) y el segundo agrupa por moneda, con el aviso de que el importe no se convierte |
| s3 | Si es ambigua, pide precisión | **No** | Respondió con SQL y buscó `institucion = 'Secretaría de Salud'`, que da **0 contratos**: en la base las instituciones están en mayúsculas ("SECRETARÍA DE SALUD", 239 contratos) |
| s4 | Avisa cuando el periodo está incompleto | **Sí** | 2,173 contratos, con "Cobertura incompleta en CompraNet histórico para 2023" |
| s5 | Dice cuando las fuentes no tienen el dato | **Sí** | "Sin datos" escrito por el código: las fuentes no registran rescisiones |
| s6 | Ningún caso se presenta como fraude | **Sí** | "Sin datos" con lenguaje neutral: una coincidencia es una señal para revisión humana |

**5 de 6 criterios se cumplen.** El sexto criterio de la épica (mantener el
contexto de turnos anteriores) no se corrió: el agente no guarda conversación.

## s3: dos problemas en una respuesta

1. **No pidió aclaración.** Es lo mismo que c01, c03 y c05 de los casos de A2:
   ante una pregunta ambigua el modelo prefiere responder. Depende de la mejora 7
   (preguntar o declarar el supuesto), que el equipo no ha decidido.
2. **Mayúsculas.** Las columnas de dependencias de ComprasMX están en mayúsculas:
   `institucion` (784 valores), `descripcion_ramo` y `tipo_de_institucion`
   siempre, y `nombre_de_la_uc` en 1,180 de 1,182. Comparar con un nombre escrito
   como en la pregunta da 0 sin error. De las respuestas guardadas en
   `eval/results`, 7 hicieron eso (e01, e02 y e05 de los casos de empresa) y las
   7 estaban mal. Es el mismo tipo de error grave de n02: el resultado se ve bien
   y no lo es.

Candidata: que el código pase a mayúsculas el texto comparado con esas columnas,
como ya hace con los nombres de proveedor (mejora 12), y lo anote en `supuestos`.
No resolvería la aclaración: s3 respondería 239, los de la Secretaría de Salud
federal. Se aplicó como mejora 26 y se volvió a correr el escenario a las 12:20:
ver la [segunda corrida](../escenario1_20261123_122038/analisis.md).

## Limitaciones que hay que declarar en A6

- **Sin contexto entre turnos.** Cada pregunta es una llamada nueva al modelo; solo
  las aclaraciones se pasan de forma explícita.
- **Aclaraciones.** Ante métricas o nombres ambiguos el agente suele responder en
  lugar de preguntar (s3, c01, c03, c05). Pendiente la mejora 7.
- **Nombres de dependencias** escritos distinto que en la base (s3, mejora 26).
- **Generalización.** Con preguntas nuevas el agente acertó 57.1 % antes de
  corregir (golden set: 93.8 %).
- **Reintentos.** El reintento por un error del validador rehace la consulta desde
  la pregunta y puede perder o agregar condiciones (c03 y c05 con la mejora 25).
- **Elección de columnas** que el código no puede revisar: q18, n05 y e05.
