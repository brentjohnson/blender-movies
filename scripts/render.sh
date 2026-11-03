#!/bin/bash
# Final render that keeps every device busy: one render_setup.py process per entry of PROCS, all sharing the
# frame range (render_setup.py skips frames another process has claimed, so it is also resumable). From a movie dir:
#   [RES=1280x720] [SAMPLES=40] [PCT=..] [OUT=..] ../scripts/render.sh <scene>.blend [-s START -e END]
# PROCS defaults to "GPU CPU" when an NVIDIA GPU is present (the two renders don't slow each other down),
# otherwise "CPU". Each process logs to <scene>_<dev>.log.
set -e
blend="${1:?usage: ../scripts/render.sh <scene>.blend [-s START -e END]}"; shift
here="$(dirname "$(readlink -f "$0")")"
if [ -z "$PROCS" ]; then
  if nvidia-smi -L >/dev/null 2>&1; then PROCS="GPU CPU"; else PROCS="CPU"; fi
fi
trap 'kill 0' INT TERM
for dev in $PROCS; do
  log="${blend%.blend}_$(echo "$dev" | tr A-Z a-z).log"
  echo "$dev -> $log"
  DEV=$dev ./run.sh -b "$blend" -P "$here/render_setup.py" "$@" -a > "$log" 2>&1 &
  sleep 5   # let the first process claim its frame before the next one starts
done
wait
echo "done: $(ls "$(dirname "$blend")/${OUT:-frames}" | wc -l) frames in ${OUT:-frames}/"
