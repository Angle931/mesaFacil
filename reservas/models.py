from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models

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
