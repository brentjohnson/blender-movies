#!/bin/bash
# Wrapper: run Blender with the patched OCIO config (Fedora's OCIO 2.4 can't read Blender 5.2's 2.5 config).
# Each movie dir has a run.sh symlink to this file; readlink -f resolves back here.
export OCIO="$(dirname "$(readlink -f "$0")")/ocio/config.ocio"
exec blender "$@"
