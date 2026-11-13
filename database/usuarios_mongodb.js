// Solo operación bootstrap, nunca cargado por Django ni por el usuario aplicación.
(() => {
  const env = process.env;
  const admin = db.getSiblingDB("admin");
  const root = env.MONGO_INITDB_ROOT_USERNAME;
  const password = env.MONGO_INITDB_ROOT_PASSWORD;
  const nombre = env.FYAG_MONGO_DB || "fyag_documentos";
  if (!root || !password || !env.FYAG_MONGO_USER || !env.FYAG_MONGO_PASSWORD ||
      root === env.FYAG_MONGO_USER || !["fyag_documentos", "fyag_documentos_test"].includes(nombre)) {
    throw new Error("Configuración bootstrap incompleta o identidad no separada");
  }
  if (env.FYAG_MONGO_BOOTSTRAP_EXISTING === "1") {
    // EXCLUSIVAMENTE docker exec local sobre volumen antiguo aún sin --auth,
    // tras inventario y respaldo. No lanzar como migración automática.
    if (!admin.getUser(root)) admin.createUser({user: root, pwd: password, roles: ["root"]});
  }
  if (!admin.auth(root, password)) throw new Error("Autenticación bootstrap rechazada");
  const target = db.getSiblingDB(nombre);
  const role = "fyag_documentos_aplicacion";
  const privileges = [
    {resource: {db: nombre, collection: "documentos_metadata"}, actions: ["find", "insert", "update", "listIndexes"]},
    {resource: {db: nombre, collection: ""}, actions: ["listCollections"]}
  ];
  if (target.getRole(role)) target.updateRole(role, {privileges, roles: []});
  else target.createRole({role, privileges, roles: []});
  if (target.getUser(env.FYAG_MONGO_USER)) {
    target.updateUser(env.FYAG_MONGO_USER, {pwd: env.FYAG_MONGO_PASSWORD, roles: [{role, db: nombre}]});
  } else {
    target.createUser({user: env.FYAG_MONGO_USER, pwd: env.FYAG_MONGO_PASSWORD, roles: [{role, db: nombre}]});
  }
  load((env.FYAG_MONGO_SCRIPTS_DIR || "/opt/fyag/database") + "/init_mongodb.js");
})();
