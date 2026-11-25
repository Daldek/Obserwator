#!/usr/bin/env bash
# Obserwator's scheduled jobs (Nogat plan 2026-11-16-operational-series, step A2,
# "The timers"): the user systemd units of deploy/systemd/ and the docker-compose
# service `jobs` run this script; docs/USAGE.md "Timers" describes it.
#
# Usage: obserwator-jobs.sh night [--start YYYY-MM-DD] [--check]
#        obserwator-jobs.sh telemetry [--check]
#        obserwator-jobs.sh current [--check]
#
#   night      02:30 local: the harvest of pl.pig.groundwater_operational from the
#              watermark its raw root holds until 02:45, then of
#              pl.imgw.hydro_operational until 05:00, then of cz.chmu.hydro_recent
#              until 06:30, the last two for the UTC days since their last whole
#              harvest, then the sealing of every other capture dataset's closed
#              UTC days, then the build of the hourly series of the months those
#              harvests asked for (ADR-031; PIG-PIB's: every month its captures
#              hold, ADR-035).
#   telemetry  06:45 local: IMGW-PIB's monthly telemetry of the current year (and
#              of the year before in January), the hourly series of each month
#              whose zip it stored, the listing check of ČHMÚ's validated hourly
#              year, then PIG-PIB's points and readings (on Mondays also its
#              chemistry and watch list), its station catalog while the points
#              are held and its readings series when either got a new version
#              (ADR-035).
#   current    hourly at :15: `obserwator current poll`.
#   --start    night only: the first UTC day of both harvests (at most 40 days
#              back), in place of the day after the last whole harvest.
#   --check    pass --check to every command: plans only, nothing written, no
#              harvest recorded, nothing built by the telemetry (its builds
#              follow what a sync stored).
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
# PIG-PIB's harvest (ADR-035) goes first: the watermark of its last capture names the
# rows to ask, so it takes no days and keeps no state. Dataset, the local time its
# requests are spread to, and its hourly series.
WATERMARKED="pl.pig.groundwater_operational 02:45 pl.pig.groundwater_subdaily"
# Each harvest by days: dataset, the local time its requests are spread to, and the
# hourly series built of its days after the sealing (ADR-031).
HARVESTS=(
  "pl.imgw.hydro_operational 05:00 pl.imgw.hydro_subdaily"
  "cz.chmu.hydro_recent 06:30 cz.chmu.hydro_subdaily"
)
# The other capture datasets: their closed UTC days are sealed after the
# harvests (the polled sources of `current poll` and the GUI's live fetches).
SEALED=pl.imgw.hydro_current,pl.imgw.meteo_current,pl.imgw.meteo_synop_current,pl.imgw.warnings_hydro_current,pl.imgw.warnings_meteo_current,pl.imgw.hydro_states_current,pl.imgw.meteo_operational,pl.imgw.meteo_states_current,cz.chmu.hydro_current
# obserwator.captures.HARVEST_DAYS: the earliest --start is today (UTC) minus 40 days.
HARVEST_DAYS=40
# --- the telemetry's PIG-PIB datasets (ADR-035, W11): the service holds one month
# of readings and replaces it about monthly, so they are asked every day ---
PIG_STATIONS=pl.pig.groundwater_stations
PIG_READINGS=pl.pig.groundwater_readings
# Asked on Mondays only: they change about yearly.
PIG_MONDAYS=pl.pig.groundwater_chemistry,pl.pig.groundwater_watchlist
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
  local override=$1 stamps end earliest entry dataset until series stamp start build
  local builds=()
  stamps="$(state_dir)/obserwator/timers" || { say "state_dir unknown"; return 1; }
  end=$(date -u -d yesterday +%F)
  earliest=$(date -u -d "-$HARVEST_DAYS days" +%F)
  read -r dataset until series <<<"$WATERMARKED"
  step "$OBSERWATOR" store sync --datasets "$dataset" --pace-until "$until" "${check[@]}"
  for entry in "${HARVESTS[@]}"; do
    read -r dataset until series <<<"$entry"
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
    # A harvest that ran, whole or partial, sealed what it got: its months are built.
    builds+=("$series $start")
    if step "$OBSERWATOR" store sync --datasets "$dataset" --pace-until "$until" \
      --start "$start" --end "$end" "${check[@]}" && ((${#check[@]} == 0)); then
      mkdir -p "$stamps" && printf '%s\n' "$end" >"$stamp.tmp" && mv -f "$stamp.tmp" "$stamp"
    fi
  done
  step "$OBSERWATOR" store sync --datasets "$SEALED" "${check[@]}"
  # The hourly series (ADR-031): every month PIG-PIB's captures hold, then the months
  # of the days each other harvest asked for.
  read -r _ _ series <<<"$WATERMARKED"
  step "$OBSERWATOR" series build --dataset "$series" "${check[@]}"
  for build in "${builds[@]}"; do
    read -r series start <<<"$build"
    step "$OBSERWATOR" series build --dataset "$series" --start "$start" --end "$end" \
      "${check[@]}"
  done
}

# The months (YYYY-MM) of the telemetry zips a `store sync --json` stored.
stored_months() {
  python3 -c '
import json, re, sys

lines = [line for line in sys.stdin if line.startswith("{")]
try:
    result = json.loads(lines[-1]).get("result") or {}
except (IndexError, ValueError, AttributeError):
    sys.exit(0)
for item in result.get("items") or ():
    found = re.search(r"Hydro_([0-9]{4}-[0-9]{2})\.zip$", str(item.get("slot") or ""))
    if found and item.get("status") in ("new", "relabeled"):
        print(found.group(1))
'
}

# "<dataset> <status>" of each item of the `store sync --json` envelopes read.
synced() {
  python3 -c '
import json, sys

for line in sys.stdin:
    if not line.startswith("{"):
        continue
    try:
        result = json.loads(line).get("result") or {}
    except (ValueError, AttributeError):
        continue
    for item in result.get("items") or ():
        parts = str(item.get("slot") or "").split(":")
        if len(parts) > 2:
            print(parts[1], item.get("status"))
'
}

telemetry() {
  local year month years out stored
  year=$(date +%Y)
  month=$(date +%m)
  years=$year
  # December's zip is published about 12 January, in the folder of its year.
  [[ $month == 01 ]] && years="$((year - 1)),$year"
  out=$(mktemp) || { say "no temporary file"; return 1; }
  step "$OBSERWATOR" store sync --datasets pl.imgw.hydro_telemetry --years "$years" \
    --json "${check[@]}" >"$out"
  cat "$out"
  # The hourly series of each month whose zip was stored (ADR-031): its telemetry
  # replaces hydro-back's hours of the month.
  if ((${#check[@]} == 0)); then
    while read -r stored; do
      step "$OBSERWATOR" series build --dataset pl.imgw.hydro_subdaily \
        --start "$stored-01" --end "$(date -u -d "$stored-01 + 1 month - 1 day" +%F)"
    done < <(stored_months <"$out")
  fi
  rm -f "$out"
  if [[ -n ${CHMU_HOURLY_STATIONS:-} ]]; then
    # One listing of historical/data/hourly/: is last year's validated hourly
    # year published (about May)? Nothing is downloaded.
    step "$OBSERWATOR" store check --datasets cz.chmu.hydro_hourly \
      --stations "$CHMU_HOURLY_STATIONS" --years "$((year - 1))"
  else
    say "cz.chmu.hydro_hourly: CHMU_HOURLY_STATIONS is not set, its check is skipped"
  fi
  pig
}

# PIG-PIB's monitoring (ADR-035, W11).
pig() {
  local readings=$PIG_READINGS out dataset status catalog="" series=""
  [[ $(date +%u) == 1 ]] && readings+=,$PIG_MONDAYS
  out=$(mktemp) || { say "no temporary file"; return 1; }
  # A station source is synchronized in a call of its own.
  step "$OBSERWATOR" store sync --datasets "$PIG_STATIONS" --json "${check[@]}" >"$out"
  step "$OBSERWATOR" store sync --datasets "$readings" --json "${check[@]}" >>"$out"
  cat "$out"
  if ((${#check[@]} == 0)); then
    while read -r dataset status; do
      case $dataset:$status in
      # The catalog also takes `automatic` from the newest night's capture of
      # mwp_auto, a new version every night: it is built whenever the points are
      # held, and an equal catalog is `unchanged`.
      "$PIG_STATIONS":new | "$PIG_STATIONS":relabeled) catalog=1 series=1 ;;
      "$PIG_STATIONS":unchanged) catalog=1 ;;
      # H_asl reads the points version, so new points build the series too.
      "$PIG_READINGS":new | "$PIG_READINGS":relabeled) series=1 ;;
      esac
    done < <(synced <"$out")
    [[ -n $catalog ]] && step "$OBSERWATOR" store catalog --provider PIG
    [[ -n $series ]] && step "$OBSERWATOR" series build --dataset "$PIG_READINGS"
  fi
  rm -f "$out"
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
