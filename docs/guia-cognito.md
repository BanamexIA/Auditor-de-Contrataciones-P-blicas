# Guía: inicio de sesión con Amazon Cognito

**Para:** quien integre Cognito en el front y el backend. Incluye al final un prompt para darle
contexto a una IA de código.

## Estado (23 nov 2026): implementado en la rama `cognito`

El backend (pasos 2) y el front (paso 3) ya están hechos; falta configurar el pool y la EC2.

**1. En la consola de Cognito, app client `6aho8eblqksfo6rp0ugavt02g`:**
- *Allowed callback URLs* y *Allowed sign-out URLs*: `http://localhost:5173/` (con la barra final).
  Cuando el front tenga otra dirección, agregarla también.
- *OAuth grant types*: Authorization code. *Scopes*: al menos `openid` y `email`.

**2. En el `.env` de la EC2** (son identificadores públicos, no secretos) y reconstruir el backend:

```
COGNITO_REGION=us-east-1
COGNITO_USER_POOL_ID=us-east-1_PxxQF4rnG
COGNITO_CLIENT_ID=6aho8eblqksfo6rp0ugavt02g
COGNITO_DOMINIO=https://us-east-1pxxqf4rng.auth.us-east-1.amazoncognito.com
```

**3. Dar de alta a cada persona en el sistema con su correo.** El pool inicia sesión con correo,
así que el *username* de Cognito es un identificador interno (UUID). El backend enlaza por
**correo verificado** (ID token) con la columna `email` de `audit.usuarios` (migración 20), y la
bitácora sigue mostrando el nombre de usuario legible. En la EC2:

```bash
# Una vez: la columna email
sudo docker compose exec -T db sh -c 'psql -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /opt/etl/sql/20_usuarios_email.sql' < /dev/null
# Usuario nuevo (pide una contraseña local de respaldo)
sudo docker compose exec -it backend python -m backend.usuarios alta --usuario ana --rol auditor --email ana@correo.com
# Usuario que ya existía
sudo docker compose exec backend python -m backend.usuarios correo --usuario emiliano --email emiliano@correo.com < /dev/null
```

El correo debe ser el mismo con el que la persona está en Cognito y estar **verificado** allá.
Si alguien entra sin estar registrado, el front muestra el correo que hay que dar de alta.

El front no necesita configuración: lee el pool de `GET /health`.

## Decisión de diseño (no cambiarla sin hablar con backend)

| Pieza | Responsabilidad |
|---|---|
| **Cognito** | *Quién eres*: usuario, contraseña, MFA, recuperación de cuenta. Emite el token (JWT). |
| **Backend (Flask)** | **Verifica la firma del token de Cognito en cada petición.** Sin esto, cualquiera podría llamar a la API. |
| **`audit.usuarios`** (Postgres) | *Qué puedes hacer*: rol (`auditor` / `admin`) y si estás activo. Si alguien se da de baja aquí, pierde el acceso en la siguiente petición aunque su token de Cognito siga vigente. |
| **Login actual** (`POST /auth/login`) | Se queda como respaldo para desarrollo local y pruebas. |

Se enlazan por el nombre de usuario: el `username` de Cognito debe ser igual al `usuario` de
`audit.usuarios` (minúsculas, `^[a-z0-9][a-z0-9._-]{1,39}$`). La bitácora y las decisiones siguen
registrando ese nombre, así que nada más cambia.

## Paso 0 — Verificar que AWS Academy lo permite (15 min)

Antes de escribir código, en la consola de la cuenta del laboratorio:

1. Cognito → *Create user pool*. Si da error de permisos, **paren aquí** y avisen: Learner Lab
   restringe algunos servicios y el plan B es quedarse con el login actual.
2. Recuerden que el pool vive en la cuenta: si la cuenta se vuelve a migrar, hay que recrearlo.
   Por eso el paso 1 queda como script.

## Paso 1 — Crear el User Pool (script con AWS CLI)

Guardar como `deploy/cognito.sh` para poder recrearlo:

- **User pool:** inicio de sesión con *username*, sin autorregistro (solo el admin crea
  usuarios), política de contraseña de 12+ caracteres, MFA opcional (TOTP).
- **App client:** *public client* (sin secreto: el front corre en el navegador), flujo
  **Authorization Code con PKCE**, *callback URL* `http://localhost:5173/` (y la del servidor
  cuando exista), *sign-out URL* la misma, *scopes* `openid profile`.
- **Dominio** del Hosted UI / Managed Login (prefijo de Cognito, p. ej. `auditor-banamexia`).
- Anotar: `REGION`, `USER_POOL_ID`, `CLIENT_ID`, `DOMINIO`.

Crear cada usuario en Cognito **y** en `audit.usuarios` con el mismo nombre:

```bash
aws cognito-idp admin-create-user --user-pool-id $USER_POOL_ID --username ana --user-attributes Name=email,Value=...
sudo docker compose exec backend python -m backend.usuarios alta --usuario ana --rol auditor   # en la EC2
```

## Paso 2 — Backend: aceptar tokens de Cognito

Archivo: `backend/usuarios/auth.py`, función `_autenticar()`.

- Nueva configuración por variables de entorno: `COGNITO_REGION`, `COGNITO_USER_POOL_ID`,
  `COGNITO_CLIENT_ID` (agregarlas a `docker-compose.yml` y `.env.example`). Si no están, todo
  funciona como hoy.
- *(Implementado: el front manda el **ID token** y se enlaza por correo — ver «Estado». Lo de
  abajo describe el diseño original con access token, que también se acepta.)*
- Si el token es un JWT de Cognito (3 partes separadas por punto), verificarlo con **PyJWT**
  (`PyJWT[crypto]`, agregar a `backend/requirements.txt`) y `PyJWKClient` sobre
  `https://cognito-idp.{region}.amazonaws.com/{pool}/.well-known/jwks.json`:
  - algoritmo **RS256** únicamente;
  - `iss` = `https://cognito-idp.{region}.amazonaws.com/{pool}`;
  - `token_use` = `access` y `client_id` = `COGNITO_CLIENT_ID` (el *access token* no trae `aud`);
  - `exp` vigente (PyJWT lo revisa).
- Con el token válido, tomar el claim `username`, pasarlo a minúsculas y buscarlo con
  `cfg.repo.activo(username)`. Si no existe o está inactivo → `401 no_autenticado`
  ("Tu usuario no está dado de alta en el sistema"). Si existe → `g.usuario = fila`, igual que hoy.
- Si el token no es de Cognito, seguir con `leer_token` (token local) como hoy.
- **No** confiar en grupos de Cognito para el rol: el rol sale de `audit.usuarios`.
- Las descargas firmadas (`/enlace`) siguen usando `AUTH_SECRET`: no se tocan.
- `GET /health` debe informar el modo, p. ej. `{"auth": "activa", "cognito": {"region", "user_pool_id", "client_id", "dominio"}}`
  (son datos públicos) para que el front sepa a dónde redirigir.
- Pruebas en `tests/test_auth.py`: generar un par de llaves RSA en la prueba, firmar tokens
  falsos y simular el JWKS. Casos: válido, firma inválida, `client_id` distinto, `token_use=id`,
  vencido, usuario no dado de alta, usuario dado de baja.
- Documentar en `docs/contratos/autenticacion.md` y `docs/api.md`.

## Paso 3 — Front: login con el Hosted UI

- Librerías: `oidc-client-ts` y `react-oidc-context` (flujo Authorization Code + PKCE, sin secreto).
  No usar Amplify completo: es mucho más pesado para lo que se necesita.
- `src/features/auth/Login.tsx`: si `/health` trae `cognito`, mostrar un botón
  «Entrar con la cuenta del equipo» que redirige al Hosted UI; si no, el formulario actual.
- Después del *callback*, guardar el **access token** con `session.set(...)` de
  `src/api/client.ts` (sessionStorage, como hoy). **No** usar localStorage para tokens.
- `client.ts` ya manda `Authorization: Bearer <token>` y vuelve al login en un 401: no cambia.
- Renovación: `automaticSilentRenew` de oidc-client-ts, o simplemente volver al login al expirar.
- «Salir» debe cerrar la sesión también en Cognito (`signoutRedirect`), no solo borrar el token.
- Configuración en `.env.local` solo si no se lee de `/health`: `VITE_COGNITO_AUTHORITY`,
  `VITE_COGNITO_CLIENT_ID`, `VITE_COGNITO_DOMAIN`.

## Paso 4 — Probar

1. Usuario en Cognito y en `audit.usuarios`: entra, pregunta, decide una señal → la bitácora
   muestra su nombre.
2. Usuario en Cognito pero **no** en `audit.usuarios`: el backend responde 401 con mensaje claro.
3. `python -m backend.usuarios baja --usuario X` con la sesión abierta: la siguiente petición da 401.
4. Token alterado a mano o de otro pool: 401.
5. Sin variables de Cognito (desarrollo local): el login actual sigue funcionando.

## Lo que NO hay que hacer

- Validar el token solo en el front.
- Decidir el rol con grupos de Cognito o con datos del token.
- Guardar el token en localStorage o en el código.
- Habilitar autorregistro en el pool.
- Romper el login local: lo usan las pruebas y el desarrollo sin AWS.

---

## Prompt para la IA de código

Copiar tal cual, desde la raya hasta el final:

---

Estoy en el repo «Auditor de Contrataciones Públicas» (proyecto escolar con Banamex). Backend en
**Flask** (`backend/`), front en **React + TypeScript + Vite** (`frontend/`), Postgres, despliegue
en una EC2 de AWS Academy con Docker Compose. Quiero agregar **Amazon Cognito** como inicio de
sesión, sin romper lo que ya existe.

Lee primero: `docs/guia-cognito.md` (esta guía, contiene las decisiones), `backend/usuarios/auth.py`,
`backend/usuarios/seguridad.py`, `backend/usuarios/repositorio.py`, `tests/test_auth.py`,
`docs/contratos/autenticacion.md`, `frontend/src/api/client.ts`, `frontend/src/api/auditor.ts`,
`frontend/src/features/auth/Login.tsx` y `frontend/src/App.tsx`.

Cómo funciona hoy: `POST /auth/login` emite un token HMAC propio; `_autenticar()` (un
`before_request`) lo valida en cada petición, busca al usuario con `repo.activo(...)` en
`audit.usuarios` y pone `g.usuario`; `usuario_actual()` alimenta la bitácora y las decisiones.
Los errores de la API tienen la forma `{"error": {"codigo", "mensaje"}}`.

Reglas que no se negocian:
1. El backend verifica la firma de los tokens de Cognito (RS256, JWKS del pool, `iss`,
   `token_use == "access"`, `client_id`, `exp`) con PyJWT. Nada de validar solo en el front.
2. Cognito solo identifica. El rol y si el usuario está activo salen de `audit.usuarios`
   (enlazado por `username` en minúsculas). Un usuario de Cognito que no esté en esa tabla recibe 401.
3. Si no están `COGNITO_REGION`, `COGNITO_USER_POOL_ID` y `COGNITO_CLIENT_ID`, todo funciona
   exactamente como hoy (login local). El login local no se elimina.
4. En el front: Authorization Code + PKCE con `oidc-client-ts` / `react-oidc-context`, token en
   sessionStorage mediante `session.set` de `client.ts`, cierre de sesión también en Cognito.
5. Todo el texto visible y los comentarios en español; los mensajes de error siguen el formato
   del backend.
6. Agrega pruebas (`tests/test_auth.py`) con llaves RSA generadas en la prueba y JWKS simulado:
   token válido, firma inválida, otro `client_id`, `token_use` = `id`, vencido, usuario no dado
   de alta, usuario dado de baja. Todas las pruebas existentes deben seguir pasando
   (`python -m pytest -q tests`) y el front debe compilar (`npm run build` en `frontend/`).
7. Actualiza `docs/contratos/autenticacion.md`, `docs/api.md`, `.env.example`,
   `docker-compose.yml` y `backend/requirements.txt`.
8. No hagas commits; deja los cambios listos para revisión.

Trabaja por partes: primero el backend con sus pruebas, luego el front. Antes de escribir código,
dime qué archivos vas a tocar y cómo vas a probarlo.
