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

Para permitir que un backend remoto llegue a Ollama:

1. Instala e inicia sesión en Tailscale tanto en la laptop como en el host del
   backend. Confirma la IP Tailscale de la laptop:

   ```powershell
   tailscale ip -4
   Get-NetAdapter | Where-Object { $_.InterfaceDescription -match "Tailscale" } |
     Select-Object Name, InterfaceDescription, Status
   ```

2. Ollama debe escuchar en una interfaz accesible por Tailscale. En Windows,
   configura `OLLAMA_HOST` desde **Configuración > Sistema > Acerca de >
   Configuración avanzada del sistema > Variables de entorno** con el valor
   `0.0.0.0:11434`, cierra Ollama desde el área de notificación y vuelve a
   iniciarlo. Esto hace que Ollama escuche en las interfaces de red; por eso
   el siguiente paso de firewall es obligatorio. Para una prueba temporal,
   puedes definir `$env:OLLAMA_HOST = "0.0.0.0:11434"` antes de iniciar Ollama
   desde esa misma sesión.

3. En PowerShell **como administrador**, crea una regla que permita el puerto
   solo por la interfaz Tailscale y desde las IPs Tailscale autorizadas del
   backend. Sustituye el ejemplo por la IP real del backend; no uses la IP de
   esta laptop como `RemoteAddress`:

   ```powershell
   $backendTailnetIp = "100.x.y.z"
   New-NetFirewallRule `
     -DisplayName "Ollama from authorized Tailscale backend" `
     -Direction Inbound `
     -Action Allow `
     -Protocol TCP `
     -LocalPort 11434 `
     -InterfaceAlias "Tailscale" `
     -RemoteAddress $backendTailnetIp `
     -Profile Any
   ```

   Si el adaptador tiene otro nombre, usa el valor exacto de `Name` mostrado
   por `Get-NetAdapter`. Limita `RemoteAddress` a los equipos que realmente
   necesiten acceso. Revisa las reglas existentes de Ollama en Windows
   Firewall y deshabilita cualquier regla amplia que permita el puerto desde
   redes públicas o la LAN; la regla anterior no reemplaza esa revisión.

4. Desde el host que ejecuta el backend, prueba la conexión usando la IP o el
   nombre Tailscale de la laptop:

   ```powershell
   $env:AGENT_BASE_URL = "http://<IP-o-nombre-tailscale>:11434"
   Invoke-RestMethod "$env:AGENT_BASE_URL/api/tags"
   ```

Ollama no ofrece autenticación. No abras el puerto 11434 al público ni confíes
solo en el nombre de la interfaz: combina la regla de firewall con ACLs de
Tailscale y permite únicamente los peers necesarios. La laptop ejecuta la
inferencia; la base de datos y el SQL permanecen en el backend.

Este script no inicia la API del agente, no ejecuta SQL y no accede a la BD.
Las llamadas instrumentadas por el backend se guardan en
`telemetry.llm_calls`; la laptop conserva sus mediciones locales en CSV.
