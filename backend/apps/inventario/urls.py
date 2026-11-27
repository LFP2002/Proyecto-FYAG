from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import ArticuloViewSet, ExistenciaViewSet, MovimientoViewSet, IngresoView
from .views_finanzas import FinanzasInventarioView
from .views_supervision import SupervisionInventarioView
from .views_bodega import BodegaOperativaView
from .views_disponibilidad import DisponibilidadSupervisorView
from .views_tecnico import TecnicoMaterialesView
from .views_materiales import OperacionesViewSet, EstadosValoracionViewSet
from .views_mermas_supervisor import MermasSupervisorView, MermaSupervisorDetalleView
from .views_mermas import MermasView, MermaDetalleView, MermaDecidirView
from .views_solicitudes_supervisor import SolicitudesSupervisorView, SolicitudSupervisorDetalleView
from .views_solicitudes import ArticulosSolicitablesView, SolicitudesMaterialesView, SolicitudDetalleView, SolicitudDecidirView

router = SimpleRouter()
router.register("articulos", ArticuloViewSet, basename="articulo-inventario")
router.register("existencias", ExistenciaViewSet, basename="existencia-inventario")
router.register("movimientos", MovimientoViewSet, basename="movimiento-inventario")
router.register('estados-valorizacion', EstadosValoracionViewSet, basename='estado-valorizacion')
urlpatterns = [path("disponibilidad/", DisponibilidadSupervisorView.as_view(), name="disponibilidad-supervisor"), path("finanzas/", FinanzasInventarioView.as_view(), name="inventario-finanzas"), path("tecnico-materiales/", TecnicoMaterialesView.as_view(), name="tecnico-materiales"), path("bodega/", BodegaOperativaView.as_view(), name="bodega-operativa"), path("ingresos/", IngresoView.as_view(), name="ingreso-inventario"), path("supervision-gerencial/", SupervisionInventarioView.as_view(), name="supervision-inventario")] + router.urls
for ruta, ambito in [('mermas-bodega', 'BODEGA'), ('mermas-obra', 'OBRA')]:
    urlpatterns += [
        path(ruta+'/', MermasView.as_view(ambito=ambito), name=ruta),
        path(ruta+'/<str:merma_id>/', MermaDetalleView.as_view(ambito=ambito), name=ruta+'-detalle'),
        path(ruta+'/<str:merma_id>/decidir/', MermaDecidirView.as_view(ambito=ambito), name=ruta+'-decidir'),
    ]
urlpatterns += [
    path('mermas-supervisor/', MermasSupervisorView.as_view(), name='mermas-supervisor'),
    path('mermas-supervisor/<str:merma_id>/', MermaSupervisorDetalleView.as_view(), name='merma-supervisor-detalle'),
    path('solicitudes-supervisor/', SolicitudesSupervisorView.as_view(), name='solicitudes-supervisor'),
    path('solicitudes-supervisor/<str:solicitud_id>/', SolicitudSupervisorDetalleView.as_view(), name='solicitud-supervisor-detalle'),
    path('articulos-solicitables/', ArticulosSolicitablesView.as_view(), name='articulos-solicitables'),
    path('solicitudes-materiales/', SolicitudesMaterialesView.as_view(), name='solicitudes-materiales'),
    path('solicitudes-materiales/<str:solicitud_id>/', SolicitudDetalleView.as_view(), name='solicitud-material-detalle'),
    path('solicitudes-materiales/<str:solicitud_id>/decidir/', SolicitudDecidirView.as_view(), name='solicitud-material-decidir'),
]
for ruta, tipo in [
    ('autorizaciones-entrega', 'AUTORIZACION_ENTREGA'), ('entregas', 'ENTREGA'),
    ('autorizaciones-devolucion', 'AUTORIZACION_DEVOLUCION'), ('devoluciones', 'DEVOLUCION'),
    ('valorizaciones', 'VALORIZACION'), ('regularizaciones-iniciales', 'REGULARIZACION'),
]:
    urlpatterns.append(path(ruta+'/', OperacionesViewSet.as_view({'get': 'list', 'post': 'create'}, tipo=tipo), name=ruta))
