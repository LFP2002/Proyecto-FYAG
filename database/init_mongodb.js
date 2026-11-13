// Ejecutar explícitamente con identidad bootstrap. No limpia datos ni crea fuentes ajenas.
(() => {
  const fs = require("fs");
  const nombre = process.env.FYAG_MONGO_DB || "fyag_documentos";
  if (!["fyag_documentos", "fyag_documentos_test"].includes(nombre)) throw new Error("Base no permitida");
  const target = db.getSiblingDB(nombre);
  const schemaPath = process.env.FYAG_MONGO_SCHEMA || "/opt/fyag/esquema.json";
  const validator = JSON.parse(fs.readFileSync(schemaPath, "utf8"));
  const name = "documentos_metadata";
  if (!target.getCollectionNames().includes(name)) {
    target.createCollection(name, {validator, validationLevel: "strict", validationAction: "error"});
  } else {
    // No migrar ni borrar documentos incompatibles por sorpresa.
    if (target.getCollection(name).countDocuments({$nor: [validator]}) !== 0) {
      throw new Error("Documentos incompatibles: inspeccionar y respaldar antes de transición explícita");
    }
    const result = target.runCommand({collMod: name, validator, validationLevel: "strict", validationAction: "error"});
    if (result.ok !== 1) throw new Error("Bootstrap no completado");
  }
  load((process.env.FYAG_MONGO_SCRIPTS_DIR || "/opt/fyag/database") + "/indices_mongodb.js");
  print("Bootstrap documental v1 correcto (sin replicación de Auditoría/Alertas)");
})();
