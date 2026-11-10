# Acceso a la base de datos en EC2

La base PostgreSQL del proyecto corre en una EC2 de AWS. No está abierta a
Internet: entras con un **túnel SSH** y te conectas con DBeaver/pgAdmin como si
la base estuviera en tu computadora.

> ⚠️ Necesitas una red que permita SSH (puerto 22). La red de la escuela lo
> bloquea: usa la de tu casa o el hotspot del celular.

## 1. Genera tu llave SSH (solo una vez)

**Windows (PowerShell):**

```powershell
mkdir $env:USERPROFILE\.ssh -Force
ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\auditor_ec2" -C "tu-nombre"
```

**macOS / Linux:**

```bash
ssh-keygen -t ed25519 -f ~/.ssh/auditor_ec2 -C "tu-nombre"
```

Cuando pida *passphrase*, puedes poner una contraseña (recomendado) o dejarla
vacía. Se crean dos archivos:

| Archivo | Qué es | ¿Se comparte? |
|---|---|---|
| `auditor_ec2` | Llave **privada** | ❌ **Nunca.** No la mandes a nadie. |
| `auditor_ec2.pub` | Llave **pública** | ✅ Sí, se la mandas al administrador. |

## 2. Manda tu llave pública y tu IP al administrador

1. Copia el contenido de la llave pública:
   - Windows: `Get-Content $env:USERPROFILE\.ssh\auditor_ec2.pub | Set-Clipboard`
   - macOS: `pbcopy < ~/.ssh/auditor_ec2.pub`
2. Abre <https://checkip.amazonaws.com> **desde la red que usarás** (casa o
   hotspot) y anota tu IP.
3. Envía ambas cosas al administrador por mensaje privado. Si cambias de red o
   tu IP cambia, tendrás que mandar la nueva.

Espera la confirmación. El administrador te dará la **IP de la EC2** y la
**contraseña de `agent_ro`** (por privado, nunca en el grupo).

## 3. Abre el túnel (cada vez que quieras usar la base)

**Windows:**

```powershell
ssh -i "$env:USERPROFILE\.ssh\auditor_ec2" -N -L 15432:127.0.0.1:5432 ubuntu@<IP_EC2>
```

**macOS / Linux:**

```bash
ssh -i ~/.ssh/auditor_ec2 -N -L 15432:127.0.0.1:5432 ubuntu@<IP_EC2>
```

- La primera vez pregunta `Are you sure you want to continue connecting?` →
  escribe `yes`.
- Si parece "congelado", **está funcionando**: `-N` no muestra nada. Deja esa
  terminal abierta mientras uses la base. Ciérrala con `Ctrl+C` al terminar.

## 4. Conéctate con DBeaver

**Nueva conexión → PostgreSQL:**

| Campo | Valor |
|---|---|
| Host | `127.0.0.1` |
| Puerto | `15432` |
| Base de datos | `auditor_contrataciones` |
| Usuario | `agent_ro` |
| Contraseña | la que te dio el administrador |

Pulsa **Test Connection**. Tienes acceso de **solo lectura** a los esquemas
`clean` y `rag` (por ejemplo `SELECT * FROM clean.contratos LIMIT 10;`). Es
normal recibir *permission denied* en `raw` y `staging`.

## Problemas comunes

| Error | Causa probable | Solución |
|---|---|---|
| `Connection timed out` | Red bloquea SSH, tu IP no está autorizada, o la EC2 está apagada | Cambia a hotspot/casa; manda tu IP actual; pregunta si la EC2 está encendida |
| `Permission denied (publickey)` | Tu llave no está registrada o usas otra | Revisa la ruta en `-i`; confirma con el administrador |
| `UNPROTECTED PRIVATE KEY FILE` (Windows) | Permisos del archivo | `icacls "$env:USERPROFILE\.ssh\auditor_ec2" /inheritance:r /grant:r "$($env:USERNAME):R"` |
| `bind: Address already in use` | Ya tienes algo en el puerto 15432 (p. ej. tu Docker local) | Usa otro puerto: `-L 25432:127.0.0.1:5432` y en DBeaver `25432` |
| DBeaver: `Connection refused` | El túnel no está abierto | Abre el paso 3 primero |

## Reglas

- No compartas tu llave privada ni la contraseña de `agent_ro`.
- No subas contraseñas ni capturas con credenciales a Git o al grupo.
- La EC2 se apaga cuando no se usa para ahorrar créditos; su IP puede cambiar
  al encenderla. Pregunta la IP vigente si no conecta.
