# MesaFácil - Instrucciones para Codex

## Objetivo del proyecto

MesaFácil es una aplicación web para gestionar las reservas de mesas
de un restaurante de Managua.

Debe permitir:

- Consultar disponibilidad sin iniciar sesión.
- Registrar reservas sin crear una cuenta de cliente.
- Confirmar la reserva mediante un código de referencia.
- Administrar mesas y reservas desde un panel protegido.

## Fuente funcional del proyecto

Antes de implementar o modificar una funcionalidad, leer:

- `docs/requirements.md`

Este documento es la fuente principal de requisitos y reglas de negocio.

Si el código, el plan de implementación y los requisitos se contradicen,
detenerse y explicar la contradicción antes de realizar cambios.

No inventar comportamientos que no estén definidos. Presentar las
decisiones pendientes para aprobación.

## Tecnologías aprobadas

- Python 3.13
- Django 5.2 LTS
- PostgreSQL 17
- Psycopg 3
- Docker Compose para PostgreSQL local
- Django Templates y Bootstrap para la interfaz
- Git y GitHub para control de versiones

No sustituir estas tecnologías ni agregar frameworks importantes sin
explicar la necesidad y obtener aprobación.

## Arquitectura

- Aplicación web cliente-servidor.
- Monolito modular.
- Patrón MVT de Django, equivalente al MVC definido en el análisis.
- La aplicación principal del dominio es `reservas`.
- No implementar microservicios ni un frontend separado.
- No crear una API REST salvo que una fase posterior lo requiera.

## Modelo del dominio

### Cliente

Debe almacenar:

- Nombre
- Teléfono
- Correo electrónico opcional

El cliente no es un usuario autenticado.

### Mesa

Debe almacenar:

- Número único
- Capacidad
- Estado activo o inactivo

No se permite combinar varias mesas para una reserva.

### Reserva

Debe almacenar:

- Código de confirmación único
- Cliente
- Mesa
- Fecha
- Horario
- Cantidad de personas
- Estado

Estados permitidos:

- Pendiente
- Confirmada
- Completada
- Cancelada

Las reservas no deben eliminarse físicamente como parte del flujo normal.

### Administrador

Utilizar el sistema de autenticación incluido en Django.

No crear un modelo propio que guarde contraseñas directamente.

## Reglas de negocio

- Una mesa solo puede reservarse si está activa.
- La capacidad debe ser suficiente para la cantidad de personas.
- No puede existir más de una reserva activa para la misma mesa,
  fecha y horario.
- Una reserva cancelada no debe bloquear la disponibilidad.
- La disponibilidad debe validarse nuevamente en el servidor antes
  de guardar o modificar una reserva.
- Las operaciones críticas deben ejecutarse de forma transaccional.
- No se enviarán correos electrónicos ni mensajes SMS.

## Forma de trabajo

- Implementar una funcionalidad pequeña por vez.
- Explicar el cambio antes de modificar archivos.
- Permitir que el estudiante revise cada etapa.
- No avanzar automáticamente a la siguiente fase.
- No realizar commits, push o despliegues sin autorización.
- No modificar migraciones ya aplicadas; crear nuevas migraciones.
- No introducir dependencias sin justificar su necesidad.
- Mantener credenciales y secretos fuera del repositorio.

## Verificación requerida

Después de realizar cambios relevantes, ejecutar según corresponda:

```bash
python manage.py check
python manage.py makemigrations --check
python manage.py test