# MesaFácil

MesaFácil es una aplicación web orientada a la gestión de reservas de mesas para restaurantes. El proyecto busca facilitar el registro, consulta y administración de reservas mediante una interfaz sencilla y un panel administrativo.

Este repositorio contiene el entorno inicial del proyecto, desarrollado como parte de la asignatura de Diseño de Sistemas.

## Estado actual

Actualmente, el proyecto cuenta con:

- Proyecto base en Django.
- Aplicación principal `reservas`.
- Base de datos PostgreSQL ejecutándose en Docker.
- Conexión entre Django y PostgreSQL.
- Migraciones iniciales aplicadas.
- Panel administrativo de Django habilitado.
- Configuración mediante variables de entorno.
- Repositorio publicado en GitHub.

Los modelos del dominio, reglas de negocio e interfaces para la gestión de reservas serán incorporados en las siguientes etapas.

## Tecnologías utilizadas

| Tecnología | Uso |
|---|---|
| Python 3.13 | Lenguaje principal |
| Django 5.2 LTS | Framework web y lógica de negocio |
| PostgreSQL 17 | Base de datos relacional |
| Docker Compose | Ejecución local de PostgreSQL |
| Django ORM | Acceso y gestión de datos |
| Django Admin | Administración interna |
| Django Templates | Renderizado de interfaces |
| Bootstrap 5.3 | Diseño visual planificado |
| Git y GitHub | Control de versiones y repositorio remoto |

Para un futuro despliegue se contempla utilizar Render, Gunicorn y WhiteNoise.

## Arquitectura

MesaFácil se desarrolla como un monolito modular utilizando el patrón MVT de Django:

- **Model:** representa los datos y las reglas relacionadas con su persistencia.
- **View:** procesa las solicitudes y coordina la lógica de la aplicación.
- **Template:** presenta la información al usuario.

Esta arquitectura permite mantener el proyecto sencillo, organizado y adecuado para su alcance académico, evitando agregar complejidad innecesaria durante las primeras etapas.

## Estructura inicial

```text
MesaFacil/
├── config/             # Configuración general de Django
├── reservas/           # Aplicación principal del sistema
│   └── migrations/     # Migraciones de la aplicación
├── .env.example        # Ejemplo de variables de entorno
├── .gitignore          # Archivos excluidos del repositorio
├── docker-compose.yml  # Servicio local de PostgreSQL
├── manage.py           # Herramienta administrativa de Django
├── requirements.txt    # Dependencias de Python
└── README.md
```

## Requisitos

Antes de ejecutar el proyecto se necesita:

- Python 3.13.
- Git.
- Docker Desktop con Docker Compose.
- Un entorno de terminal como CMD, PowerShell o Git Bash.

## Instalación local

### 1. Clonar el repositorio

Mediante SSH:

```bash
git clone git@github.com:Angle931/mesaFacil.git
cd mesaFacil
```

### 2. Crear el entorno virtual

En Windows:

```cmd
py -V:3.13 -m venv .venv
.venv\Scripts\activate.bat
```

### 3. Instalar las dependencias

```cmd
python -m pip install -r requirements.txt
```

### 4. Configurar las variables de entorno

Copia el archivo de ejemplo:

```cmd
copy .env.example .env
```

El archivo `.env` debe contener una configuración similar a:

```env
POSTGRES_DB=mesafacil
POSTGRES_USER=mesafacil_user
POSTGRES_PASSWORD=change_me
POSTGRES_PORT=5432

DATABASE_URL=postgresql://mesafacil_user:change_me@localhost:5432/mesafacil
```

El valor utilizado en `POSTGRES_PASSWORD` debe coincidir con la contraseña incluida en `DATABASE_URL`.

El archivo `.env` contiene información local sensible y no debe subirse al repositorio.

### 5. Iniciar PostgreSQL

```cmd
docker compose up -d db
```

Verifica que el contenedor se encuentre saludable:

```cmd
docker compose ps
```

### 6. Aplicar las migraciones

```cmd
python manage.py migrate
```

### 7. Crear un usuario administrador

```cmd
python manage.py createsuperuser
```

### 8. Iniciar la aplicación

```cmd
python manage.py runserver
```

La aplicación estará disponible en:

```text
http://127.0.0.1:8000/
```

El panel administrativo estará disponible en:

```text
http://127.0.0.1:8000/admin/
```

## Comandos útiles

Comprobar la configuración de Django:

```cmd
python manage.py check
```

Consultar el estado de PostgreSQL:

```cmd
docker compose ps
```

Detener los servicios de Docker:

```cmd
docker compose down
```

Reiniciar PostgreSQL:

```cmd
docker compose restart db
```

## Justificación tecnológica

Django fue seleccionado porque integra en un mismo framework el manejo de rutas, formularios, autenticación, administración y acceso a datos, lo que permite reducir el tiempo de desarrollo.

PostgreSQL se utiliza desde el inicio para mantener consistencia entre el entorno local y el futuro entorno de despliegue. Docker Compose facilita su instalación y permite que otros integrantes del equipo reproduzcan el entorno de desarrollo.

Esta combinación proporciona una base sencilla y suficientemente robusta para desarrollar MesaFácil sin introducir tecnologías adicionales que aumenten innecesariamente el alcance del proyecto.

## Próximas etapas

- Diseñar los modelos del dominio.
- Implementar la gestión de mesas y horarios.
- Implementar la creación y administración de reservas.
- Incorporar validaciones de disponibilidad.
- Crear las vistas y plantillas para los usuarios.
- Agregar pruebas automatizadas.
- Preparar el despliegue en Render.

## Documentación

- [Requisitos funcionales y reglas de negocio](docs/requirements.md)
- `AGENTS.md`: instrucciones de desarrollo para asistentes de programación.