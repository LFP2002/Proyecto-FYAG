"""Production-only schema migration and explicit SQL access matrix (AUD-025)."""
import django
from django.conf import settings
from django.core.management import call_command
from django.db import connection, transaction
from psycopg import sql

OWNER = 'fyag_sql_migration'

SECURITY_WRITE = '''usuarios_usuario usuarios_estadoacceso usuarios_seguridadcredencial
                    usuarios_desafiocorreo usuarios_desafiorecuperacioncorreo'''.split()
SECURITY_EVENTS = '''usuarios_usuarioevento usuarios_eventoacceso usuarios_eventoinstalacionfyag'''.split()
CHALLENGES = SECURITY_WRITE[-2:]
APPEND = '''alertas_alertaevento comercial_presupuestoevento comercial_presupuestoprecioevento
    finanzas_egresoevento finanzas_finanzasevento inventario_mermaevento inventario_movimientoinventario
    inventario_solicitudmaterialevento obras_categoriaservicioevento obras_costoobraevento obras_obraevento
    obras_obraparticipanteevento obras_turnoobraevento usuarios_recuperacionacceso usuarios_recuperacioncorreoevento'''.split()
BUSINESS = '''adjuntos_adjuntodocumento alertas_alerta alertas_estadoreconciliacion chat_archivochat
    chat_canalchat chat_conversacionchat chat_cupochat chat_mensajechat chat_participantechat chat_ticketchat
    comercial_cliente comercial_presupuesto comercial_presupuestoitem finanzas_cierresincobro finanzas_documentocobro
    finanzas_egreso finanzas_pagodocumento inventario_articuloinventario inventario_estadovaloracion
    inventario_existenciainventario inventario_merma inventario_operacionmaterial inventario_solicitudmaterialobra
    obras_categoriaservicio obras_cierrecostosobra obras_controlcostosobra obras_cortesiaobra obras_evidenciaturno
    obras_gastoobra obras_obra obras_obraparticipante obras_turnoobra token_blacklist_blacklistedtoken
    token_blacklist_outstandingtoken'''.split()
SYSTEM = '''auth_group auth_group_permissions auth_permission django_admin_log django_content_type django_migrations
    django_session usuarios_usuario_groups usuarios_usuario_user_permissions'''.split()
INSTALL = 'usuarios_instalacionfyag'
ACTIVATION = 'usuarios_activacionbloqueos'
TI = 'usuarios_recuperaciontievento'
ACT = 'chat_actochat'
EXPECTED = set(SECURITY_WRITE + SECURITY_EVENTS + APPEND + BUSINESS + SYSTEM + [INSTALL, ACTIVATION, TI, ACT])


@transaction.atomic
def permissions():
    with connection.cursor() as cursor:
        cursor.execute("""SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                          WHERE n.nspname='public' AND c.relkind='r' AND c.relowner=current_user::regrole""")
        if {row[0] for row in cursor.fetchall()} != EXPECTED:
            raise RuntimeError('El inventario SQL cambió: revisar expresamente la matriz AUD-025.')

        # No conservar ACL ajenas a la matriz, incluyendo permisos de columna.
        cursor.execute("""SELECT DISTINCT c.relname, a.attname, r.rolname
            FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace
            CROSS JOIN LATERAL aclexplode(a.attacl) p LEFT JOIN pg_roles r ON r.oid=p.grantee
            WHERE n.nspname='public' AND p.grantee <> c.relowner""")
        for table, column, grantee in cursor.fetchall():
            target = sql.Identifier(grantee) if grantee else sql.SQL('PUBLIC')
            cursor.execute(sql.SQL('REVOKE ALL ({}) ON TABLE {} FROM {} CASCADE').format(
                sql.Identifier(column), sql.Identifier('public', table), target))

        for kind, catalog, namespace, owner, acl, extra in (
            ('TABLES', 'pg_class', 'relnamespace', 'relowner', 'relacl', "AND obj.relkind='r'"),
            ('SEQUENCES', 'pg_class', 'relnamespace', 'relowner', 'relacl', "AND obj.relkind='S'"),
            ('FUNCTIONS', 'pg_proc', 'pronamespace', 'proowner', 'proacl', ''),
        ):
            cursor.execute(f'''SELECT DISTINCT r.rolname FROM {catalog} obj JOIN pg_namespace n ON n.oid=obj.{namespace}
                CROSS JOIN LATERAL aclexplode(obj.{acl}) p JOIN pg_roles r ON r.oid=p.grantee
                WHERE n.nspname='public' AND p.grantee<>obj.{owner} {extra}''')
            recipients = [sql.SQL('PUBLIC'), *(sql.Identifier(row[0]) for row in cursor.fetchall())]
            cursor.execute(sql.SQL(f'REVOKE ALL ON ALL {kind} IN SCHEMA public FROM {{}} CASCADE').format(sql.SQL(', ').join(recipients)))

        def grant(role, privilege, tables):
            who = sql.Identifier(f'fyag_sql_{role}')
            for table in tables:
                cursor.execute(sql.SQL('GRANT {} ON TABLE {} TO {}').format(
                    sql.SQL(privilege), sql.Identifier('public', table), who))
                if 'INSERT' in privilege:
                    cursor.execute("""SELECT s.relname FROM pg_depend d JOIN pg_class s ON s.oid=d.objid
                        WHERE d.classid='pg_class'::regclass AND d.refclassid='pg_class'::regclass
                          AND d.deptype IN ('a','i') AND s.relkind='S' AND d.refobjid=%s::regclass""", [f'public.{table}'])
                    for name, in cursor.fetchall():
                        cursor.execute(sql.SQL('GRANT USAGE ON SEQUENCE {} TO {}').format(sql.Identifier('public', name), who))

        grant('web', 'SELECT, INSERT, UPDATE', BUSINESS + SECURITY_WRITE)
        grant('web', 'SELECT, INSERT', APPEND + SECURITY_EVENTS + [ACT])
        grant('web', 'UPDATE (mensaje_id, caducado, huella)', [ACT])
        grant('web', 'SELECT', ['django_migrations', 'django_content_type', ACTIVATION, TI, INSTALL])
        grant('web', 'UPDATE (id)', [INSTALL])  # Row lock only: writes rejected by the guard below.
        grant('web', 'DELETE', CHALLENGES + ['chat_archivochat', 'chat_mensajechat', 'chat_cupochat', 'chat_canalchat',
             'chat_ticketchat', 'comercial_presupuestoitem'])

        grant('security', 'SELECT, INSERT, UPDATE', SECURITY_WRITE)
        grant('security', 'DELETE', CHALLENGES)
        grant('security', 'SELECT, INSERT', SECURITY_EVENTS + [ACTIVATION, TI, INSTALL])
        grant('security', 'UPDATE (clave_digest, clave_vence_en)', [INSTALL])
        grant('security', 'SELECT', ['django_migrations'])

        grant('mail', 'SELECT', ['usuarios_usuario', 'usuarios_seguridadcredencial', *CHALLENGES])
        grant('mail', 'INSERT, UPDATE, DELETE', CHALLENGES)
        grant('mail', 'UPDATE (id)', ['usuarios_usuario'])
        grant('mail', 'UPDATE (usuario_id)', ['usuarios_seguridadcredencial'])
        grant('alerts', 'SELECT', ['comercial_presupuesto', 'obras_obra', 'obras_turnoobra', 'finanzas_documentocobro', 'finanzas_pagodocumento'])
        grant('alerts', 'SELECT, INSERT', ['alertas_alerta', 'alertas_estadoreconciliacion'])
        grant('alerts', 'UPDATE (estado, resuelta_en, ultima_comprobacion_en)', ['alertas_alerta'])
        grant('alerts', 'UPDATE (ultima_correcta_en)', ['alertas_estadoreconciliacion'])
        grant('alerts', 'SELECT, INSERT', ['alertas_alertaevento'])
        grant('documents', 'SELECT', ['obras_evidenciaturno', 'obras_turnoobra'])
        grant('attachments', 'SELECT', ['adjuntos_adjuntodocumento'])
        grant('chat', 'SELECT, DELETE', ['chat_mensajechat', 'chat_archivochat', 'chat_cupochat', 'chat_ticketchat', 'chat_canalchat'])
        grant('chat', 'SELECT, UPDATE (id)', ['chat_conversacionchat'])
        grant('chat', 'UPDATE (estado, mensaje_id, nombre, mime, tamano_bytes, sha256)', ['chat_archivochat'])
        grant('chat', 'SELECT, UPDATE (mensaje_id, caducado, huella)', [ACT])

        # Preserve the original trigger and transaction, but only it can mark the singleton initialized.
        cursor.execute('ALTER FUNCTION public.fyag_marcar_instalacion_usuario() SECURITY DEFINER')
        cursor.execute('ALTER FUNCTION public.fyag_marcar_instalacion_usuario() SET search_path TO pg_catalog, public, pg_temp')
        cursor.execute("""CREATE OR REPLACE FUNCTION public.fyag_sql_solo_bloqueo() RETURNS trigger
            LANGUAGE plpgsql SET search_path TO pg_catalog AS $$
            BEGIN
                RAISE EXCEPTION 'Permiso de fila limitado a bloqueo' USING ERRCODE='42501';
            END $$""")
        for table, role, column in [('usuarios_usuario', 'mail', 'id'), ('usuarios_seguridadcredencial', 'mail', 'usuario_id'),
                                    ('chat_conversacionchat', 'chat', 'id'), (INSTALL, 'web', 'id')]:
            relation = sql.Identifier('public', table)
            cursor.execute(sql.SQL('DROP TRIGGER IF EXISTS fyag_sql_solo_bloqueo ON {}').format(relation))
            cursor.execute(sql.SQL('''CREATE TRIGGER fyag_sql_solo_bloqueo BEFORE UPDATE OF {} ON {}
                FOR EACH ROW WHEN (current_user = {}) EXECUTE FUNCTION public.fyag_sql_solo_bloqueo()''').format(
                sql.Identifier(column), relation, sql.Literal(f'fyag_sql_{role}')))

        # Trigger execution itself requires no runtime EXECUTE. Only named helper functions do.
        for name, params, roles in (
            ('fyag_acceso_tiempos_validos', 'timestamptz[], integer', ('web', 'security')),
            ('fyag_material_error', '', ('web',)), ('fyag_merma_error', '', ('web',)),
            ('fyag_merma_raiz', 'public.inventario_merma', ('web',)),
            ('fyag_solicitud_error', '', ('web',)), ('fyag_solicitud_raiz', 'bigint', ('web',)),
            ('fyag_chat_error', '', ('web', 'chat')),
        ):
            cursor.execute(sql.SQL(f'GRANT EXECUTE ON FUNCTION {{}}({params}) TO {{}}').format(
                sql.Identifier('public', name), sql.SQL(', ').join(sql.Identifier(f'fyag_sql_{role}') for role in roles)))


def main():
    if settings.FYAG_PRODUCTION_ROLE != 'migration':
        raise SystemExit('Se requiere la identidad de migraciones.')
    django.setup()
    with connection.cursor() as cursor:
        cursor.execute('SELECT current_user, pg_try_advisory_lock(%s)', [0x465941470025001])
        if cursor.fetchone() != (OWNER, True):
            raise SystemExit('Identidad SQL incorrecta o migración concurrente.')
    try:
        call_command('migrate', interactive=False)
        permissions()
        print('Matriz SQL AUD-025 aplicada.')
    finally:
        connection.close()


if __name__ == '__main__':
    main()
