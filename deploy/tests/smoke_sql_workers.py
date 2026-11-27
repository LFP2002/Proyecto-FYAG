"""AUD-025: run via `exec -T SERVICE python - [seed|verify]` in the disposable lab.

Stop the continuous alerts/documents/attachments/chat workers before seeding;
then run this script without arguments once in each worker service via `run`.
Run seed and verify in backend. Mail runs the negative checks only here.
"""
import json
import sys
from datetime import date, timedelta
from io import BytesIO, StringIO
from uuid import uuid4

import django
from django.conf import settings
from django.core.management import call_command
from django.db import DatabaseError, connection, transaction
from django.utils import timezone

assert settings.DATABASES['default']['NAME'] == 'fyag_aud025_lab'
django.setup()


def denied(statement, state='42501'):
    try:
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(statement)
            transaction.set_rollback(True)
    except DatabaseError as exc:
        assert exc.__cause__.sqlstate == state, (statement, exc.__cause__.sqlstate)
    else:
        raise AssertionError(statement)


def seed():
    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image
    from apps.adjuntos.models import AdjuntoDocumento
    from apps.chat import services
    from apps.chat.models import ActoChat, ArchivoChat, MensajeChat
    from apps.comercial.models import Cliente, Presupuesto
    from apps.obras import services as obras, services_turnos as turnos
    from apps.obras.models import CategoriaServicio
    from apps.usuarios.models import Usuario

    batch = uuid4().hex[:12]

    def user(suffix, role):
        return Usuario.objects.create_user(username=f'worker025_{batch}_{suffix}', email=f'{suffix}-{batch}@worker025.test', rol=role)

    supervisor = user('supervisor', 'SUPERVISOR_OBRAS')
    finance = user('finance', 'ADMINISTRATIVO_FINANZAS')
    tech = user('tech', 'TECNICO')
    other = user('other', 'TECNICO')
    client = Cliente.objects.create(tipo_cliente='EMPRESA', tipo_identificacion='SIN_IDENTIFICACION',
        nombre_legal='Cliente AUD025', correo='cliente@worker025.test')
    budget = Presupuesto.objects.create(cliente=client, creado_por=finance,
        descripcion='AUD025 aprobado', estado='APROBADO_CLIENTE')
    category = CategoriaServicio.objects.create(nombre=f'AUD025 {batch}', activo=True)
    obra = obras.crear_obra({'presupuesto': budget.pk, 'categoria_servicio': category.pk,
        'descripcion': 'Obra AUD025', 'fecha_programada': date.today()+timedelta(days=7),
        'tecnico_responsable': tech.pk, 'motivo': 'Principal'}, supervisor)
    obras.iniciar_obra(obra, supervisor, 'Inicio')
    turno = turnos.iniciar_turno(obra, {}, tech)
    image = BytesIO()
    Image.new('RGB', (12, 12), 'blue').save(image, 'PNG')
    photo = SimpleUploadedFile('aud025.png', image.getvalue(), content_type='image/png')
    turno = turnos.finalizar_turno(obra.pk, turno.pk, {'descripcion_trabajo': 'Trabajo AUD025'}, tech, fotos=[photo])
    assert turno.fotos.exists()
    AdjuntoDocumento.objects.create(tipo='INFORME_TECNICO', obra=obra,
        nombre_visible='aud025.png', mime='image/png', tamano_bytes=100, sha256='a'*64,
        registrado_por=supervisor, clave_idempotencia=uuid4(), huella_solicitud='a'*64)
    Presupuesto.objects.create(cliente=client, creado_por=finance,
        descripcion='AUD025 pendiente', estado='PENDIENTE_FINANZAS')
    conv, _ = services.crear_conversacion({'tipo': 'DIRECTA', 'destinatario': other.pk,
        'clave_idempotencia': str(uuid4())}, tech)
    now = timezone.now()
    with transaction.atomic():
        key = uuid4()
        row = MensajeChat.objects.create(conversacion=conv, autor=tech, texto='AUD025 caducado',
            creado_en=now-timedelta(days=2), vence_en=now-timedelta(days=1), clave_idempotencia=key, huella='a'*64)
        ActoChat.objects.create(conversacion=conv, autor=tech, accion='MENSAJE', clave=key,
            huella=row.huella, mensaje_id=row.pk)
    services.publicar_texto(conv.pk, {'texto': 'AUD025 vigente', 'clave_idempotencia': str(uuid4())}, tech)
    ArchivoChat.objects.create(creado_en=now-timedelta(hours=2))


def verify():
    from apps.adjuntos import metadata
    from apps.adjuntos.models import AdjuntoDocumento
    from apps.alertas.models import AlertaEvento
    from apps.chat.models import ActoChat, ArchivoChat, MensajeChat
    from apps.documentos import mongo
    from apps.obras.models import EvidenciaTurno

    assert AlertaEvento.objects.filter(alerta__tipo='PRESUPUESTO_PENDIENTE_FINANZAS', tipo='CREACION').exists()
    assert not MensajeChat.objects.filter(texto='AUD025 caducado').exists()
    assert MensajeChat.objects.filter(texto='AUD025 vigente').exists()
    assert ActoChat.objects.filter(accion='MENSAJE', caducado=True, mensaje_id=None, huella='').exists()
    assert not ArchivoChat.objects.exists()
    assert mongo.coleccion().find_one({'_id': f'evidencia_turno:{EvidenciaTurno.objects.get().pk}'})
    assert metadata.coleccion().find_one({'_id': f'adjunto:{AdjuntoDocumento.objects.get().pk}'})
    print('OK: proyecciones, evento de alerta y retención Chat con filas reales.')


role = settings.FYAG_PRODUCTION_ROLE
with connection.cursor() as cursor:
    cursor.execute('''SELECT rolname, rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls OR rolinherit,
        EXISTS (SELECT FROM pg_auth_members WHERE member=r.oid), has_schema_privilege('public','CREATE')
        FROM pg_roles r WHERE rolname=current_user''')
    assert cursor.fetchone() == (f'fyag_sql_{role}', False, False, False)

if role == 'web':
    if sys.argv[1] == 'seed':
        seed()
    else:
        assert sys.argv[1] == 'verify'
        verify()
else:
    for statement in ('SELECT * FROM usuarios_activacionbloqueos', 'SELECT * FROM inventario_articuloinventario',
                      'CREATE TABLE public.aud025_denegado(id int)', 'SET ROLE fyag_sql_migration',
                      'TRUNCATE usuarios_usuarioevento'):
        denied(statement)
    for statement in {
        'alerts': ('UPDATE comercial_presupuesto SET estado=estado', 'DELETE FROM alertas_alertaevento'),
        'documents': ('UPDATE obras_evidenciaturno SET id=id', 'SELECT * FROM adjuntos_adjuntodocumento'),
        'attachments': ('DELETE FROM adjuntos_adjuntodocumento', 'SELECT * FROM obras_evidenciaturno'),
        'chat': ('UPDATE chat_mensajechat SET texto=texto', 'DELETE FROM chat_actochat'),
        'mail': ('UPDATE usuarios_usuario SET password=password', 'SELECT * FROM usuarios_estadoacceso'),
    }[role]:
        denied(statement)

    if role == 'chat':
        from apps.chat.purga import purgar

        denied("DELETE FROM chat_mensajechat WHERE texto='AUD025 vigente'", '23514')
        denied("UPDATE chat_actochat SET huella='' WHERE accion='CONVERSACION'", '23514')
        result = purgar()
        assert result['estado'] == 'completo' and result['registros']['mensajes']['eliminados'] == 1, result
        assert result['registros']['reservas']['transferidas'] == 1, result
    elif role in {'documents', 'attachments'}:
        output = StringIO()
        call_command('reconciliar_documentos_mongodb' if role == 'documents' else 'reconciliar_adjuntos_mongodb', stdout=output)
        assert json.loads(output.getvalue()) == {'resultado': 'sincronizado', 'cantidad': 1}
    elif role == 'alerts':
        from apps.alertas.services import reconciliar

        result = reconciliar()
        assert result['transiciones'] >= 1, result
    print(f'OK: {role}, denegaciones SQL y ciclo dirigido cuando corresponde.')
