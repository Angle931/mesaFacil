class ReservaServiceError(Exception):
    """Error esperado de una operación de reservas, sin detalles de SQL."""


class SinDisponibilidad(ReservaServiceError):
    def __init__(self):
        super().__init__("No existen mesas disponibles para la solicitud.")


class ConflictoReserva(ReservaServiceError):
    def __init__(self):
        super().__init__("El turno dejó de estar disponible. Consulta nuevamente.")


class GeneracionCodigoAgotada(ReservaServiceError):
    def __init__(self):
        super().__init__("No se pudo generar un código único después de cinco intentos.")
