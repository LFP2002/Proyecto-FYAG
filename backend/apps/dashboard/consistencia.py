"""Snapshot PostgreSQL por respuesta, sin cambiar el aislamiento de la sesión."""
from contextlib import contextmanager

from django.db import connection, transaction
from django.utils import timezone


@contextmanager
def lectura_estable():
    # No degradar silenciosamente un atomic exterior (ATOMIC_REQUESTS/callers).
    # Los tests que prueban HTTP/snapshot utilizan TransactionTestCase real.
    if connection.in_atomic_block:
        raise RuntimeError("Dashboard requiere una transacción de lectura propia.")
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            # Establece el snapshot antes de autorizar y de cualquier agregado.
            cursor.execute("SELECT pg_current_snapshot()")
            cursor.fetchone()
        yield timezone.now()
