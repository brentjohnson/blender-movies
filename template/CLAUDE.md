# __NAME__

<One-paragraph description of the shot: subject, setting, duration, mood.>

Shared pipeline, scripts, learnings and machine notes are in `../CLAUDE.md`. This file holds
only what is specific to this movie.

## Files

```
scripts/build_scene.py   -> __NAME__.blend
```

## Commands

```bash
./run.sh -b --factory-startup -P scripts/build_scene.py
./run.sh -b __NAME__.blend -P ../scripts/still.py -- 1 $PWD/tests/t1.png 50 16
./run.sh -b __NAME__.blend -P ../scripts/render_setup.py -a
../scripts/encode.sh
```

- `build_scene.py` env overrides: `SAMPLES`, `RES_PCT`, `EXPOSURE`.

## Scene notes

<Scale, camera, lighting and material decisions, and the values that worked.>
