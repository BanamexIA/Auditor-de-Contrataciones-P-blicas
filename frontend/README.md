# Front del Auditor de Contrataciones

Aplicación web en **React + TypeScript (Vite)** que habla con el backend **Flask** del proyecto.

- **Izquierda — Chat:** el auditor pregunta en español; el Agente Consulta genera un SQL de solo
  lectura y la respuesta se muestra como tabla. El botón **«Analizar y generar reporte»** corre
  Calidad, Detección, Normativo y Reportes sobre ese caso.
- **Derecha — Reporte:** visor del PDF del caso. El auditor puede resaltar, subrayar y agregar
  notas personales (se guardan en su navegador). **El reporte oficial no se modifica**: tiene un
  SHA-256 registrado y pasó el verificador de citas.
- **Derecha — Señales y decisión:** revisión humana. Cada señal se marca como relevante,
  descartada (con comentario obligatorio) o pendiente, y el caso se cierra cuando todas están
  decididas. Todo queda en la bitácora con el usuario.

## Arranque

Requiere Node.js 18+ (`node -v`). Si no lo tienes instalado, `dev.ps1` usa una copia portátil en `.node/`.

```powershell
cd frontend
copy .env.example .env.local     # y ajusta BACKEND_URL
npm install
npm run dev                      # http://localhost:5173
```

`BACKEND_URL` es a dónde Vite redirige `/api`:

| Backend | `BACKEND_URL` | Antes |
|---|---|---|
| Local (`docker compose up`) | `http://localhost:5000` | — |
| EC2 | `http://localhost:15000` | Abrir el túnel: `ssh -i "$env:USERPROFILE\.ssh\auditor_ec2" -N -L 15000:127.0.0.1:5000 ubuntu@auditor-ec2` |

El inicio de sesión usa los usuarios del backend (`python -m backend.usuarios alta ...`).
Si el backend no tiene `AUTH_SECRET` (solo en desarrollo), la app no pide sesión.

## Qué endpoints usa

Todos documentados en [docs/api.md](../docs/api.md):

| Uso | Endpoint |
|---|---|
| Sesión | `GET /health`, `POST /auth/login`, `GET /auth/yo` |
| Preguntar | `POST /demo/preguntar` |
| Analizar | `POST /demo/casos/<id>/analizar` |
| Ver el PDF | `GET /casos/<id>/reportes/<v>/contenido` (bytes verificados con SHA-256) |
| Señales y cierre | `GET /casos/<id>`, `GET /casos/<id>/senales`, `POST /casos/<id>/senales/<sid>/decision`, `POST /casos/<id>/transiciones` |

`/demo/*` existe mientras no está el orquestador (LangGraph). Cuando exista, solo cambia
`src/api/auditor.ts`.

## Estructura

```
src/
├─ api/
│  ├─ client.ts        fetch + token Bearer + errores {"error": {codigo, mensaje}}
│  └─ auditor.ts       una función por endpoint del backend
├─ features/
│  ├─ auth/            Login
│  ├─ chat/            Chat, tabla de resultados, botón de análisis
│  ├─ pdf/             Visor y notas personales (pdf.js + pdf-lib)
│  └─ senales/         Revisión humana: decisión por señal y cierre del caso
├─ lib/notas.ts        Notas del auditor en localStorage (por caso y versión)
└─ types/              Tipos de la API, del chat y de las anotaciones
```

## Notas del visor

| Herramienta | Tecla |
|---|---|
| Seleccionar | V |
| Resaltar / Subrayar / Tachar | H / U / K |
| Nota | N |
| Cuadro de texto | T |

`Supr` borra la nota seleccionada; `Ctrl+Z` / `Ctrl+Y` deshacen y rehacen. «Copia con notas»
descarga un PDF personal con las marcas aplanadas; «Reporte» descarga el oficial sin cambios.

## Limitaciones

- Las notas viven en el navegador de cada auditor: no se comparten ni cuentan como decisión.
  Lo que cuenta para el caso son las decisiones de la pestaña Señales.
- Una pregunta tarda lo que tarde el modelo en la laptop del agente (con `qwen2.5:7b` sin GPU,
  1–2 minutos). El proxy espera hasta 10 minutos.
- El análisis usa por defecto el texto de respaldo para las narrativas (segundos en vez de minutos).
