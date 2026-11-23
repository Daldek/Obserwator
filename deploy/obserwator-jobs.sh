#!/usr/bin/env bash
# Obserwator's scheduled jobs (Nogat plan 2026-11-16-operational-series, step A2,
# "The timers"): the user systemd units of deploy/systemd/ and the docker-compose
# service `jobs` run this script; docs/USAGE.md "Timers" describes it.
#
# Usage: obserwator-jobs.sh night [--start YYYY-MM-DD] [--check]
#        obserwator-jobs.sh telemetry [--check]
#        obserwator-jobs.sh current [--check]
#
#   night      02:30 local: the harvest of pl.imgw.hydro_operational until 05:00,
#              then of cz.chmu.hydro_recent until 06:30, each for the UTC days
#              since its last whole harvest, then the sealing of every other
#              capture dataset's closed UTC days.
#   telemetry  06:45 local: IMGW-PIB's monthly telemetry of the current year (and
#              of the year before in January) and the listing check of ČHMÚ's
#              validated hourly year.
#   current    hourly at :15: `obserwator current poll`.
#   --start    night only: the first UTC day of both harvests (at most 40 days
#              back), in place of the day after the last whole harvest.
#   --check    pass --check to every command: plans only, nothing written, no
#              harvest recorded.
#
# Environment:
#   OBSERWATOR            the program (default: obserwator on PATH)
#   OBSERWATOR_RAW_ROOT, OBSERWATOR_ROOT, OBSERWATOR_STATE_DIR
#                         as for obserwator itself; the day of each dataset's
#                         last whole harvest is kept in
#                         <state_dir>/obserwator/timers/<dataset>.harvested
#   CHMU_HOURLY_STATIONS  telemetry: comma-separated WIGOS ids whose validated
#                         hourly year is checked (cz.chmu.hydro_hourly needs
#                         stations); unset or empty: the check is skipped
#
# Every step runs even when one before it failed. The exit code is that of the
# first step that failed (obserwator's codes: 2 invalid input, 4 conflict such
# as the capture lock held for 10 minutes, 10 partial), 0 when all succeeded,
# 64 for a wrong call of this script.
set -uo pipefail

# --- the night's datasets (ADR-030): the served capture datasets of the registry,
# the declared ones left out; tests/unit/test_deploy_jobs.py keeps them equal ---
# Each harvest: dataset and the local time its requests are spread to.
HARVESTS=(
  "pl.imgw.hydro_operational 05:00"
  "cz.chmu.hydro_recent 06:30"
)
# The other capture datasets: their closed UTC days are sealed after the
# harvests (the polled sources of `current poll` and the GUI's live fetches).
SEALED=pl.imgw.hydro_current,pl.imgw.meteo_current,pl.imgw.meteo_synop_current,pl.imgw.warnings_hydro_current,pl.imgw.warnings_meteo_current,pl.imgw.hydro_states_current,pl.imgw.meteo_operational,pl.imgw.meteo_states_current,cz.chmu.hydro_current
# obserwator.captures.HARVEST_DAYS: the earliest --start is today (UTC) minus 40 days.
HARVEST_DAYS=40
# ------------------------------------------------------------------------------

OBSERWATOR=${OBSERWATOR:-obserwator}
status=0
check=()

say() { printf 'obserwator-jobs: %s\n' "$*"; }
usage() { sed -n '/^# Usage:/,/^#$/p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 64; }

# Run one step; remember the code of the first that fails.
step() {
  say "run: $*"
  "$@"
  local code=$?
  if ((code != 0)); then
    say "exit $code: $*"
    ((status == 0)) && status=$code
  fi
  return "$code"
}

valid_day() { [[ $1 =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] && date -u -d "$1" +%F >/dev/null 2>&1; }

state_dir() {
  if [[ -n ${OBSERWATOR_STATE_DIR:-} ]]; then
    printf '%s\n' "$OBSERWATOR_STATE_DIR"
    return
  fi
  "$OBSERWATOR" config show --json |
    python3 -c 'import json, sys; print(json.load(sys.stdin)["keys"]["state_dir"]["value"])'
}

night() {
  local override=$1 stamps end earliest entry dataset until stamp start
  stamps="$(state_dir)/obserwator/timers" || { say "state_dir unknown"; return 1; }
  end=$(date -u -d yesterday +%F)
  earliest=$(date -u -d "-$HARVEST_DAYS days" +%F)
  for entry in "${HARVESTS[@]}"; do
    read -r dataset until <<<"$entry"
    stamp=$stamps/$dataset.harvested
    if [[ -n $override ]]; then
      start=$override
    elif [[ -f $stamp ]] && valid_day "$(<"$stamp")"; then
      start=$(date -u -d "$(<"$stamp") + 1 day" +%F)
      if [[ $start > $end ]]; then
        say "$dataset: harvested up to $end already"
        continue
      fi
    else
      start=$end
    fi
    if [[ $start < $earliest ]]; then
      say "$dataset: the days before $earliest are beyond the source's reach"
      start=$earliest
    fi
    if step "$OBSERWATOR" store sync --datasets "$dataset" --pace-until "$until" \
      --start "$start" --end "$end" "${check[@]}" && ((${#check[@]} == 0)); then
      mkdir -p "$stamps" && printf '%s\n' "$end" >"$stamp.tmp" && mv -f "$stamp.tmp" "$stamp"
    fi
  done
  step "$OBSERWATOR" store sync --datasets "$SEALED" "${check[@]}"
  # O4 (hourly series) adds here: series build of the months the night touched.
}

telemetry() {
  local year month years
  year=$(date +%Y)
  month=$(date +%m)
  years=$year
  # December's zip is published about 12 January, in the folder of its year.
  [[ $month == 01 ]] && years="$((year - 1)),$year"
  step "$OBSERWATOR" store sync --datasets pl.imgw.hydro_telemetry --years "$years" "${check[@]}"
  if [[ -n ${CHMU_HOURLY_STATIONS:-} ]]; then
    # One listing of historical/data/hourly/: is last year's validated hourly
    # year published (about May)? Nothing is downloaded.
    step "$OBSERWATOR" store check --datasets cz.chmu.hydro_hourly \
      --stations "$CHMU_HOURLY_STATIONS" --years "$((year - 1))"
  else
    say "cz.chmu.hydro_hourly: CHMU_HOURLY_STATIONS is not set, its check is skipped"
  fi
}

current() {
  step "$OBSERWATOR" current poll "${check[@]}"
}

(($# >= 1)) || usage
job=$1
shift
start=""
while (($#)); do
  case $1 in
  --check) check=(--check) ;;
  --start)
    if [[ $job != night || $# -lt 2 ]] || ! valid_day "$2"; then usage; fi
    start=$2
    shift
    ;;
  *) usage ;;
  esac
  shift
done

case $job in
night) night "$start" ;;
telemetry) telemetry ;;
current) current ;;
*) usage ;;
esac
exit "$status"
