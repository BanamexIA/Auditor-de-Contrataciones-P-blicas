# Diseño de despliegue (Fase 9)

> Diseño objetivo, no implementado. El repositorio actual es un entorno de
> desarrollo local: `docker-compose.yml` levanta `db` y `backend`, publica sus
> puertos solo en `127.0.0.1` y conserva PostgreSQL en un volumen Docker. Este
> documento describe la arquitectura propuesta para AWS; no implica que existan
> una cuenta, VPC, EC2, bucket, roles IAM, dominio o configuración de Tailscale
> de producción.

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
