# Autenticación de la API

**Estado:** Aprobado por Backend (19 nov) · **Usan:** Front-end, administrador · **Tabla:** `audit.usuarios`

## Decisiones (19 nov 2026)

| Tema | Decisión |
|---|---|
| Roles | `auditor` (opera los casos) y `admin` (lo mismo, más administración). Hoy ningún endpoint es solo de admin; las altas de usuarios y agentes son por CLI |
| Inicio de sesión | Usuario y contraseña → token firmado que dura 8 h (`AUTH_TOKEN_HORAS`) |
| Alta de usuarios | Solo el administrador, por CLI en la EC2 |
| Identidad | `creado_por`, `decidido_por` y el `usuario` de la bitácora salen del token; el front **no** los manda |

## Flujo del front

1. `POST /auth/login` con `{"usuario", "contrasena"}` → `{"token", "expira", "usuario": {...}}`.
2. Guarda el token **en memoria** (o `sessionStorage`), no en `localStorage`.
3. Mándalo en cada petición: `Authorization: Bearer <token>`.
4. Si cualquier respuesta es **401 `no_autenticado`** (expiró o dieron de baja al
   usuario), borra el token y lleva al login.
5. Al recargar la página, `GET /auth/yo` dice si el token sigue sirviendo y quién es.
6. **Cerrar sesión** = borrar el token en el front (el token no se puede anular
   antes de que expire, salvo dando de baja al usuario).

### Reportes en un `<iframe>`

Un iframe no puede mandar el header. Pide primero un enlace temporal:

```ts
const { url } = await api.get(`/casos/${id}/reportes/${v}/enlace`);   // con token
iframe.src = url.startsWith("http") ? url : `/api${url}`;              // S3 o backend
```

El enlace dura 5 minutos y solo sirve para ese reporte; pide uno nuevo cada vez
que lo muestres.

## Cognito (opcional, desde el 23 nov 2026)

Con `COGNITO_REGION`, `COGNITO_USER_POOL_ID` y `COGNITO_CLIENT_ID` la API también acepta tokens
de Amazon Cognito (`Authorization: Bearer <token>`), además del token local.
Detalle y pasos en [../guia-cognito.md](../guia-cognito.md).

- El backend verifica siempre la firma (RS256, JWKS del pool), `iss` y `exp`. Además:
  - **ID token** (lo que manda el front): `aud` = app client y `email_verified`. Se busca por
    **correo** en `audit.usuarios.email` (migración 20). El pool inicia sesión con correo, así que
    el `username` de Cognito es un UUID y no sirve para la bitácora.
  - **Access token**: `client_id` = app client; se busca por `username` en `audit.usuarios.usuario`.
- Cognito solo identifica. Si no hay usuario activo con ese correo (o username) →
  `401 no_autenticado`, con el correo recibido en el mensaje.
- El rol sale de `audit.usuarios`, nunca del token ni de grupos de Cognito.
- `GET /auth/yo` con un token de Cognito actualiza `ultimo_acceso` (no hay `/auth/login`).
- El login local sigue funcionando; las descargas firmadas siguen usando `AUTH_SECRET`.

## Seguridad

| Medida | Detalle |
|---|---|
| Contraseñas | `scrypt` con sal; mínimo 10 caracteres; nunca en claro, ni en logs |
| Token | HMAC-SHA256 con `AUTH_SECRET` (≥ 32 caracteres, solo en el `.env` de la EC2). Cambiar el secreto cierra todas las sesiones |
| Baja | El token de un usuario dado de baja deja de servir en la siguiente petición; el rol vigente es el de la BD |
| Fuerza bruta | 5 intentos fallidos en 5 min bloquean ese usuario 5 min (429). En memoria: se reinicia con el contenedor |
| Enumeración | Usuario inexistente y contraseña incorrecta dan la misma respuesta y tardan lo mismo |
| Sin `AUTH_SECRET` | La API queda **abierta** (solo desarrollo local); `/health` lo dice y el log avisa. Compose exige el secreto |

## Administrar usuarios (en la EC2)

```bash
cd /opt/auditor/app
sudo docker compose exec -it backend python -m backend.usuarios alta --usuario ana --rol auditor --nombre "Ana P."
sudo docker compose exec backend python -m backend.usuarios listar
sudo docker compose exec -it backend python -m backend.usuarios contrasena --usuario ana
sudo docker compose exec backend python -m backend.usuarios rol --usuario ana --rol admin
sudo docker compose exec backend python -m backend.usuarios baja --usuario ana
# Cognito: correo con el que la persona entra (también: alta ... --email ana@correo.com)
sudo docker compose exec backend python -m backend.usuarios correo --usuario ana --email ana@correo.com
```

`alta` y `contrasena` piden la contraseña sin mostrarla (por eso `-it`). La
contraseña inicial se entrega a la persona por privado y ella la cambia con el
administrador.
