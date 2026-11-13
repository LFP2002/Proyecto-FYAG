(() => {
  try {
    const target = db.getSiblingDB(process.env.FYAG_MONGO_DB || "fyag_documentos");
    if (!target.auth(process.env.FYAG_MONGO_USER, process.env.FYAG_MONGO_PASSWORD)) quit(1);
    if (target.runCommand({ping: 1}).ok !== 1) quit(1);
    // ping solo no demuestra autorización: leer la colección también.
    target.documentos_metadata.findOne({}, {_id: 1});
    quit(0);
  } catch (_) { quit(1); }
})();
