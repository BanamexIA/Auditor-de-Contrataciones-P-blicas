# Guía: preparar tu laptop como agente de inferencia

**Para:** integrantes del equipo que prestan su laptop como agente · **Tiempo:** ~20 min (más la descarga del modelo)

Tu laptop corre el modelo con Ollama. La EC2 (`auditor-ec2`) se conecta a ella por
Tailscale, revisa cada 60 s si está disponible y le manda trabajo cuando hay un caso.
Nadie fuera de Tailscale puede llegar a tu Ollama.

```
EC2 (backend)  ──Tailscale, puerto 11434──►  tu laptop (Ollama + modelo)
```

La configuración se hace **una sola vez**. Después, para trabajar solo necesitas la
laptop encendida, Tailscale conectado y Ollama abierto.

---

## 1. Tailscale

1. Instala Tailscale (https://tailscale.com/download) e inicia sesión con la cuenta
   que el equipo ya tiene en el grupo (`group:equipo`).
2. En PowerShell, anota el nombre de tu equipo y tu IP:
   ```powershell
   tailscale status
   ```
   La primera línea es tu laptop: `100.x.x.x   <nombre>   tu-cuenta@   windows   -`.
   **Mándale `<nombre>` al administrador del backend.**

## 2. Ollama y el modelo

1. Instala Ollama: https://ollama.com/download
2. Descarga los dos modelos del proyecto:
   ```powershell
   ollama pull qwen2.5:7b
   ollama pull nomic-embed-text
   ollama list
   ```
   - `qwen2.5:7b` es el modelo que redacta la consulta SQL (valor de `AGENT_MODEL`).
   - `nomic-embed-text` hace los embeddings de la búsqueda normativa (RAG). Sin él,
     el caso sigue, pero el reporte sale sin fragmentos de norma.

## 3. Que Ollama acepte conexiones de Tailscale

Por defecto Ollama solo escucha en `localhost`.

```powershell
setx OLLAMA_HOST "0.0.0.0:11434"
```

Cierra Ollama (clic derecho al ícono junto al reloj → **Quit**) y vuelve a abrirlo
desde Inicio. Comprueba:

```powershell
netstat -ano | findstr 11434
```

Debe decir `0.0.0.0:11434`. Si dice `127.0.0.1:11434`, cierra sesión en Windows y
vuelve a entrar.

## 4. Firewall: solo desde Tailscale

`0.0.0.0` abre Ollama en todas tus redes; el firewall lo limita a Tailscale
(`100.64.0.0/10`). Abre PowerShell **como administrador** (Inicio → PowerShell →
clic derecho → *Ejecutar como administrador*):

```powershell
New-NetFirewallRule -DisplayName "Ollama solo Tailscale" -Direction Inbound -Protocol TCP -LocalPort 11434 -RemoteAddress 100.64.0.0/10 -Action Allow
```

Si Windows pregunta si permites `ollama.exe`, **no lo permitas en redes públicas**.

**¿Tienes antivirus con firewall propio** (Bitdefender, Kaspersky, Norton, McAfee)?
Agrega ahí la misma regla: permitir `ollama.exe`, entrada TCP, puerto 11434, IP
remota `100.64.0.0/10`. No dejes reglas de "cualquier IP" para Ollama.

## 5. Prueba en tu laptop

```powershell
tailscale ip -4
curl.exe -m 5 http://<tu-IP-100.x>:11434/api/version
```

Debe responder `{"version":"..."}`. Avisa al administrador: él hace el alta y te
confirma que tu laptop aparece como **disponible**.

---

## Lo hace el administrador (EC2)

```bash
cd /opt/auditor/app
curl -m 5 http://<nombre>:11434/api/version
sudo docker compose exec backend python -m backend.agentes alta --usuario <usuario> --nombre <nombre>
sudo docker compose exec backend python -m backend.agentes listar
```

La regla de Tailscale que deja a la EC2 llegar al puerto 11434 de `group:equipo` ya
existe; un integrante nuevo solo tiene que estar en ese grupo.

## Día a día

- Laptop encendida, **Tailscale conectado** y **Ollama abierto** mientras haya trabajo.
- Si apagas la laptop, el backend usa otra disponible. Si no hay ninguna, el caso se
  bloquea con el motivo y el auditor lo desbloquea cuando vuelvas.
- Si cambia `AGENT_MODEL`, vuelve a hacer `ollama pull` con el nuevo modelo.
- Los motores se conectan **solo por Tailscale**. El túnel SSH a la EC2 es para ver el
  front y no lo necesitas para prestar tu laptop.

## Si algo falla

El administrador ve el estado con `listar`:

| Estado | Qué significa | Qué hacer |
|---|---|---|
| `disponible` | Todo bien | Nada |
| `sin_modelo` | Ollama responde pero no tiene el modelo | `ollama pull <AGENT_MODEL>` |
| `apagado` | La EC2 no llega a tu Ollama | Revisa la tabla de abajo |

| Síntoma | Causa probable | Arreglo |
|---|---|---|
| `curl` a `localhost:11434` falla | Ollama cerrado | Ábrelo |
| `localhost` responde, la IP `100.x` no | Ollama sigue en `127.0.0.1` | Paso 3: Quit, abrir de nuevo o cerrar sesión |
| Tailscale dice `offline` | Tailscale desconectado | Ábrelo y conéctate |
| Desde la EC2: timeout, aunque `tailscale ping` responda | Firewall de Windows o del antivirus | Paso 4; revisa reglas de **bloqueo** para `ollama.exe` |
| `New-NetFirewallRule`: *Access is denied* | PowerShell sin permisos | Ábrela como administrador |

## Dejar de ser agente

```powershell
Remove-NetFirewallRule -DisplayName "Ollama solo Tailscale"
[Environment]::SetEnvironmentVariable("OLLAMA_HOST", $null, "User")
```

Reinicia Ollama y pide al administrador la baja
(`python -m backend.agentes baja --nombre <nombre>`).

Detalles técnicos: [contratos/agentes.md](contratos/agentes.md).
