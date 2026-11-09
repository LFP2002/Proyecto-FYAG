
const database = db.getSiblingDB("fyag_documentos");

const colecciones = [
  "auditoria_eventos",
  "alertas_eventos",
  "documentos_metadata"
];

colecciones.forEach((nombre) => {
  if (!database.getCollectionNames().includes(nombre)) {
    database.createCollection(nombre);
    print("Colección creada: " + nombre);
  } else {
    print("Colección existente: " + nombre);
  }
});

print("Colecciones disponibles:");
printjson(database.getCollectionNames());
