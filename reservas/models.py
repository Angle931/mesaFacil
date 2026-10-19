from django.core.validators import MinValueValidator
from django.db import models

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
