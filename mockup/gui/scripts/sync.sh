#!/usr/bin/env bash
# Fills the demo store of the Obserwator GUI mockup with real IMGW-PIB data.
set -u
O=/home/claude-agent/workspace/IMGWTools/.venv/bin/obserwator
R=/home/claude-agent/data/obserwator-demo/store
run() { echo "=== $(date -Is) $*"; "$O" "$@" --root "$R" --json 2>&1 | grep -v '^\[' | cut -c1-400; }
run store catalog --provider IMGW-PIB
run store catalog --provider CHMI
run store sync --datasets pl.imgw.hydro_semiannual --years 1951-2025
run store sync --datasets pl.imgw.hydro_daily --years 1951-2025
run store sync --datasets pl.imgw.meteo_climate_daily --years 1961-2025
run store sync --datasets pl.imgw.meteo_precip_daily --years 1961-2025
echo "=== $(date -Is) done"
