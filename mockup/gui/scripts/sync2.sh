#!/usr/bin/env bash
# ČHMÚ demo stations and the IMGW-PIB catalog with the static locations; after sync.sh.
set -u
while pgrep -f obserwator-demo/sync.sh >/dev/null; do sleep 30; done
O=/home/claude-agent/workspace/IMGWTools/.venv/bin/obserwator
R=/home/claude-agent/data/obserwator-demo/store
run() { echo "=== $(date -Is) $*"; "$O" "$@" --root "$R" --json 2>&1 | grep -v '^\[' | cut -c1-400; }
HYDRO=0-203-1-240000,0-203-1-294000,0-203-1-257000,0-203-1-266000,0-203-1-263000,0-203-1-316000,0-203-1-320000,0-203-1-040000,0-203-1-200100,0-203-1-293000,0-203-1-311000,0-203-1-286600,0-203-1-019000
METEO=0-203-0-11514,0-20000-0-11653,0-20000-0-11787,0-20000-0-11603,0-20000-0-11457,0-20000-0-11464,0-20000-0-11723,0-203-0-11790,0-203-0-11763,0-203-0-11731,0-20000-0-11518
run store catalog --provider IMGW-PIB
run store sync --datasets cz.chmi.hydro_daily --stations "$HYDRO"
run store sync --datasets cz.chmi.meteo_daily --stations "$METEO"
echo "=== $(date -Is) done"
