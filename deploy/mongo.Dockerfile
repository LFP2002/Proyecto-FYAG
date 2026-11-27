FROM mongo:8.0
COPY database/*.js /opt/fyag/database/
COPY backend/apps/documentos/esquema.json /opt/fyag/esquema.json
COPY backend/apps/adjuntos/esquema.json /opt/fyag/adjuntos_esquema.json
COPY database/usuarios_mongodb.js /docker-entrypoint-initdb.d/10-fyag.js
COPY deploy/mongo-start.sh /usr/local/bin/fyag-mongo
ENTRYPOINT ["sh", "/usr/local/bin/fyag-mongo"]
CMD ["mongod", "--auth", "--bind_ip_all"]
