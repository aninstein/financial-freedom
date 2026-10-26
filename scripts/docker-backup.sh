#!/usr/bin/env bash
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."
mkdir -p .runtime/backups
backup=".runtime/backups/financial-freedom-$(date +%Y%m%d-%H%M%S).sql"
docker compose exec -T mysql sh -c 'MYSQL_PWD="$(cat /run/secrets/mysql_password)" exec mysqldump --user=financial_freedom --single-transaction --no-tablespaces --routines --triggers financial_freedom' > "$backup"
test -s "$backup"
[[ "$(tail -n 1 "$backup")" == '-- Dump completed on '* ]]
chmod 600 "$backup"
printf 'MySQL backup: %s\n' "$backup"
wiki_backup="${backup%.sql}-llm-wiki.tar.gz"
docker compose exec -T web sh -c 'if [ -d /app/data/llm-wiki ]; then tar -C /app/data -czf - llm-wiki; fi' > "$wiki_backup"
if test -s "$wiki_backup"; then
  chmod 600 "$wiki_backup"
  printf 'Investment wiki backup: %s\n' "$wiki_backup"
else
  rm -f "$wiki_backup"
fi
