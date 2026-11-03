# Blender Movies

Procedurally generated Blender movies, rendered headless from Python scripts. Everything about a
scene lives in a script, so it can be rebuilt, tweaked and re-rendered without opening the GUI.

This file covers what all movies share. Each `<name>-movie/CLAUDE.md` adds the notes for that movie only.

## Layout

```
blender-movies/
  CLAUDE.md               this file: shared pipeline, learnings, gotchas, machine notes
  run.sh                  Blender wrapper (sets OCIO); every movie dir symlinks run.sh -> ../run.sh
  ocio/                   patched OCIO config (see machine notes)
  new_movie.sh            ./new_movie.sh <name>  ->  <name>-movie/ scaffold from template/
  template/               starting CLAUDE.md + build_scene.py for new movies
  scripts/                shared, scene-agnostic tools (run from inside a movie dir)
    devices.py            Cycles device selection (DEV=CPU|GPU|BOTH), used by the others
    still.py              single test frame
    bench.py              time one frame under a device/quality config
    bake.py               bake all Mantaflow domains (or DOMAIN=<name>) and save
    render_setup.py       final-render settings, resumable PNG frames
    encode.sh             frames/ -> output/<movie>.mp4
    grid.py               tile test stills into one contact sheet (PIL)
  <name>-movie/
    CLAUDE.md             notes for this movie
    run.sh -> ../run.sh
    scripts/build_scene.py   builds <scene>.blend from scratch (the only per-movie script)
    <scene>.blend, cache/, tests/, frames/, output/
```

Rules for where things go:
- Code that works for any scene goes in `../scripts/`. Code that knows about specific objects goes in the movie's `scripts/`.
- If a movie needs a variant of a shared script, add an env knob to the shared one. Don't fork it.
- General Blender/rendering learnings go in this file. Values that are specific to one shot go in the movie's CLAUDE.md.

## Pipeline

Run everything from inside the movie dir:

```
scripts/build_scene.py      -> <scene>.blend            (builds the whole scene from scratch)
../scripts/bake.py          -> cache/                   (bakes simulations, if any)
../scripts/still.py         -> tests/*.png              (single test frames)
../scripts/grid.py          -> tests/grid.png           (contact sheet of stills)
../scripts/bench.py         -> timing for device/quality configs
../scripts/render_setup.py  -> frames/f_####.png        (final render, resumable)
../scripts/encode.sh        -> output/<movie>.mp4       (ffmpeg H.264)
```

Typical loop:

```bash
cd <name>-movie
./run.sh -b --factory-startup -P scripts/build_scene.py      # with draft-quality env overrides
./run.sh -b <scene>.blend -P ../scripts/bake.py
for f in 1 60 120; do ./run.sh -b <scene>.blend -P ../scripts/still.py -- $f $PWD/tests/s$f.png 40 16; done
../scripts/grid.py tests/grid.png tests/s1.png tests/s60.png tests/s120.png
# ...iterate, then full quality:
./run.sh -b --factory-startup -P scripts/build_scene.py && ./run.sh -b <scene>.blend -P ../scripts/bake.py
./run.sh -b <scene>.blend -P ../scripts/render_setup.py -a
../scripts/encode.sh
```

- Always launch Blender through `./run.sh` (it sets machine-specific env such as `OCIO`). Any
  step that saves the .blend without it can silently reset color management. See the
  machine notes below.
- `build_scene.py` scripts should read env overrides for quality knobs (sim resolution, samples,
  resolution percentage, lighting tweaks), so drafts and finals come from the same script.
- `build_scene.py` finds the movie root with `os.path.dirname(os.path.dirname(__file__))`. The shared
  scripts find it from `bpy.data.filepath`.
- Shared script env knobs: `DEV` (all render scripts; default CPU), `EXPOSURE` and `SUN_ROT` (still.py),
  `RES=WxH`, `SAMPLES`, `PCT` and `OUT` (render_setup.py; defaults keep the scene's values and write to frames/), `PCT`, `SPP`, `VB` and `VSR` (bench.py),
  `DOMAIN` (bake.py), `FPS` and `FRAMES_DIR` (encode.sh).
- Rebuilding the scene invalidates any simulation bake. Re-bake after changes to emitters, domains or animation.
- Render to PNG frames, not straight to video. The frames survive crashes, and `use_overwrite=False` +
  `use_placeholder=True` make `-a` resumable (and allow several processes to share a frame range).

## Workflow learnings

- **Iterate on stills, not animations.** Render 3–4 key frames (start, peak action, late)
  at 30–50 % resolution and 16–24 samples, tile them with `grid.py`, and look at the result.
  Each round takes about a minute.
- **Draft sims at low resolution.** A Mantaflow bake at res 64 with no noise takes about 15 s. At res 160 with 2× noise it takes about 3.5 min and 1.7 GB.
  Tune emitter behavior at low res and switch to full resolution only for the final bake.
- **Benchmark before committing to a long render.** Device choice made a 15× difference (see machine notes).
  Volume-heavy frames cost 3–4× more than clear ones, so estimate from the heaviest frames.
- Keep `build_scene.py` deterministic (`random.seed`) so rebuilds are reproducible.
- Bake animation per frame from Python (compute the value, `keyframe_insert` every frame) instead of
  editing F-curves. It's simpler, physically exact, and avoids the Blender 5 Action/channelbag API.
- For many small moving things (hundreds of flakes or motes), simulate them in Python and store one point per
  item per frame, with an int `frame` attribute, in a single mesh. A geometry-nodes tree then deletes points where
  `frame != Scene Time` and instances geometry on the rest. That avoids hundreds of keyframed objects, and
  `build_scene.py` stays deterministic. See blob-movie.

## Realism learnings

- **Scale and physics.** Model in real meters and seconds, and drive motion from real physics
  (e.g. `z = ½at²`) so things move with believable weight. Delay sound-driven effects such as
  camera shake by distance / 343 m/s.
- **Long lens from far away.** A long lens (e.g. 135 mm at a few hundred meters) compresses the scene and hides missing detail.
  For a handheld/operator feel: Track-To on an empty that follows the subject with lag
  (`aim += (desired-aim)*0.12`), plus a small sum-of-sines shake.
- **Lighting.** Use the Sky Texture `MULTIPLE_SCATTERING` with a low sun. The sun's azimuth relative to the camera matters a lot:
  backlit gives silhouettes, front-lit is flat, side light reads best.
  The physical sky is very bright, so use view exposure about −1.8 with AgX, "Medium High Contrast".
- **Fire and glow.** A closed mesh with an *emission volume* shader works well: blackbody temperature
  with spatial falloff, plus 4D noise driven by `frame` for flicker.
  Tint the blackbody toward yellow, otherwise AgX makes it look pink.
- **Smoke.** Mantaflow gas with fire+smoke flows, with high albedo (0.95), 2 volume bounces, and anisotropy about 0.3
  so it reads as white steam rather than grey. Use only a little fuel, otherwise the scene becomes a pink fireball.
  - Place emitters where the smoke should appear, not where it would bury the main subject; animate their position if needed.
  - Animate emission with `flow_settings.use_inflow`, `density` and `fuel_amount` keyframes.
- **Atmosphere.** A huge low-density volume cube (density about 7e-5) adds aerial perspective.
  It's easy to overdo; 3.5e-4 washed everything out. A very bright light inside haze lights the whole frame,
  so keep such lights modest (~7e5 W was the ceiling for a point light).
- **Vegetation.** Hair particles instancing a displaced icosphere. Use `distribution='RAND'`, because the default
  jittered grid looks like rows of golf balls. Use many small varied instances (160k, size 0.6, random 0.9).

## Gotchas

### Blender 5.x Python API
- The Principled BSDF idname is `ShaderNodeBsdfPrincipled`, not `ShaderNodePrincipledBSDF`.
- `Fac` sockets were renamed to `Factor` (ColorRamp input, Noise/Wave/Attribute outputs).
- `ShaderNodeMix` has duplicate socket names per data type. Pick the *enabled* one
  (`next(i for i in node.inputs if i.name == k and i.enabled)`). Its color output is `outputs[2]`.
- Particle rotation enum: `'GLOB_Z'` (not `OBJECT_Z`). The engine enum is `'BLENDER_EEVEE'` or `'CYCLES'`.
- Compositor: `scene.compositing_node_group = <CompositorNodeTree>` with a `NodeGroupOutput`.
  The Glare node's type is an input socket (`inputs["Type"]`), not a property.
- `Material.use_nodes` is deprecated (still works, warns).
- Bake fluids with `bpy.context.temp_override(object=dom, active_object=dom)` + `bpy.ops.fluid.bake_all()`.
  It blocks in background mode.
- Drivers with simple expressions (`frame / 3.0`) work headless without enabling script auto-exec.
- Hair particles rendered as objects are scaled by `hair_length` × `particle_size`. A tiny hair length
  makes the instances invisible. Keep `hair_length = 1` and control size with `particle_size`.
- Random rotation for hair instances needs `rotation_mode = 'NOR'` (plus `phase_factor_random`). With
  `rotation_mode = 'NONE'`, `rotation_factor_random` is ignored and every instance keeps the source's orientation.
- An area light's `spread` concentrates the same power into a narrower beam. Lower `energy` when you narrow it.
- Area lights are visible to the camera. Seen from behind, a big one shows up as a dark panel once the camera
  moves or widens. Set `light_obj.visible_camera = False`.
- Pose bones without a parent can be keyed from a world transform W applied to their rest geometry:
  `pb.matrix_basis = bone.matrix_local.inverted() @ W @ bone.matrix_local`. Bone-parenting an object
  needs `matrix_parent_inverse = (rig.matrix_world @ bone.matrix_local @ Translation((0, bone.length, 0))).inverted()`.
- Get a mesh from metaballs without operators: `bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph))`.

### Geometry and shading
- **Volume meshes need outward normals.** A lathe built from a profile that runs downward has
  inverted faces and the volume renders as nothing. Reverse the faces in that case.
- **Object-coordinate textures on scaled objects.** Coordinates stay in unscaled local units (±1).
  Apply scale (`transform_apply(scale=True)`) on big planes before using object-space textures.
  Same for Displace modifiers: use `texture_coords='GLOBAL'` and sizes in meters.
- **Coloured shadows from refractive/volume objects.** Cycles almost never finds caustic paths from soft area
  lights through a refractive shell. More samples and MNEE didn't help through an absorbing volume, so the shadow
  stays grey. Instead, mix in a Transparent BSDF for *Is Shadow Ray*, gated to rays arriving from outside
  (`max(1 - Backfacing, min(TransparentDepth, 1))`). The interior volume then tints the shadow, and the inside
  doesn't wash out. It shows best under one dominant hard light. See blob-movie.
- **Adaptive fluid domain + motion blur = vertical streaks.** The domain transform changes every frame.
  Set `domain.cycles.use_motion_blur = False`.

## Machine-specific notes

Add a section per machine. Record anything that changes how scripts must run or how fast they are, and
update `run.sh` / `scripts/devices.py` defaults to match the machine you're on.

### `fedora` (hostname): Fedora 44, AMD Ryzen AI 7 PRO 350 (8C/16T) + Radeon 860M iGPU, 30 GB RAM
- Install everything the project needs:
  ```bash
  sudo dnf install blender ffmpeg-free python3 python3-pillow git gh
  ```
  `blender` runs every step, `ffmpeg-free` is used by `encode.sh`, `python3-pillow` by `grid.py`,
  and `git`/`gh` for version control and GitHub. After installing or upgrading Blender, check the OCIO note below.
- Blender 5.2.2 LTS from Fedora packages (`/usr/bin/blender`), ffmpeg at `/usr/bin/ffmpeg`, Python 3 with PIL.
- **Broken OCIO out of the box.** Fedora ships OpenColorIO 2.4, but Blender 5.2's config is version 2.5,
  so Blender falls back to "Standard" only (no AgX/Filmic). Fix: `ocio/config.ocio` is a copy with
  `ocio_profile_version: 2.4` and the 2.5-only `interop_id:` / `interchange:` blocks removed.
  `run.sh` exports `OCIO` to point at it. Re-create the copy if Blender is upgraded.
- **Render on the CPU, not the iGPU.** Benchmark: CPU 8.6 s, CPU+HIP 34.6 s, HIP alone
  147 s. The 860M slows down even mixed rendering, so `devices.py` defaults to `DEV=CPU`.
- Reference timings (Cycles CPU, 1280×720, 40 samples, OIDN, outdoor scene with sky, haze and smoke):
  ~24 s/frame for clear frames, up to ~61 s/frame when smoke fills the frame. Smoke bake at res 160 + noise ≈ 3.5 min.
- Fedora's `ffmpeg-free` has no `libx264`. `encode.sh` falls back to `libopenh264` (still H.264, plays anywhere).
  For better compression, install ffmpeg from RPM Fusion.
- Claude Code's safety check blocks `rm` with globs after `cd`. Use absolute paths, or clean up manually.
