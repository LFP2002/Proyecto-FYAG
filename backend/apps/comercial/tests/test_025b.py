"""SPEC-025B: vínculos históricos, permisos y aislamiento del inventario."""
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from apps.comercial.models import PresupuestoItem
from apps.comercial import services_presupuestos as servicios
from apps.inventario.models import ArticuloInventario, ExistenciaInventario, MovimientoInventario
from apps.inventario.services import crear_articulo, editar_articulo
from apps.usuarios.models import Usuario
from .test_presupuesto_api import AF, G, PresupuestoAPIBase, datos_item

S = Usuario.Rol.SUPERVISOR_OBRAS
B = Usuario.Rol.BODEGUERO


class MaterialesPresupuesto025B(PresupuestoAPIBase):
    def material(self, codigo='qa25-cobre', activo=True):
        return crear_articulo({
            'codigo': codigo, 'nombre': 'Tubería de cobre',
            'unidad': 'm', 'activo': activo,
        }, self.usuarios[B])

    def datos(self, articulo, **cambios):
        return datos_item(orden=2, descripcion=articulo.nombre, unidad=articulo.unidad,
                          articulo=articulo.pk, precio_unitario='8500.00', **cambios)

    def alta(self, articulo, presupuesto=None):
        r = self.client.post(self.detalle(presupuesto)+'items/', self.datos(articulo), format='json')
        self.assertEqual(r.status_code, 201, r.data)
        return r.data

    def test_vinculo_precio_independiente_y_sin_stock(self):
        a = self.material()
        saldo = ExistenciaInventario.objects.get(articulo=a).saldo
        antes = MovimientoInventario.objects.count()
        result = self.alta(a)
        self.assertEqual(result['articulo'], a.pk)
        self.assertEqual(result['codigo_articulo'], a.codigo)
        self.assertEqual(result['precio_unitario'], '8500.00')
        self.assertEqual(result['subtotal'], '21250.00')
        detalle = self.client.get(self.detalle()).data
        self.assertIsNone(detalle['items'][0]['articulo'])
        self.assertEqual(detalle['items'][0]['codigo_articulo'], '')
        self.assertEqual(detalle['items'][1]['articulo'], a.pk)
        self.assertEqual(self.accion('enviar-finanzas').status_code, 200)
        self.assertEqual(MovimientoInventario.objects.count(), antes)
        self.assertEqual(ExistenciaInventario.objects.get(articulo=a).saldo, saldo)

    def test_inactivo_inexistente_id_estricto_y_codigo_no_editable(self):
        a = self.material(activo=False)
        for invalido in (a.pk, 9223372036854775807, True, str(a.pk), 0):
            with self.subTest(articulo=invalido):
                data = self.datos(a)
                data['articulo'] = invalido
                self.assertEqual(self.client.post(self.detalle()+'items/', data, format='json').status_code, 400)
        data = self.datos(a)
        data['codigo_articulo'] = 'inventado'
        self.assertEqual(self.client.post(self.detalle()+'items/', data, format='json').status_code, 400)
        self.assertEqual(self.presupuesto.items.count(), 1)

    def test_snapshot_rechaza_catalogo_obsoleto_y_preserva_historia(self):
        a = self.material()
        data = self.datos(a)
        data['unidad'] = 'kg'
        self.assertEqual(self.client.post(self.detalle()+'items/', data, format='json').status_code, 400)
        item = self.alta(a)
        path = self.detalle()+f"items/{item['id']}/"
        editar_articulo(a.pk, {'nombre':'Nombre nuevo','activo':False}, self.usuarios[B])
        edit = self.client.patch(path, {'articulo':a.pk,'precio_unitario':'9000.00'}, format='json')
        self.assertEqual(edit.status_code, 200, edit.data)
        self.assertEqual(edit.data['descripcion'], 'Tubería de cobre')
        self.assertEqual(edit.data['codigo_articulo'], a.codigo)
        self.assertEqual(self.client.patch(path, {'unidad':'kg'}, format='json').status_code, 400)
        self.assertEqual(self.accion('enviar-finanzas').status_code, 200)
        self.assertEqual(self.client.patch(path, {'articulo':None}, format='json').status_code, 409)
        self.assertEqual(self.accion('rechazar-finanzas', datos={'motivo':'Revisar'}).status_code, 200)
        rev = self.accion('crear-revision')
        self.assertEqual(rev.status_code, 201, rev.data)
        copia = rev.data['items'][1]
        self.assertEqual((copia['articulo'], copia['codigo_articulo'], copia['descripcion'], copia['precio_unitario']),
                         (a.pk, a.codigo, 'Tubería de cobre', '9000.00'))

    def test_cambio_de_material_y_desvinculacion(self):
        a = self.material()
        b = self.material('qa25-otro')
        item = self.alta(a)
        path = self.detalle()+f"items/{item['id']}/"
        r = self.client.patch(path, {'articulo':b.pk}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['codigo_articulo'], b.codigo)
        r = self.client.patch(path, {'articulo':None,'descripcion':'Servicio','unidad':'hora'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual((r.data['articulo'],r.data['codigo_articulo'],r.data['unidad']), (None,'','hora'))

    def test_supervisor_scope_y_roles(self):
        a = self.material()
        self.autenticar(S)
        self.assertEqual(self.client.post(self.detalle()+'items/', self.datos(a), format='json').status_code, 404)
        propio = servicios.crear_presupuesto(cliente=self.cliente, descripcion='Propio', usuario=self.usuarios[S])
        result = self.alta(a, propio)
        path = self.detalle(propio)+f"items/{result['id']}/"
        for rol in (G, B, Usuario.Rol.TECNICO, Usuario.Rol.ADMINISTRADOR_TI):
            self.autenticar(rol)
            self.assertEqual(self.client.patch(path, {'articulo':None}, format='json').status_code, 403)

    def test_constraint_y_proteccion(self):
        a = self.material()
        item = self.alta(a)
        with self.assertRaises(ProtectedError):
            ArticuloInventario.objects.get(pk=a.pk).delete()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PresupuestoItem.objects.filter(pk=item['id']).update(codigo_articulo='')
