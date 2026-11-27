# Guía: usar el front desde la EC2 (sin `npm run dev`)

**Para:** quien administra la EC2 · **Tiempo:** ~15 min la primera vez

Desde el 2026-11-24 la imagen del backend también compila el front y Flask lo sirve en `/`
(`backend/front.py`). La API sigue en la raíz (`/casos`, `/health`…) y además responde bajo `/api/...`,
que es lo que usa el front. Ya no hace falta Node ni Vite para usarlo.

## 1. Reconstruir el backend

```bash
cd /opt/auditor/app
git pull
sudo docker compose up -d --build backend     # la primera vez tarda más: instala y compila el front
curl -s localhost:5000/ | head -c 80          # debe empezar con <!doctype html>
```

## 2. Entrar tú, con el túnel SSH

```powershell
ssh -i ~/.ssh/labsuser-nueva.pem -N -o ServerAliveInterval=30 -L 15000:127.0.0.1:5000 ubuntu@auditor-ec2
```

Abre `http://localhost:15000/`. Para que Cognito acepte este origen, agrega en el *app client*
(Cognito → *App clients* → *Login pages* → *Edit*), con la barra final:

- *Allowed callback URLs*: `http://localhost:15000/`
- *Allowed sign-out URLs*: `http://localhost:15000/`

(`http://localhost:5173/` puede quedarse para quien siga usando `npm run dev`.)

## 3. Que el equipo entre sin la llave SSH: HTTPS por Tailscale

Cognito solo acepta `http://` en `localhost`; para cualquier otra dirección exige HTTPS. Tailscale da un
certificado válido para la EC2 dentro del tailnet:

1. En la consola de Tailscale → **DNS**: activa **MagicDNS** y **HTTPS Certificates** (una vez).
2. En la EC2:
   ```bash
   sudo tailscale serve --bg 5000
   tailscale serve status        # muestra la URL, p. ej. https://auditor-ec2.<tu-tailnet>.ts.net
   ```
3. En Cognito agrega esa URL (con la barra final) en *Allowed callback URLs* y *Allowed sign-out URLs*.
4. Comparte la URL: funciona para cualquier integrante conectado al tailnet; desde fuera no se ve.

`tailscale serve` reenvía a `127.0.0.1:5000`, donde el contenedor ya escucha; no se abre ningún puerto
en el grupo de seguridad de AWS. Para quitarlo: `sudo tailscale serve --https=443 off`.

## 3b. URL pública para la demo: Tailscale Funnel

`serve` (paso 3) solo se ve dentro del tailnet. Para que el jurado entre desde cualquier navegador, sin
Tailscale, se usa **Funnel**: la misma URL `https://auditor-ec2.<tu-tailnet>.ts.net`, pero pública.

1. **Consola de Tailscale → DNS:** *MagicDNS* y *HTTPS Certificates* activados (igual que en el paso 3).
2. **Consola de Tailscale → Access controls:** permite Funnel al nodo de la EC2 (`tag:db`) agregando
   esto al archivo de políticas y guarda:
   ```json
   "nodeAttrs": [
     { "target": ["tag:db"], "attr": ["funnel"] }
   ]
   ```
   (Si ya existe `nodeAttrs`, agrega solo el objeto a la lista.)
3. **En la EC2:**
   ```bash
   sudo tailscale serve --https=443 off 2>/dev/null   # si antes se usó serve en el mismo puerto
   sudo tailscale funnel --bg 5000
   tailscale funnel status
   curl -s https://auditor-ec2.<tu-tailnet>.ts.net/api/health   # desde cualquier máquina
   ```
   La primera vez el certificado tarda unos segundos en emitirse.
4. **Cognito** (cuenta de Aarón) → *App client* → *Login pages*: agrega
   `https://auditor-ec2.<tu-tailnet>.ts.net/` en *Allowed callback URLs* y *Allowed sign-out URLs*.
5. Prueba desde un teléfono **con los datos móviles** (fuera de Tailscale): debe abrir el login.

**Seguridad.** La página de login queda pública; la API sigue pidiendo sesión (Cognito o usuario local) y
solo entran correos dados de alta (paso 4). Aun así, enciéndelo para la demo y apágalo después:
```bash
sudo tailscale funnel --https=443 off
```
Funnel no depende de la IP de la EC2: la URL no cambia aunque el lab de AWS se reinicie, pero el lab
(cuenta de Aarón: EC2, S3 y Cognito) debe estar iniciado.

## 4. Dar de alta a cada integrante

Cognito solo dice quién es la persona; el rol lo da el backend. Cada correo debe existir en
`audit.usuarios` (si no, el login dice «tu cuenta no está dada de alta»):

```bash
# nuevo usuario que entra solo por Cognito
sudo docker compose exec -T backend python -m backend.usuarios alta --usuario mario --rol auditor \
    --nombre "Mario" --email correo@ejemplo.com < /dev/null
# usuario que ya existe: solo agregarle el correo
sudo docker compose exec -T backend python -m backend.usuarios correo --usuario alean --email correo@ejemplo.com < /dev/null
sudo docker compose exec -T backend python -m backend.usuarios listar < /dev/null
```

El correo debe ser el mismo con el que la persona está en el *User pool* de Cognito (en minúsculas).

## Si algo falla

| Síntoma | Causa | Arreglo |
|---|---|---|
| `localhost:15000/` muestra JSON de error | La imagen no tiene el front | `sudo docker compose up -d --build backend` |
| Cognito: *redirect_mismatch* | La URL no está en *Allowed callback URLs* | Agrégala exacta, con la barra final |
| «No hay conexión con el backend» | Túnel cerrado o backend caído | Reabre el túnel; `sudo docker compose ps` |
| «tu cuenta no está dada de alta» | El correo no está en `audit.usuarios` | Paso 4 |
| La URL `.ts.net` no abre | El equipo no está conectado a Tailscale o falta el paso 1 | Conectar Tailscale; revisar *HTTPS Certificates* |
