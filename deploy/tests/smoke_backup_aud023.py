"""Synthetic AUD-023 fixture/check; feed to isolated backend through stdin."""
from datetime import date, timedelta
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
import sys
from uuid import uuid4

import django
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, connection, transaction
from django.utils import timezone
from PIL import Image

action = sys.argv[1]
assert action in ('seed', 'verify')
assert settings.DATABASES['default']['NAME'] == f"fyag_aud023_{'source' if action == 'seed' else 'target'}"
assert settings.FYAG_PRODUCTION_ROLE == 'web'
django.setup()

from apps.adjuntos import metadata as adjmeta
from apps.adjuntos.models import AdjuntoDocumento
from apps.chat import almacen, services as chat, tickets
from apps.chat.models import ArchivoChat, CanalChat, MensajeChat, TicketChat
from apps.comercial.models import Cliente, Presupuesto
from apps.documentos import services as documentos
from apps.inventario.models import ExistenciaInventario, MovimientoInventario
from apps.inventario.services import crear_articulo, registrar_ingreso
from apps.obras import services as obras, services_gastos, services_turnos
from apps.obras.evidencias import ruta_privada
from apps.obras.models import CategoriaServicio, CostoObraEvento, EvidenciaTurno, GastoObra, Obra
from apps.usuarios.models import DesafioCorreo, DesafioRecuperacionCorreo, EstadoAcceso, SeguridadCredencial, Usuario
from apps.usuarios.tokens import RefreshToken

PHOTO = BytesIO()
Image.new('RGB', (16, 16), 'blue').save(PHOTO, 'PNG')
CONTENT = PHOTO.getvalue()
CHECKSUM = sha256(CONTENT).hexdigest()
LOGIN = 'ti@aud023.test'
# Fixed, public test data. Never use these literals outside the guarded databases.
PASSWORD = 'Synthetic-AUD023-Only!87'


def auth_client():
    from rest_framework.test import APIClient
    client = APIClient(enforce_csrf_checks=True)
    client.defaults['HTTP_HOST'] = settings.ALLOWED_HOSTS[0]
    client.defaults['HTTP_ORIGIN'] = settings.FYAG_PUBLIC_BASE_URL
    return client


def seed():
    def user(name, role):
        existing = Usuario.objects.filter(username=name).first()
        return existing or Usuario.objects.create_user(username=name, email=f'{name}@aud023.test', rol=role, password=PASSWORD)

    ti = user('ti', 'ADMINISTRADOR_TI')
    finance = user('finanzas', 'ADMINISTRATIVO_FINANZAS')
    supervisor = user('supervisor', 'SUPERVISOR_OBRAS')
    tech = user('tecnico', 'TECNICO')
    bodega = user('bodega', 'BODEGUERO')
    pending = user('pendiente', 'TECNICO')
    now = timezone.now()
    state = SeguridadCredencial.objects.get(usuario=pending)
    state.estado, state.emitida_en, state.vence_en = 'INICIAL', now, now + timedelta(hours=2)
    state.desafio_digest, state.desafio_vence_en, state.desafio_version = 'd'*64, state.vence_en, pending.sesion_version
    state.save()
    EstadoAcceso.objects.filter(usuario=pending).update(estado='BLOQUEO_TEMPORAL', bloqueo_inicio=now,
        bloqueado_hasta=now+timedelta(minutes=15), ciclos_en=[now], version=2, actualizado_en=now)
    DesafioCorreo.objects.get_or_create(digest='a'*64, defaults=dict(usuario=ti, email=ti.email,
        proposito='TITULARIDAD', emitido_en=now, vence_en=now+timedelta(hours=1)))
    DesafioRecuperacionCorreo.objects.get_or_create(usuario=ti,
        defaults=dict(digest='b'*64, vinculo='c'*64, vence_en=now+timedelta(hours=1)))
    assert ti.sesion_version == 1
    RefreshToken.for_user(ti)  # History must remain; version must invalidate this generation.

    obra = Obra.objects.first()
    if obra is None:
        client = Cliente.objects.create(tipo_cliente='EMPRESA', tipo_identificacion='SIN_IDENTIFICACION',
            nombre_legal='Cliente AUD023', correo='cliente@aud023.test')
        budget = Presupuesto.objects.create(cliente=client, creado_por=finance, descripcion='AUD023', estado='APROBADO_CLIENTE')
        category = CategoriaServicio.objects.create(nombre='AUD023', activo=True)
        obra = obras.crear_obra({'presupuesto': budget.pk, 'categoria_servicio': category.pk, 'descripcion': 'Obra AUD023',
            'fecha_programada': date.today()+timedelta(days=7), 'tecnico_responsable': tech.pk, 'motivo': 'Ensayo'}, supervisor)
        obras.iniciar_obra(obra, supervisor, 'Ensayo')
    services_gastos.crear_gasto(obra, {'tipo': 'MATERIAL', 'descripcion': 'Insumo AUD023', 'unidad': 'metro',
        'cantidad': '2.500', 'costo_unitario_neto': '12500.00', 'fecha_gasto': timezone.localdate()}, supervisor)
    article = crear_articulo({'codigo': 'AUD023', 'nombre': 'Insumo AUD023', 'unidad': 'metro'}, bodega)
    registrar_ingreso({'articulo': article.pk, 'cantidad': '5.250', 'clave_idempotencia': str(uuid4())}, bodega)
    turno = services_turnos.iniciar_turno(obra, {}, tech)
    turno = services_turnos.finalizar_turno(obra.pk, turno.pk, {'descripcion_trabajo': 'Trabajo AUD023'}, tech,
        fotos=[SimpleUploadedFile('aud023.png', CONTENT, content_type='image/png')])
    evidencia = turno.fotos.get()
    documentos.sincronizar(documentos.fuente(evidencia.pk))
    documentos.editar(supervisor, evidencia.pk, 0, {'descripcion': 'Anotacion evidencia'}, 'aud023')

    adjunto = AdjuntoDocumento.objects.create(tipo='INFORME_TECNICO', obra=obra, nombre_visible='aud023.png',
        mime='image/png', tamano_bytes=len(CONTENT), sha256=CHECKSUM, registrado_por=supervisor,
        clave_idempotencia=uuid4(), huella_solicitud=CHECKSUM)
    from apps.adjuntos.almacen import Staging
    # Same bytes and destination convention as publication, without requiring an antivirus service in this fixture.
    with Staging() as staging:
        staging.file.write(CONTENT)
        staging.publicar(adjunto.clave_interna)
    adjmeta.sincronizar(adjunto)
    adjmeta.editar(adjunto, supervisor, {'revision': 0, 'descripcion': 'Anotacion adjunto'}, 'aud023')

    conv, _ = chat.crear_conversacion({'tipo': 'DIRECTA', 'destinatario': tech.pk, 'clave_idempotencia': str(uuid4())}, ti)
    row = ArchivoChat.objects.create()
    with almacen.Staging(row.clave_interna) as stage, transaction.atomic():
        stage.file.write(CONTENT)
        stage.publicar()
        chat._publicar(conv.pk, '', uuid4(), CHECKSUM, ti, archivo=row,
                       metadata={'nombre': 'aud023.png', 'mime': 'image/png', 'tamano_bytes': len(CONTENT), 'sha256': CHECKSUM})
    tickets.emitir(ti)
    tickets.admitir('127.0.0.1')
    print('Fixture AUD-023 persistida.')


def restored():
    ti = Usuario.objects.get(email=LOGIN)
    pending = Usuario.objects.get(username='pendiente')
    assert ti.sesion_version == 2 and ti.check_password(PASSWORD)
    assert pending.sesion_version == 2 and not pending.has_usable_password()
    assert pending.seguridad_credencial.desafio_digest is None
    assert pending.estado_acceso.estado == 'BLOQUEO_TEMPORAL' and pending.estado_acceso.version == 2
    assert not any(model.objects.exists() for model in (DesafioCorreo, DesafioRecuperacionCorreo, TicketChat, CanalChat))
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_user, has_schema_privilege('public','CREATE'), token FROM token_blacklist_outstandingtoken LIMIT 1")
        role, ddl, old_refresh = cursor.fetchone()
        assert role == 'fyag_sql_web' and not ddl
    try:
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute('DELETE FROM obras_costoobraevento')
    except DatabaseError as exc:
        assert exc.__cause__.sqlstate == '42501'
    else:
        raise AssertionError('Evento de costo mutable')
    obra = Obra.objects.get()
    assert obra.presupuesto.cliente.nombre_legal == 'Cliente AUD023'
    assert GastoObra.objects.get(obra=obra).subtotal == Decimal('31250.00')
    assert CostoObraEvento.objects.filter(obra=obra).exists() and obra.eventos.exists()
    assert ExistenciaInventario.objects.get().saldo == Decimal('5.250') and MovimientoInventario.objects.count() == 1
    evidence = EvidenciaTurno.objects.get(obra=obra)
    assert evidence.turno.obra_id == obra.pk
    assert sha256(ruta_privada(evidence.nombre_interno).read_bytes()).hexdigest() == evidence.sha256
    doc = documentos.mongo.coleccion().find_one({'_id': f'evidencia_turno:{evidence.pk}'})
    assert (doc['obra_id'], doc['turno_id'], doc['revision'], doc['descripcion']) == (obra.pk, evidence.turno_id, 1, 'Anotacion evidencia')
    attachment = AdjuntoDocumento.objects.get(obra=obra)
    from apps.adjuntos.almacen import copia_verificada
    with copia_verificada(attachment) as stream:
        assert stream.read() == CONTENT
    meta = adjmeta.coleccion().find_one({'_id': f'adjunto:{attachment.pk}'})
    assert (meta['destino_id'], meta['revision'], meta['descripcion']) == (obra.pk, 1, 'Anotacion adjunto')
    file = ArchivoChat.objects.get(estado='PUBLICADO', mensaje=MensajeChat.objects.get())
    with almacen.copia_verificada(file) as out:
        assert out.read() == CONTENT
    client = auth_client()
    assert client.get('/api/auth/setup/estado/', secure=True).data == {'pendiente': False}
    csrf = client.get('/api/auth/csrf/', secure=True).data['csrfToken']
    client.cookies[settings.JWT_REFRESH_COOKIE_NAME] = old_refresh
    revoked = client.post('/api/auth/refresh/', {}, format='json', secure=True, HTTP_X_CSRFTOKEN=csrf)
    assert revoked.status_code == 401, revoked.status_code
    response = client.post('/api/auth/login/', {'email': LOGIN, 'password': PASSWORD}, format='json', secure=True, HTTP_X_CSRFTOKEN=csrf)
    assert response.status_code == 200 and 'access' in response.data, response.status_code
    print('OK: datos, auditoria, ACL, stock, costos, archivos, Mongo y autenticacion.')


(seed if action == 'seed' else restored)()
