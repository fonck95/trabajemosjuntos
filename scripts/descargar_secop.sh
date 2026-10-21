#!/usr/bin/env bash
# Descarga todos los contratos de entidades de Yondó desde SECOP (datos.gov.co) a data/secop/raw/.
# La descarga en un solo bloque se cortaba (curl error 18): ahora se hace por páginas desde fugas_secop.py.
# Uso: scripts/descargar_secop.sh
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/fugas_secop.py --descargar
# Luego: python3 scripts/secop_analisis.py data/secop/raw && mv data/secop/raw/secop_resumen.json data/secop/
