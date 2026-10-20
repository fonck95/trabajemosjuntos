#!/usr/bin/env bash
# Descarga todos los contratos de entidades de Yondó desde SECOP Integrado (datos.gov.co, dataset rpmr-utcd)
# Uso: scripts/descargar_secop.sh <carpeta_salida>
set -euo pipefail
OUT="${1:-data/secop/raw}"
mkdir -p "$OUT"
curl -sS -G "https://www.datos.gov.co/resource/rpmr-utcd.json" \
  --data-urlencode "\$limit=50000" \
  --data-urlencode "\$where=municipio_entidad='Yondó' OR upper(nombre_de_la_entidad) like '%YOND%'" \
  -o "$OUT/integrado.json"
python3 -c "import json,sys;print(len(json.load(open(sys.argv[1]))),'registros')" "$OUT/integrado.json"
# Luego: python3 scripts/secop_analisis.py "$OUT" && mv "$OUT/secop_resumen.json" data/secop/
