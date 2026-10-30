# Blob

A cute green blob character (about 0.55 m tall) in a simple studio set. The body is a refractive
jelly with a green absorbing/scattering volume inside and sparkles suspended in it.

Shared pipeline, scripts, learnings and machine notes are in `../CLAUDE.md`. This file holds
only what is specific to this movie.

## Files

```
scripts/build_scene.py   -> blob.blend
tests/                   look-dev stills (blob_v1..v5, blob_hero)
```

## Commands

```bash
./run.sh -b --factory-startup -P scripts/build_scene.py
./run.sh -b blob.blend -P ../scripts/still.py -- 1 $PWD/tests/x.png 50 32
./run.sh -b blob.blend -P ../scripts/render_setup.py -a
../scripts/encode.sh
```

- `build_scene.py` env overrides: `ABSORB` (volume density, 9.0), `SCATTER` (0.8), `GLOW_COUNT` (70),
  `FLAKE_COUNT` (400), `SAMPLES` (128), `RES_PCT`, `EXPOSURE` (−0.6).
- No simulations, so there is nothing to bake.

## Scene notes

- **Body.** A metaball field (body + stubby arms/feet melt into one surface), converted to a mesh with
  `bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph))`. Front faces −Y.
- **Material.** A refractive shell around a volume with absorption and scattering (anisotropy 0.3). It needs high
  transmission/transparent bounce limits (12–16), and `volume_step_rate = 0.5` because the body is small.
  Refractive caustics are on, and `blur_glossy = 0.5` keeps them clean.
- **Sparkles.** Two hair-particle systems inside the body ("glow" and "flakes"). Keep `hair_length = 1`;
  size them with `particle_size`.
- **Set.** A cyclorama with area lights. Narrowing an area light's `spread` concentrates its power, so lower `energy` to match.
- **Camera.** 85 mm. Render at 1280×720, CPU, light tree on.
- **Compositor.** A soft Bloom glare (threshold 1.5, strength 0.4) makes the sparkles twinkle.
