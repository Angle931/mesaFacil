from datetime import time


HORARIOS = tuple(time(hora) for hora in range(12, 22))
HORARIOS_CHOICES = tuple((hora, hora.strftime("%H:%M")) for hora in HORARIOS)
