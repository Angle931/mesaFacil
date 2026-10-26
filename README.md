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
- Django Admin: gestión de mesas y clientes; reservas únicamente para consulta.
- 115 pruebas funcionales y concurrentes del dominio y servicios sobre PostgreSQL.
- Ejecución nativa con PostgreSQL en Docker y ejecución completamente contenerizada.

Continúan pendientes la escritura de reservas desde Admin, el flujo público,
sus formularios, vistas y plantillas, la evaluación con veinte usuarios
simultáneos y el despliegue en Render. No se envían correos ni SMS.

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
| Bootstrap 5.3 | Interfaz pública planificada |

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

Panel: **http://127.0.0.1:8000/admin/**. La pantalla pública en `/` todavía no
está implementada; esa ruta no sirve como comprobación de funcionamiento.

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

## Preparación futura para Render

La imagen excluye `.env`, `.venv`, Git y datos de PostgreSQL. La construcción no
necesita credenciales de la aplicación. Los estáticos se recogen al arrancar
con las variables de ejecución; son regenerables y no requieren volumen.

Para el despliegue posterior:

- Usar este Dockerfile o la imagen resultante y PostgreSQL administrado.
- Definir `DATABASE_URL` administrada, una `SECRET_KEY` propia, `DEBUG=False`
  y `ALLOWED_HOSTS` con el dominio del servicio.
- Gunicorn escucha en `0.0.0.0` y respeta `PORT` (8000 por defecto).
- La imagen tiene `RUN_MIGRATIONS=false` por defecto. Compose local lo activa
  explícitamente. En Render las migraciones deben coordinarse antes del
  despliegue según las capacidades del plan contratado.
- Verificar HTTPS, proxy, cookies seguras y `check --deploy` antes de publicar.

Este incremento no configura ni ejecuta un despliegue, ni agrega `render.yaml`,
Nginx, Redis o servicios adicionales.

## Documentación

- [Requisitos funcionales y reglas de negocio](docs/requirements.md).
- [Diagrama de clases](docs/diagrams/class-diagram.md).
- [Instrucciones de trabajo](AGENTS.md).
