"""Hora de observación centralizada en PostgreSQL, no la fecha del hecho de origen."""
from django.db import connection


def ahora():
    # No CURRENT_TIMESTAMP: en una transacción exterior podría preceder a una
    # espera por locks. clock_timestamp() es la hora real del servidor de datos.
    with connection.cursor() as cursor:
        cursor.execute("SELECT clock_timestamp()")
        return cursor.fetchone()[0]
