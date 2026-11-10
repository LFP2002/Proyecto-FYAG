const database = db.getSiblingDB("fyag_documentos");

// Verificar que las colecciones existan.
const colecciones = [
  "auditoria_eventos",
  "alertas_eventos",
  "documentos_metadata"
];

for (const nombre of colecciones) {
  if (!database.getCollectionNames().includes(nombre)) {
    throw new Error(
      "La colección no existe: " + nombre +
      ". Ejecuta primero init_mongodb.js."
    );
  }
}

const auditoria = database.getCollection("auditoria_eventos");

auditoria.createIndex(
  { usuario_id: 1, fecha: -1 },
  { name: "idx_auditoria_usuario_fecha" }
);

auditoria.createIndex(
  { accion: 1, fecha: -1 },
  { name: "idx_auditoria_accion_fecha" }
);

const alertas = database.getCollection("alertas_eventos");

alertas.createIndex(
  { obra_id: 1, fecha: -1 },
  { name: "idx_alertas_obra_fecha" }
);

alertas.createIndex(
  { atendida: 1, fecha: -1 },
  { name: "idx_alertas_estado_fecha" }
);

const documentos = database.getCollection("documentos_metadata");

documentos.createIndex(
  { obra_id: 1, fecha: -1 },
  { name: "idx_documentos_obra_fecha" }
);

documentos.createIndex(
  { tipo_archivo: 1 },
  { name: "idx_documentos_tipo_archivo" }
);

print("\nÍndices de MongoDB configurados correctamente.");

for (const nombre of colecciones) {
  print("\nColección: " + nombre);

  const indices = database
    .getCollection(nombre)
    .getIndexes();

  indices.forEach((indice) => {
    print(" - " + indice.name);
  });
}

print("\nConfiguración de índices finalizada.");
