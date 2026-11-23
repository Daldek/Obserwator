#!/usr/bin/env bash
# Backups of Obserwator's two roots (Nogat plan 2026-11-16-operational-series,
# step A4, "Backups (D10)"; Nogat DEV-18.5): deploy/systemd/obserwator-backup.*
# runs it every Sunday at 07:00; docs/USAGE.md "Backups" describes it.
#
# Usage: obserwator-backup.sh --raw-root DIR --data-root DIR --target DIR
#          [--mode auto|weekly|monthly] [--date YYYY-MM-DD] [--log-dir DIR]
#          [--keep-weekly N] [--keep-monthly N] [--min-free-percent P]
#
#   --raw-root, --data-root  the roots, read only (their markers
#                       obserwator-store.json and obserwator-data.json must be there)
#   --target            the backup share; snapshots go to
#                       <target>/obserwator/{weekly,monthly}/<YYYY-MM-DD>/{raw,data}/
#   --mode              auto (default): monthly when the month has no monthly
#                       snapshot yet (the first Sunday of the month), else weekly
#   --date              the snapshot's name (default: today, local)
#   --log-dir           Obserwator's log directory for the records (default:
#                       <state_dir>/obserwator/logs, state_dir from
#                       $OBSERWATOR_STATE_DIR or `obserwator config show`)
#   --keep-weekly N     weekly snapshots kept (default 8)
#   --keep-monthly N    monthly snapshots kept (default 6)
#   --min-free-percent P  a full copy is refused when it would leave less than
#                       P % of the target's file system free (default 15)
#
# Weekly: rsync -aH with --link-dest to the newest snapshot, so unchanged files
# are hard links and only new ones take space. Monthly: a full copy without
# --link-dest, then the restore test (restore-test.log beside the snapshot and
# one record in Obserwator's log). .incoming/ directories are never copied.
# Permissions are not kept (--no-perms): a CIFS share fixes them by its mount
# options, and a mode differing from the source's would make rsync copy every
# file instead of linking it. The only deletion is of whole snapshot
# directories beyond the retention under <target>/obserwator/{weekly,monthly}/,
# never following a link.
#
# Environment: OBSERWATOR (the program, default: obserwator on PATH).
# Exit: 0 done, 1 failed (a copy, the restore test), 2 wrong call or roots,
# 3 a full refused for free space, 4 another backup of the target runs.
set -euo pipefail

OBSERWATOR=${OBSERWATOR:-obserwator}
DATA_SAMPLE=50   # version files of the restored data root checked against their sidecars
RAW_SAMPLE=100   # version directories of the raw root restored and checked

mode=auto day=$(date +%F) log_dir="" raw="" data="" target=""
keep_weekly=8 keep_monthly=6 min_free=15
incomplete="" restore_tmp=""

say() { printf 'obserwator-backup: %s\n' "$*"; }
usage() {
  say "$1" >&2
  sed -n '/^# Usage:/,/^#$/p' "$0" | sed 's/^# \{0,1\}//' >&2
  exit 2
}
# shellcheck disable=SC2329  # invoked by the EXIT trap
cleanup() {
  if [[ -n $restore_tmp && -d $restore_tmp ]]; then rm -rf --one-file-system -- "$restore_tmp"; fi
  if [[ -n $incomplete && -d $incomplete ]]; then rm -rf --one-file-system -- "$incomplete"; fi
}
trap cleanup EXIT

resolve_log_dir() {
  if [[ -n $log_dir ]]; then
    printf '%s\n' "$log_dir"
  elif [[ -n ${OBSERWATOR_STATE_DIR:-} ]]; then
    printf '%s\n' "$OBSERWATOR_STATE_DIR/obserwator/logs"
  else
    "$OBSERWATOR" config show --json | python3 -c \
      'import json, sys; print(json.load(sys.stdin)["keys"]["state_dir"]["value"] + "/obserwator/logs")'
  fi
}

# One app record of nogat-log/1 in <log dir>/app-<UTC day>.jsonl, as Obserwator's
# servers write them (DEV-12.4).
record() {
  local level=$1 event=$2 text=$3 dir version
  if ! dir=$(resolve_log_dir); then
    say "no log directory for the record: $text" >&2
    return 0
  fi
  version=$("$OBSERWATOR" version 2>/dev/null || true)
  version=${version##* v}
  python3 - "$dir" "$level" "$event" "$text" "${version:-unknown}" <<'PY' || say "record not written: $text" >&2
import json, os, sys
from datetime import datetime, timezone

directory, level, event, message, version = sys.argv[1:]
now = datetime.now(timezone.utc)
record = {
    "time": now.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
    "level": level, "app": "obserwator", "version": version, "kind": "app",
    "request_id": None, "event": event, "message": message, "error": None,
}
os.makedirs(directory, exist_ok=True)
line = (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
fd = os.open(os.path.join(directory, f"app-{now:%Y-%m-%d}.jsonl"),
             os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o666)
try:
    os.write(fd, line)
finally:
    os.close(fd)
PY
}

fail() {
  local code=$1 event=$2 text=$3
  say "$text" >&2
  record error "$event" "$text"
  exit "$code"
}

# The number of entries of `store scan` (a kind or all).
scan_total() {
  local root=$1 kind=${2:-}
  "$OBSERWATOR" store scan --root "$root" ${kind:+--kind "$kind"} --limit 1 --json |
    python3 -c 'import json, sys; print(json.load(sys.stdin)["page"]["total"])'
}
problems() { scan_total "$1" problem; }
versions() {
  local all bad
  all=$(scan_total "$1") && bad=$(problems "$1") && echo $((all - bad))
}

# Sidecar paths on stdin: each file's SHA-256 against its obserwator-meta/1 sidecar.
verify_sidecars() {
  python3 -c '
import hashlib, json, sys
checked = bad = 0
for line in sys.stdin:
    sidecar = line.rstrip("\n")
    if not sidecar:
        continue
    checked += 1
    path = sidecar[: -len(".meta.json")]
    try:
        expected = json.load(open(sidecar, encoding="utf-8"))["sha256"]
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                digest.update(block)
        if digest.hexdigest() != expected:
            bad += 1
            print(f"  mismatch: {path}")
    except (OSError, ValueError, KeyError, TypeError) as error:
        bad += 1
        print(f"  unreadable: {path}: {error}")
print(f"{checked} {bad}")
sys.exit(1 if bad else 0)
'
}

# The newest complete snapshot of either kind, for --link-dest.
newest_snapshot() {
  find "$base/weekly" "$base/monthly" -mindepth 1 -maxdepth 1 -type d \
    -regextype posix-extended -regex '.*/[0-9]{4}-[0-9]{2}-[0-9]{2}' -printf '%f %p\n' |
    sort -r | sed -n '1s/^[^ ]* //p'
}

copy() {
  local source=$1 destination=$2 link=${3:-} code=0
  mkdir -p "$destination"
  rsync -aH --no-perms --exclude=.incoming/ ${link:+"--link-dest=$link"} "$source/" "$destination/" || code=$?
  # 24: files vanished during the copy, which only staging files of a write do.
  ((code == 0 || code == 24))
}

prune() {
  local dir=$1 keep=$2 old
  local -a snapshots
  mapfile -t snapshots < <(find "$dir" -mindepth 1 -maxdepth 1 -type d \
    -regextype posix-extended -regex '.*/[0-9]{4}-[0-9]{2}-[0-9]{2}' -printf '%f\n' | sort -r)
  for old in "${snapshots[@]:keep}"; do
    rm -rf --one-file-system -- "${dir:?}/$old"
    say "removed $dir/$old (beyond $keep kept)"
  done
}

# The monthly restore test: the data root copied back and checked whole, a
# sample of the raw root's version directories likewise. Prints its report.
restore_test() {
  local snapshot=$1 before=$2 after=$3 ok=0 count bad out entry version station
  restore_tmp=$(mktemp -d "$base/.restore-test.XXXXXX")
  echo "restore test of $snapshot, $(date -u +%FT%TZ), obserwator: $("$OBSERWATOR" version 2>&1 || true)"

  copy "$snapshot/data" "$restore_tmp/data" || { echo "data: copy FAILED"; ok=1; }
  count=$(versions "$restore_tmp/data") || count=-1
  bad=$(problems "$restore_tmp/data") || bad=-1
  if ((bad == 0 && count >= before && count <= after)); then
    echo "data: store scan ok: $count versions (the source: $before before the copy, $after after it), 0 problems"
  else
    echo "data: store scan FAILED: $count versions (the source: $before before the copy, $after after it), $bad problems"
    ok=1
  fi
  if out=$(find "$restore_tmp/data" -name .incoming -prune -o -type f -name '*.meta.json' -print |
    shuf -n "$DATA_SAMPLE" | verify_sidecars); then
    echo "data: SHA-256 ok: $(tail -n1 <<<"$out" | cut -d' ' -f1) version files match their sidecars"
  else
    echo "data: SHA-256 FAILED:"
    echo "$out"
    ok=1
  fi
  entry=$("$OBSERWATOR" store scan --root "$restore_tmp/data" --kind series --limit 1 --json |
    python3 -c 'import json, sys; r = json.load(sys.stdin)["result"]; print(r[0]["version"] if r else "")') || entry=""
  version=${entry%/*}
  station=""
  if [[ -n $entry && -d $restore_tmp/data/$version/stations ]]; then
    station=$(find "$restore_tmp/data/$version/stations" -maxdepth 1 -type f -printf '%f\n' | sort | sed -n '1s/\..*$//p')
  fi
  if [[ -z $station ]]; then
    echo "data: series read skipped: no series version with a station file"
  elif count=$("$OBSERWATOR" series read --root "$restore_tmp/data" --version "$version" \
    --station "$station" --limit 5 --json |
    python3 -c 'import json, sys; d = json.load(sys.stdin); ok = d["status"] == "ok" and d["result"]; print(len(d["result"])) if ok else sys.exit(1)'); then
    echo "data: series read ok: $version, station $station, $count records read"
  else
    echo "data: series read FAILED: $version, station $station"
    ok=1
  fi

  # The raw root: a random sample of version directories (those holding a sidecar).
  mkdir -p "$restore_tmp/raw"
  {
    echo obserwator-store.json
    (cd "$snapshot/raw" && find . -name .incoming -prune -o -type f -name '*.meta.json' -printf '%h\n' |
      sort -u | shuf -n "$RAW_SAMPLE")
  } >"$restore_tmp/raw-sample.txt"
  if ! rsync -aHr --files-from="$restore_tmp/raw-sample.txt" "$snapshot/raw/" "$restore_tmp/raw/"; then
    echo "raw: copy FAILED"
    ok=1
  fi
  local dirs sidecars
  dirs=$(($(wc -l <"$restore_tmp/raw-sample.txt") - 1))
  sidecars=$(find "$restore_tmp/raw" -type f -name '*.meta.json' | wc -l)
  count=$(versions "$restore_tmp/raw") || count=-1
  bad=$(problems "$restore_tmp/raw") || bad=-1
  if ((bad == 0 && count == sidecars)); then
    echo "raw: store scan ok: $dirs version directories, $count versions, 0 problems"
  else
    echo "raw: store scan FAILED: $dirs version directories, $sidecars sidecars, $count versions, $bad problems"
    ok=1
  fi
  if out=$(find "$restore_tmp/raw" -type f -name '*.meta.json' | verify_sidecars); then
    echo "raw: SHA-256 ok: $(tail -n1 <<<"$out" | cut -d' ' -f1) version files match their sidecars"
  else
    echo "raw: SHA-256 FAILED:"
    echo "$out"
    ok=1
  fi
  rm -rf --one-file-system -- "$restore_tmp"
  restore_tmp=""
  if ((ok == 0)); then echo "result: passed"; else echo "result: failed"; fi
  return "$ok"
}

while (($#)); do
  (($# >= 2)) || usage "$1 needs a value"
  case $1 in
  --raw-root) raw=$2 ;;
  --data-root) data=$2 ;;
  --target) target=$2 ;;
  --mode) mode=$2 ;;
  --date) day=$2 ;;
  --log-dir) log_dir=$2 ;;
  --keep-weekly) keep_weekly=$2 ;;
  --keep-monthly) keep_monthly=$2 ;;
  --min-free-percent) min_free=$2 ;;
  *) usage "unknown option $1" ;;
  esac
  shift 2
done

[[ -n $raw && -n $data && -n $target ]] || usage "--raw-root, --data-root and --target are required"
[[ $mode =~ ^(auto|weekly|monthly)$ ]] || usage "--mode is auto, weekly or monthly"
if [[ ! $day =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || ! date -d "$day" >/dev/null 2>&1; then usage "--date is YYYY-MM-DD"; fi
[[ $keep_weekly =~ ^[1-9][0-9]*$ && $keep_monthly =~ ^[1-9][0-9]*$ ]] || usage "--keep-weekly and --keep-monthly are at least 1"
if [[ ! $min_free =~ ^[0-9]+$ ]] || ((min_free > 100)); then usage "--min-free-percent is 0 to 100"; fi
[[ -f $raw/obserwator-store.json ]] || fail 2 backup_failed "$raw is no raw root (no obserwator-store.json): is it mounted?"
[[ -f $data/obserwator-data.json ]] || fail 2 backup_failed "$data is no data root (no obserwator-data.json)"
[[ -d $target && ! -L $target ]] || fail 2 backup_failed "$target is no directory: is the share mounted?"
raw=$(realpath -- "$raw") data=$(realpath -- "$data") target=$(realpath -- "$target")
base=$target/obserwator
for root in "$raw" "$data"; do
  case "$base/" in "$root"/*) fail 2 backup_failed "the target lies in the root $root" ;; esac
  case "$root/" in "$base"/*) fail 2 backup_failed "the root $root lies in the target" ;; esac
done
for dir in "$base" "$base/weekly" "$base/monthly"; do
  [[ ! -L $dir ]] || fail 2 backup_failed "$dir is a link; the script follows none"
  mkdir -p "$dir"
done

exec 9>"$base/.backup.lock"
flock -n 9 || { say "another backup of $target runs" >&2; exit 4; }

# Snapshots left by an interrupted run are the script's own: removed whole.
find "$base/weekly" "$base/monthly" -mindepth 1 -maxdepth 1 -type d -name '*.incomplete' \
  -exec rm -rf --one-file-system -- {} +

if [[ $mode == auto ]]; then
  if compgen -G "$base/monthly/${day:0:7}-[0-9][0-9]" >/dev/null; then mode=weekly; else mode=monthly; fi
fi
snapshot=$base/$mode/$day
[[ ! -e $snapshot ]] || fail 2 backup_failed "$snapshot exists already"
link=""
[[ $mode == weekly ]] && link=$(newest_snapshot)

before=0 after=0
if [[ $mode == monthly ]]; then
  before=$(versions "$data") || fail 1 backup_failed "store scan of $data failed before the monthly full"
fi
if [[ -z $link ]]; then
  # A full copy (the monthly, or the first weekly) must leave min_free % free:
  # the share also holds the raw root and other stores, and a full share stops
  # Obserwator's writer. Counted: both roots (hard links once) and, for the
  # monthly, the data root's restore copy.
  need=$(du -skc --exclude=.incoming "$raw" "$data" | tail -n1 | cut -f1)
  if [[ $mode == monthly ]]; then need=$((need + $(du -sk --exclude=.incoming "$data" | cut -f1))); fi
  read -r size avail < <(df -Pk "$base" | awk 'NR == 2 {print $2, $4}')
  left=$((avail - need))
  if ((left * 100 < min_free * size)); then
    fail 3 backup_refused "refused the $mode full copy to $snapshot: it needs $((need / 1024)) MiB of $((avail / 1024)) MiB free and would leave $((left * 100 / size)) % of $((size / 1024)) MiB free, below $min_free %"
  fi
fi

incomplete=$snapshot.incomplete
say "$mode snapshot $snapshot${link:+ (unchanged files linked to $link)}"
copy "$raw" "$incomplete/raw" ${link:+"$link/raw"} || fail 1 backup_failed "rsync of $raw to $incomplete/raw failed"
copy "$data" "$incomplete/data" ${link:+"$link/data"} || fail 1 backup_failed "rsync of $data to $incomplete/data failed"
mv -T -- "$incomplete" "$snapshot"
incomplete=""
say "snapshot done: $snapshot"

result=0
if [[ $mode == monthly ]]; then
  after=$(versions "$data") || after=$before
  if restore_test "$snapshot" "$before" "$after" >"$snapshot/restore-test.log" 2>&1; then
    say "restore test passed: $snapshot/restore-test.log"
    record info backup_restore_test "restore test of $snapshot passed: $(grep -E '^(data|raw):' "$snapshot/restore-test.log" | paste -sd ';' -)"
  else
    result=1
    say "restore test FAILED: $snapshot/restore-test.log" >&2
    record error backup_restore_test "restore test of $snapshot failed, nothing pruned: see $snapshot/restore-test.log"
  fi
fi

if ((result == 0)); then
  prune "$base/weekly" "$keep_weekly"
  prune "$base/monthly" "$keep_monthly"
fi
exit "$result"
