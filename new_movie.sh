#!/bin/bash
# Scaffold a new movie project:  ./new_movie.sh <name>   ->  <name>-movie/
set -e
cd "$(dirname "$(readlink -f "$0")")"
name="${1:?usage: ./new_movie.sh <name>}"
dir="$name-movie"
[ -e "$dir" ] && { echo "$dir already exists" >&2; exit 1; }
mkdir -p "$dir"/{scripts,tests,frames,output}
ln -s ../run.sh "$dir/run.sh"
sed "s/__NAME__/$name/g" template/CLAUDE.md > "$dir/CLAUDE.md"
sed "s/__NAME__/$name/g" template/scripts/build_scene.py > "$dir/scripts/build_scene.py"
echo "Created $dir/. Next: cd $dir && ./run.sh -b --factory-startup -P scripts/build_scene.py"
