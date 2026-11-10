const database = db.getSiblingDB("fyag_documentos");
const esquemas = {
  auditoria_eventos: {
    bsonType: "object",
    properties: {
      accion: {
        bsonType: "string"
      },
      usuario_id: {
        bsonType: ["int", "long"]
      },
      obra_id: {
        bsonType: ["int", "long", "null"]
      },
      fecha: {
        bsonType: "date"
      },
      detalles: {
        bsonType: "object"
      }
    }
  },

  alertas_eventos: {
    bsonType: "object",
    properties: {
      tipo: {
        bsonType: "string"
      },
      mensaje: {
        bsonType: "string"
      },
      obra_id: {
        bsonType: ["int", "long"]
      },
      fecha: {
        bsonType: "date"
      },
      atendida: {
        bsonType: "bool"
      }
    }
  },

  documentos_metadata: {
    bsonType: "object",
    properties: {
      nombre: {
        bsonType: "string"
      },
      obra_id: {
        bsonType: ["int", "long"]
      },
      fecha: {
        bsonType: "date"
      },
      tipo_archivo: {
        bsonType: "string"
      },
      ruta_archivo: {
        bsonType: "string"
      }
    }
  }
};


for (const [nombre, esquema] of Object.entries(esquemas)) {

  const resultado = database.runCommand({
    collMod: nombre,
    validator: {
      $jsonSchema: esquema
    },
    validationLevel: "strict",
    validationAction: "error"
  });

  if (resultado.ok !== 1) {
    throw new Error(
      "Error al configurar las validaciones: " + nombre
    );
  }

  print("Validaciones configuradas: " + nombre);
}

print("Configuración de validaciones finalizada.");
