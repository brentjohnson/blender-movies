# Rocket Launch

A 10 s (240 frames @ 24 fps) shot of a rocket lifting off, seen from about 700 m away with a long lens:
Mantaflow exhaust smoke, a volumetric flame, ground billows from the flame trench, haze and vegetation.

Shared pipeline, scripts, learnings and machine notes are in `../CLAUDE.md`. This file holds
only what is specific to this movie.

## Files

```
scripts/build_scene.py   -> rocket_launch.blend
cache/smoke/             Mantaflow bake (~1.7 GB at res 160 + noise); bake.log
frames/                  final 1280×720 frames;  output/rocket_launch_test.mp4
waveletNoiseTile.bin     Mantaflow noise tile, written to the cwd during the bake
```

## Commands

```bash
SMOKE_RES=64 SMOKE_NOISE=0 ./run.sh -b --factory-startup -P scripts/build_scene.py   # fast draft sim
./run.sh -b rocket_launch.blend -P ../scripts/bake.py                                # domain: SmokeDomain
./run.sh -b rocket_launch.blend -P ../scripts/still.py -- <frame> $PWD/tests/x.png <pct> <samples>
# ...iterate, then full-res:
./run.sh -b --factory-startup -P scripts/build_scene.py && ./run.sh -b rocket_launch.blend -P ../scripts/bake.py
RES=1280x720 SAMPLES=40 ./run.sh -b rocket_launch.blend -P ../scripts/render_setup.py -a
../scripts/encode.sh output/rocket_launch_test.mp4
```

- `build_scene.py` env overrides: `SMOKE_RES`, `SMOKE_NOISE`, `SAMPLES`, `RES_PCT`, `HAZE`, `SUN_ROT`.
- The scene is built at 1920×1080 / 96 spp. The finished render used `RES=1280x720 SAMPLES=40` to fit the CPU budget.
- Key frames for still rounds: pre-ignition, ignition, peak smoke, late climb.

## Scene notes

- **Motion.** The rocket rises with constant net acceleration (~3.4 m/s², `z = ½at²`), so it creeps off the
  pad like the real thing. Camera shake starts when the sound would arrive (700 m / 343 m/s ≈ 2 s).
- **Camera.** 135 mm at about 700 m, low (6 m). Track-To on an empty that follows the rocket with lag
  (`aim += (desired-aim)*0.12`) to mimic a human operator, plus a small sum-of-sines shake.
- **Lighting.** Sky Texture `MULTIPLE_SCATTERING`, sun elevation about 13°. Azimuth: backlit (250°) gives silhouettes
  and front-lit (160°) is flat. Side light (205°, the default) reads best. View exposure about −1.8, AgX "Medium High Contrast".
- **Exhaust plume.** A closed revolved mesh (`revolve()` reverses faces when the profile runs downward)
  with an emission volume shader: blackbody temperature falls off along the length, there is a radial falloff, and
  `frame`-driven 4D noise makes it flicker. Blackbody tinted toward yellow.
- **Smoke.**
  - Keep the engine's smoke emitter *at the end of the plume*, not at the nozzle. Otherwise smoke
    buries the flame. Animate its local offset as the rocket climbs.
  - Separate emitters at the flame-trench exits give the classic sideways ground billows.
- **Engine light.** A point light at about 7e5 W. Brighter lights up the whole haze volume.
- **Timings.** ~24 s/frame before ignition, rising to ~61 s/frame as the smoke spreads (1280×720, 40 spp, CPU).
  The full 240 frames took about 3 h.
