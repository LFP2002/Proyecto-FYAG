(() => {
  const nombre = process.env.FYAG_MONGO_DB || "fyag_documentos";
  if (!["fyag_documentos", "fyag_documentos_test"].includes(nombre)) throw new Error("Base no permitida");
  db.getSiblingDB(nombre).documentos_metadata.createIndex(
    {obra_id: 1, creado_en: -1, evidencia_id: -1}, {name: "documentos_obra_creacion_evidencia"}
  );
})();
