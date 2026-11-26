from django.db.models import Count, OuterRef, Q, Subquery, Value, IntegerField, F
from django.db.models.functions import Coalesce, Substr
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.usuarios.acceso import sesion_operativa
from apps.usuarios.configuracion_c2 import relaciones_seguridad
from apps.usuarios.models import Usuario
from .models import ConversacionChat, MensajeChat, ParticipanteChat
from .permissions import revalidar
from .validaciones import id_url, texto


def query(params, permitidos):
    if set(params)-set(permitidos) or any(len(params.getlist(k)) != 1 or not params[k] for k in params):
        raise ValidationError({'query': ['Parámetro desconocido, vacío o repetido.']})
    if 'page' in params:
        id_url(params['page'])


def elegibles():
    return Usuario.objects.filter(is_active=True, rol__in=Usuario.Rol.values, seguridad_credencial__estado='PERSONAL').select_related(*relaciones_seguridad()).order_by('id')


def directorio(actor, params):
    revalidar(actor)
    query(params, {'buscar', 'page'})
    qs = elegibles().exclude(pk=actor.pk)
    if 'buscar' in params:
        buscar = texto(params['buscar'], 100)
        qs = qs.filter(Q(username__icontains=buscar) | Q(first_name__icontains=buscar) | Q(last_name__icontains=buscar))
    # Estado de seguridad efectivo compartido (incluye caducidad de bloqueo),
    # aplicado antes de paginar/contar. select_related evita N+1.
    return [u for u in qs if sesion_operativa(u)]


def conversaciones(actor):
    actual = revalidar(actor)
    return ConversacionChat.objects.filter(participantes__usuario=actual).order_by('id')


def con_contadores(qs, actor, ahora=None):
    ahora = ahora or timezone.now()
    cursor = ParticipanteChat.objects.filter(conversacion_id=OuterRef('conversacion_id'), usuario_id=actor.pk).values('ultimo_leido_mensaje_id')[:1]
    # Subquery correlacionada al participante del usuario, sin consultas por mensaje.
    pendientes = MensajeChat.objects.filter(conversacion_id=OuterRef('pk'), vence_en__gt=ahora).exclude(autor_id=actor.pk).annotate(
        _leido=Coalesce(Subquery(cursor), Value(0))).filter(id__gt=F('_leido')).order_by().values('conversacion_id').annotate(n=Count('pk')).values('n')
    # Misma ventana de vigencia que historial y contador. No exponer archivo,
    # clave de idempotencia ni información de conversaciones de terceros.
    ultimo = MensajeChat.objects.filter(conversacion_id=OuterRef('pk'), vence_en__gt=ahora).order_by('-id')
    return qs.annotate(
        no_leidos=Coalesce(Subquery(pendientes, output_field=IntegerField()), Value(0)),
        preview_id=Subquery(ultimo.values('pk')[:1]),
        preview_autor=Subquery(ultimo.values('autor_id')[:1]),
        preview_texto=Subquery(ultimo.annotate(fragmento=Substr('texto', 1, 120)).values('fragmento')[:1]),
        preview_creado=Subquery(ultimo.values('creado_en')[:1]),
        preview_vence=Subquery(ultimo.values('vence_en')[:1]),
    )


def obtener(actor, pk, *, bloquear=False):
    qs = conversaciones(actor)
    if bloquear:
        qs = qs.select_for_update()
    obj = qs.filter(pk=pk).first()
    if obj is None:
        raise NotFound('Conversación no disponible.')
    if bloquear:
        revalidar(actor)
    return obj


def mensajes(actor, pk, params):
    query(params, {'antes_id'})
    obtener(actor, pk)
    qs = MensajeChat.objects.filter(conversacion_id=pk, conversacion__participantes__usuario_id=actor.pk,
        vence_en__gt=timezone.now()).select_related('archivo').order_by('-id')
    if 'antes_id' in params:
        qs = qs.filter(id__lt=id_url(params['antes_id']))
    return qs
