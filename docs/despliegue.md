# Guía de despliegue en AWS (Fase 9)

> Esta guía describe opciones de piloto; no se ha desplegado infraestructura
> AWS desde este repositorio. Para compartir solo PostgreSQL con el menor costo,
> usa primero la ruta de EC2 Academy con túnel SSH (o SSM port forwarding si el
> laboratorio lo permite). Tailscale sigue reservado para la conexión backend a
> los agentes Ollama, no para el acceso de compañeros a PostgreSQL.
>
> El backend actual solo expone comprobaciones de salud (`/health` y
> `/health/db`): no hay frontend ni flujo de auditoría/LLM completo en la API.
> Los datos bajo `data/raw/` y los archivos `.env` no se versionan. Este piloto
> sirve para validar infraestructura y conectividad, no para producción ni para
> procesar datos reales sin las aprobaciones y controles correspondientes.

## Ruta recomendada: compartir la base con AWS Academy

La opción mínima es una sola EC2 con PostgreSQL en Docker. Los compañeros
acceden mediante un túnel SSH (o SSM port forwarding cuando esté disponible);
el puerto PostgreSQL permanece enlazado a `127.0.0.1` en la instancia y no se
abre en el grupo de seguridad. No crea ALB, NAT Gateway, RDS, S3 ni frontend.
Tailscale no se usa para la conexión de base de datos de los compañeros: en
esta arquitectura se reserva para que el backend llegue a Ollama en las
laptops, como se explica en la sección 6.

**Esto minimiza el costo, pero no garantiza costo cero.** Los 20 créditos de
AWS Academy pueden tener límites de servicios, región, duración y uso; no
asumas que son 20 USD ni que son aplicables fuera del Learner Lab. Antes de
crear recursos, revisa el saldo exacto, su vencimiento y el comportamiento al
agotar créditos con el instructor/administrador. No cambies a un plan de pago
ni agregues una tarjeta para continuar si no aceptan cargos. Si el crédito no
cubre EC2, EBS o la dirección IPv4, detén el despliegue y usa la base local.

1. **Confirma el presupuesto y acceso.** Entra al portal de Academy/Learner Lab
   y confirma que puedes crear EC2, discos EBS y asignar una IP pública. Anota
   el saldo, la fecha de vencimiento y las reglas de apagado del laboratorio.
   Activa alertas de costo si el entorno las ofrece; una alerta no equivale a
   un límite de gasto.
2. **Crea una sola EC2 en la región permitida.** Usa Linux, el tipo de instancia
   más pequeño permitido que aguante la carga medida y un volumen EBS cifrado.
   La base local observada es de unos 7.1 GiB, así que no selecciones un disco
   menor que los datos, índices, WAL y espacio temporal que realmente requiera
   la restauración. Evita Elastic IP. Un IPv4 público y EBS pueden generar
   cargos, así que confirma su cobertura antes de lanzar.
3. **Limita el grupo de seguridad.** No agregues ingreso TCP 5432 ni 5000. Para
   acceder a la base, permite SSH/22 solo desde las IP públicas actuales de los
   compañeros que la usarán (reglas `/32`) y autentica con claves SSH
   individuales; agrega las claves públicas de los compañeros a
   `/home/ubuntu/.ssh/authorized_keys` y nunca compartas una llave privada. Si
   el Academy Lab permite SSM port forwarding para todos, prefiérelo y no abras
   SSH. La EC2 necesita salida a Internet para instalar paquetes; no crees NAT
   Gateway.
4. **Instala Docker y descarga el proyecto.** Conéctate por SSM o SSH temporal
   desde tu IP autorizada. Instala Docker, Compose y las herramientas necesarias:

   ```bash
   sudo apt-get update
   sudo apt-get install -y docker.io docker-compose-v2 git curl
   sudo systemctl enable --now docker
   ```

   En Ubuntu, el paquete de los repositorios de la distribución se llama
   `docker-compose-v2`; `docker-compose-plugin` corresponde al repositorio apt
   de Docker y puede no estar configurado. Si `docker-compose-v2` tampoco se
   encuentra, habilita el componente `universe` y vuelve a actualizar el índice:

   ```bash
   sudo apt-get install -y software-properties-common
   sudo add-apt-repository universe
   sudo apt-get update
   sudo apt-get install -y docker-compose-v2
   ```

   Si prefieres usar los paquetes oficiales de Docker, configura primero su
   [repositorio apt para Ubuntu](https://docs.docker.com/engine/install/ubuntu/#install-using-the-repository)
   y luego instala `docker-compose-plugin`. Verifica con
   `sudo docker compose version`. Después descarga el proyecto:

   ```bash
   sudo install -d -o ubuntu -g ubuntu -m 755 /opt/auditor
   git clone "URL_DEL_REPOSITORIO" /opt/auditor/app
   ```

   Reemplaza la URL por la del repositorio. El `git clone` deja la rama
   predeterminada seleccionada; si necesitas otra rama o una revisión concreta,
   usa el nombre real en `git -C /opt/auditor/app switch <rama>` o
   `git -C /opt/auditor/app checkout <hash-o-etiqueta>`, no el texto entre
   corchetes. Si GitHub requiere autenticación, no incluyas tokens en la URL o
   el historial; en ese caso prepara un artefacto de despliegue privado.
5. **Configura los secretos.** En la EC2 crea el `.env` desde la plantilla y
   edítalo sin copiar contraseñas a comandos o Git:

   ```bash
   cd /opt/auditor/app
   cp .env.example .env
   chmod 600 .env
   nano .env
   ```

   Edita el archivo como el usuario `ubuntu`, sin `sudo`, porque el repositorio
   y el archivo pertenecen a ese usuario. Cambia todas las contraseñas de
   ejemplo por valores distintos y aleatorios.
   En EC2 fija además `DB_HOST=db` (el backend corre en Docker; `127.0.0.1`
   apuntaría al propio contenedor) y `DB_PORT_HOST=5432` para que el puerto
   del host coincida con el túnel del paso 7.
   `DB_PASSWORD` debe coincidir con `ETL_USER_PASSWORD`; no compartas
   `POSTGRES_PASSWORD`. Elige una contraseña para `AGENT_RO_PASSWORD` y
   establece el modelo del agente solo si la inferencia se configurará. En
   Academy no dependas de Secrets Manager si no está disponible en el
   laboratorio.
6. **Inicia y verifica PostgreSQL.** Inicia Docker Compose:

   ```bash
   cd /opt/auditor/app
   sudo docker compose up -d --build
   sudo docker compose ps
   sudo ss -lntp | grep 5432
   ```

   Confirma que el puerto del host está enlazado solo a `127.0.0.1:5432`, no a
   `0.0.0.0:5432` ni a una interfaz pública.
7. **Conecta cada compañero por túnel SSH.**

   - **Llave privada:** es el archivo `.pem` descargado al crear el key pair de
     EC2; AWS no permite volver a descargarlo. No lo compartas con compañeros.
     Para dar acceso individual, cada compañero genera su propio par de llaves
     con `ssh-keygen` y entrega de forma segura su llave **pública** (`.pub`) al
     administrador. El administrador agrega esa llave pública a
     `/home/ubuntu/.ssh/authorized_keys` en EC2. La ruta privada será la
     ubicación del archivo de ese compañero en su propia computadora, por
     ejemplo `C:\Users\Ana\.ssh\auditor-equipo.pem`.
   - **Usuario EC2:** en la AMI Ubuntu es `ubuntu`. No es el nombre de usuario
     de AWS ni el de PostgreSQL.
   - **IP pública EC2:** en AWS Console abre **EC2 → Instances → selecciona la
     instancia → Details → Public IPv4 address**. Usa esa dirección, no el
     hostname `ip-172-31-...` ni la IPv4 privada `172.31.x.x`. Si el campo está
     vacío, la instancia no tiene IPv4 pública y este comando no funcionará;
     usa SSM port forwarding si Academy lo permite. En el security group, SSH
     (22) debe estar permitido solo desde la IP pública actual del compañero.

   En Windows PowerShell, abre el túnel con los valores reales:

   ```powershell
   ssh -i "$env:USERPROFILE\.ssh\auditor-equipo.pem" -N -L 15432:127.0.0.1:5432 ubuntu@<IP_PUBLICA_EC2>
   ```

   Sustituye la ruta por la ubicación real de la llave privada propia y
   `<IP_PUBLICA_EC2>` por la IPv4 pública mostrada en la consola. En macOS/Linux
   el mismo comando se ejecuta en una terminal, con la ruta local del archivo
   `.pem`. Mantén esa terminal abierta mientras uses la base.

   En DBeaver/pgAdmin configura host `127.0.0.1`, puerto `15432`, base
   `auditor_contrataciones` y usuario `agent_ro` (con la contraseña
   `AGENT_RO_PASSWORD` configurada en el `.env` del servidor). El tráfico va
   dentro del túnel SSH; PostgreSQL no queda directamente expuesto. Cada
   usuario debe cerrar el túnel al terminar. Si la instancia no tiene IP
   pública, usen SSM port forwarding cuando Academy lo permita o una solución
   de acceso privado aprobada; no abran 5432 a Internet.
8. **Da acceso mínimo.** Para consultas usa `agent_ro`; no compartas
   `POSTGRES_PASSWORD`. El rol `agent_ro` solo puede leer `clean` y `rag`.
   Restringe `etl_user` al integrante que cargue datos y rota las contraseñas
   si se comparten por necesidad. No guardes ninguna contraseña en Git,
   mensajes públicos o capturas de pantalla.
9. **Carga los datos.** La vía recomendada es restaurar un respaldo de la base
   local (ver [Subir la base local a EC2](#subir-la-base-local-a-ec2)); evita
   subir los CSV de `data/raw/` y re-ejecutar el ETL completo en la instancia.
   Mantén respaldos cifrados fuera de la instancia y prueba restaurarlos antes
   de depender de la única copia.
10. **Apaga cuando no trabajen.** Detener EC2 reduce el cómputo, pero EBS y
   algunos recursos pueden seguir generando cargos; al volver a iniciarla la
   dirección pública puede cambiar. Confirma la facturación de cada recurso en
   Academy. Al terminar el proyecto, exporta y valida un respaldo y elimina
   explícitamente EC2, volúmenes huérfanos y demás recursos para evitar cargos.

La base solo estará disponible cuando la EC2 esté encendida y los usuarios
autorizados puedan crear el túnel SSH/SSM. La configuración de Tailscale para
conectar el backend con agentes es un flujo separado y no habilita a los
compañeros acceso a PostgreSQL. Si necesitan disponibilidad permanente,
primero estimen los cargos mensuales; no hay una solución de base de datos en
nube, multiusuario y permanentemente disponible que se pueda prometer como
gratuita sin verificar una oferta y sus límites vigentes.

## Subir la base local a EC2

Restaura un respaldo `pg_dump` en formato custom en lugar de recalcular el ETL.
Haz un respaldo de **toda la base**: un dump solo de `staging` (como
`staging.dump`) no incluye `clean` ni `rag`, que son los esquemas que lee
`agent_ro`. Ambos lados usan la imagen `pgvector/pgvector:pg17`; no restaures en
una versión mayor de PostgreSQL distinta sin probarlo.

**Requisitos previos:** EC2 con los pasos 1–6 completados, `docker compose ps`
con `db` en estado `healthy`, y un EBS con espacio para la base restaurada
(~7.1 GiB observados más índices y WAL) **y** una copia del dump. Como
referencia, 30 GiB gp3 suelen bastar; verifica con `df -h` antes de restaurar.

### 1. Crear el respaldo en tu laptop (PowerShell)

No redirijas la salida binaria con `>` en Windows PowerShell 5.1: la convierte a
UTF-16 y corrompe el archivo. Genera el dump dentro del contenedor y cópialo:

```powershell
docker compose exec db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -Z 6 -f /tmp/auditor.dump'
docker compose cp db:/tmp/auditor.dump .\auditor.dump
docker compose exec db rm /tmp/auditor.dump
Get-FileHash .\auditor.dump -Algorithm SHA256
```

Anota el hash. El archivo contiene datos del proyecto: no lo subas a Git (los
`*.dump` están en `.gitignore`), ni a chats o almacenamiento público.

### 2. Copiarlo a la EC2

```powershell
ssh -i "$env:USERPROFILE\.ssh\auditor-equipo.pem" ubuntu@<IP_PUBLICA_EC2> "mkdir -p /opt/auditor/backups && chmod 700 /opt/auditor/backups"
scp -i "$env:USERPROFILE\.ssh\auditor-equipo.pem" .\auditor.dump ubuntu@<IP_PUBLICA_EC2>:/opt/auditor/backups/
```

En la EC2 verifica que el hash coincida (`sha256sum` devuelve minúsculas; la
comparación no distingue mayúsculas):

```bash
sha256sum /opt/auditor/backups/auditor.dump
```

Si `scp` se interrumpe con archivos grandes, reintenta con
`rsync --partial --progress -e "ssh -i <llave>"` desde WSL/macOS/Linux.

### 3. Restaurar en el contenedor

La base de la EC2 debe ser **nueva** (creada por `init/00-init.sql`, que ya
crea los roles `etl_user` y `agent_ro`). Los roles son globales y `pg_dump` no
los incluye; por eso deben existir con los mismos nombres antes de restaurar.

```bash
cd /opt/auditor/app
sudo docker compose cp /opt/auditor/backups/auditor.dump db:/tmp/auditor.dump
sudo docker compose exec db sh -c \
  'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists -j 2 /tmp/auditor.dump'
sudo docker compose exec db rm /tmp/auditor.dump
```

`--clean --if-exists` reemplaza los esquemas vacíos creados por la
inicialización con los del dump, incluidos propietarios y permisos. Es normal
ver algunos avisos (por ejemplo, sobre la extensión o el esquema `public`);
revisa que no haya errores de tablas o datos. **No uses `--clean` sobre una base
de EC2 que ya tenga datos que quieras conservar.**

### 4. Verificar

```bash
sudo docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT pg_size_pretty(pg_database_size(current_database()));" -c "\dn"'
sudo docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "ANALYZE;"'
```

Compara el tamaño y el conteo de tablas clave (por ejemplo,
`SELECT count(*) FROM clean.contratos;`) con la base local. Después prueba el
acceso con el usuario de lectura desde el túnel del paso 7 (DBeaver con
`agent_ro`): debe poder leer `clean` y `rag` y recibir *permission denied* en
`raw`/`staging`. Si `agent_ro` no puede leer `clean`, vuelve a ejecutar los
`GRANT` de `init/00-init.sql` como `postgres`.

Finalmente borra la copia de `/opt/auditor/backups/` si no la usarás como
respaldo, o consérvala cifrada fuera de la instancia: si se termina la EC2, el
volumen y el dump se pierden con ella.

## Guía paso a paso: piloto en AWS

La siguiente alternativa usa ALB/HTTPS y recursos adicionales; **no la sigas
para el objetivo de costo mínimo**. Úsala solo si el proyecto necesita una API
web pública y hay presupuesto aprobado.

### 1. Preparar la cuenta y decidir el alcance

1. Elige la región AWS y confirma que la cuenta tenga MFA, responsables de
   operación y alertas de presupuesto habilitadas.
2. Usa un dominio que controles para HTTPS. Solicita un certificado público en
   AWS Certificate Manager (ACM) **en la misma región del ALB** y completa la
   validación DNS antes de crear el listener HTTPS.
3. Usa el diseño de dimensionamiento de la sección 2 para escoger EC2 y EBS.
   La base local observada ocupa aproximadamente 7.1 GiB; esa cifra no incluye
   crecimiento, backups ni el margen operativo necesario.

### 2. Crear los grupos de seguridad

Crea dos grupos de seguridad en la VPC elegida:

| Grupo | Ingreso | No abrir |
|---|---|---|
| ALB | TCP 443 desde las direcciones cliente autorizadas (o Internet si el acceso público está aprobado) | SSH, 5000 y 5432 |
| EC2 | TCP 80 **solo desde el grupo de seguridad del ALB** | SSH/22, 5000 y PostgreSQL/5432 |

El ALB debe poder salir al puerto 80 de la EC2. Mantén la salida de la EC2
restringida a lo que requieran SSM, la descarga de paquetes/imágenes y los
servicios AWS necesarios. No agregues reglas de ingreso `0.0.0.0/0` para SSH,
PostgreSQL u Ollama.

### 3. Crear el rol IAM de la instancia

1. Crea un rol para EC2 y adjunta `AmazonSSMManagedInstanceCore` para administrar
   la instancia con Systems Manager Session Manager, sin abrir SSH.
2. Crea una política de mínimo privilegio que permita
   `secretsmanager:GetSecretValue` únicamente sobre el secreto del paso 7.
   Si ese secreto usa una clave KMS administrada por el cliente, permite
   `kms:Decrypt` solo sobre esa clave.
3. No configures access keys de IAM en la instancia. No otorgues permisos de S3
   hasta que la aplicación implemente esa integración; si ETL necesita leer
   archivos de un bucket, concédele acceso solo al prefijo correspondiente.

### 4. Crear el ALB y su grupo de destino

1. Crea un Application Load Balancer **internet-facing** en al menos dos
   subredes públicas de distintas zonas de disponibilidad y asígnale el grupo
   de seguridad del ALB.
2. Crea un target group para instancias, protocolo HTTP, puerto 80 y ruta de
   health check `/health/db`. Registra la EC2 después de crearla.
3. Crea el listener HTTPS/443 con el certificado ACM del paso 1. Opcionalmente,
   crea HTTP/80 solo para redirigir a HTTPS.
4. Si tienes dominio, crea en DNS un alias hacia el ALB. No uses la dirección
   IP del ALB como destino permanente.

### 5. Crear la instancia EC2

1. Lanza una AMI Ubuntu Server 24.04 LTS en una subred con salida a Internet,
   asigna el grupo EC2 del paso 2 y el rol IAM del paso 3.
2. Para este piloto puede estar en una subred pública, pero **sin reglas de
   ingreso directas**: la única entrada de aplicación será desde el grupo del
   ALB. Para producción, ubícala en subred privada y configura NAT o endpoints
   VPC necesarios para SSM y las dependencias.
3. Usa almacenamiento EBS cifrado y con capacidad suficiente según las
   mediciones. Protege la instancia contra terminación accidental si conservarás
   la base local.
4. En EC2, confirma que Systems Manager indique que la instancia está
   administrada y abre una sesión de Session Manager. No habilites SSH como
   solución alternativa permanente.

### 6. Instalar Docker y obtener el código

Dentro de la sesión de Session Manager:

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2 git nginx jq curl awscli
sudo systemctl enable --now docker
```

Obtén una revisión identificable del repositorio en `/opt/auditor/app`
(reemplaza el marcador por la URL que corresponda):

```bash
sudo install -d -m 755 /opt/auditor
sudo git clone "URL_DEL_REPOSITORIO" /opt/auditor/app
sudo git -C /opt/auditor/app checkout COMMIT_O_TAG
sudo chown -R ubuntu:ubuntu /opt/auditor/app
cd /opt/auditor/app
```

Reemplaza `URL_DEL_REPOSITORIO` y `COMMIT_O_TAG` por la URL y el commit/tag que
vas a desplegar. Si el repositorio es privado, no pongas un token de GitHub en
la URL ni en el historial del shell. Para un despliegue mantenible, construye y
escanea la imagen en CI, publícala en ECR privado y despliega una etiqueta
inmutable en vez de darle credenciales de GitHub a la instancia.

### 7. Guardar y cargar los secretos

En Secrets Manager, crea un secreto de tipo texto JSON, por ejemplo
`auditor/piloto/compose-env`, con valores generados para este ambiente. Los
valores de contraseña deben ser distintos; `DB_PASSWORD` debe coincidir con
`ETL_USER_PASSWORD`, porque el backend usa ese rol. Usa valores hexadecimales o
compatibles con `.env` para evitar problemas de interpretación de caracteres:

```json
{
  "POSTGRES_USER": "postgres",
  "POSTGRES_PASSWORD": "<secreto-unico>",
  "POSTGRES_DB": "auditor_contrataciones",
  "ETL_USER": "etl_user",
  "ETL_USER_PASSWORD": "<secreto-unico-del-rol-etl>",
  "AGENT_RO_USER": "agent_ro",
  "AGENT_RO_PASSWORD": "<secreto-unico-del-rol-lectura>",
  "DB_HOST": "db",
  "DB_PORT": "5432",
  "DB_NAME": "auditor_contrataciones",
  "DB_USER": "etl_user",
  "DB_PASSWORD": "<el-mismo-valor-de-ETL_USER_PASSWORD>",
  "AGENT_BASE_URL": "http://<IP-o-nombre-tailscale-del-agente>:11434",
  "AGENT_MODEL": "qwen2.5:7b"
}
```

No uses los valores de ejemplo de `.env.example`. En la instancia, crea el
archivo `.env` sin imprimir el contenido en la terminal:

```bash
set -o pipefail
aws secretsmanager get-secret-value \
  --secret-id auditor/piloto/compose-env \
  --query SecretString --output text |
  jq -r 'to_entries[] | "\(.key)=\(.value)"' |
  sudo tee /opt/auditor/app/.env >/dev/null
sudo chmod 600 /opt/auditor/app/.env
```

Si Ollama no está conectado por Tailscale, no invoques funciones de inferencia;
`host.docker.internal` es un valor de desarrollo y no resuelve el agente en AWS.
Sigue la sección 6 para configurar la conectividad privada. Ollama no debe
aceptar conexiones de Internet.

### 8. Iniciar PostgreSQL y el backend

Desde la raíz del repositorio:

```bash
cd /opt/auditor/app
sudo docker compose up -d --build
sudo docker compose ps
sudo docker compose logs --tail=100 db backend
```

En una base nueva, `init/00-init.sql` crea los roles, esquemas y extensiones
iniciales. Aplica una sola vez y en orden los SQL numerados que requiera el
ambiente; no repitas scripts de transformación sobre una base con datos sin
revisar antes su idempotencia:

```bash
for file in etl/sql/*.sql; do
  name=$(basename "$file")
  sudo docker compose exec -T db sh -c \
    "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -v ON_ERROR_STOP=1 -f /opt/etl/sql/$name" \
    || exit 1
done
```

La base persiste en el volumen Docker `postgres_data`. No uses
`docker compose down -v` para detener o actualizar el servicio.

### 9. Poner Nginx entre el ALB y el backend

Compose publica el backend únicamente en `127.0.0.1:5000`; por eso el ALB no
puede conectarse directamente a ese puerto. Nginx en el host recibe el tráfico
del ALB en el puerto 80 y lo reenvía al backend local:

```bash
sudo tee /etc/nginx/sites-available/default >/dev/null <<'EOF'
server {
    listen 80 default_server;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto;
    }
}
EOF
sudo nginx -t
sudo systemctl enable --now nginx
sudo systemctl reload nginx
```

Registra la instancia en el target group. Espera a que aparezca `healthy` y
confirma que el health check usa `/health/db`.

### 10. Verificar el despliegue

Usa el nombre DNS del ALB o el dominio configurado:

```bash
curl -i "https://DOMINIO/health"
curl -i "https://DOMINIO/health/db"
sudo docker compose ps
sudo docker compose logs --tail=100 backend db
```

Se espera HTTP 200 y `{"status":"ok","database":"connected"}` en `/health/db`.
Prueba también que `http://<IP_PUBLICA_EC2>:5000` y PostgreSQL/5432 no sean
accesibles desde fuera, y que solo HTTPS del ALB esté disponible para clientes.
No interpretes una comprobación de salud correcta como prueba de que el ETL,
Ollama, el frontend o el flujo de auditoría estén operativos.

### 11. Cargar datos (opcional y por separado)

El contenedor no carga automáticamente archivos CSV; además, `data/raw/` está
excluido de Git. Antes de transferir datos, confirma autorización, clasificación
y retención. Si se usa S3 para el traslado, mantenlo privado, cifrado y limita
el rol a un prefijo temporal; elimina la copia temporal al terminar. Una vez
que los archivos estén en `/opt/auditor/app/data/raw/`, instala dependencias y
ejecuta primero el modo de validación:

```bash
cd /opt/auditor/app
sudo apt-get install -y python3-venv python3-pip
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
sudo .venv/bin/python etl/run_etl.py --fecha-descarga YYYY-MM-DD --dry-run
```

Sustituye `YYYY-MM-DD` por la fecha real de descarga y, tras revisar la salida,
ejecuta el proceso con `--load-raw` para cargar los CSV y transformar las tablas:

```bash
sudo .venv/bin/python etl/run_etl.py --fecha-descarga YYYY-MM-DD --load-raw
```

Sigue también [README.md](../README.md#etapas-de-etl). Mantén cerrados los
puertos PostgreSQL externos: `etl/db_config.py` resuelve `DB_HOST=db` a
`127.0.0.1` cuando ETL corre fuera de Docker, y Compose ya publica la base solo
en el loopback del host.

### 12. Actualizar, respaldar y detener

- Antes de actualizar, registra la revisión desplegada y crea/verifica un
  respaldo PostgreSQL según la sección 4. Luego actualiza a una revisión
  identificable y ejecuta `sudo docker compose up -d --build`; valida de nuevo
  `/health/db`.
- Para detener servicios sin borrar datos: `sudo docker compose down`.
- Para eliminar el piloto, planifica qué hacer con el volumen, EBS, snapshots,
  secretos, ALB, certificado y recursos facturables. No borres la única copia de
  los datos.

Esta ruta de EC2 única es para pruebas controladas: tiene un punto único de
falla y PostgreSQL comparte la instancia con la aplicación. Antes de producción,
completa los controles y decisiones pendientes de las siguientes secciones,
incluyendo servidor WSGI para Flask, autenticación/autorización, observabilidad,
restauración probada y una estrategia de despliegue/rollback.

## 1. Arquitectura objetivo

- **Acceso web:** auditor → HTTPS → Application Load Balancer (ALB) público con
  certificado TLS de ACM → backend en subred privada. Si el front-end se sirve
  desde el mismo ALB, enrutarlo al servicio correspondiente; no exponer
  directamente el puerto de desarrollo del backend.
- **Aplicación:** backend y, inicialmente, PostgreSQL pueden vivir en la misma
  EC2 en contenedores Docker. La BD solo debe estar en una red privada de Docker,
  sin puerto publicado en el host. La arquitectura futura preferida es migrar
  PostgreSQL a RDS privado si el costo, operación y requisitos del proyecto lo
  permiten.
- **Inferencia:** Ollama corre en las laptops administradas de los auditores;
  la comunicación desde backend hacia Ollama usa Tailscale. No hay fallback
  automático a un proveedor cloud.
- **Reportes y respaldos:** S3 privado con cifrado, roles IAM separados y
  prefijos diferenciados.
- **ETL:** proceso programado o manual separado del servicio web, con rol y
  credenciales de menor privilegio para cargar las tablas necesarias.

No ejecutar `docker compose` de desarrollo como configuración de producción
sin revisar publicación de puertos, secretos, volúmenes, TLS, logging,
actualizaciones y reglas de red.

## 2. Dimensionamiento de EC2 y EBS

### Evidencia disponible

La base PostgreSQL local midió **7,268 MB (aprox. 7.1 GiB)** con
`pg_database_size`. Los objetos más grandes observados fueron `clean.contratos`
(3,785 MB), `staging.contratos` (1,125 MB) y `raw.compranet_historico`
(1,098 MB). Esta cifra es una medición del entorno local que contiene las capas
raw, staging y clean; **no es una estimación del volumen de producción**, una
medición de crecimiento ni una recomendación de instancia.

### Método para seleccionar instancia y volumen

1. Medir el uso real de CPU, memoria, I/O, conexiones y latencia con la carga
   representativa de Fase 7; repetir con ETL y consultas concurrentes. La
   instancia debe reservar memoria para PostgreSQL y el backend además del
   sistema operativo, Docker, cachés y conexiones.
2. Medir cuánto crecen la BD y los índices durante una carga completa y cada
   actualización de fuentes. Definir retención de respaldos y crecimiento
   esperado con el responsable del producto.
3. Calcular el EBS de datos a partir de:

   `datos actuales + crecimiento durante el horizonte de planificación + WAL y temporales + espacio para mantenimiento/restauración + margen operativo`

   Cada término se debe medir o acordar; no asignar porcentajes o capacidades
   como si ya fueran requisitos confirmados. Mantener el sistema operativo y los
   datos separados cuando simplifique expansión, snapshots y recuperación.
4. Elegir familia y tamaño de EC2 según el pico observado de memoria/CPU y las
   pruebas de rendimiento; elegir tipo, capacidad, IOPS y throughput de EBS según
   mediciones de lectura/escritura y latencia. Verificar los límites de la
   instancia antes de fijar el volumen.
5. Repetir pruebas de restauración y carga. Cambiar la clase o capacidad solo
   con datos, ventana de mantenimiento y rollback definidos.

**Pendiente antes de producción:** concurrencia objetivo, volumen de usuarios,
crecimiento de datos, retención, tamaño de las fuentes futuras, RPO/RTO, nivel
de servicio, costo máximo y decisión EC2 con PostgreSQL frente a RDS. La
medición de 7.1 GiB sirve como línea base local, no determina por sí sola el
tamaño de la instancia o del volumen.

## 3. VPC, grupos de seguridad y puertos

La política de red es denegar por defecto y permitir solo el flujo necesario.
Los grupos de seguridad son stateful; la siguiente tabla es el objetivo de
ingreso:

| Recurso | Ingreso permitido | Ingreso que debe permanecer cerrado |
|---|---|---|
| ALB público | TCP 443 desde clientes autorizados o Internet si el producto lo requiere | Administración y PostgreSQL |
| EC2 de aplicación | Puerto del target del ALB únicamente desde el grupo de seguridad del ALB | 5000 desde Internet, 22 público y 5432 público |
| PostgreSQL en la misma EC2 | Sin ingreso desde la VPC; solo red privada de Docker | Puerto publicado en interfaces del host |
| RDS, si se adopta | TCP 5432 únicamente desde el grupo de seguridad de aplicación | Acceso público y cualquier origen general |
| Ollama en laptop | TCP 11434 desde los nodos backend autorizados por Tailscale y el firewall local | Internet, LAN no autorizada y otros agentes |

- No crear una regla `0.0.0.0/0` para SSH o PostgreSQL. La administración de
  EC2 debe hacerse con Systems Manager Session Manager; si no está disponible,
  definir una alternativa privada y temporal con auditoría.
- Para acceso web, terminar TLS en el ALB con certificado ACM y cifrado hacia el
  target según el requisito de seguridad. No publicar directamente el puerto de
  Flask. HTTP no se expone; si se necesita redirección, debe ser solo desde el
  ALB y aprobarse como excepción explícita.
- En el Compose de producción, no mapear `5432` al host. Si PostgreSQL migra a
  RDS, mantenerlo en subredes privadas y restringirlo al grupo de aplicación.
- Mantener rutas, NACLs, reglas de salida y DNS coherentes con Tailscale, S3,
  Secrets Manager, ECR y los servicios de observabilidad utilizados.

## 4. PostgreSQL, respaldos y recuperación

### Política propuesta

- Generar respaldos lógicos con `pg_dump` en formato custom y respaldar también
  la configuración y versiones de extensiones (`pgvector`, `unaccent`) y los
  scripts de migración. El respaldo debe ser consistente y corresponder a una
  versión identificable del esquema.
- Subirlos a un bucket de respaldos separado del bucket de reportes, bajo un
  prefijo no público, por ejemplo `postgres/{ambiente}/{fecha}/`. No incluir
  credenciales en el nombre ni en los logs.
- Cifrar en tránsito y en reposo con SSE-KMS. Usar versionado y una política de
  retención aprobada; restringir la eliminación y la administración de la clave
  a roles separados. Considerar Object Lock solo después de acordar requisitos
  legales y de retención.
- Definir frecuencia de copia, retención, **RPO** y **RTO** con el socio
  formador. Esos valores no están determinados por este diseño. Los snapshots
  EBS son una capa adicional y no sustituyen respaldos lógicos probados.
- Alertar ante respaldo fallido, antigüedad fuera del RPO acordado, falta de
  espacio, errores de restauración o discrepancias en las verificaciones.

### Recuperación

1. Declarar el incidente y preservar el volumen y los respaldos existentes;
   no sobrescribir la única copia recuperable.
2. Provisionar una EC2 o RDS de recuperación en subred privada con controles de
   acceso equivalentes.
3. Recuperar el respaldo más reciente que pase integridad; instalar versiones
   compatibles de PostgreSQL y extensiones, restaurar roles/configuración y
   aplicar migraciones en orden.
4. Verificar salud, conteos acordados, permisos, vistas, índices, RAG, última
   marca de ETL y lectura de metadatos de reportes. La ausencia de un objeto en
   S3 debe detectarse por separado: el backup de PostgreSQL no respalda esos
   objetos.
5. Mantener el sistema restaurado aislado hasta validar con el responsable;
   cambiar el tráfico con un plan de reversión documentado.
6. Ejecutar simulacros periódicos y registrar duración real, fallos y datos
   recuperados para comprobar RPO/RTO.

El rol de respaldo debe poder escribir y verificar sus propios objetos; no debe
tener permisos para leer reportes de auditoría salvo necesidad aprobada. Si
PostgreSQL se mueve a RDS, evaluar backups automáticos/PITR de RDS además de las
exportaciones necesarias para recuperación portable.

## 5. Bucket privado de reportes

- Usar un bucket dedicado por ambiente, con **Block Public Access** habilitado en
  cuenta y bucket, Object Ownership en modo que deshabilite ACLs y cifrado
  SSE-KMS. Exigir TLS mediante política de bucket y denegar carga sin el cifrado
  requerido.
- Convención de objeto:
  `reportes/{caso_id}/{version}.pdf`. Generar o validar `caso_id` y `version` en
  el servidor; rechazar separadores, `..`, caracteres de control y nombres que
  permitan traversal. El cliente no elige la clave arbitrariamente.
- Aplicar tags/metadatos no sensibles. Calcular SHA-256 del archivo y guardar
  `s3_uri`, hash, versión y metadatos en `audit.reportes`; no guardar una URL
  prefirmada como ubicación permanente.
- Flujo de carga: generar el artefacto → calcular hash → subir a S3 → comprobar
  respuesta y metadatos → insertar el registro en PostgreSQL. Si falla el
  registro, limpiar el objeto huérfano de forma controlada o dejarlo para una
  tarea de reconciliación; nunca registrar éxito antes de confirmar la carga.
- Flujo de descarga: autenticar al usuario y autorizar su acceso al caso antes
  de emitir una URL prefirmada HTTPS de corta duración. No registrar la URL en
  bitácoras, analytics ni errores. El bucket no concede lectura pública.
- Definir versionado, retención/borrado y restauración según la política de
  reportes; la baja de un reporte debe auditarse y no saltarse retenciones
  obligatorias.

El rol IAM de aplicación se limita al bucket y prefijo de reportes: cargar
objetos, consultar metadatos y leer solo si el flujo de descarga lo requiere;
`kms:Encrypt`/`kms:GenerateDataKey` y, si aplica, `kms:Decrypt` solo para la
clave KMS del bucket. Limitar recursos, condiciones de cifrado y acciones a lo
estrictamente necesario. El proceso de respaldo usa otro rol y otro prefijo o
bucket.

## 6. Tailscale y acceso de los agentes

El backend es el único iniciador de conexiones a Ollama. Cada agente pertenece
a un usuario/equipo autorizado y acepta solo conexiones TCP al puerto 11434
desde el backend. Las laptops no reciben acceso entre sí ni a PostgreSQL/S3.
Ollama no tiene autenticación: ACL de Tailscale y firewall del host son
controles obligatorios en conjunto; no exponerlo a Internet.

Borrador conceptual de política Tailscale (sustituir el grupo por identidades
administradas; validar con el administrador de la tailnet y su versión de
políticas antes de aplicar):

```json
{
  "groups": {
    "group:network-admins": ["<admin@organizacion.example>"]
  },
  "tagOwners": {
    "tag:backend": ["group:network-admins"],
    "tag:agent": ["group:network-admins"]
  },
  "acls": [
    {
      "action": "accept",
      "src": ["tag:backend"],
      "dst": ["tag:agent:11434"]
    }
  ]
}
```

La regla no autoriza tráfico entre agentes; en Tailscale las conexiones no
permitidas se deniegan. No habilitar reglas generales por grupo que reabran ese
tráfico. Asignar `tag:backend` únicamente a la instancia controlada y `tag:agent`
a equipos registrados; auditar cambios de miembros y etiquetas.

### Cómo llega el contenedor a la red privada

- En desarrollo, `host.docker.internal` resuelve al host local y no es una
  dirección de producción. En AWS, no reutilizar ese valor como nombre del
  agente.
- La propuesta es ejecutar el cliente Tailscale en el host EC2 y resolver el
  agente por su nombre/IP Tailscale autorizado. El backend debe alcanzar esa
  dirección desde su red Docker sin exponer la API de Ollama ni montar la socket
  de administración de Tailscale dentro del contenedor.
- Antes de producción, validar ruta de ida y vuelta, forwarding/firewall del
  host, DNS MagicDNS, puerto permitido y conectividad desde el propio contenedor.
  Si el bridge de Docker no enruta de forma segura, usar un proxy/sidecar de
  salida controlado en la red privada o una integración de red aprobada; no
  solucionar el problema abriendo Tailscale/Ollama a toda la VPC o Internet.
- En cada laptop, enlazar Ollama a una interfaz alcanzable por Tailscale y
  aplicar firewall de Windows/Linux limitado al puerto 11434, interfaz y
  dirección(es) del backend autorizadas. Verificar que reglas preexistentes no
  permitan acceso más amplio.
- Criterio de aceptación: `GET /api/tags` y una generación de prueba funcionan
  desde el backend autorizado; la misma prueba falla desde una laptop no
  autorizada y desde Internet.

## 7. Secretos, IAM y datos sensibles

- No copiar `.env` local a AMI, imagen, artefacto o repositorio de producción.
  Los valores de `.env.example` son marcadores de desarrollo, no secretos
  válidos.
- Guardar contraseñas de PostgreSQL, claves de terceros y material de
  configuración en AWS Secrets Manager (o un almacén aprobado) con cifrado KMS,
  política de acceso por rol y rotación. Inyectar secretos al iniciar el
  servicio; no imprimirlos, incluirlos en excepciones ni exponerlos en endpoints
  de salud.
- Usar IAM instance profile/roles temporales, no access keys estáticas en la
  EC2, contenedores, laptops o archivos. Separar roles de aplicación, respaldo,
  despliegue y administración. Conceder `iam:PassRole` solo al proceso de
  despliegue autorizado.
- Restringir `agent_ro` a lectura de las vistas/tablas necesarias; usar
  credenciales distintas para ETL y administración. Nunca distribuir
  credenciales de base a laptops de inferencia.
- No guardar prompts, respuestas o datos personales en telemetría salvo una
  decisión de privacidad explícita. Filtrar secretos/URLs prefirmadas de logs,
  traces y métricas; definir retención, acceso y eliminación de datos personales.
- Habilitar CloudTrail y logs de auditoría pertinentes; limitar acceso y
  retención de logs. Rotar cualquier secreto si se sospecha exposición.

## 8. Registro de agentes y agente apagado

`audit.agentes` ya define los campos `usuario`, `nombre_tailnet`, `modelo`,
`estado` y `ultima_verificacion`. La tabla es solo DDL por ahora; la API,
autenticación de usuarios, heartbeat y administración del registro no están
implementados.

Diseño del registro:

1. El usuario autenticado registra un equipo autorizado; el servidor vincula el
   usuario de identidad con el nombre/identidad del nodo Tailscale y un modelo
   permitido. No confiar en un `usuario` enviado libremente por el cliente.
2. Guardar estado operativo (`desconocido`, `disponible`, `no_disponible`,
   `deshabilitado`) y actualizar `ultima_verificacion` tras una prueba exitosa.
   Una respuesta de `/api/tags` comprueba disponibilidad/modelo, no identidad
   por sí sola; la identidad se controla con Tailscale.
3. Al iniciar un trabajo, seleccionar solo un agente asociado al usuario/caso,
   habilitado, reciente y con el modelo requerido. Evitar endpoints o IPs
   arbitrarios proporcionados por el usuario.
4. Si el nodo está apagado, suspender la llamada, mostrar al auditor el estado
   pendiente y la acción necesaria (encender/conectar equipo o elegir otro
   agente autorizado). Al vencer el timeout, registrar el motivo y dejar el
   caso en `BLOQUEADO`/pendiente; no simular éxito, perder la solicitud ni
   cambiar silenciosamente a cloud.
5. Aplicar timeout finito y reintentos limitados con backoff solo para errores
   transitorios. Usar idempotencia para evitar duplicar reportes o acciones al
   reintentar. Permitir reanudación explícita cuando el agente vuelva.
6. Auditar alta, cambio de modelo, deshabilitación y verificaciones sin guardar
   credenciales, prompts sensibles ni tokens.

Pendiente definir autenticación/SSO, propietario del registro, varios agentes
por usuario, unicidad de `nombre_tailnet`, vigencia de la verificación y reglas
de revocación. Esas decisiones pueden requerir cambios posteriores a `audit.agentes`.

## 9. Despliegue, operación y criterios de aceptación

Antes de habilitar tráfico:

- fijar región, VPC, subredes, dominio/certificado, roles, claves KMS y
  responsables;
- construir imágenes desde versiones revisadas, escanearlas, almacenarlas en
  ECR privado y desplegar una versión identificable con rollback;
- comprobar solo 443 público, backend accesible solo desde el ALB, PostgreSQL
  sin acceso público y S3 sin acceso público;
- comprobar health checks, métricas/alertas, rotación de logs, capacidad de
  disco, expiración de secretos y alarmas de gasto;
- probar Tailscale desde el contenedor y comprobar que un agente no autorizado
  es rechazado;
- hacer una carga de prueba, un respaldo y una restauración completa en un
  ambiente aislado;
- ejecutar una prueba de descarga con autorización, expiración de URL,
  verificación SHA-256 y bloqueo de acceso anónimo al reporte;
- acordar RPO/RTO, retención, concurrencia, hardware/modelos permitidos y
  procedimiento de respuesta a incidentes.

**No se ha desplegado infraestructura AWS ni se han ejecutado estas pruebas
contra recursos de producción.** La selección final de EC2/EBS, políticas de
retención, RPO/RTO y parámetros de Tailscale queda sujeta a medición y aprobación.
