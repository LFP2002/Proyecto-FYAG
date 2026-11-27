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
        self.assertIsNone(r.data['precio_unitario'])
        self.assertEqual(self.client.patch(path, {'articulo': None}, format='json').status_code, 400)
        r = self.client.patch(path, {'articulo':None,'descripcion':'Servicio','unidad':'hora','precio_unitario':'40.00'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual((r.data['articulo'],r.data['codigo_articulo'],r.data['unidad']), (None,'','hora'))

    def test_supervisor_scope_y_roles(self):
        a = self.material()
        self.autenticar(S)
        self.assertEqual(self.client.post(self.detalle()+'items/', self.datos(a), format='json').status_code, 404)
        propio = servicios.crear_presupuesto(cliente=self.cliente, descripcion='Propio', usuario=self.usuarios[S])
        self.assertEqual(self.client.post(self.detalle(propio)+'items/', self.datos(a), format='json').status_code, 403)
        respuesta = self.client.post(self.detalle(propio)+'items/', {'articulo':a.pk,'cantidad':'2.500','orden':2}, format='json')
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        result = respuesta.data
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

    def test_precios_pendientes_finanzas_y_traza(self):
        a = self.material()
        propio = servicios.crear_presupuesto(cliente=self.cliente, descripcion='Propio', usuario=self.usuarios[S])
        base = self.detalle(propio)
        self.autenticar(S)
        r = self.client.post(base+'items/', {'articulo':a.pk,'cantidad':'2.500','orden':1}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual((r.data['unidad'], r.data['precio_unitario'], r.data['subtotal']), (a.unidad, None, None))
        item = base+f"items/{r.data['id']}/"
        precio = item+'precio-comercial/'
        self.assertEqual(self.client.patch(item, {'precio_unitario':'0.00'}, format='json').status_code, 403)
        r = self.client.post(base+'enviar-finanzas/', {}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertIsNone(r.data['monto_neto'])
        self.assertEqual(self.client.patch(precio, {'precio_unitario':'500.00'}, format='json').status_code, 403)
        self.autenticar(G)
        resumen = self.client.get('/api/presupuestos/seguimiento-comercial/').data['resumen']['estados']['PENDIENTE_FINANZAS']
        self.assertEqual((resumen['sin_precio'], resumen['monto_neto']), (1, None))
        self.autenticar(AF)
        aprobar = base+'aprobar-finanzas/'
        self.assertEqual(self.client.post(aprobar, {}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(item, {'cantidad':'1.000'}, format='json').status_code, 409)
        self.assertEqual(self.client.patch(precio, {'cantidad':'1.000','precio_unitario':'500.00'}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(precio, {'precio_unitario':None}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(precio, {'precio_unitario':'0.00'}, format='json').data['subtotal'], '0.00')
        r = self.client.post(aprobar, {}, format='json')
        self.assertIn('monto_neto', r.data)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.client.patch(precio, {'precio_unitario':'500.00'}, format='json').data['subtotal'], '1250.00')
        version = self.client.get(base).data['version_comercial']
        self.assertEqual(self.client.post(aprobar, {}, format='json').status_code, 400)
        self.assertEqual(self.client.post(aprobar, {'version_comercial_esperada':version}, format='json').data['monto_neto'], '1250.00')
        self.assertEqual(self.client.patch(precio, {'precio_unitario':'600.00'}, format='json').status_code, 409)
        self.assertEqual(self.client.post(base+'enviar-cliente/', {}, format='json').status_code, 200)
        self.assertEqual(list(propio.eventos_precio.order_by('pk').values_list('precio_anterior','precio_nuevo','registrado_por_id')),
                         [(None, Decimal('0.00'), self.usuarios[AF].pk), (Decimal('0.00'), Decimal('500.00'), self.usuarios[AF].pk)])
        self.assertFalse(MovimientoInventario.objects.exists())

    def test_envio_no_admite_precio_pendiente_incluso_si_estado_ya_aprobado(self):
        from apps.comercial.models import Presupuesto
        linea = self.alta(self.material())
        self.assertEqual(self.accion('enviar-finanzas').status_code, 200)
        version = self.client.get(self.detalle()).data['version_comercial']
        self.assertEqual(self.accion('aprobar-finanzas', datos={'version_comercial_esperada': version}).status_code, 200)
        PresupuestoItem.objects.filter(pk=linea['id']).update(precio_unitario=None)
        self.assertEqual(self.accion('enviar-cliente').status_code, 400)
        self.assertEqual(Presupuesto.objects.get(pk=self.presupuesto.pk).estado, 'APROBADO_FINANZAS')

    def test_aprobacion_rechaza_huella_obsoleta_y_exige_revision(self):
        linea = self.alta(self.material())
        self.assertEqual(self.accion('enviar-finanzas').status_code, 200)
        version = self.client.get(self.detalle()).data['version_comercial']
        precio = self.detalle()+f"items/{linea['id']}/precio-comercial/"
        self.assertEqual(self.client.patch(precio, {'precio_unitario':'9000.00'}, format='json').status_code, 200)
        eventos = self.presupuesto.eventos.count()
        r = self.accion('aprobar-finanzas', datos={'version_comercial_esperada':version})
        self.assertEqual(r.status_code, 409, r.data)
        self.assertEqual(r.data['code'], 'version_comercial_obsoleta')
        self.presupuesto.refresh_from_db()
        self.assertEqual(self.presupuesto.estado, 'PENDIENTE_FINANZAS')
        self.assertEqual(self.presupuesto.eventos.count(), eventos)
        nueva = self.client.get(self.detalle()).data['version_comercial']
        self.assertNotEqual(version, nueva)
        self.assertEqual(self.accion('aprobar-finanzas', datos={'version_comercial_esperada':nueva}).status_code, 200)

    def test_aprobacion_legada_impide_total_cero(self):
        self.alta(self.material())
        self.presupuesto.items.update(precio_unitario=Decimal('0.00'))
        self.presupuesto.estado = 'PENDIENTE_GERENCIA'
        self.presupuesto.politica_aprobacion = 'GERENCIA_LEGADA'
        self.presupuesto.requiere_aprobacion_gerencia = True
        self.presupuesto.save()
        version = self.client.get(self.detalle()).data['version_comercial']
        r = self.accion('aprobar-finanzas', datos={'version_comercial_esperada':version})
        self.assertEqual(r.status_code, 400, r.data)
        self.assertIn('monto_neto', r.data)
        self.presupuesto.refresh_from_db()
        self.assertEqual(self.presupuesto.estado, 'PENDIENTE_GERENCIA')
