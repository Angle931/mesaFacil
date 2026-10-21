"""Consulta informativa y registro atómico. No contiene operaciones de edición."""

from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from .codigos import generar_codigo_confirmacion
from .exceptions import ConflictoReserva, GeneracionCodigoAgotada, SinDisponibilidad
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


def _mesas_ocupadas(fecha, hora):
    return Reserva.objects.filter(
        fecha=fecha, hora=hora, estado__in=ESTADOS_BLOQUEANTES,
    ).values_list("mesa_id", flat=True)


def _disponibles(fecha, hora, cantidad_personas):
    return Mesa.objects.filter(activa=True, capacidad__gte=cantidad_personas).exclude(
        pk__in=_mesas_ocupadas(fecha, hora),
    ).order_by("capacidad", "pk")


def consultar_mesas_disponibles(*, fecha, hora, cantidad_personas):
    """Devuelve una lista ordenada; no garantiza disponibilidad al registrar."""
    fecha, hora, cantidad_personas = _validar_solicitud(fecha, hora, cantidad_personas)
    return list(_disponibles(fecha, hora, cantidad_personas))


def _bloquear_candidatas(cantidad_personas):
    # Incluir ocupadas y adquirir TODOS los bloqueos antes de elegir por capacidad.
    return list(
        Mesa.objects.select_for_update().filter(
            activa=True, capacidad__gte=cantidad_personas,
        ).order_by("pk")
    )


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
