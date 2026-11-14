# Acceso a la base de datos en EC2

La base PostgreSQL del proyecto corre en una EC2 de AWS. No está abierta a
Internet: entras por **Tailscale** (red privada del equipo) y un **túnel SSH**,
y te conectas con DBeaver como si la base estuviera en tu computadora.

```
Tu laptop ──Tailscale──▶ auditor-ec2 ──túnel SSH──▶ PostgreSQL (127.0.0.1:5432)
DBeaver → 127.0.0.1:15432 ───────────────┘
```

Con Tailscale la EC2 siempre se llama `auditor-ec2`, aunque su IP pública
cambie, y funciona también desde la red de la escuela.

## Resumen: qué hace cada quien

| Paso | Tú (compañero) | Administrador |
|---|---|---|
| 1 | Generar tu llave SSH | — |
| 2 | Enviar tu llave **pública** y tu correo de Tailscale | — |
| 3 | — | Agregar tu llave a la EC2, invitarte a Tailscale y darte la contraseña |
| 4 | Instalar Tailscale y aceptar la invitación | — |
| 5 | Abrir el túnel y conectarte con DBeaver | — |

---

## 1. Genera tu llave SSH (solo una vez)

Abre **PowerShell** (Windows) o **Terminal** (macOS/Linux) y ejecuta:

**Windows:**

```powershell
mkdir $env:USERPROFILE\.ssh -Force
ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\auditor_ec2" -C "tu-nombre"
```

**macOS / Linux:**

```bash
ssh-keygen -t ed25519 -f ~/.ssh/auditor_ec2 -C "tu-nombre"
```

Cambia `tu-nombre` por tu nombre (ej. `mario`); solo sirve para identificar la
llave. Cuando pida *passphrase* puedes escribir una contraseña (recomendado) o
pulsar Enter para dejarla vacía.

Se crean **dos archivos**:

| Archivo | Qué es | ¿Se comparte? |
|---|---|---|
| `auditor_ec2` | Llave **privada** | ❌ **Nunca.** No la mandes a nadie ni la subas a Git. |
| `auditor_ec2.pub` | Llave **pública** | ✅ Sí, esta es la que mandas. |

## 2. Envía tu llave pública al administrador

Muestra el contenido del archivo `.pub`:

**Windows:**

```powershell
Get-Content $env:USERPROFILE\.ssh\auditor_ec2.pub
```

**macOS / Linux:**

```bash
cat ~/.ssh/auditor_ec2.pub
```

Copia **la línea completa** y mándala por mensaje privado. Debe verse así
(una sola línea, larga):

```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHZu3wVT...xxxxxxxx tu-nombre
```

> ⚠️ **No mandes la "huella" (fingerprint).** Al terminar `ssh-keygen` aparece
> algo como `SHA256:G3UwBpltxAbuwt6l...`. Eso **no** es la llave y no sirve
> para entrar.
>
> | ✅ Llave pública (correcta) | ❌ Huella (incorrecta) |
> |---|---|
> | Empieza con `ssh-ed25519 AAAAC3NzaC1lZDI1NTE5` | Empieza con `SHA256:` |
> | ~80 caracteres + tu nombre | ~50 caracteres |

Manda también **el correo con el que iniciarás sesión en Tailscale** (paso 4).

## 3. (Administrador) Dar de alta al compañero

Entrar a la EC2 (EC2 Instance Connect o SSH) y:

1. **Agregar la llave pública** en una línea nueva:

   ```bash
   echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA...llave-completa... nombre" >> ~/.ssh/authorized_keys
   cat ~/.ssh/authorized_keys
   ```

   - Usa **`>>`** (dos signos). Con uno solo (`>`) se **borran todas** las
     llaves, incluida la tuya.
   - Cada línea del archivo debe empezar con `ssh-ed25519 AAAA` o `ssh-rsa AAAA`.
   - Para quitar a alguien: `sed -i '/ nombre$/d' ~/.ssh/authorized_keys`.

2. **Tailscale:** en <https://login.tailscale.com/admin>
   - **Users → Invite users** con su correo.
   - **Access controls:** agregar ese mismo correo en `group:equipo` y guardar.

3. **Enviarle por privado** la contraseña de `agent_ro`
   (`grep AGENT_RO_PASSWORD /opt/auditor/app/.env` en la EC2). Nunca en el
   grupo.

## 4. Instala Tailscale (solo una vez)

1. Descarga e instala desde <https://tailscale.com/download>.
2. Acepta la invitación del correo e inicia sesión **con el mismo correo** que
   mandaste al administrador.
3. Comprueba que ves la EC2:

   ```powershell
   tailscale status
   ```

   Debe aparecer una línea con `auditor-ec2`. Si no aparece, la EC2 está
   apagada o tu cuenta no está en el grupo: avisa al administrador.

## 5. Conéctate (cada vez que uses la base)

### 5.1 Abre el túnel

**Windows:**

```powershell
ssh -i "$env:USERPROFILE\.ssh\auditor_ec2" -N -L 15432:127.0.0.1:5432 ubuntu@auditor-ec2
```

**macOS / Linux:**

```bash
ssh -i ~/.ssh/auditor_ec2 -N -L 15432:127.0.0.1:5432 ubuntu@auditor-ec2
```

- La primera vez pregunta `Are you sure you want to continue connecting?` →
  escribe `yes` (la palabra completa, no `y`).
- Si escribiste passphrase en el paso 1, te la pedirá.
- Después **no muestra nada y parece congelado: así debe ser**. Deja esa
  ventana abierta mientras uses la base; ciérrala con `Ctrl+C` al terminar.

### 5.2 Configura DBeaver

**Nueva conexión → PostgreSQL:**

| Campo | Valor |
|---|---|
| Host | `127.0.0.1` |
| Port | **`15432`** (no 5432) |
| Database | `auditor_contrataciones` |
| Username | `agent_ro` (sin "e": no es `agente_ro`) |
| Password | la que te dio el administrador |

Pulsa **Test Connection** → debe decir *Connected*. Prueba:

```sql
SELECT current_user, count(*) FROM clean.contratos;
```

Tienes acceso de **solo lectura** a `clean` y `rag`. Es normal recibir
*permission denied* en `raw` y `staging`.

> 💡 Si tienes la base local en Docker Desktop, apágalo mientras usas el
> túnel: ambos podrían usar el puerto `15432` y te conectarías a la base
> equivocada.

## Problemas comunes

| Error | Causa | Solución |
|---|---|---|
| `Could not resolve hostname auditor-ec2` | Tailscale apagado o en otra cuenta | Abre Tailscale, revisa `tailscale status`; usa el correo correcto |
| `Connection timed out` | La EC2 o el lab están apagados | Pregunta al administrador si está encendida |
| `Permission denied (publickey)` | Tu llave no está en la EC2, o `-i` apunta a otro archivo | Revisa la ruta; confirma que mandaste el `.pub` correcto |
| `Identity file ... not accessible` | La ruta de `-i` no existe | `ls $env:USERPROFILE\.ssh` y usa el nombre real |
| `UNPROTECTED PRIVATE KEY FILE` (Windows) | Permisos del archivo | `icacls "$env:USERPROFILE\.ssh\auditor_ec2" /inheritance:r /grant:r "$($env:USERNAME):R"` |
| `bind: Address already in use` | Algo ya usa el puerto 15432 (ej. Docker local) | Apaga Docker Desktop o usa `-L 25432:127.0.0.1:5432` y `25432` en DBeaver |
| DBeaver: `Connection refused` / `timed out` | El túnel no está abierto o se cayó | Vuelve a ejecutar el paso 5.1 |
| `password authentication failed` | Usuario o contraseña incorrectos | Usuario exacto `agent_ro`; pide de nuevo la contraseña |

### Si aparece `Permission denied (publickey)`

Significa que **sí llegas** a la EC2 (Tailscale funciona), pero no acepta tu
llave. Revisa en orden:

1. **Tu laptop:** `ls $env:USERPROFILE\.ssh` debe mostrar `auditor_ec2` y
   `auditor_ec2.pub`. En `-i` va el archivo **sin** `.pub`, y el usuario es
   siempre **`ubuntu@`**, no tu nombre.
2. **Compara tu llave:** `Get-Content $env:USERPROFILE\.ssh\auditor_ec2.pub`
   debe ser **idéntica** a la línea que el administrador agregó.
3. **(Administrador) en la EC2:**

   ```bash
   cat ~/.ssh/authorized_keys          # la línea completa, en una sola línea
   chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys
   ```

4. **Diagnóstico:** repite el túnel con `ssh -v ...` y envía las últimas 15
   líneas al administrador; él puede revisar en la EC2
   `sudo journalctl -u ssh -n 20 --no-pager` justo después de tu intento.

## Disponibilidad

**La EC2 debe estar encendida.** Tailscale solo da un nombre fijo
(`auditor-ec2`) y una ruta privada; la base vive dentro de la instancia. Para
usarla, el administrador debe:

1. Iniciar el Learner Lab (**Start Lab**). La sesión dura unas horas; al
   terminar, AWS **detiene la instancia** automáticamente.
2. Encender la instancia (**Instance state → Start**) si está detenida.

Al encenderla, Tailscale y la base arrancan solos y el nombre `auditor-ec2` no
cambia: no hay que avisar ninguna IP. Comprueba con `tailscale status`: si
`auditor-ec2` aparece como `offline`, la instancia está apagada.

## Reglas

- La llave **privada** y la contraseña de `agent_ro` no se comparten, ni se
  suben a Git, ni van en capturas de pantalla.
- La EC2 solo está disponible cuando el administrador tiene el lab y la
  instancia encendidos. Acuerden horarios en el grupo.
- Si dejas el equipo o pierdes tu laptop, avisa para que retiren tu llave y tu
  acceso de Tailscale.

## Rol compartido `agent_ro`

Todo el equipo usa **un solo rol de solo lectura**, `agent_ro` (el mismo que
usa el Agente Consulta). Es una decisión del equipo: no hay roles personales en
la base.

- **Quién entra** se controla por persona con la llave SSH y Tailscale, no con
  el usuario de la base. Retirar una llave o un correo de Tailscale corta el
  acceso de esa persona aunque conozca la contraseña.
- En la base no se puede distinguir quién ejecutó una consulta: todas aparecen
  como `agent_ro`. Para rastrear un acceso, usa el registro de SSH de la EC2
  (`journalctl -u ssh`) y el panel de Tailscale.
- `agent_ro` solo tiene `SELECT` sobre `clean` y `rag`. No puede escribir ni
  leer `raw`, `staging`, `audit` ni `telemetry`.

### Rotar la contraseña (administrador)

Rótala cuando alguien deje el equipo, cuando se filtre o al cerrar el semestre.

1. En la EC2, genera una contraseña nueva y cámbiala en
   `/opt/auditor/app/.env` (`AGENT_RO_PASSWORD=...`).
2. Aplica el cambio en la base:

   ```bash
   cd /opt/auditor/app
   docker compose exec db psql -U postgres -d auditor_contrataciones \
     -c "ALTER ROLE agent_ro WITH PASSWORD '<nueva>';"
   ```

3. Reinicia los servicios que usen `agent_ro` (`docker compose up -d`) y manda
   la contraseña nueva por privado a cada integrante.

## Prueba de acceso

Registro de compañeros que ya se conectaron desde fuera de la red de la EC2
(evidencia de la tarea B1).

| Fecha | Integrante | Red (casa / escuela) | `SELECT current_user, count(*) FROM clean.contratos` |
|---|---|---|---|
| 2026-11-11 | Mario | Escuela | Conectado |
