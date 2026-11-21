# LLM Report Studio (front-end)

Aplicación web en **React + TypeScript (Vite)** con dos paneles:

- **Izquierda — Asistente:** conversación con el LLM. Cada petición devuelve un
  informe en PDF.
- **Derecha — Visor/editor PDF:** muestra el informe y permite **resaltar,
  subrayar, tachar, pegar notas, insertar cuadros de texto y reescribir texto
  del propio PDF**. Las anotaciones se guardan solas y el PDF se puede descargar
  o subir a S3 como nueva versión con las marcas aplanadas.

El backend (Python + FastAPI + S3) se implementará después. Mientras tanto la app
trae un **modo simulación** que genera informes de ejemplo y guarda todo en la
memoria del navegador, con la misma interfaz que usará la API real.

## Arranque rápido

Node.js no está instalado en el sistema; hay una copia portátil en `.node/`.

```powershell
.\dev.ps1            # servidor de desarrollo en http://localhost:5173
.\dev.ps1 build      # compilación de producción en dist/
```

Con Node instalado en el sistema funcionan los comandos normales:
`npm install`, `npm run dev`, `npm run build`.

## Configuración

Copia `.env.example` como `.env.local`:

| Variable | Valor por defecto | Descripción |
|---|---|---|
| `VITE_USE_MOCK` | `true` | `false` para usar el backend FastAPI real |
| `VITE_API_BASE_URL` | `/api` | Prefijo o URL completa de la API |
| `BACKEND_URL` | `http://localhost:8000` | Destino del proxy `/api` en desarrollo |

## Arquitectura

```
src/
├─ api/                      Capa de servicios (lo único que sabe de HTTP)
│  ├─ types.ts               Interfaces LlmApi y DocumentsApi
│  ├─ contracts.ts           DTO snake_case de FastAPI + mapeadores
│  ├─ httpClient.ts          fetch + errores {detail} de FastAPI
│  ├─ http/                  Implementación real (FastAPI + URLs prefirmadas de S3)
│  ├─ mock/                  Implementación simulada (LLM falso + "S3" en memoria)
│  └─ index.ts               Elige real o simulada según VITE_USE_MOCK
├─ features/
│  ├─ chat/                  Panel de conversación (useChat, ChatPanel)
│  └─ pdf/                   Visor/editor
│     ├─ PdfWorkspace.tsx    Carga, autoguardado, exportar/subir, atajos
│     ├─ PdfPage.tsx         Canvas + capa de texto de pdf.js (render perezoso)
│     ├─ AnnotationLayer.tsx Resaltados, notas, cuadros de texto, reemplazos
│     ├─ annotationsReducer  Estado con deshacer/rehacer
│     ├─ exportPdf.ts        Aplana anotaciones con pdf-lib
│     └─ selection.ts        Selección del navegador → rectángulos PDF
├─ components/               SplitPane, Icon
└─ types/                    Modelos compartidos (chat, documentos, anotaciones)
```

- **pdf.js** (`pdfjs-dist`) dibuja las páginas y la capa de texto seleccionable.
- **pdf-lib** genera los informes simulados y exporta el PDF anotado.
- Las anotaciones se guardan en **coordenadas PDF a escala 1**, independientes
  del zoom, como JSON en el backend. El PDF original nunca se modifica; las
  versiones anotadas se suben aparte.

El contrato completo con FastAPI (endpoints, cuerpos, flujo de subida a S3, CORS
del bucket y un esqueleto en Python) está en [docs/API_CONTRACT.md](docs/API_CONTRACT.md).

## Uso del editor

| Herramienta | Tecla | Cómo se usa |
|---|---|---|
| Seleccionar | V | Selecciona texto → aparece un menú para resaltar/subrayar/tachar. Clic en una anotación para editarla. |
| Resaltar / Subrayar / Tachar | H / U / K | Selecciona texto con el ratón. |
| Nota | N | Clic en la página; se puede arrastrar. |
| Cuadro de texto | T | Clic en la página y escribe; se mueve con el punto azul y se ensancha por el borde. |
| Editar texto del PDF | E | Clic sobre una línea del PDF para reescribirla. |

Además: `Supr` borra la anotación seleccionada, `Ctrl+Z` / `Ctrl+Y` deshacen y
rehacen, `Esc` vuelve a Seleccionar. El panel lateral lista todas las anotaciones,
permite comentarlas, cambiarles el color y saltar a ellas.

## Limitaciones conocidas

- "Editar texto" tapa el fragmento original con un recuadro blanco y escribe el
  nuevo texto encima (Helvetica). Es lo habitual en editores web; no reescribe el
  flujo de texto interno del PDF.
- Las fuentes estándar del PDF solo admiten caracteres latinos (acentos y ñ sí);
  emojis u otros alfabetos se sustituyen por `?` al exportar.
- Páginas con rotación distinta de 0° no se han contemplado al exportar.
- En modo simulación todo se pierde al recargar la página.
