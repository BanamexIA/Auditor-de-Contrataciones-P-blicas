# Telemetría local del modelo

Ollama corre en la laptop del auditor; la laptop no requiere Docker ni acceso a
PostgreSQL. El script consulta Ollama directamente y guarda la llamada en
`telemetry/results/llm_calls.csv`. La métrica NVIDIA y VRAM se mide en ese mismo
equipo; en equipos sin `nvidia-smi` ambas columnas quedan en `null`.

## Preparación

1. Instala Python y las dependencias del repositorio (una sola vez):

   ```powershell
   python -m pip install -r requirements.txt
   ```

2. Instala Ollama y descarga un modelo de generación:

   ```powershell
   ollama pull qwen2.5:7b
   ollama list
   ```

3. Desde la raíz del repositorio, configura el modelo instalado y corre la
   comprobación:

   ```powershell
   $env:AGENT_BASE_URL = "http://localhost:11434"
   $env:AGENT_MODEL = "qwen2.5:7b"
   python agent_host\check_agent.py
   ```

   Si el modelo tiene otro nombre, usa exactamente el nombre de `ollama list`.
   El script verifica `/api/tags`, genera una respuesta breve y muestra tokens,
   latencia, tiempo al primer token, versión de Ollama y cuantización.

4. La ejecución local usa CSV y no necesita claves ni credenciales de BD. Para
   cambiar el archivo:

   ```powershell
   $env:TELEMETRY_CSV_PATH = "C:\ruta\privada\llm_calls.csv"
   ```

## Conexión en la red privada

Para una integración futura, la laptop debe estar conectada a Tailscale y
permitir acceso a Ollama solo desde la interfaz de Tailscale. Ollama no tiene
autenticación; no lo expongas directamente a internet. La configuración de
`OLLAMA_HOST` y las reglas de Windows Firewall dependen del sistema y la
administración de red del equipo. No abras el puerto 11434 al público.

Este script no inicia la API del agente, no ejecuta SQL y no accede a la BD.
Las llamadas instrumentadas por el backend se guardan en
`telemetry.llm_calls`; la laptop conserva sus mediciones locales en CSV.
