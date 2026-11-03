#!/bin/sh
# Copia consistente do banco (segura com WAL), compactada e mantida por 14 dias.
# O banco guarda telefones e mensagens, então as cópias só podem ser lidas pelo dono.
set -eu

DB_PATH="${DB_PATH:-/opt/chatbot/database.db}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/chatbot}"
RETENTION_DAYS=14
BACKUP_FILE="$BACKUP_DIR/db-$(date +%F).sqlite"

umask 077
sqlite3 "$DB_PATH" ".backup '$BACKUP_FILE'"
gzip -f "$BACKUP_FILE"
find "$BACKUP_DIR" -name 'db-*.sqlite.gz' -mtime +"$RETENTION_DAYS" -delete
