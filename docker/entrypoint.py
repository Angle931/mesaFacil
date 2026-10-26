"""Preparación local opcional y arranque del servidor; comandos de gestión directos."""

import os
import subprocess
import sys


def main():
    argumentos = sys.argv[1:]
    if argumentos != ["serve"]:
        if not argumentos:
            raise SystemExit("Se requiere 'serve' o un comando explícito.")
        os.execvp(argumentos[0], argumentos)

    migraciones = os.environ.get("RUN_MIGRATIONS", "false").strip().lower()
    if migraciones not in {"true", "false"}:
        raise SystemExit("RUN_MIGRATIONS debe ser true o false.")
    if migraciones == "true":
        subprocess.run([sys.executable, "manage.py", "migrate", "--noinput"], check=True)
    subprocess.run([sys.executable, "manage.py", "collectstatic", "--noinput"], check=True)

    puerto = os.environ.get("PORT", "8000")
    procesos = os.environ.get("WEB_CONCURRENCY", "2")
    if not puerto.isdecimal() or not 1 <= int(puerto) <= 65535:
        raise SystemExit("PORT debe ser un puerto válido.")
    if not procesos.isdecimal() or int(procesos) < 1:
        raise SystemExit("WEB_CONCURRENCY debe ser un entero positivo.")
    os.execvp(sys.executable, [
        sys.executable, "-m", "gunicorn", "config.wsgi:application",
        "--bind", f"0.0.0.0:{puerto}", "--workers", procesos,
        "--access-logfile", "-", "--error-logfile", "-",
    ])


if __name__ == "__main__":
    main()
