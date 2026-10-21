from datetime import date, datetime, time

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.utils import timezone

from .codigos import PATRON_CODIGO, generar_codigo_confirmacion
from .horarios import HORARIOS, HORARIOS_CHOICES
from .validators import normalizar_telefono

class Mesa(models.Model):
    numero = models.CharField(max_length=20, unique=True)
    capacidad = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    activa = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(capacidad__gte=1),
                name="mesa_capacidad_mayor_cero",
            ),
        ]

    def __str__(self):
        return f"Mesa {self.numero}"


class Cliente(models.Model):
    nombre = models.CharField(max_length=150)
    telefono = models.CharField(
        max_length=12,
        validators=[RegexValidator(r"\A\+505[0-9]{8}\Z", "El teléfono debe tener el formato +505XXXXXXXX.")],
    )
    correo = models.EmailField(max_length=254, blank=True, default="")

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(nombre__regex=r"\S"),
                name="cliente_nombre_no_vacio",
            ),
            models.CheckConstraint(
                condition=models.Q(telefono__regex=r"^\+505[0-9]{8}$"),
                name="cliente_telefono_formato_nicaragua",
            ),
        ]

    def clean_fields(self, exclude=None):
        excluidos = set(exclude or ())
        errores = {}
        if "correo" not in excluidos and self.correo is None:
            errores["correo"] = [ValidationError("El correo no admite NULL; usa una cadena vacía si no se proporciona.", code="null")]
            excluidos.add("correo")
        for campo in ("nombre", "correo"):
            valor = getattr(self, campo)
            if campo not in excluidos and isinstance(valor, str):
                setattr(self, campo, valor.strip())
        if "telefono" not in excluidos:
            try:
                self.telefono = normalizar_telefono(self.telefono)
            except ValidationError as error:
                errores["telefono"] = error.error_list
                excluidos.add("telefono")
        try:
            super().clean_fields(exclude=excluidos)
        except ValidationError as error:
            errores.update(error.error_dict)
        if errores:
            raise ValidationError(errores)

    def __str__(self):
        return self.nombre


class Reserva(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        CONFIRMADA = "CONFIRMADA", "Confirmada"
        COMPLETADA = "COMPLETADA", "Completada"
        CANCELADA = "CANCELADA", "Cancelada"

    codigo_confirmacion = models.CharField(
        max_length=16, unique=True, editable=False,
        default=generar_codigo_confirmacion,
        validators=[RegexValidator(PATRON_CODIGO, "El código debe contener 16 caracteres del alfabeto permitido.")],
    )
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="reservas")
    mesa = models.ForeignKey(Mesa, on_delete=models.PROTECT, related_name="reservas")
    fecha = models.DateField()
    hora = models.TimeField(choices=HORARIOS_CHOICES)
    cantidad_personas = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.PENDIENTE)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(cantidad_personas__gte=1), name="reserva_personas_mayor_cero"),
            models.CheckConstraint(
                condition=models.Q(estado__in=("PENDIENTE", "CONFIRMADA", "COMPLETADA", "CANCELADA")),
                name="reserva_estado_valido",
            ),
            models.CheckConstraint(condition=models.Q(hora__in=HORARIOS), name="reserva_hora_valida"),
            models.CheckConstraint(condition=models.Q(codigo_confirmacion__regex=PATRON_CODIGO), name="reserva_codigo_formato_valido"),
            models.UniqueConstraint(
                fields=("mesa", "fecha", "hora"),
                condition=models.Q(estado__in=("PENDIENTE", "CONFIRMADA")),
                name="reserva_unica_activa_mesa_fecha_hora",
            ),
        ]

    def clean(self):
        super().clean()
        errores = {}
        anterior = None
        if not self._state.adding:
            anterior = type(self).objects.filter(pk=self.pk).first()

        reprogramada = anterior is None or (self.fecha, self.hora) != (anterior.fecha, anterior.hora)
        asignacion_cambiada = reprogramada or (
            self.mesa_id, self.cantidad_personas
        ) != (anterior.mesa_id, anterior.cantidad_personas)

        if anterior is not None:
            if self.codigo_confirmacion != anterior.codigo_confirmacion:
                errores["codigo_confirmacion"] = "El código de confirmación no puede cambiar."
            transiciones = {
                self.Estado.PENDIENTE: {self.Estado.CONFIRMADA, self.Estado.CANCELADA},
                self.Estado.CONFIRMADA: {self.Estado.COMPLETADA, self.Estado.CANCELADA},
                self.Estado.COMPLETADA: set(),
                self.Estado.CANCELADA: set(),
            }
            if self.estado != anterior.estado and self.estado not in transiciones.get(anterior.estado, set()):
                errores["estado"] = "La transición de estado no está permitida."

        if isinstance(self.fecha, date) and isinstance(self.hora, time):
            inicio = timezone.make_aware(datetime.combine(self.fecha, self.hora), timezone.get_default_timezone())
            ahora = timezone.now()
            if reprogramada and inicio <= ahora:
                errores["fecha"] = "La fecha y hora deben ser futuras al crear o reprogramar."
            if self.estado == self.Estado.COMPLETADA and inicio > ahora:
                errores["estado"] = "No se puede completar una reserva antes de su fecha y hora."

        if asignacion_cambiada and self.mesa_id:
            mesa = Mesa.objects.filter(pk=self.mesa_id).first()
            if mesa is not None:
                if not mesa.activa:
                    errores["mesa"] = "La mesa debe estar activa."
                if isinstance(self.cantidad_personas, int) and self.cantidad_personas > mesa.capacidad:
                    errores["cantidad_personas"] = "La cantidad de personas supera la capacidad de la mesa."
        if errores:
            raise ValidationError(errores)

    def __str__(self):
        return f"Reserva {self.codigo_confirmacion}"
