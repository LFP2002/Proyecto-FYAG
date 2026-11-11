"""Parches locales 004A. Ejecutar una vez, desde el contenedor backend.

No crea commits ni modifica specs. Comprueba todos los fragmentos antes de escribir.
Si el proyecto ya difiere de la base conocida, aborta antes de hacer cambios.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # /app


class Cambio:
    def __init__(self, path):
        self.path = ROOT / path
        if not self.path.is_file():
            raise SystemExit(f"Falta archivo esperado: {self.path}")
        self.original = self.path.read_text(encoding="utf-8")
        self.nuevo = self.original

    def reemplazar(self, anterior, siguiente, descripcion):
        if siguiente in self.nuevo:
            print(f"Ya aplicado: {descripcion}")
            return
        if anterior in self.nuevo:
            if self.nuevo.count(anterior) != 1:
                raise SystemExit(f"Fragmento ambiguo: {descripcion}")
            self.nuevo = self.nuevo.replace(anterior, siguiente, 1)
            return
        raise SystemExit(
            f"No se encontró el fragmento esperado: {descripcion}\n"
            "No se escribió ningún archivo. Revisa los cambios locales."
        )


modelos = Cambio("apps/obras/models.py")
if modelos.nuevo.count("datos_anteriores = models.JSONField(default=dict, blank=True)") != 2:
    raise SystemExit("Primero aplica la corrección de JSONField y migración 0003.")
modelos.reemplazar(
    'Q(tipo="CREACION", estado_anterior__isnull=True,\n'
    '                      estado_nuevo="PLANIFICADA", motivo="")',
    'Q(tipo="CREACION", estado_anterior__isnull=True,\n'
    '                      estado_nuevo="PLANIFICADA")',
    "Permitir motivo en evento de creación",
)
modelos.reemplazar(
    '''        if errores:
            raise ValidationError(errores)


class CategoriaServicioEvento''',
    '''        if (
            self.tipo == self.Tipo.CREACION
            and isinstance(self.datos_nuevos, dict)
            and self.datos_nuevos.get("tecnico_responsable") is not None
            and not self.motivo
        ):
            errores["motivo"] = "Obligatorio al asignar técnico al crear."
        if errores:
            raise ValidationError(errores)


class CategoriaServicioEvento''',
    "Motivo obligatorio si creación incluye técnico",
)

excepciones = Cambio("apps/comercial/exceptions.py")
excepciones.reemplazar(
    '\n\nclass DatosInvalidos(ErrorPresupuesto):',
    '''

class PresupuestoUtilizado(ErrorPresupuesto):
    codigo = "presupuesto_utilizado"
    mensaje = "No se puede anular un presupuesto con obra asociada."


class DatosInvalidos(ErrorPresupuesto):''',
    "Excepción comercial presupuesto_utilizado",
)

comercial = Cambio("apps/comercial/services_presupuestos.py")
comercial.reemplazar(
    '''    RecursoNoEncontrado,
)''',
    '''    RecursoNoEncontrado,
    PresupuestoUtilizado,
)''',
    "Importar excepción de uso operativo",
)
comercial.reemplazar(
    '''    if anterior not in origenes:
        raise EstadoIncompatible()
    motivo = _motivo_normalizado(motivo, motivo_obligatorio)''',
    '''    if anterior not in origenes:
        raise EstadoIncompatible()
    if destino == Estado.ANULADO:
        # Ambos flujos bloquean primero el mismo presupuesto persistido.
        # Importación local para evitar acoplar la carga inicial de Comercial.
        from apps.obras.models import Obra
        if Obra.objects.filter(presupuesto_id=actual.pk).exists():
            raise PresupuestoUtilizado()
    motivo = _motivo_normalizado(motivo, motivo_obligatorio)''',
    "Bloquear anulación cuando existe una obra",
)

vistas = Cambio("apps/comercial/views_presupuestos.py")
vistas.reemplazar(
    '''    RecursoNoEncontrado,
)''',
    '''    RecursoNoEncontrado,
    PresupuestoUtilizado,
)''',
    "Importar la excepción para traducción HTTP",
)
vistas.reemplazar(
    '''    if isinstance(error, EstadoIncompatible):
        return ConflictoPresupuesto(error)''',
    '''    if isinstance(error, (EstadoIncompatible, PresupuestoUtilizado)):
        return ConflictoPresupuesto(error)''',
    "Mapear presupuesto_utilizado a HTTP 409",
)

cambios = [modelos, excepciones, comercial, vistas]
for archivo in cambios:
    if archivo.original != archivo.nuevo:
        # Solo después de validar TODOS los patrones se escribe.
        archivo.path.write_text(archivo.nuevo, encoding="utf-8", newline="")
        print(f"Actualizado: {archivo.path.relative_to(ROOT)}")
    else:
        print(f"Sin cambio: {archivo.path.relative_to(ROOT)}")
print("Parches 004A aplicados. Genera la nueva migración de Obras y ejecuta tests.")
