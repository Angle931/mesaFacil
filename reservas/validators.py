import re

from django.core.exceptions import ValidationError


def normalizar_telefono(valor):
    """Normaliza un teléfono local o con +505, sin descartar caracteres inválidos."""
    mensaje = "Ingresa ocho dígitos de Nicaragua, con prefijo +505 opcional; usa solo espacios o guiones como separadores."
    if not isinstance(valor, str) or not re.fullmatch(r"\+?[0-9 -]+", valor):
        raise ValidationError(mensaje, code="telefono_invalido")
    compacto = valor.replace(" ", "").replace("-", "")
    if re.fullmatch(r"[0-9]{8}", compacto):
        return f"+505{compacto}"
    if re.fullmatch(r"\+505[0-9]{8}", compacto):
        return compacto
    raise ValidationError(mensaje, code="telefono_invalido")
