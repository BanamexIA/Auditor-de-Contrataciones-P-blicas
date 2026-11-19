# Registro de agentes (B7)

**Estado:** Aprobado por Backend (15 nov) · **Usan:** Orquestación, administrador, Front-end · **Tabla:** `audit.agentes`

Un **agente** es una laptop del equipo con Ollama, conectada por Tailscale. El
backend lleva el registro de cuáles existen, si responden y cuál usar en cada caso.

## Decisiones (15 nov 2026)

| Tema | Decisión | Por qué |
|---|---|---|
| Alta y baja | Solo el administrador, por CLI en la EC2 | La API no tiene autenticación todavía |
| Dirección | Solo el **nombre en Tailscale**; el backend arma `http://<nombre>:11434` | Evita que alguien haga que la EC2 llame a cualquier servidor |
| Verificación | Periódica (cada `AGENTES_VERIFICAR_CADA_S`, 60 s) **y** justo antes de usar | El estado mostrado está al día y el orquestador no usa un agente que se apagó |
| Selección | Primero un agente disponible del usuario del caso; si no hay, cualquiera disponible | El caso no se detiene porque una sola laptop esté apagada |

## Administrar (en la EC2)

```bash
cd /opt/auditor/app
docker compose exec backend python -m backend.agentes alta --usuario alean --nombre laptop-alean
docker compose exec backend python -m backend.agentes listar           # --todos incluye bajas
docker compose exec backend python -m backend.agentes verificar        # --nombre laptop-alean
docker compose exec backend python -m backend.agentes baja --nombre laptop-alean
```

`--modelo` en el alta fija un modelo para esa laptop; sin él se usa `AGENT_MODEL`.
La baja no borra la fila: queda `activo = false` y deja de usarse.

## Cómo se verifica

El backend llama a `GET /api/version` y `GET /api/tags` del agente (3 s de tiempo
máximo cada una):

| Resultado | `estado` |
|---|---|
| Responde y el modelo está instalado | `disponible` |
| Responde sin el modelo | `sin_modelo` |
| No responde, error de DNS o de red | `apagado` (`ultimo_error` guarda el tipo) |
| Nunca verificado | `desconocido` |

## Uso en el orquestador

```python
from backend.agentes.servicio import AgenteNoDisponible, seleccionar_agente
from llm.ollama_client import OllamaClient

try:
    agente = seleccionar_agente(repo_agentes, usuario=caso["creado_por"])
except AgenteNoDisponible as exc:
    repo.transitar(caso_id, "bloqueado", str(exc))   # motivo claro para el auditor
else:
    client = OllamaClient(base_url=agente["url"], model=agente["modelo"])
```

Mensaje de ejemplo cuando nadie responde:

> Ningún agente de inferencia disponible: laptop-mich (apagado), laptop-alean (sin_modelo). Enciende la laptop con Ollama y desbloquea el caso.

`equipo` en la bitácora es el `nombre_tailnet` del agente (contrato 5).

## Requisitos de red (por verificar en la EC2)

1. **Política de Tailscale (verificado 18 nov).** Sin esta regla Tailscale descarta
   el tráfico EC2 → laptop (timeout, aunque `tailscale ping` responda):
   ```json
   {"src": ["tag:db"], "dst": ["group:equipo"], "ip": ["tcp:11434"]}
   ```
2. La laptop tiene Ollama escuchando fuera de localhost (`setx OLLAMA_HOST "0.0.0.0:11434"`
   y reiniciar Ollama) y el firewall solo permite el puerto 11434 desde `100.64.0.0/10`
   (ARQUITECTURA §5). Si hay antivirus con firewall propio (p. ej. Bitdefender), la
   misma regla va ahí también.
3. **El contenedor del backend debe resolver el nombre de Tailscale.** MagicDNS
   funciona en el host, pero Docker puede no heredarlo. Prueba:
   `docker compose exec backend python -c "import socket; print(socket.gethostbyname('laptop-alean'))"`.
   Si falla, se agrega `dns: [100.100.100.100]` al servicio `backend` en Compose.
