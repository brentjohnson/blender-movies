#!/bin/bash
# Final render: one render_setup.py process per entry of PROCS (one per device), all sharing the
# frame range (render_setup.py skips frames another process has claimed, so it is also resumable). From a movie dir:
#   [RES=1280x720] [SAMPLES=40] [PCT=..] [OUT=..] ../scripts/render.sh <scene>.blend [-s START -e END]
# PROCS defaults to "GPU" when an NVIDIA GPU is present. Without one, PROCS is ignored and a single CPU process runs
# (a GPU process would pick a slow iGPU or just double up on the CPU). Add a CPU process (PROCS="GPU CPU") only
# for scenes where the GPU is slow, like heavy smoke: elsewhere the CPU process starves the GPU process of the
# CPU time it needs for sync/denoise (blob: 5.8 -> 11.5 s/frame). Each process logs to <scene>_<dev>.log.
set -e
blend="${1:?usage: ../scripts/render.sh <scene>.blend [-s START -e END]}"; shift
here="$(dirname "$(readlink -f "$0")")"
if ! nvidia-smi -L >/dev/null 2>&1; then
  [ -n "$PROCS" ] && [ "$PROCS" != CPU ] && echo "no NVIDIA GPU: ignoring PROCS=\"$PROCS\", rendering on the CPU"
  PROCS="CPU"
fi
PROCS="${PROCS:-GPU}"
trap 'kill 0' INT TERM
for dev in $PROCS; do
  log="${blend%.blend}_$(echo "$dev" | tr A-Z a-z).log"
  echo "$dev -> $log"
  DEV=$dev ./run.sh -b "$blend" -P "$here/render_setup.py" "$@" -a > "$log" 2>&1 &
  sleep 5   # let the first process claim its frame before the next one starts
done
wait
out="${OUT:-frames}"; [ "${out#/}" = "$out" ] && out="$(dirname "$blend")/$out"   # as render_setup.py resolves it
echo "done: $(ls "$out" | wc -l) frames in $out/"
