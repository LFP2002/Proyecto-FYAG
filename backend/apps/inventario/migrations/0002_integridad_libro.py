"""Saldo inicial, libro append-only y conciliación de saldo al commit PostgreSQL."""
from django.db import migrations


SQL = """
CREATE FUNCTION fyag_inventario_existencia_inicial() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO inventario_existenciainventario (articulo_id, saldo) VALUES (NEW.id, 0);
  RETURN NEW;
END; $$;
CREATE TRIGGER fyag_inventario_existencia_inicial AFTER INSERT ON inventario_articuloinventario
FOR EACH ROW EXECUTE FUNCTION fyag_inventario_existencia_inicial();

CREATE FUNCTION fyag_inventario_proteger_articulo() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Use desactivacion; no eliminar articulo' USING ERRCODE='23514';
  END IF;
  IF (NEW.codigo IS DISTINCT FROM OLD.codigo OR NEW.unidad IS DISTINCT FROM OLD.unidad)
     AND EXISTS (SELECT 1 FROM inventario_movimientoinventario WHERE articulo_id=OLD.id) THEN
    RAISE EXCEPTION 'Identidad con movimientos inmutable' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END; $$;
CREATE TRIGGER fyag_inventario_proteger_articulo BEFORE UPDATE OR DELETE ON inventario_articuloinventario
FOR EACH ROW EXECUTE FUNCTION fyag_inventario_proteger_articulo();

CREATE FUNCTION fyag_inventario_no_mutar() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'Libro de inventario inmutable' USING ERRCODE='23514';
END; $$;
CREATE TRIGGER fyag_inventario_libro_inmutable BEFORE UPDATE OR DELETE ON inventario_movimientoinventario
FOR EACH ROW EXECUTE FUNCTION fyag_inventario_no_mutar();
CREATE TRIGGER fyag_inventario_existencia_no_borrar BEFORE DELETE ON inventario_existenciainventario
FOR EACH ROW EXECUTE FUNCTION fyag_inventario_no_mutar();

CREATE FUNCTION fyag_inventario_aplicar_ingreso() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE disponible numeric; habilitado boolean;
BEGIN
  SELECT activo INTO habilitado FROM inventario_articuloinventario WHERE id=NEW.articulo_id FOR UPDATE;
  IF habilitado IS DISTINCT FROM true THEN
    RAISE EXCEPTION 'Articulo inexistente o inactivo' USING ERRCODE='23514';
  END IF;
  SELECT saldo INTO disponible FROM inventario_existenciainventario WHERE articulo_id=NEW.articulo_id FOR UPDATE;
  IF disponible IS NULL OR NEW.saldo_anterior IS DISTINCT FROM disponible
     OR NEW.saldo_posterior IS DISTINCT FROM disponible + NEW.cantidad THEN
    RAISE EXCEPTION 'Saldo o snapshots incoherentes' USING ERRCODE='23514';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM usuarios_usuario WHERE id=NEW.actor_id AND is_active AND rol='BODEGUERO') THEN
    RAISE EXCEPTION 'Actor de ingreso no autorizado' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END; $$;
CREATE TRIGGER fyag_inventario_validar_ingreso BEFORE INSERT ON inventario_movimientoinventario
FOR EACH ROW EXECUTE FUNCTION fyag_inventario_aplicar_ingreso();

CREATE FUNCTION fyag_inventario_saldo_ingreso() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  UPDATE inventario_existenciainventario SET saldo=NEW.saldo_posterior WHERE articulo_id=NEW.articulo_id;
  RETURN NEW;
END; $$;
CREATE TRIGGER fyag_inventario_saldo_ingreso AFTER INSERT ON inventario_movimientoinventario
FOR EACH ROW EXECUTE FUNCTION fyag_inventario_saldo_ingreso();

CREATE FUNCTION fyag_inventario_conciliar() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE actual numeric; libro numeric;
BEGIN
  IF TG_OP='UPDATE' AND NEW.articulo_id IS DISTINCT FROM OLD.articulo_id THEN
    RAISE EXCEPTION 'Existencia no puede cambiar de articulo' USING ERRCODE='23514';
  END IF;
  SELECT saldo INTO actual FROM inventario_existenciainventario WHERE articulo_id=NEW.articulo_id;
  SELECT COALESCE(sum(cantidad),0) INTO libro FROM inventario_movimientoinventario WHERE articulo_id=NEW.articulo_id;
  IF actual IS NULL OR actual IS DISTINCT FROM libro THEN
    RAISE EXCEPTION 'Saldo debe corresponder al libro' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END; $$;
CREATE CONSTRAINT TRIGGER fyag_inventario_conciliar AFTER INSERT OR UPDATE ON inventario_existenciainventario
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION fyag_inventario_conciliar();
"""

REVERSE = """
DROP TRIGGER fyag_inventario_conciliar ON inventario_existenciainventario;
DROP FUNCTION fyag_inventario_conciliar();
DROP TRIGGER fyag_inventario_saldo_ingreso ON inventario_movimientoinventario;
DROP FUNCTION fyag_inventario_saldo_ingreso();
DROP TRIGGER fyag_inventario_validar_ingreso ON inventario_movimientoinventario;
DROP FUNCTION fyag_inventario_aplicar_ingreso();
DROP TRIGGER fyag_inventario_existencia_no_borrar ON inventario_existenciainventario;
DROP TRIGGER fyag_inventario_libro_inmutable ON inventario_movimientoinventario;
DROP FUNCTION fyag_inventario_no_mutar();
DROP TRIGGER fyag_inventario_proteger_articulo ON inventario_articuloinventario;
DROP FUNCTION fyag_inventario_proteger_articulo();
DROP TRIGGER fyag_inventario_existencia_inicial ON inventario_articuloinventario;
DROP FUNCTION fyag_inventario_existencia_inicial();
"""


class Migration(migrations.Migration):
    dependencies = [("inventario", "0001_initial")]
    operations = [migrations.RunSQL(SQL, REVERSE)]
