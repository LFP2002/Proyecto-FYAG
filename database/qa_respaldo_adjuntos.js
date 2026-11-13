// Opt-in EXCLUSIVO compose.adjuntos-qa.yaml. Sin --drop ni borrado de datos.
(() => {
  const env = process.env;
  if (env.FYAG_ADJUNTOS_RECOVERY_QA !== "1" || env.FYAG_MONGO_DB !== "fyag_documentos_test") throw new Error("Solo laboratorio QA aislado");
  const fs = require("fs"), cp = require("child_process");
  const temporal = fs.mkdtempSync("/tmp/fyag-qa-backup-");
  const config = temporal + "/config.json";
  try {
    fs.writeFileSync(config, JSON.stringify({password: env.MONGO_INITDB_ROOT_PASSWORD}), {mode: 0o600});
    const restaurar = env.FYAG_QA_RESTAURAR === "1";
    const args = ["--config", config, "--username", env.MONGO_INITDB_ROOT_USERNAME, "--authenticationDatabase", "admin", "--archive=/backup/mongo.archive"];
    if (restaurar) args.push("--nsInclude=fyag_documentos_test.*");
    else args.push("--db=fyag_documentos_test");
    cp.execFileSync(restaurar ? "mongorestore" : "mongodump", args, {stdio: "pipe"});
    print(restaurar ? "QA Mongo restaurado sin drop" : "QA Mongo respaldado");
  } finally {
    fs.unlinkSync(config);
    fs.rmdirSync(temporal);
  }
})();
