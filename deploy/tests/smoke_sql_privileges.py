"""AUD-025: feed to `exec -T backend python -` only in the disposable lab."""
from uuid import uuid4

import django
from django.conf import settings
from django.db import DatabaseError, connection, transaction

assert settings.DATABASES['default']['NAME'] == 'fyag_aud025_lab'
django.setup()

from apps.inventario.models import ExistenciaInventario
from apps.inventario.services import crear_articulo, registrar_ingreso
from apps.usuarios.models import Usuario


def denied(statement):
    try:
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(statement)
            transaction.set_rollback(True)
    except DatabaseError as exc:
        assert exc.__cause__.sqlstate == '42501', exc.__cause__.sqlstate
    else:
        raise AssertionError(f'Operación indebidamente autorizada: {statement}')


with connection.cursor() as cursor:
    cursor.execute('''SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, rolinherit
                      FROM pg_roles WHERE rolname=current_user''')
    assert cursor.fetchone() == ('fyag_sql_web', False, False, False, False, False, False)
    cursor.execute("SELECT has_database_privilege(current_user,current_database(),'TEMP'), has_schema_privilege('public','CREATE')")
    assert cursor.fetchone() == (False, False)
    cursor.execute("SELECT EXISTS (SELECT FROM pg_auth_members WHERE member=current_user::regrole)")
    assert cursor.fetchone() == (False,)

for command in ('CREATE ROLE aud025_denegado', 'CREATE SCHEMA aud025_denegado', 'CREATE TABLE public.aud025_denegado(id int)',
                'CREATE TEMP TABLE aud025_denegado(id int)', 'SET ROLE fyag_sql_migration', 'SET ROLE fyag_sql_security',
                'SET session_replication_role=replica', 'ALTER TABLE usuarios_usuario DISABLE TRIGGER ALL',
                'GRANT fyag_sql_migration TO fyag_sql_web', 'UPDATE usuarios_instalacionfyag SET inicializada_en=NULL',
                'UPDATE usuarios_instalacionfyag SET id=1',
                'INSERT INTO usuarios_activacionbloqueos DEFAULT VALUES',
                'INSERT INTO usuarios_recuperaciontievento DEFAULT VALUES'):
    denied(command)

for table in ('usuarios_usuarioevento', 'usuarios_eventoinstalacionfyag', 'usuarios_eventoacceso',
              'usuarios_activacionbloqueos', 'usuarios_recuperaciontievento', 'usuarios_recuperacioncorreoevento',
              'finanzas_finanzasevento', 'alertas_alertaevento', 'inventario_movimientoinventario', 'obras_obraevento'):
    denied(f'UPDATE {table} SET id=id')
    denied(f'DELETE FROM {table}')
    denied(f'TRUNCATE {table}')

actor = Usuario.objects.create_user(username='bodega_aud025', email='bodega-aud025@qa.test', rol='BODEGUERO',
                                   password='Solo-Ficticia-AUD025!95')
article = crear_articulo({'codigo': 'AUD025', 'nombre': 'Artículo sintético', 'unidad': 'unidad'}, actor)
payload = {'articulo': article.pk, 'cantidad': '5.250', 'clave_idempotencia': str(uuid4())}
movement, created = registrar_ingreso(payload, actor)
assert created and str(ExistenciaInventario.objects.get(articulo=article).saldo) == '5.250'
assert registrar_ingreso(payload, actor) == (movement, False)
print('OK: aislamiento SQL, auditoría append-only, ingreso con triggers y repetición idempotente.')
