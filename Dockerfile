FROM python:3.13.17-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && python -m pip check

RUN useradd --create-home --uid 10001 --user-group app \
    && mkdir /app/staticfiles \
    && chown app:app /app/staticfiles

COPY manage.py ./
COPY config/ ./config/
COPY reservas/ ./reservas/
COPY docker/ ./docker/

USER app
EXPOSE 8000

ENTRYPOINT ["python", "/app/docker/entrypoint.py"]
CMD ["serve"]
