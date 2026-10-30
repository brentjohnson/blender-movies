#!/bin/bash
# Encode frames/f_####.png in the current movie dir to H.264 MP4:
#   ../scripts/encode.sh [output/name.mp4]      (default: output/<movie-dir>.mp4; FPS env, default 24)
# Uses libx264 when available; Fedora's ffmpeg-free lacks it, so fall back to libopenh264.
set -e
out="${1:-output/$(basename "$PWD").mp4}"
mkdir -p "$(dirname "$out")"
if ffmpeg -hide_banner -encoders 2>/dev/null | grep -q libx264; then
  codec=(-c:v libx264 -preset slow -crf 16)
else
  codec=(-c:v libopenh264 -b:v 20M -maxrate 30M)
fi
ffmpeg -y -framerate "${FPS:-24}" -i frames/f_%04d.png "${codec[@]}" \
  -pix_fmt yuv420p -movflags +faststart "$out"
