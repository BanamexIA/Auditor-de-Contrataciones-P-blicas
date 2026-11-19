# Front de demo

Una sola página (`index.html`, sin dependencias ni compilación): escribes una pregunta y el
Agente Consulta la contesta con una tabla. Usa `POST /demo/preguntar` del backend
(rama `integracion-demo`; ver `docs/api.md`).

## Correrlo

```powershell
cd front
python -m http.server 8080
```

Abre http://localhost:8080.

- **API local:** `http://localhost:5000`.
- **API de la EC2:** abre el túnel y usa `http://localhost:15000`:
  `ssh -i <llave> -N -L 15000:127.0.0.1:5000 ubuntu@auditor-ec2`
- Si la API tiene autenticación, la página pide usuario y contraseña (se crean con
  `python -m backend.usuarios alta`).
- El backend solo acepta el origen de `CORS_ORIGENES` (por defecto `http://localhost:8080`).
  Si sirves la página en otro puerto, agrégalo en el `.env` del backend.

Ctrl+Enter envía la pregunta. Con `qwen2.5:7b` la respuesta tarda de 10 a 60 s.
