# MesaFácil

Aplicación web para gestionar reservas de mesas de un restaurante de Managua,
desarrollada para la asignatura de Diseño de Sistemas.

## Estado actual

- Modelos `Mesa`, `Cliente` y `Reserva` con relaciones protegidas, validaciones y restricciones en PostgreSQL.
- Turnos independientes de una hora, desde las 12:00 hasta las 21:00.
- Servicios de disponibilidad, registro, modificación, reprogramación y cambios de estado.
- Registro atómico de cliente y reserva, sin reutilización automática de clientes por teléfono.
- Asignación por menor capacidad suficiente y desempate por identificador.
- Bloqueos transaccionales, unicidad de reservas activas por turno y cinco intentos ante colisiones reales del código.
- Correcciones de contacto con copy-on-write para clientes compartidos.
- Django Admin: gestión de mesas y clientes y edición de reservas mediante servicios.
- Pantalla pública de consulta, selección de mesa, registro y confirmación.
- 115 pruebas funcionales y concurrentes del dominio y servicios sobre PostgreSQL.
- Ejecución nativa con PostgreSQL en Docker y ejecución completamente contenerizada.
- Workflow CI/CD definido en `.github/workflows/ci-cd.yml`; su activación y
  verificación en GitHub, GHCR y Render continúan pendientes.

Continúan pendientes las correcciones de permisos, presentación de errores y
temas Light/Dark/Auto del Admin, ampliar la cobertura HTTP del flujo público y
del Admin, evaluar veinte usuarios simultáneos y desplegar en Render.
No se envían correos ni SMS. Un resultado satisfactorio de las pruebas actuales
no significa que esos pendientes estén resueltos.

## Arquitectura y tecnologías

Monolito modular cliente-servidor con el patrón MVT de Django. `reservas`
contiene el dominio y los servicios; `config` contiene la configuración.
No hay frontend independiente ni API REST.

| Tecnología | Uso |
|---|---|
| Python 3.13 y Django 5.2 LTS | Aplicación y Django Templates |
| PostgreSQL 17 y Psycopg 3 | Persistencia e integridad transaccional |
| Docker Compose | Servicios locales db y web |
| Gunicorn | Servidor WSGI dentro del contenedor Linux |
| WhiteNoise | Estáticos, incluidos los de Admin |
| Bootstrap 5.3 | Interfaz pública |

La imagen usa `python:3.13.17-slim-bookworm`, dependencias fijadas en
`requirements.txt` y el usuario sin privilegios `app` (UID 10001).

```text
config/                    Configuración y entrada WSGI
reservas/                  Modelos, servicios y Admin
reservas/tests/            Pruebas de modelos, servicios y concurrencia
reservas/migrations/       Migraciones del dominio
docker/entrypoint.py       Preparación de arranque y servidor
Dockerfile                 Imagen reutilizable de la aplicación
.dockerignore              Exclusiones de construcción
docker-compose.yml         Servicios locales db y web
.env.example               Variables de ejemplo
docs/                      Requisitos y diagrama conceptual
```

## Variables de entorno

Necesitas Docker Desktop iniciado con contenedores Linux y Docker Compose.
El flujo nativo requiere además Python 3.13 y un entorno virtual.

En una copia nueva del repositorio:

```cmd
copy .env.example .env
```

Si `.env` ya existe, agrega las variables faltantes sin sobrescribir sus valores.
Reemplaza los placeholders localmente; no publiques `.env` ni claves reales.

| Variable | Uso |
|---|---|
| `SECRET_KEY` | Clave aleatoria obligatoria, sin respaldo |
| `DEBUG` | Booleano explícito; predeterminado `False` |
| `ALLOWED_HOSTS` | Hosts separados por comas, sin esquema ni puerto |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Inicialización de PostgreSQL local |
| `POSTGRES_PORT` | Puerto publicado en Windows, normalmente `5432` |
| `DATABASE_URL` | Conexión nativa a `localhost:POSTGRES_PORT` |
| `DATABASE_URL_DOCKER` | Compose: mismas credenciales y base, host `db`, puerto `5432` |
| `WEB_CONCURRENCY` | Procesos Gunicorn; predeterminado `2` |

Ejemplo sin credenciales reales:

```env
SECRET_KEY=replace_with_generated_local_secret_key
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1
WEB_CONCURRENCY=2
POSTGRES_DB=mesafacil
POSTGRES_USER=mesafacil_user
POSTGRES_PASSWORD=change_me
POSTGRES_PORT=5432
DATABASE_URL=postgresql://mesafacil_user:change_me@localhost:5432/mesafacil
DATABASE_URL_DOCKER=postgresql://mesafacil_user:change_me@db:5432/mesafacil
```

Dentro de `web`, `localhost` es el propio contenedor. Compose inyecta
`DATABASE_URL_DOCKER` como `DATABASE_URL`; Django nativo conserva su URL local.
Codifica los caracteres reservados de usuario y contraseña al incluirlos en
las URLs. Ambas deben coincidir con las credenciales de la base existente.
La conexión usa una espera máxima de cinco segundos por intento, salvo que la
URL indique otro `connect_timeout`. Si `localhost` tarda por la resolución IPv6
en Windows, usa `127.0.0.1` en la URL nativa.

Genera una clave con el entorno virtual y Django instalados:

```cmd
python -B -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

O utiliza la imagen, sin arrancar Django ni la base:

```cmd
docker compose build web
docker compose run --rm --no-deps web python -B -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Copia el resultado únicamente en `.env`, entre comillas simples para conservar
caracteres especiales. `python-dotenv` mantiene el flujo local; las variables
ya presentes en el proceso tienen prioridad.

## Flujo completamente contenerizado

Después de configurar `.env` con `DEBUG=False`:

```cmd
docker compose config --quiet
docker compose up --build
```

Para segundo plano:

```cmd
docker compose up --build -d
docker compose ps
```

Compose espera a que PostgreSQL esté saludable. `web` aplica las migraciones
existentes, ejecuta `collectstatic` y arranca Gunicorn. Si la preparación falla,
el servidor no arranca. No se generan migraciones ni superusuarios automáticamente.

Panel: **http://127.0.0.1:8000/admin/**.
Pantalla pública: **http://127.0.0.1:8000/**.

Con `web` iniciado:

```cmd
docker compose exec web python manage.py migrate --noinput
docker compose exec web python manage.py showmigrations reservas
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py collectstatic --noinput
docker compose exec web python manage.py check
docker compose exec web python manage.py makemigrations --check
docker compose exec web python manage.py test reservas
docker compose exec web id
```

Las pruebas crean y eliminan una base de pruebas independiente. El usuario
PostgreSQL local debe poder crearla; la concurrencia se prueba sobre PostgreSQL,
sin sustituirlo por SQLite.

Para un comando sin tener `web` iniciado:

```cmd
docker compose run --rm web python manage.py check
```

Los comandos explícitos de gestión omiten la preparación del servidor: no
ejecutan migraciones ni `collectstatic` automáticamente.

Registros y detención:

```cmd
docker compose logs -f web
docker compose logs -f db
docker compose stop
docker compose down
```

`stop` detiene; `down` elimina contenedores y red, conservando el volumen nombrado
`postgres_data`. No uses `down -v` para detener normalmente: eliminaría sus datos.
Mantén el mismo nombre de proyecto Compose para reutilizar el volumen existente.
Cambiar las variables de inicialización no cambia las credenciales de una base
ya inicializada.

Los puertos se publican únicamente en `127.0.0.1`. No se monta código ni hay
recarga automática: después de cambiar código vuelve a ejecutar
`docker compose up --build -d`.

## Flujo nativo: Django local y PostgreSQL en Docker

Compose sigue permitiendo levantar únicamente la base:

```cmd
docker compose up -d db
```

Detén `web` si necesitas reutilizar su puerto 8000:

```cmd
docker compose stop web
```

En CMD, crea y activa el entorno virtual si aún no existe:

```cmd
py -V:3.13 -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput
python manage.py runserver --nostatic
```

`runserver --nostatic` deja que WhiteNoise entregue los estáticos recogidos,
también con `DEBUG=False`. Gunicorn se ejecuta en Linux dentro del contenedor;
Windows conserva el servidor de desarrollo nativo. Solo crea el superusuario
si hace falta: ambos flujos comparten los datos de PostgreSQL.

```cmd
python manage.py check
python manage.py makemigrations --check
python manage.py test reservas
```

## CI/CD: GitHub Actions, GHCR y Render

El archivo `.github/workflows/ci-cd.yml` define dos jobs. Todavía no se ha
ejecutado ni configurado en servicios externos como parte de este incremento.

| Evento | Build and test | Publicación y Deploy Hook |
|---|---|---|
| Pull request dirigida a `main`, incluidos forks | Sí | No |
| Push a `main`, incluidos merges | Sí | Solo después de aprobar CI |
| Push a otra rama | No se dispara | No |

No se incluye `workflow_dispatch` ni se usa `pull_request_target`.

### Construcción y pruebas

El primer job construye una sola imagen y utiliza contenedores en la red
temporal `mesafacil-ci`, sin Compose, `.env` ni datos locales. PostgreSQL 17
recibe una contraseña aleatoria; la clave Django y la URL temporal se generan
en ejecución y se enmascaran antes de usarlas. No se incorporan a la imagen.

Después de esperar la salud de PostgreSQL, el job ejecuta dentro de la imagen:

```text
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --noinput
python manage.py migrate --check
python manage.py collectstatic --noinput
python manage.py test reservas
```

Las conexiones independientes de las pruebas concurrentes utilizan esa misma
base temporal. Después arranca Gunicorn con el entrypoint real y `DEBUG=False`:
comprueba HTTP 200 en `/` y `/admin/login/`, el CSS de Admin servido por WhiteNoise
con gzip y caché inmutable, y el usuario no privilegiado. Es un smoke test;
no sustituye las pruebas funcionales de todos los formularios ni las visuales.

Ante fallos se muestran los logs de los contenedores de validación, aplicación
y PostgreSQL. La limpieza se programa con `always()`, incluso cuando falla CI.
La eliminación afecta únicamente a contenedores temporales del runner.

### Imagen probada y publicación

Solo para push a `main`, la imagen aprobada se guarda con `docker save` y se
transfiere comprimida como artefacto de un día de retención. El segundo job
utiliza `docker load` y compara su ID con el producido por el primer job.
No reconstruye la imagen ni copia el sistema de archivos de un contenedor en
ejecución. Si la identidad no coincide, no inicia sesión ni publica.

El job de CI solo tiene `contents: read`. El segundo añade `packages: write`
y usa `GITHUB_TOKEN`, sin PAT de publicación. Publica en minúsculas:

```text
ghcr.io/angle931/mesafacil:sha-<SHA completo del commit>
ghcr.io/angle931/mesafacil:latest
```

El tag SHA conserva la referencia del commit aprobado; los tags de un registro
son técnicamente mutables, por lo que otros publicadores no deben sobrescribirlos.

### Concurrencia y orden de despliegue

Las PR cancelan ejecuciones anteriores de la misma PR. Las ejecuciones de
`main` comparten un grupo y no cancelan la ejecución activa. GitHub puede
reemplazar ejecuciones pendientes cuando se acumulan pushes; una ejecución
cancelada no se considera aprobada y no publica.

Como la cola no garantiza orden cronológico, la imagen incluye la etiqueta
`io.mesafacil.ci.run-number`. Antes de promover `latest`, el workflow compara
el número publicado con `GITHUB_RUN_NUMBER`. Una ejecución antigua conserva
su tag SHA, pero no retrocede `latest` ni invoca el hook.

La primera publicación admite que `latest` todavía no exista. Un error de red,
autenticación o una etiqueta de orden ausente no se trata como primera
publicación: se detiene la promoción. Si ya existe una imagen sin esa etiqueta,
o se reinicia la numeración del workflow, habrá que revisar la transición
manualmente antes de promover. Mantener un único workflow publicador de `latest`.

### Configuración manual posterior en GitHub y GHCR

Estos pasos no se ejecutan automáticamente al añadir el archivo:

1. Verificar las versiones de las acciones y fijarlas por SHA inmutable antes
   de activar CD. Las referencias actuales son tags de versiones explícitas;
   no se resolvieron ni descargaron desde GitHub en este incremento.
2. Revisar y fusionar el workflow. La PR solo construirá y probará; el push a
   `main` habilitará el job de publicación.
3. Permitir a `GITHUB_TOKEN` publicar paquetes y confirmar que el paquete esté
   asociado con este repositorio y permita el acceso de sus Actions.
4. Elegir la visibilidad de `ghcr.io/angle931/mesafacil`. Un paquete público
   simplifica la descarga desde Render. Si es privado, configurar en Render
   credenciales de lectura del registro; no usar un PAT para publicar desde CI.
5. Guardar el Deploy Hook solo como el secret `RENDER_DEPLOY_HOOK_URL`. El hook
   tiene capacidad de despliegue: no copiarlo a archivos, imágenes ni logs.
6. Proteger `main` exigiendo la comprobación **Build and test**, revisión y sin
   push forzado. Añadir el workflow no configura esa protección por sí mismo.

La publicación y el hook no son atómicos. Si el hook falta o falla después de
publicar, el job falla pero las imágenes ya publicadas permanecen disponibles.

## Despliegue posterior en Render

La imagen excluye `.env`, `.venv`, Git y datos de PostgreSQL. La construcción no
necesita credenciales de la aplicación. Los estáticos se recogen al arrancar
con las variables de ejecución; son regenerables y no requieren volumen.

Crear un servicio mediante **Existing Image**, con
`ghcr.io/angle931/mesafacil:latest`; no desplegar directamente desde el repositorio.
Conservar el comando predeterminado de la imagen (`serve`). Configurar:

| Variable | Valor en Render |
|---|---|
| `DATABASE_URL` | URL de PostgreSQL administrado y sus opciones TLS |
| `SECRET_KEY` | Clave propia de producción |
| `DEBUG` | `False` |
| `ALLOWED_HOSTS` | Dominio del servicio, sin esquema ni puerto |
| `PORT` | Valor proporcionado por Render, o configurado en el servicio |
| `RUN_MIGRATIONS` | `true` para el MVP de una instancia; ver limitación siguiente |
| `WEB_CONCURRENCY` | Opcional; el entrypoint usa `2` por defecto |

El entrypoint ejecuta migraciones cuando `RUN_MIGRATIONS=true`, después
`collectstatic` y finalmente Gunicorn. La imagen mantiene el valor predeterminado
`false`; se activa explícitamente en Compose local o en el servicio Render.
Para varias instancias o despliegues superpuestos, coordinar las migraciones
por separado en vez de ejecutarlas desde cada instancia.

El workflow invoca el Deploy Hook solo después de promover `latest`. No
comprueba la finalización del despliegue. Revisar su resultado en Render y,
cuando esté disponible, configurar la política de espera para evitar
despliegues superpuestos. La serialización en GitHub ordena las publicaciones
y las solicitudes; no controla por sí sola toda la ejecución interna de Render.

- Usar este Dockerfile o la imagen resultante y PostgreSQL administrado.
- Gunicorn escucha en `0.0.0.0` y respeta `PORT` (8000 por defecto).
- Verificar HTTPS, proxy, cookies seguras y `check --deploy` antes de publicar.

No hace falta una ruta nueva de salud para los smoke tests de este incremento.
No se añade `render.yaml`, Nginx, Redis ni una dependencia. El entorno local
y sus contenedores y volúmenes no son utilizados por el workflow.

### Rollback

Seleccionar manualmente en Render una imagen previamente aprobada:

```text
ghcr.io/angle931/mesafacil:sha-<commit-anterior>
```

No retroceder `latest`. Coordinar o pausar nuevas solicitudes de CD mientras
se revisa el rollback; antes de retomar CD, restaurar la configuración del
servicio a `ghcr.io/angle931/mesafacil:latest`. El hook despliega la imagen
configurada en Render, no cambia automáticamente un servicio fijado a un SHA.
Retroceder la imagen no revierte migraciones ni datos: comprobar compatibilidad
del código anterior con el esquema actual.

### Límites y verificación pendiente

Los artefactos de imagen consumen almacenamiento y transferencia; las
construcciones y pruebas consumen minutos de Actions. Los planes gratuitos
pueden limitar memoria, disponibilidad y persistencia de la base de datos.
Comprobar las cuotas y condiciones vigentes antes de activar el despliegue.
Este incremento no crea secrets, publica imágenes ni ejecuta hooks; la primera
ejecución real de Actions y de Render continúa pendiente.

## Documentación

- [Requisitos funcionales y reglas de negocio](docs/requirements.md).
- [Diagrama de clases](docs/diagrams/class-diagram.md).
- [Instrucciones de trabajo](AGENTS.md).
