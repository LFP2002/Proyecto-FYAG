FROM postgres:18
COPY postgres/provision.sh postgres/provision.sql /opt/fyag/
COPY postgres/10-fyag.sh /docker-entrypoint-initdb.d/
