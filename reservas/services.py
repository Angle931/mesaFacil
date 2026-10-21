"""Disponibilidad y operaciones transaccionales del dominio de reservas."""

from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models import Q
from django.utils import timezone

from .codigos import generar_codigo_confirmacion
from .exceptions import ConflictoReserva, GeneracionCodigoAgotada, ReservaNoEncontrada, SinDisponibilidad
from .models import Cliente, Mesa, Reserva


ESTADOS_BLOQUEANTES = (Reserva.Estado.PENDIENTE, Reserva.Estado.CONFIRMADA)
RESTRICCION_DISPONIBILIDAD = "reserva_unica_activa_mesa_fecha_hora"
MAX_INTENTOS_CODIGO = 5


def _validar_solicitud(fecha, hora, cantidad_personas):
    datos = {"fecha": fecha, "hora": hora, "cantidad_personas": cantidad_personas}
    errores = {}
    for nombre, valor in datos.items():
        try:
            if nombre == "cantidad_personas" and isinstance(valor, (bool, float)):
                raise ValidationError("Ingresa una cantidad entera de personas.")
            datos[nombre] = Reserva._meta.get_field(nombre).clean(valor, None)
        except ValidationError as error:
            errores[nombre] = error.error_list
    if not errores:
        inicio = timezone.make_aware(
            datetime.combine(datos["fecha"], datos["hora"]),
            timezone.get_default_timezone(),
        )
        if inicio <= timezone.now():
            errores["fecha"] = ["La fecha y hora deben ser futuras."]
    if errores:
        raise ValidationError(errores)
    return datos["fecha"], datos["hora"], datos["cantidad_personas"]


def _mesas_ocupadas(fecha, hora, exclude_reserva_id=None):
    reservas = Reserva.objects.filter(
        fecha=fecha, hora=hora, estado__in=ESTADOS_BLOQUEANTES,
    )
    if exclude_reserva_id is not None:
        reservas = reservas.exclude(pk=exclude_reserva_id)
    return reservas.values_list("mesa_id", flat=True)


def _disponibles(fecha, hora, cantidad_personas, exclude_reserva_id=None):
    return Mesa.objects.filter(activa=True, capacidad__gte=cantidad_personas).exclude(
        pk__in=_mesas_ocupadas(fecha, hora, exclude_reserva_id),
    ).order_by("capacidad", "pk")


def consultar_mesas_disponibles(*, fecha, hora, cantidad_personas):
    """Devuelve una lista ordenada; no garantiza disponibilidad al registrar."""
    fecha, hora, cantidad_personas = _validar_solicitud(fecha, hora, cantidad_personas)
    return list(_disponibles(fecha, hora, cantidad_personas))


def _bloquear_candidatas(cantidad_personas, mesa_original_id=None):
    # Incluir ocupadas y adquirir TODOS los bloqueos antes de elegir por capacidad.
    filtro = Q(activa=True, capacidad__gte=cantidad_personas)
    if mesa_original_id is not None:
        filtro |= Q(pk=mesa_original_id)
    return list(Mesa.objects.select_for_update().filter(filtro).order_by("pk"))


def _restricciones_codigo():
    # unique=True tiene nombre generado por Django: identificarlo por su columna.
    with connection.cursor() as cursor:
        restricciones = connection.introspection.get_constraints(cursor, Reserva._meta.db_table)
    columna = Reserva._meta.get_field("codigo_confirmacion").column
    return {
        nombre for nombre, detalle in restricciones.items()
        if detalle["unique"] and detalle["columns"] == [columna]
    }


def _restriccion_duplicada(error):
    causa = error.__cause__
    if getattr(causa, "sqlstate", None) != "23505":
        return None
    return getattr(getattr(causa, "diag", None), "constraint_name", None)


def _insertar_reserva(*, cliente, mesa, fecha, hora, cantidad_personas):
    restricciones_codigo = _restricciones_codigo()
    for _ in range(MAX_INTENTOS_CODIGO):
        reserva = Reserva(
            cliente=cliente, mesa=mesa, fecha=fecha, hora=hora,
            cantidad_personas=cantidad_personas,
            codigo_confirmacion=generar_codigo_confirmacion(),
        )
        # La unicidad del código se resuelve al insertar. El resto de las
        # validaciones, incluidas las restricciones de Meta, permanece activo.
        reserva.full_clean(validate_unique=False)
        try:
            with transaction.atomic():
                reserva.save(force_insert=True)
        except IntegrityError as error:
            # El savepoint ya se recuperó; es seguro continuar la transacción.
            restriccion = _restriccion_duplicada(error)
            if restriccion in restricciones_codigo:
                continue
            if restriccion == RESTRICCION_DISPONIBILIDAD:
                raise ConflictoReserva() from error
            raise
        return reserva
    raise GeneracionCodigoAgotada()


def registrar_reserva(*, nombre, telefono, fecha, hora, cantidad_personas, correo=""):
    """Crea cliente y reserva juntos; nunca busca clientes por teléfono.

    Si el llamador abre otra transacción, el commit definitivo depende de ella.
    """
    fecha, hora, cantidad_personas = _validar_solicitud(fecha, hora, cantidad_personas)
    cliente = Cliente(nombre=nombre, telefono=telefono, correo=correo)
    cliente.full_clean()
    with transaction.atomic():
        candidatas = _bloquear_candidatas(cantidad_personas)
        # Una espera por bloqueo puede haber dejado atrás el inicio del turno.
        _validar_solicitud(fecha, hora, cantidad_personas)
        mesa = _disponibles(fecha, hora, cantidad_personas).filter(
            pk__in=[candidata.pk for candidata in candidatas],
        ).first()
        if mesa is None:
            raise SinDisponibilidad()
        cliente.save(force_insert=True)
        return _insertar_reserva(
            cliente=cliente, mesa=mesa, fecha=fecha, hora=hora,
            cantidad_personas=cantidad_personas,
        )


CAMPOS_OCUPACION = frozenset(("fecha", "hora", "cantidad_personas", "mesa_id"))
CAMPOS_CONTACTO = frozenset(("nombre", "telefono", "correo"))
ESTADOS_FINALES = (Reserva.Estado.CANCELADA, Reserva.Estado.COMPLETADA)


def _validar_diccionario(datos, permitidos, nombre):
    if not isinstance(datos, dict):
        raise ValidationError({nombre: "Se requiere un diccionario de cambios."})
    if any(clave not in permitidos for clave in datos):
        raise ValidationError({nombre: "Se proporcionaron campos no permitidos."})


def _validar_identificador(valor, modelo, campo):
    if isinstance(valor, (bool, float)):
        raise ValidationError({campo: "Ingresa un identificador entero válido."})
    try:
        identificador = modelo._meta.pk.clean(valor, None)
    except (ValidationError, TypeError, ValueError) as error:
        raise ValidationError({campo: "Ingresa un identificador entero válido."}) from error
    if identificador is None or identificador <= 0:
        raise ValidationError({campo: "Ingresa un identificador entero válido."})
    return identificador


def _bloquear_reserva(reserva_id):
    identificador = _validar_identificador(reserva_id, Reserva, "reserva_id")
    try:
        return Reserva.objects.select_for_update().get(pk=identificador)
    except Reserva.DoesNotExist as error:
        raise ReservaNoEncontrada() from error


def _normalizar_cambios(reserva, cambios):
    normalizados = {}
    errores = {}
    for campo, valor in cambios.items():
        try:
            if campo == "mesa_id":
                normalizados[campo] = _validar_identificador(valor, Mesa, campo)
            else:
                if campo == "cantidad_personas" and isinstance(valor, (bool, float)):
                    raise ValidationError("Ingresa una cantidad entera de personas.")
                normalizados[campo] = Reserva._meta.get_field(campo).clean(valor, reserva)
        except ValidationError as error:
            errores[campo] = error.messages
    if errores:
        raise ValidationError(errores)
    return normalizados


def _inicio(fecha, hora):
    return timezone.make_aware(datetime.combine(fecha, hora), timezone.get_default_timezone())


def _validar_ocupacion_modificable(reserva, fecha_original, hora_original):
    if reserva.estado in ESTADOS_FINALES:
        raise ValidationError({"estado": "No se puede modificar la ocupación de una reserva finalizada."})
    if _inicio(fecha_original, hora_original) <= timezone.now():
        raise ValidationError({"fecha": "No se puede modificar la ocupación de una reserva cuyo inicio ya se alcanzó."})


def _elegir_mesa_modificacion(reserva, fecha, hora, cantidad, mesa_explicita):
    if mesa_explicita is not None:
        # Una sola adquisición ordenada: nunca bloquear origen y destino por separado.
        mesas = list(Mesa.objects.select_for_update().filter(
            pk__in=(reserva.mesa_id, mesa_explicita),
        ).order_by("pk"))
        mesa = next((fila for fila in mesas if fila.pk == mesa_explicita), None)
        if mesa is None or not mesa.activa or mesa.capacidad < cantidad:
            raise ValidationError({"mesa_id": "La mesa debe existir, estar activa y tener capacidad suficiente."})
        if _mesas_ocupadas(fecha, hora, reserva.pk).filter(mesa_id=mesa.pk).exists():
            raise ConflictoReserva()
        return mesa

    mesas = _bloquear_candidatas(cantidad, mesa_original_id=reserva.mesa_id)
    mesa = _disponibles(fecha, hora, cantidad, exclude_reserva_id=reserva.pk).filter(
        pk__in=[fila.pk for fila in mesas],
    ).first()
    if mesa is None:
        raise SinDisponibilidad()
    return mesa


def _actualizar_contacto(reserva, datos):
    """Bloquear el cliente antes de normalizar, comparar y contar asociaciones."""
    cliente = Cliente.objects.select_for_update().get(pk=reserva.cliente_id)
    resultado = Cliente(
        nombre=datos.get("nombre", cliente.nombre),
        telefono=datos.get("telefono", cliente.telefono),
        correo=datos.get("correo", cliente.correo),
    )
    resultado.full_clean()
    campos = [campo for campo in ("nombre", "telefono", "correo") if getattr(resultado, campo) != getattr(cliente, campo)]
    if not campos:
        return False
    if Reserva.objects.filter(cliente_id=cliente.pk).count() > 1:
        resultado.save(force_insert=True)
        reserva.cliente = resultado
        return True
    cliente.nombre = resultado.nombre
    cliente.telefono = resultado.telefono
    cliente.correo = resultado.correo
    cliente.save(update_fields=campos)
    reserva.cliente = cliente
    return False


def _guardar_modificacion(reserva, campos):
    # El error sale del savepoint antes de examinar sus diagnósticos.
    try:
        with transaction.atomic():
            reserva.save(update_fields=campos)
    except IntegrityError as error:
        if _restriccion_duplicada(error) == RESTRICCION_DISPONIBILIDAD:
            raise ConflictoReserva() from error
        raise


def modificar_reserva(reserva_id, cambios_reserva, datos_cliente=None):
    """Aplica cambios parciales sobre la versión bloqueada; nunca regenera el código."""
    _validar_diccionario(cambios_reserva, CAMPOS_OCUPACION, "cambios_reserva")
    if datos_cliente is not None:
        _validar_diccionario(datos_cliente, CAMPOS_CONTACTO, "datos_cliente")
    with transaction.atomic():
        reserva = _bloquear_reserva(reserva_id)
        cambios = _normalizar_cambios(reserva, cambios_reserva)
        ocupacion_cambiada = any(getattr(reserva, campo) != valor for campo, valor in cambios.items())
        fecha_original, hora_original = reserva.fecha, reserva.hora
        campos = []
        if ocupacion_cambiada:
            _validar_ocupacion_modificable(reserva, fecha_original, hora_original)
            fecha, hora, cantidad = _validar_solicitud(
                cambios.get("fecha", reserva.fecha), cambios.get("hora", reserva.hora),
                cambios.get("cantidad_personas", reserva.cantidad_personas),
            )
            mesa = _elegir_mesa_modificacion(reserva, fecha, hora, cantidad, cambios.get("mesa_id"))
            reserva.fecha = fecha
            reserva.hora = hora
            reserva.cantidad_personas = cantidad
            reserva.mesa = mesa
            campos.extend(("fecha", "hora", "cantidad_personas", "mesa"))

        if datos_cliente:
            if _actualizar_contacto(reserva, datos_cliente):
                campos.append("cliente")

        if ocupacion_cambiada:
            # Revalidar también si hubo espera por las mesas o el cliente.
            _validar_ocupacion_modificable(reserva, fecha_original, hora_original)
        if campos or datos_cliente:
            reserva.full_clean()
        if campos:
            _guardar_modificacion(reserva, campos)
        return reserva


def cambiar_estado_reserva(reserva_id, nuevo_estado):
    with transaction.atomic():
        reserva = _bloquear_reserva(reserva_id)
        estado = Reserva._meta.get_field("estado").clean(nuevo_estado, reserva)
        if estado == reserva.estado:
            return reserva
        list(Mesa.objects.select_for_update().filter(pk=reserva.mesa_id).order_by("pk"))
        reserva.estado = estado
        reserva.full_clean()
        _guardar_modificacion(reserva, ("estado",))
        return reserva


def confirmar_reserva(reserva_id):
    return cambiar_estado_reserva(reserva_id, Reserva.Estado.CONFIRMADA)


def cancelar_reserva(reserva_id):
    return cambiar_estado_reserva(reserva_id, Reserva.Estado.CANCELADA)
