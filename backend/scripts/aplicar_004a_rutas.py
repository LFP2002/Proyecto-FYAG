"""Añadir inclusión de rutas de Obras sin sobrescribir config/urls.py.

Ejecutar una vez dentro de /app (contenedor backend), después de instalar archivos.
Es seguro volver a ejecutarlo: no duplica la inclusión.
"""

from pathlib import Path


archivo = Path("config/urls.py")
texto = archivo.read_text(encoding="utf-8")
objetivo = '    path("api/", include("apps.obras.urls")),\n'
if objetivo in texto:
    print("Rutas de Obras ya presentes; sin cambios.")
else:
    anterior = '    path("api/", include("apps.comercial.urls")),\n'
    if texto.count(anterior) != 1:
        raise SystemExit("No coincide el patrón esperado en config/urls.py. No se modificó.")
    texto = texto.replace(anterior, anterior + objetivo)
    archivo.write_text(texto, encoding="utf-8")
    print("Rutas Obras 004A añadidas a config/urls.py.")
