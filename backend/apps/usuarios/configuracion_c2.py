"""C2 solo admite el laboratorio dedicado, nunca un modo productivo."""
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def habilitado():
    value = getattr(settings, "BLOQUEOS_C2_HABILITADO", False)
    if type(value) is not bool:
        raise ImproperlyConfigured("C2 requiere habilitación booleana explícita.")
    if not value:
        return False
    db = settings.DATABASES["default"]
    ids = getattr(settings, "BLOQUEOS_C2_TI_QA_IDS", ())
    if (getattr(settings, "BLOQUEOS_C2_ENTORNO", "") != "QA_AISLADO_C2"
        or db["ENGINE"] != "django.db.backends.postgresql"
        or db["NAME"] not in {"fyag_spec018c_c2_qa", "test_fyag_spec018c_c2_qa"}
        or db["HOST"] != "postgres" or db.get("ATOMIC_REQUESTS", False)
        or type(ids) is not tuple or len(ids) != 2 or ids[0] == ids[1]
        or any(type(pk) is not int or not 0 < pk <= 9223372036854775807 for pk in ids)
        or getattr(settings, "BLOQUEOS_C2_RECUPERACION_QA_CONFIRMADA", False) is not True
        or getattr(settings, "BLOQUEOS_C2_RIESGO_DOS_QA_ACEPTADO", False) is not True
        or getattr(settings, "BLOQUEOS_C2_RESPUESTAS", "") != "401_GENERICO"
        or getattr(settings, "BLOQUEOS_C2_SESIONES_TEMPORALES", "") != "REVOCAR_TODAS_QA"):
        raise ImproperlyConfigured("Activación C2 denegada: falta aislamiento, recuperadoras QA o política explícita; producción no autorizada.")
    return True


def relaciones_seguridad():
    return ("seguridad_credencial", "estado_acceso") if bloqueos_activos() else ("seguridad_credencial",)


def perfil_bloqueos():
    perfil = settings.FYAG_BLOQUEOS_PERFIL
    qa = habilitado()
    if perfil not in {'deshabilitado', 'qa_c2', 'produccion'} or (perfil == 'qa_c2' and not qa) or (qa and perfil == 'produccion'):
        raise ImproperlyConfigured('Perfiles de bloqueo incompatibles o inválidos.')
    # El selector QA histórico sigue siendo válido con sus guardas originales.
    if qa:
        return 'qa_c2'
    if perfil == 'produccion':
        from .preflight_bloqueos import validar_configuracion_productiva
        validar_configuracion_productiva()
    return perfil


def bloqueos_activos():
    return perfil_bloqueos() != 'deshabilitado'
