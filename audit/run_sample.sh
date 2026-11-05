#!/usr/bin/env bash
# Smoke test: build fake CASAS files and run the whole audit on them.
# Outputs go to sample_run/, never to your real reports.
set -euo pipefail
cd "$(dirname "$0")"
export AUDIT_SAMPLE=1
rm -rf sample_run
python tests/make_sample_data.py
python scripts/parse_casas.py --glob "data/sample/raw/**/*"
python scripts/profile_homes.py
python scripts/inventory.py
python scripts/feasibility.py
echo
echo "Smoke test finished. Look at sample_run/reports/ to see what the real reports will contain."
