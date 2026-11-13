// Ampliación 012B explícita: NO cambia claves de usuarios ni la colección 012A.
(() => {
  const env = process.env;
  const admin = db.getSiblingDB("admin");
  if (!admin.auth(env.MONGO_INITDB_ROOT_USERNAME, env.MONGO_INITDB_ROOT_PASSWORD)) throw new Error("Bootstrap rechazado");
  const nombre = env.FYAG_MONGO_DB || "fyag_documentos";
  if (!["fyag_documentos", "fyag_documentos_test"].includes(nombre)) throw new Error("Base no permitida");
  const target = db.getSiblingDB(nombre);
  const fs = require("fs");
  const validator = JSON.parse(fs.readFileSync(env.FYAG_ADJUNTOS_SCHEMA || "/opt/fyag/adjuntos_esquema.json", "utf8"));
  const name = "adjuntos_metadata";
  if (!target.getCollectionNames().includes(name)) target.createCollection(name, {validator, validationLevel: "strict", validationAction: "error"});
  else {
    if (target.getCollection(name).countDocuments({$nor: [validator]}) !== 0) throw new Error("Adjuntos incompatibles: detener sin borrar");
    if (target.runCommand({collMod: name, validator, validationLevel: "strict", validationAction: "error"}).ok !== 1) throw new Error("Bootstrap no completado");
  }
  target.getCollection(name).createIndex({tipo: 1, destino_id: 1, registrado_en: -1, adjunto_id: -1}, {name: "adjuntos_tipo_destino_fecha"});
  const role = "fyag_documentos_aplicacion";
  if (!target.getRole(role)) throw new Error("Ejecutar primero bootstrap 012A");
  target.updateRole(role, {roles: [], privileges: [
    {resource: {db: nombre, collection: "documentos_metadata"}, actions: ["find", "insert", "update", "listIndexes"]},
    {resource: {db: nombre, collection: name}, actions: ["find", "insert", "update", "listIndexes"]},
    {resource: {db: nombre, collection: ""}, actions: ["listCollections"]}
  ]});
  print("Bootstrap adjuntos v1 correcto; credenciales y colección 012A conservadas");
})();
