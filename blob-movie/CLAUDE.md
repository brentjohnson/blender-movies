# Blob

A cute green blob character (about 0.55 m tall) in a simple studio set. The body is a refractive
jelly with a green absorbing/scattering volume inside and sparkles suspended in it.

Shared pipeline, scripts, learnings and machine notes are in `../CLAUDE.md`. This file holds
only what is specific to this movie.

## Files

```
scripts/build_scene.py   -> blob.blend (ANIM=walk -> blob_walk.blend)
scripts/walk.py          walk-test choreography (pure math, imported by build_scene.py)
tests/                   look-dev stills (blob_v1..v8, blob_hero; v6 = silver flakes, v7 = cylinder legs, v8 = green shadow)
  preview/               low-res sparkle-drift preview frames (PCT=40 SAMPLES=16 OUT=tests/preview)
  walk/                  low-res walk-test frames (PCT=50 SAMPLES=16 OUT=tests/walk)
```

## Commands

```bash
./run.sh -b --factory-startup -P scripts/build_scene.py
ANIM=walk ./run.sh -b --factory-startup -P scripts/build_scene.py                  # walk test
PCT=50 SAMPLES=16 OUT=tests/walk ./run.sh -b blob_walk.blend -P ../scripts/render_setup.py -a
FRAMES_DIR=tests/walk ../scripts/encode.sh output/blob_walk_test.mp4
./run.sh -b blob.blend -P ../scripts/still.py -- 1 $PWD/tests/x.png 50 32
./run.sh -b blob.blend -P ../scripts/render_setup.py -a
../scripts/encode.sh
```

- `build_scene.py` env overrides: `ANIM` (idle | walk), `ABSORB` (volume density, 11.0), `GREEN_SHADOW` (1), `SHADOW_TINT` (1.0), `BACK_W` (1500), `SCATTER` (0.8), `SKIN_ROUGH` (0.12),
  `FLAKE_COUNT` (900), `FLAKE_SIZE` (0.004, hex radius), `DRIFT` (0.0125 m/s), `TUMBLE` (0.5 rad/s),
  `FRAMES` (240 at 24 fps; walk sets its own length), `LEG_R` (0.12), `LEG_X` (0.105), `LEG_Z` (0.03), `LEG_FILLET` (0.35), `VOXEL` (0.005, remesh voxel size), `FLAKE_ROUGH` (0.04, min of a 0.04–0.16 per-flake spread), `SAMPLES` (128), `RES_PCT`, `EXPOSURE` (−0.6).
- No Blender simulations, so there is nothing to bake. The flake drift is simulated in `build_scene.py` (~7 s).

## Scene notes

- **Body.** A metaball field (body + stubby arms/feet melt into one surface), converted to a mesh with
  `bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph))`. Front faces −Y. The mesh is then voxel
  remeshed (`VOXEL`; even topology, ~44k verts), soles are flattened, and his right half (−X) is mirrored
  onto the left with `bmesh.ops.symmetrize`. The result is exactly symmetric (max mirror error 0). The metaball
  polygonizer and the two sole passes had left the sides slightly different.
- **Legs.** Short cylinders with flat soles and soft edges. They start as fat vertical capsule metaballs that merge
  well into the body (a metaball's visible radius is much smaller than its element radius). After meshing,
  `flatten_soles()` moves each lower-hemisphere vertex along its ray from the hemisphere centre onto a
  rounded-cylinder profile (flat sole, fillet = `LEG_FILLET` × leg radius). Thinner/lower capsules gave
  spindly or pinched legs; the chosen look is `tests/blob_v7_legs.png`.
  The measured leg radius actually spans the whole merged base (~0.26 m). That's part of the chosen look; an
  exact projection onto the profile turned his bottom into a wide puck. The second leg's pass pushed ~550
  vertices below z=0. They were hidden while standing but floated him 7 cm whenever the floor clamp ran, so
  they're lifted onto the sole plane.
- **Material.** A refractive shell around a volume with absorption and scattering (anisotropy 0.3). It needs high
  transmission/transparent bounce limits (12–16), and `volume_step_rate = 0.5` because the body is small.
  Refractive caustics are on, and `blur_glossy = 0.5` keeps them clean.
- **Green shadow.** Real caustics don't show: even at 1024 spp, and with MNEE shadow caustics, the floor got no
  green. Instead, shadow rays pass through the skin (Light Path *Is Shadow Ray* → Transparent BSDF), so the volume
  tints them. Only rays coming from outside pass (front face, or Transparent Depth ≥ 1). Shadow rays starting
  inside stay blocked; letting those through lit the milky interior directly and washed him out. The transparent
  BSDF adds its own green (`SHADOW_TINT`) so the colour survives AgX and the fill. A hard spot `Back` light (`BACK_W`)
  high behind him throws the shadow toward the camera. `ABSORB` went 9 → 11 to offset the extra light.
- **Sparkles.** Weightless silver glitter, like a snow globe with no gravity. `build_scene.py` simulates each
  hex flake drifting on curl noise (divergence-free, so flakes don't bunch up) and tumbling. Near the skin
  the outward velocity is cancelled and the flake is pushed in, with a hard stop at `MARGIN`. Eyeballs are
  spherical obstacles. The result is stored as one point per flake per frame (`frame`, `rot`, `size` attributes)
  in the "Flakes" mesh. The `FlakeInstances` geometry-nodes tree deletes all points except the current frame's
  and instances a hex on each. Changing the body, eyes or frame range means rebuilding (the sim reruns).
  Checked: no flake leaves the body in any frame, and the mean height stays at 0.26 m throughout.
  Flakes also stay above `FLAKE_FLOOR` (0.12 m), out of the legs, because the legs deform when he walks.
- **Walk test (`ANIM=walk`).** `walk.py` plans everything per frame: stand, walk a 0.55 m circle at 0.45 m/s,
  speed up through a 90° turn into a 1.5 m/s run, and try to hop a 0.24 m hurdle. The hop is too low
  (`TRIP_LIFT` 0.15), so his right foot catches the bar at the top of it. The foot sticks briefly, the bar
  pops him up (`CLIP_POP`), and he rotates forward exactly π by the time his head reaches the floor. There he
  smooshes out from the floor contact to 1/3 height, jiggles, oozes back up, finishes
  the flip in the air, lands on his feet with a jelly splat, and does a dizzy wobble. His eyes pop out on the
  splat and roll away. Once he's standing they roll back, sink into the front of his base, float up through
  him and pop out into their sockets, with a body "gulp" and jiggle for each. He frowns when he notices
  they're gone (`FROWN_DELAY`) and grins when the second one pops in. The face is a "Frown" shape key on
  the mouth curve; negative values give a bigger grin. After he lands, the camera carries on along its track in a
  straight line, ending 2.2 m past him and slightly closer, with the aim on his face. It ends up looking back
  at him from a 3/4 front view (`CAM_DELAY`, `CAM_MOVE`). Don't interpolate an orbit angle here: his heading
  has accumulated 2π from the walk circle, which spun the camera a full 360°. The hurdle rocks forward
  and rattles back down.
  Gait frames: phase advances at v/stride. Each foot plants at the body's position at its mid-stance and arcs
  to the next plant. The body bobs, sways, leans and banks; banking lifts him so the wide base never cuts the floor.
  Tumble frames: rigid rotation `theta` about the body's middle, squash anchored at head, middle or feet, and the
  legs ride the body (plus tuck).
  Smoosh (head splat): a uniform bone scale looked stiff, so a world-space GN deformer ("Smoosh" group) runs
  after the rig on the body and on the eyes, mouth and flakes. A slice at u = z/H moves to H·(a·u + b·u²), with
  a=0.12 and a+b=1/3, and spreads from the contact point by 1/√(a + 2b·u) to keep its volume. The floor slice puddles
  ~2.9× while the far end stays domed. It's driven by the keyed "Smoosh" empty: location = contact,
  scale.x − 1 = amount, scale.y = H. The GN reads its own object's world transform (Self Object → Object Info),
  so bone-parented objects deform consistently with the body.
  Eyes: not bone-parented; keyed in world space every frame (pupils parented to their eyeballs). They ride
  the chest (`body_M[i] @ rest`, now the chest's transform) until the splat, then a small sim handles the pop, bounces (restitution 0.45) and
  rolling (rotation = distance / 0.044 m, damped to a stop). They roll back on a Bezier that approaches from
  in front of him, then follow a body-local path: in through the skin, up through the jelly, slerping to
  forward, and out with ease-out-back and a scale bulge. They don't get the smoosh. Timings are in walk.py
  (`EYE_*`). A floor probe of rest vertices keeps him exactly on the floor during contacts
  and above it in the air.
  Rig: parentless bones, all keyed in world space with `matrix_basis = rest⁻¹ @ M @ rest`. `body` (pivot z=0.06)
  and `leg.R`/`leg.L` (standing on the soles) point up, so an affine M = rigid @ squash-along-up never needs shear.
  `chest` (z 0.12–0.45) is the body tilted in world space about its root by the planner's `lag`, a spring
  (2.2 Hz, ζ 0.3, ≤0.15 rad) driven by his horizontal acceleration. It lags when he speeds up and sways forward
  when he stops; it's off during the tumble. `arm.R`/`arm.L` run along the arm stubs. They point sideways, so
  they can't take the squash without shear. Instead each is rigid: the chest's rotation, then
  `swing` (about his X, + = back) and `abd` (raise out to the side) about the shoulder, which rides the
  squashed chest. walk.py `secondary()` plans the arm angles: opposite the feet when walking, back for the
  wind-up, forward on the hop, flailing in the trip, splayed on the splat, drooping while he's eyeless, a cheer
  when his eyes are back. A 3 Hz springy follower adds lag and overshoot.
  Weights: legs as below; each arm owns its stub (fading in along the axis from the shoulder, within 0.11 m of
  it); the rest is chest above z 0.14–0.24 and body below.
  The whole lower base is weighted to the legs (split left/right with a soft seam; a radius around each leg
  axis left the outer corners on the body, hanging like a fixed skirt), fading into the body by z=0.11. Mouth
  and flakes are bone-parented to `chest`, and the eyes ride the chest's transform.
  Camera: 55 mm, aim lags him (0.2/frame, rising with the hop), and the camera trucks sideways (0.08/frame).
  Lights: the same rig (plus the back spot, widened to 70°) scaled 1.6× around the course, with a wider key.
  Lights are hidden from the camera.
- **Set.** A cyclorama with area lights. Narrowing an area light's `spread` concentrates its power, so lower `energy` to match.
- **Camera.** 85 mm. Render at 1280×720, CPU, light tree on.
- **Compositor.** None. The bloom glare was removed along with the glowing motes, because sparkles should glint, not glow.
