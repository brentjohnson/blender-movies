#!/bin/bash
# Encode frames/f_####.png in the current movie dir to H.264 MP4:
#   ../scripts/encode.sh [output/name.mp4]      (default: output/<movie-dir>.mp4)
# Env: FPS (default 24), FRAMES_DIR (default frames).
# Encoder: libx264 if available. Fedora's ffmpeg-free lacks it, so next try NVIDIA's h264_nvenc (needs an NVIDIA GPU),
# then libopenh264 (lowest quality per bit, but works anywhere).
set -e
out="${1:-output/$(basename "$PWD").mp4}"
mkdir -p "$(dirname "$out")"
in=(-framerate "${FPS:-24}" -i "${FRAMES_DIR:-frames}/f_%04d.png")
enc() { ffmpeg -hide_banner -y "${in[@]}" "$@" -pix_fmt yuv420p -movflags +faststart "$out"; }
encoders="$(ffmpeg -hide_banner -encoders 2>/dev/null)"
if grep -q libx264 <<<"$encoders"; then
  enc -c:v libx264 -preset slow -crf 16
elif grep -q h264_nvenc <<<"$encoders" && nvidia-smi -L >/dev/null 2>&1 \
     && enc -c:v h264_nvenc -preset p7 -tune hq -rc vbr -cq 16 -b:v 0 -profile:v high; then
  :
else
  enc -c:v libopenh264 -b:v 20M -maxrate 30M
fi
