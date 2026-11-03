#!/bin/bash
# Blender wrapper. Each movie dir has a run.sh symlink to this file; readlink -f resolves back here.
# Picks the binary in this order:
#   1. $BLENDER, if set
#   2. the newest official blender.org build in ~/.local/opt/blender-*/ (has CUDA/OptiX; Fedora's package doesn't)
#   3. the system `blender`
# Fedora's Blender links OCIO 2.4, which can't read Blender 5.2's 2.5 config. Only for that binary, point
# OCIO at the patched copy in ocio/. Official builds bundle OCIO 2.5 and use their own config.
root="$(dirname "$(readlink -f "$0")")"
if [ -z "$BLENDER" ]; then
  BLENDER="$(ls -d "$HOME"/.local/opt/blender-*/blender 2>/dev/null | sort -V | tail -1)"
  [ -x "$BLENDER" ] || BLENDER="$(command -v blender)"
fi
if [ "$(readlink -f "$BLENDER")" = /usr/bin/blender ]; then
  export OCIO="$root/ocio/config.ocio"
fi
exec "$BLENDER" "$@"
