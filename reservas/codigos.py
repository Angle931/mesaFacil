import secrets


ALFABETO_CODIGO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
PATRON_CODIGO = r"^[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{16}$"


def generar_codigo_confirmacion():
    return "".join(secrets.choice(ALFABETO_CODIGO) for _ in range(16))
