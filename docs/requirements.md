# Requisitos de MesaFácil

## 1. Propósito

MesaFácil es una aplicación web para centralizar la gestión de reservas
de mesas de un restaurante de Managua.

La aplicación debe reducir pérdidas de información, confusiones y
reservas duplicadas ocasionadas por registros manuales o distribuidos
entre llamadas y redes sociales.

## 2. Actores

### Cliente

Persona que consulta la disponibilidad y registra una reserva.

El cliente:

- No necesita crear una cuenta.
- Proporciona únicamente los datos necesarios para la reserva.
- No tiene acceso al panel administrativo.

### Personal administrativo

Usuario autenticado responsable de:

- Consultar reservas.
- Modificar reservas.
- Actualizar sus estados.
- Gestionar las mesas del restaurante.

Para esta versión solamente existirá un tipo de usuario administrativo.

## 3. Requisitos funcionales

### RF-01: Consultar disponibilidad

El sistema debe mostrar las mesas disponibles de acuerdo con:

- Fecha.
- Horario.
- Cantidad de personas.

Solamente deben considerarse mesas activas cuya capacidad sea suficiente.

La aplicación utilizará horarios predefinidos y no mostrará un mapa
visual de las mesas.

### RF-02: Registrar reserva

El cliente debe poder registrar una reserva proporcionando:

- Nombre.
- Número de teléfono.
- Correo electrónico opcional.
- Fecha.
- Horario.
- Cantidad de personas.

La reserva debe asociarse con una mesa activa, disponible y con capacidad
suficiente.

No se debe permitir más de una reserva incompatible para la misma mesa,
fecha y horario.

El cliente no necesita crear una cuenta.

### RF-03: Confirmar reserva

Después de registrar correctamente una reserva, el sistema debe mostrar:

- Código de confirmación.
- Nombre del cliente.
- Fecha.
- Horario.
- Cantidad de personas.
- Mesa asignada.

La confirmación solamente se mostrará dentro de la aplicación.

No se enviarán correos electrónicos ni mensajes SMS.

### RF-04: Autenticación administrativa

El personal administrativo debe autenticarse mediante nombre de usuario
y contraseña antes de acceder al panel.

La implementación debe utilizar el sistema de autenticación de Django.

No debe crearse un modelo propio para almacenar contraseñas.

### RF-05: Consultar reservas administrativamente

El personal autenticado debe poder consultar las reservas y filtrarlas
por:

- Fecha.
- Horario.
- Estado.

Esta versión no incluirá:

- Reportes estadísticos.
- Exportación de información.

### RF-06: Modificar reserva

El personal autenticado debe poder modificar:

- Datos del cliente.
- Teléfono.
- Correo electrónico.
- Fecha.
- Horario.
- Cantidad de personas.
- Mesa asignada.

Antes de guardar los cambios, el servidor debe validar nuevamente:

- Disponibilidad.
- Capacidad de la mesa.
- Campos requeridos.
- Conflictos con otras reservas.

### RF-07: Actualizar estado de reserva

Los estados permitidos inicialmente son:

- Pendiente.
- Confirmada.
- Completada.
- Cancelada.

Las reservas no deben eliminarse físicamente como parte del flujo normal.

### RF-08: Gestionar mesas

El personal autenticado debe poder:

- Registrar mesas.
- Consultar mesas.
- Modificar mesas.
- Activar o desactivar mesas.

Cada mesa debe contener:

- Número único.
- Capacidad.
- Estado activo o inactivo.

No se implementará la unión automática de varias mesas.

## 4. Modelo conceptual

### Cliente

Campos conceptuales:

- `nombre`
- `telefono`
- `correo`

Relaciones:

- Un cliente puede tener cero o varias reservas.
- Cada reserva pertenece a un cliente.

El cliente es una entidad del dominio, pero no es un usuario autenticado.

### Mesa

Campos conceptuales:

- `numero`
- `capacidad`
- `activa`

Relaciones:

- Una mesa puede aparecer en diferentes reservas.
- Cada reserva se asigna a una sola mesa.

### Reserva

Campos conceptuales:

- `codigo_confirmacion`
- `fecha`
- `hora`
- `cantidad_personas`
- `estado`
- `cliente`
- `mesa`

Relaciones:

- Cada reserva pertenece a un cliente.
- Cada reserva utiliza una mesa.

### Usuario administrativo

Los administradores se representarán mediante el modelo de usuario
proporcionado por Django.

No se almacenarán contraseñas directamente en modelos del dominio.

## 5. Reglas de negocio

- El número de una mesa debe ser único.
- La capacidad de una mesa debe ser mayor que cero.
- La cantidad de personas debe ser mayor que cero.
- Una mesa inactiva no puede ofrecerse para nuevas reservas.
- La mesa seleccionada debe tener capacidad suficiente.
- La disponibilidad debe comprobarse en el servidor.
- La disponibilidad debe verificarse nuevamente antes de guardar.
- El código de confirmación debe ser único.
- El correo electrónico del cliente es opcional.
- El nombre, teléfono, fecha, horario y cantidad de personas son
  obligatorios.
- Las reservas no deben eliminarse como parte de la operación normal.
- Las credenciales administrativas no deben exponerse.
- Las operaciones críticas de reservación deben ejecutarse de manera
  transaccional.
- Las validaciones del navegador no sustituyen las validaciones del
  servidor.

## 6. Requisitos no funcionales

### RNF-01: Usabilidad

El proceso público no debe superar cuatro pantallas desde la consulta
de disponibilidad hasta la confirmación.

La interfaz debe presentar:

- Instrucciones comprensibles.
- Etiquetas claras.
- Mensajes de validación útiles.

### RNF-02: Diseño adaptable

La interfaz debe funcionar en:

- Computadoras.
- Tabletas.
- Teléfonos con pantallas desde 360 píxeles de ancho.

No se desarrollará una aplicación móvil nativa.

### RNF-03: Rendimiento

Las consultas de disponibilidad y los listados administrativos deben
responder en un máximo de tres segundos bajo una carga académica de
hasta veinte usuarios simultáneos.

### RNF-04: Seguridad y privacidad

- Las contraseñas deben almacenarse mediante el mecanismo seguro de
  Django.
- Las funciones administrativas requieren autenticación.
- Los datos personales solamente deben ser visibles para personal
  autorizado.
- Se deben recopilar únicamente los datos necesarios.
- El despliegue público deberá utilizar HTTPS.
- Los secretos y credenciales deben permanecer fuera del repositorio.

### RNF-05: Integridad

El sistema debe impedir:

- Datos obligatorios incompletos.
- Capacidades inválidas.
- Asignación de mesas inactivas.
- Asignación de mesas con capacidad insuficiente.
- Conflictos para una misma mesa, fecha y horario.

## 7. Arquitectura aprobada

- Arquitectura cliente-servidor.
- Aplicación monolítica modular.
- Patrón MVT de Django, equivalente al MVC conceptual.
- Django Templates para la interfaz.
- PostgreSQL como base de datos.
- Docker Compose para PostgreSQL durante el desarrollo local.
- Despliegue futuro compatible con Render.

No se implementarán microservicios, un frontend independiente ni una API
REST mientras no exista un requisito que lo justifique.

## 8. Fuera del alcance actual

La primera versión no incluye:

- Aplicación móvil nativa.
- Cuentas para clientes.
- Correos electrónicos o mensajes SMS.
- Mapa visual de mesas.
- Unión automática de mesas.
- Estadísticas.
- Exportación de reservas.
- Roles administrativos avanzados.
- Microservicios.
- Integraciones externas.
- API pública.

## 9. Estado actual

Completado:

- Proyecto Django.
- Aplicación `reservas`.
- Entorno virtual.
- PostgreSQL en Docker.
- Variables de entorno.
- Migraciones iniciales de Django.
- Superusuario administrativo.
- Repositorio Git y GitHub.

Siguiente etapa:

1. Implementar `Cliente`.
2. Implementar `Mesa`.
3. Implementar `Reserva`.
4. Crear relaciones y restricciones.
5. Crear y aplicar migraciones.
6. Registrar los modelos en Django Admin.
7. Implementar pruebas de las reglas principales.

## 10. Decisiones pendientes

Codex no debe decidir automáticamente los siguientes puntos:

- Lista exacta de horarios disponibles.
- Formato y longitud del código de confirmación.
- Si un cliente existente se reutiliza mediante su teléfono.
- Qué criterio se utiliza para asignar automáticamente una mesa cuando
  existen varias disponibles.
- Qué estados bloquean la disponibilidad de una mesa.

Recomendación inicial para revisión:

- `PENDIENTE` y `CONFIRMADA` bloquean disponibilidad.
- `CANCELADA` y `COMPLETADA` no bloquean nuevas reservas.
- Cuando existan varias mesas disponibles, seleccionar la mesa activa
  con menor capacidad suficiente.

Estas decisiones deben aprobarse antes de implementarse.

## 11. Criterios de aceptación del dominio

La etapa de dominio se considerará terminada cuando:

- Los tres modelos estén implementados.
- Las migraciones se apliquen correctamente en PostgreSQL.
- Los modelos puedan gestionarse desde Django Admin.
- No se pueda registrar una reserva incompatible.
- No se pueda usar una mesa inactiva.
- No se pueda exceder la capacidad de una mesa.
- El código de confirmación sea único.
- Los estados utilicen valores controlados.
- `python manage.py check` no presente errores.
- Las pruebas automatizadas del dominio sean satisfactorias.