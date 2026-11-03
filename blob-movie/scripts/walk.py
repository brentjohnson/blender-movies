"""Walk-test choreography for the blob. Pure math, no bpy, so it can be checked outside Blender.

plan(fps, leg_x, leg_y, height) returns per-frame poses for: stand, walk a full circle, turn while
speeding up to a run, hop up onto a rolling pin lying across his path, ride it as it rolls forward
(backpedalling on top, arms windmilling), kick it out behind him, pitch forward onto his head,
squash to a third of his height, rebound over the rest of the flip, land on his feet, wobble, settle.

Frames come in two modes. "gait" frames give the body pose plus separate world positions for each foot
(the hop and the ride are gait frames too, tagged with act="hop"/"ride"). "tumble" frames give a rigid body
transform (centre height cz, forward rotation theta about the body's centre) and a squash anchored at the
head, the centre or the feet. The legs move with the body, plus a tuck, and both feet are held back briefly
where the pin dragged them.

Conventions: design meters (he's ~0.58 tall; build_scene.py scales the whole character to 12 cm), seconds, Z up. Heading h is the travel direction in the XY plane (radians from +X).
The blob's front faces local -Y, so his yaw is h + pi/2. His left is local +X; his right leg is at -X.
"""
import math

G = 9.81
V_WALK, V_RUN = 0.45, 1.5             # m/s
A_START, A_RUN = 1.0, 1.5             # m/s^2: start walking, speed up to run
R_CIRCLE, R_TURN = 0.55, 0.7          # walk circle radius, run-up turn radius
START = (-1.0, 0.3)
H0 = -math.pi / 2                     # starts facing -Y, toward the camera
STAND_BEFORE = 5.0                    # s: an opening hold, close on him, to show the sparkles drifting
BREATH_HZ, BREATH_AMP = 0.45, 0.018   # while he stands: slow breathing, as squash (stretch on the in-breath)
BLINKS = (1.6, 3.55, 3.85)            # s: a blink, then a double blink, during the opening hold
BLINK_T = (0.06, 0.04, 0.10)          # s: close, hold shut, open
RUN_IN = 1.4                          # m of straight run before the rolling pin
# Rolling pin, in design units (x 0.207 for real size: a 5 cm barrel, 25 cm long, 10 cm handles)
PIN_R = 0.12                          # barrel radius; its top (0.24) is as high as the old hurdle bar
PIN_LEN = 1.2                         # barrel length
HANDLE_R, HANDLE_LEN = 0.055, 0.48
HOP_APEX = 0.12                       # how far his soles clear the top of the barrel
TUCK = 0.04                           # feet pull up under him in the air, m
RIDE_V = 0.85                         # m/s the pin rolls with him on top
RIDE_T = 2.4                          # s of riding before he kicks it out
RIDE_STEP = 2.4                       # backpedal cycles per second
SLIP_V = -1.7                         # m/s: the pin squirts back out from under him
PIN_DECEL = 1.2                       # m/s^2 rolling resistance on the marble
CLIP_POP = 0.5                        # m/s upward as the pin leaves his feet
VX_TRIP = 1.1                         # m/s forward while tumbling
HEAD_SQUASH = 1 / 3                   # height at the bottom of the head splat (done by the smoosh deformer)
HEAD_T = (0.08, 0.08, 0.15)           # s: squash down, hold (with a jiggle), ooze back up
VZ_REBOUND = 2.4                      # m/s up off his head
VX_REBOUND = 0.45                     # m/s forward on the rebound
# His eyes pop out on the head splat, roll away, and after he's back on his feet they roll back, sink into
# his base, float up through him and pop out into their sockets. The eye motion itself is built in
# build_scene.py; these are the timings (seconds), shared so the body can react.
EYE_RETURN_DELAY = 0.9                # after landing on his feet
EYE_ROLL_BACK = 1.4
EYE_ABSORB = 0.35                     # pushing in through the skin
EYE_FLOAT = 1.3                       # rising through the jelly
EYE_POP = 0.18
EYE_STAGGER = 0.2                     # the left eye trails the right
FROWN_DELAY = 0.8                     # after landing: he notices his eyes are gone
CAM_DELAY, CAM_MOVE = 0.2, 2.4        # after landing: the camera swings round past him to see his face
STAND_END = EYE_RETURN_DELAY + EYE_ROLL_BACK + EYE_STAGGER + EYE_ABSORB + EYE_FLOAT + EYE_POP + 1.2
PIVOT = 0.06                          # body bone head: lean and squash happen about this height

SPRING_W = 2 * math.pi * 4.0          # jelly wobble: 4 Hz
SPRING_Z = 0.35                       # damping ratio


def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def smooth(e0, e1, x):
    t = clamp((x - e0) / (e1 - e0))
    return t * t * (3 - 2 * t)


def lerp(a, b, t):
    return a + (b - a) * t


def stride(v):
    """Full gait-cycle length (two steps) at speed v. Short legs take quick little steps."""
    return max(0.17, 0.26 + 0.2 * (v - V_WALK))


def offset(h, lx, ly):
    """Body-local (lx, ly) offset -> world XY, for heading h."""
    s, c = math.sin(h), math.cos(h)
    return (lx * -s + ly * -c, lx * c + ly * -s)


def plan(fps, leg_x, leg_y, height):
    s_circle = 2 * math.pi * R_CIRCLE
    s_turn = s_circle + math.pi / 2 * R_TURN
    s_pin = s_turn + RUN_IN
    top = 2 * PIN_R
    v0 = math.sqrt(2 * G * (top + HOP_APEX))
    t_land = (v0 + math.sqrt(v0 * v0 - 2 * G * top)) / G   # coming down onto the top of the barrel
    s_takeoff = s_pin - V_RUN * t_land

    # ---- pass 1: integrate the path (arc length, speed, heading, gait phase) with substeps
    sub = 10
    dt = 1.0 / (fps * sub)
    t = s = v = phase = 0.0
    x, y = START
    h = H0
    t_to = None
    frames = []
    step = 0
    while True:
        if step % sub == 0:
            kappa = 1 / R_CIRCLE if s < s_circle else 1 / R_TURN if s < s_turn else 0.0
            frames.append(dict(t=t, s=s, v=v, x=x, y=y, h=h, phase=phase, kappa=kappa))
            if t_to is not None:
                break                              # the trip takes over from the first frame after takeoff
        step += 1
        # target speed and acceleration limit for where he is on the course
        if t < STAND_BEFORE:
            vt, acc = 0.0, A_START
        elif s < s_circle:
            vt, acc = V_WALK, A_START
        else:
            vt, acc = V_RUN, A_RUN
        v += clamp(vt - v, -acc * dt, acc * dt)
        kappa = 1 / R_CIRCLE if s < s_circle else 1 / R_TURN if s < s_turn else 0.0
        h += kappa * v * dt
        x += math.cos(h) * v * dt
        y += math.sin(h) * v * dt
        s += v * dt
        phase += v / stride(v) * dt
        t += dt
        if t_to is None and s >= s_takeoff:
            t_to = t

    n = len(frames)
    phases = [f["phase"] for f in frames]

    def at_phase(p):
        """Interpolated (x, y, h) of the path when the gait phase reaches p."""
        if p <= phases[0]:
            f = frames[0]
            return f["x"], f["y"], f["h"]
        lo, hi = 0, n - 1
        if p >= phases[hi]:
            f = frames[hi]
            return f["x"], f["y"], f["h"]
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if phases[mid] < p:
                lo = mid
            else:
                hi = mid
        a, b = frames[lo], frames[hi]
        u = (p - a["phase"]) / max(b["phase"] - a["phase"], 1e-12)
        return lerp(a["x"], b["x"], u), lerp(a["y"], b["y"], u), lerp(a["h"], b["h"], u)

    def at_time(tq):
        i = int(clamp(round(tq * fps), 0, n - 1))
        f = frames[i]
        return f["x"], f["y"], f["h"]

    def foot_at(pose, side):
        px, py, ph = pose
        ox, oy = offset(ph, side * leg_x, leg_y)
        return px + ox, py + oy, ph

    # ---- pass 2: body pose, squash spring and feet per frame
    legs = ((-1, 0.0), (1, 0.5))                    # (side, phase offset): right leg at -X, then left
    sq, sq_v = 0.0, 0.0                             # squash spring state (scale - 1, its velocity)
    acc_f = bank_f = 0.0
    out = []
    for i, f in enumerate(frames):
        t, v, ph = f["t"], f["v"], f["phase"]
        a_raw = (v - frames[i - 1]["v"]) * fps if i else 0.0
        acc_f += (a_raw - acc_f) * 0.2
        bank_f += (math.atan(v * v * f["kappa"] / G) * 1.5 - bank_f) * 0.15

        run = smooth(0.6, 1.3, v)                   # 0 walking .. 1 running
        moving = smooth(0.05, 0.2, v)
        duty = lerp(0.6, 0.35, run)                 # fraction of the cycle a foot is on the ground
        lift = lerp(0.02, 0.055, run)
        c2 = math.cos(4 * math.pi * (ph - duty / 2))  # twice per cycle, 1 at each mid-stance
        c1 = math.cos(2 * math.pi * (ph - duty / 2))  # once per cycle, 1 at right-leg mid-stance

        # walking vaults over the stance leg (high at mid-stance); running sinks into it
        z = moving * ((1 - run) * 0.010 * 0.5 * (1 + c2) + run * 0.022 * 0.5 * (1 - c2))
        sway = -moving * lerp(0.010, 0.004, run) * c1   # toward the stance leg (right leg is -X)
        roll = sway * 2.5 + bank_f
        pitch = 0.10 * run * moving + 0.04 * acc_f

        # squash/stretch: a damped spring around a target, kicked at takeoff and landing
        target = -run * moving * 0.05 * 0.5 * (1 + c2)
        breath = BREATH_AMP * math.sin(2 * math.pi * BREATH_HZ * t) * (1 - smooth(STAND_BEFORE - 0.4, STAND_BEFORE + 0.2, t))
        target += breath
        # crouch before the hop
        target = lerp(target, -0.18, smooth(t_to - 0.18, t_to - 0.08, t) * (1 - smooth(t_to - 0.04, t_to, t)))
        sq, sq_v = spring(sq, sq_v, target, 1.0 / fps)

        # feet
        feet = []
        for side, off in legs:
            p = ph + off
            k = math.floor(p)
            u = p - k
            plant_a = foot_at(at_phase(k + duty / 2 - off), side)
            if u < duty:
                fx, fy, fh = plant_a
                fz = 0.0
            else:
                plant_b = foot_at(at_phase(k + 1 + duty / 2 - off), side)
                w = (u - duty) / (1 - duty)
                ws = w * w * (3 - 2 * w)
                fx, fy, fh = (lerp(plant_a[j], plant_b[j], ws) for j in range(3))
                fz = lift * math.sin(math.pi * w)
            # standing still: feet settle under him
            nx, ny, nh = foot_at((f["x"], f["y"], f["h"]), side)
            fx, fy, fh, fz = lerp(nx, fx, moving), lerp(ny, fy, moving), lerp(nh, fh, moving), fz * moving
            # the hop: both feet come together and plant for the takeoff
            wj = smooth(t_to - 0.16, t_to - 0.08, t)
            if wj > 0:
                jx, jy, jh = foot_at(at_time(t_to - 0.06), side)
                fx, fy, fh, fz = lerp(fx, jx, wj), lerp(fy, jy, wj), lerp(fh, jh, wj), lerp(fz, 0.0, wj)
            feet.append((fx, fy, fz, fh + math.pi / 2))

        out.append(dict(mode="gait", x=f["x"], y=f["y"], z=z, yaw=f["h"] + math.pi / 2, pitch=pitch,
                        roll=roll, sway=sway, squash=1 + sq, feet=feet, smoosh=0.0, breath=breath))

    # ---- pass 3: hop onto the rolling pin, ride it, kick it out, tumble. Straight line along the takeoff heading.
    last = frames[-1]
    x0, y0, h = last["x"], last["y"], last["h"]
    ux, uy = math.cos(h), math.sin(h)
    C = height / 2                                  # rotate about the body's middle
    pitch0 = out[-1]["pitch"]
    d_pin0 = s_pin - last["s"]                      # pin axis, along the line from (x0, y0)
    vh = d_pin0 / t_land                            # hop speed so he comes down right on top of it
    t_slip = t_land + RIDE_T

    def pin_v(tau):
        """Pin speed tau seconds after he lands on it: carried forward with him, then kicked back out."""
        if tau < 0:
            return 0.0
        if tau < RIDE_T:
            return RIDE_V * (0.7 + 0.3 * smooth(0.0, 0.25, tau)) * (1 + 0.1 * math.sin(2 * math.pi * 1.1 * tau))
        ts = tau - RIDE_T
        v_s = pin_v(RIDE_T - 1e-6)
        if ts < 0.08:
            return lerp(v_s, SLIP_V, smooth(0.0, 0.08, ts))
        return min(SLIP_V + PIN_DECEL * (ts - 0.08), 0.0)

    def offset_on_pin(tau):
        """His body's lead over the pin axis while riding: lurch on landing, a balance wobble, and a tip
        forward as he kicks it away. Returns (total, lurch, wobble, tip)."""
        lurch = 0.06 * (1 - math.exp(-tau / 0.07)) * math.exp(-tau / 0.45)
        wob = 0.03 * math.sin(2 * math.pi * 1.3 * tau) * smooth(0.2, 0.8, tau)
        tip = 0.05 * smooth(RIDE_T - 0.35, RIDE_T, tau)
        return lurch + wob + tip, lurch, wob, tip

    def top_z(dx):
        dx = clamp(dx, -0.85 * PIN_R, 0.85 * PIN_R)
        return PIN_R + math.sqrt(PIN_R * PIN_R - dx * dx)

    def pose_at(d):
        return x0 + ux * d, y0 + uy * d, h

    # phase boundaries (seconds after takeoff) and the state at each; the slip state comes from the ride below
    off_s = offset_on_pin(RIDE_T)
    t_c = sum(HEAD_T)
    t2 = 2 * VZ_REBOUND / G
    t_end_guess = t_slip + 2.0 + t_c + t2 + STAND_END
    # pin track: integrate its speed finely over the whole shot
    sub = 20
    pin_d = [d_pin0]
    dpin = d_pin0
    for k in range(1, int(math.ceil(t_end_guess * fps)) + 2):
        for j in range(sub):
            tq = (k - 1 + (j + 0.5) / sub) / fps
            dpin += pin_v(tq - t_land) / (fps * sub)
        pin_d.append(dpin)

    def pin_at(tt):
        i = int(clamp(round(tt * fps), 0, len(pin_d) - 1))
        return pin_d[i]

    d_clip = pin_at(t_slip) + off_s[0]
    cz_clip = C + top_z(off_s[0])
    pitch_slip = 0.04 + 2.5 * off_s[2] + 3.0 * off_s[3] + off_s[1]
    # tumble: rotate pi while falling until the (upside-down) head is on the floor, i.e. cz = height - C
    a, b, c = 0.5 * G, -CLIP_POP, (height - C) - cz_clip
    t1 = (-b + math.sqrt(b * b - 4 * a * c)) / (2 * a)
    t_clip = t_slip
    t_head = t_clip + t1
    d_head = d_clip + VX_TRIP * t1
    t_launch = t_head + t_c
    d_launch = d_head + 0.35 * t_c
    theta_launch = math.pi + 0.25                   # keeps rolling a little while squashed
    t_feet = t_launch + t2
    d_feet = d_launch + VX_REBOUND * t2
    t_end = t_feet + STAND_END
    eyes = []
    for k in range(2):
        t_ret = t_feet + EYE_RETURN_DELAY + k * EYE_STAGGER
        t_abs = t_ret + EYE_ROLL_BACK
        t_flt = t_abs + EYE_ABSORB
        t_pop = t_flt + EYE_FLOAT
        eyes.append(dict(t_eject=t_head, t_return=t_ret, t_absorb=t_abs, t_float=t_flt, t_pop=t_pop,
                         t_done=t_pop + EYE_POP))
    kicks = [(e["t_absorb"], -0.5) for e in eyes] + [(e["t_pop"] + EYE_POP * 0.5, 0.7) for e in eyes]

    sq, sq_v = sq, sq_v + 2.5                       # spring off the ground: stretch
    n_trip = int(math.ceil(t_end * fps))
    landed = False
    for k in range(1, n_trip + 1):
        tt = k / fps
        hold_w = 0.0
        roll = 0.0
        smoosh = 0.0
        if tt < t_land:                             # the hop up onto the pin, legs tucking
            d = vh * tt
            z = v0 * tt - 0.5 * G * tt * tt
            sq, sq_v = spring(sq, sq_v, 0.0, 1.0 / fps)
            tuck = TUCK * smooth(0.0, 0.1, tt) * (1 - smooth(t_land - 0.1, t_land, tt))
            feet = []
            for side in (-1, 1):
                fx, fy, fh = foot_at(pose_at(d), side)
                feet.append((fx, fy, z + tuck, fh + math.pi / 2))
            out.append(dict(mode="gait", act="hop", x=x0 + ux * d, y=y0 + uy * d, z=z, yaw=h + math.pi / 2,
                            pitch=lerp(pitch0, 0.0, tt / t_land), roll=0.0, sway=0.0, squash=1 + sq,
                            feet=feet, smoosh=0.0))
            continue
        if tt < t_slip:                             # riding: carried forward on top, backpedalling
            tau = tt - t_land
            if not landed:
                sq_v -= 3.0                         # lands on the barrel with a squash
                landed = True
            off, lurch, wob, tip = offset_on_pin(tau)
            dp = pin_at(tt)
            d = dp + off
            ph = RIDE_STEP * tau
            bob = 0.012 * (0.5 + 0.5 * math.cos(4 * math.pi * ph))
            z = top_z(off) + bob
            sq, sq_v = spring(sq, sq_v, -0.04 * (0.5 + 0.5 * math.cos(4 * math.pi * ph)), 1.0 / fps)
            fade = smooth(0.0, 0.15, tau)
            ls = 0.10
            feet = []
            for side, po in ((-1, 0.0), (1, 0.5)):
                u = (ph + po) % 1.0
                if u < 0.5:                         # stance: the barrel top carries the foot forward
                    rel, lift = -ls / 2 + ls * u / 0.5, 0.0
                else:                               # swing it back for the next step
                    w = (u - 0.5) / 0.5
                    rel, lift = ls / 2 - ls * (w * w * (3 - 2 * w)), 0.045 * math.sin(math.pi * w)
                dx = 0.5 * off + rel * fade
                fx, fy, fh = foot_at(pose_at(dp + dx), side)
                feet.append((fx, fy, top_z(dx) + lift * fade, fh + math.pi / 2))
            out.append(dict(mode="gait", act="ride", x=x0 + ux * d, y=y0 + uy * d, z=z, yaw=h + math.pi / 2,
                            pitch=0.04 + 2.5 * wob + 3.0 * tip + lurch,
                            roll=0.07 * math.sin(2 * math.pi * 0.9 * tau + 0.5) * smooth(0.1, 0.5, tau),
                            sway=0.0, squash=1 + sq, feet=feet, smoosh=0.0))
            continue
        if tt < t_head:                             # pin kicked out: pitch forward onto his head
            tau = tt - t_clip
            d = d_clip + VX_TRIP * tau
            cz = cz_clip + CLIP_POP * tau - 0.5 * G * tau * tau
            theta = pitch_slip + (math.pi - pitch_slip) * (tau / t1) ** 1.3
            tuck = TUCK * smooth(0.0, t1, tau)
            hold_w = 1.0 - smooth(0.04, 0.12, tau)  # the feet get dragged back with the pin, then come free
            anchor, contact = C, None
            sq, sq_v = spring(sq, sq_v, 0.0, 1.0 / fps)
        elif tt < t_launch:                         # head splat: squash to a third, hold, spring back
            tau = tt - t_head
            d = d_head + 0.35 * tau
            cz = height - C
            theta = math.pi + 0.25 * tau / t_c
            tuck = 0.0
            down, hold, up = HEAD_T
            if tau < down:
                u = tau / down
                sq_abs = 1 - (1 - HEAD_SQUASH) * (1 - (1 - u) ** 2)
            elif tau < down + hold:
                jig = 0.06 * math.sin(math.pi * (tau - down) / hold * 2)   # a quick jelly jiggle while flat
                sq_abs = HEAD_SQUASH + (1 - HEAD_SQUASH) * abs(jig)
            else:
                sq_abs = HEAD_SQUASH + (1 - HEAD_SQUASH) * smooth(0.0, 1.0, (tau - down - hold) / up)
            # the body stays rigid; the smoosh deformer squashes him from the floor contact outward
            smoosh = (1 - sq_abs) / (1 - HEAD_SQUASH)
            sq, sq_v = 0.0, 0.0
            anchor, contact = height, "head"
        elif tt < t_feet:                           # rebound: up and over the second half of the flip
            tau = tt - t_launch
            if tt - 1.0 / fps < t_launch:
                sq_v = 1.8                          # leaves his head with a stretch
            d = d_launch + VX_REBOUND * tau
            cz = (height - C) + VZ_REBOUND * tau - 0.5 * G * tau * tau
            theta = theta_launch + (2 * math.pi - theta_launch) * (tau / t2)
            tuck = 0.03 * math.sin(math.pi * tau / t2)
            anchor, contact = C, None
            sq, sq_v = spring(sq, sq_v, 0.0, 1.0 / fps)
        else:                                       # feet down: splat, slide to a stop, dizzy wobble
            tau = tt - t_feet
            if tau < 1.0 / fps:
                sq_v -= 3.5
            for tk, kv in kicks:                    # gulp as each eye sinks in, jiggle as it pops out
                if tk <= tt < tk + 1.0 / fps:
                    sq_v += kv
            d = d_feet + VX_REBOUND * 0.12 * (1 - math.exp(-tau / 0.12))
            cz = C
            theta = 2 * math.pi
            tuck = 0.0
            roll = 0.08 * math.exp(-tau / 0.8) * math.sin(2 * math.pi * 1.3 * tau)
            anchor, contact = 0.0, "feet"
            sq, sq_v = spring(sq, sq_v, 0.0, 1.0 / fps)
        out.append(dict(mode="tumble", x=x0 + ux * d, y=y0 + uy * d, z=cz - C, cz=cz, C=C,
                        yaw=h + math.pi / 2, theta=theta, roll=roll, squash=1 + sq, anchor=anchor,
                        contact=contact, tuck=tuck, hold_w=hold_w, smoosh=smoosh))

    t0 = last["t"]
    eyes = [{k: t0 + v for k, v in e.items()} for e in eyes]
    T = dict(to=t0, land=t0 + t_land, clip=t0 + t_clip, head=t0 + t_head, launch=t0 + t_launch, feet=t0 + t_feet,
             frown=t0 + t_feet + FROWN_DELAY, smile=max(e["t_done"] for e in eyes))
    secondary(out, fps, leg_y, T)
    pin = []
    for i in range(len(out)):
        dp = pin_d[0] if i < len(frames) else pin_at((i - len(frames) + 1) / fps)
        pin.append((x0 + ux * dp, y0 + uy * dp, (dp - d_pin0) / PIN_R))
    return dict(frames=out, pin=pin, pin_h=h, t_takeoff=t0, t_land=t0 + t_land, t_clip=t0 + t_clip, t_head=t0 + t_head,
                t_feet=t0 + t_feet, eyes=eyes, t_frown=t0 + t_feet + FROWN_DELAY,
                t_smile=max(e["t_done"] for e in eyes), start=START, h0=H0)


def secondary(out, fps, leg_y, T):
    """Add arm angles and the chest's follow-through to every frame (in place).

    Arms: "swing_R/L" rotates about his left-right axis (positive swings the arm back), "abd_R/L" raises it
    out to the side. They swing opposite the feet when walking, go back for the crouch and forward for the
    hop, flail in the trip, splay on the splat, droop while he's eyeless, and go up in a cheer when his eyes
    are back. A springy follower smooths the targets so the arms lag and overshoot a little.
    Chest: "lag" is a world-space tilt (x, y) of the upper body, a spring driven by his horizontal
    acceleration: it lags when he speeds up and swings forward when he stops. It's off while he tumbles."""
    dt = 1.0 / fps
    tgt = []
    for i, f in enumerate(out):
        t = i * dt
        sw = [0.0, 0.0]
        ab = [0.12, 0.12]
        if f.get("act") == "hop":                                     # hop: reach forward
            sw, ab = [-0.9, -0.9], [0.5, 0.5]
        elif f.get("act") == "ride":                                  # riding the pin: windmill for balance
            tau = t - T["land"]
            big = smooth(0.05, 0.3, tau)
            sw = [lerp(-0.9, 1.3 * math.sin(2 * math.pi * 1.7 * tau + k * math.pi / 2), big) for k in range(2)]
            ab = [lerp(0.5, 0.95 + 0.35 * math.cos(2 * math.pi * 1.7 * tau + k * math.pi / 2), big) for k in range(2)]
        elif f["mode"] == "gait":
            h = f["yaw"] - math.pi / 2
            fx, fy = math.cos(h), math.sin(h)
            run = smooth(0.6, 1.3, math.hypot(*(
                (out[min(i + 1, len(out) - 1)][c] - out[max(i - 1, 0)][c]) * fps / 2 for c in ("x", "y"))))
            for k in range(2):
                foot = f["feet"][k]
                rel = (foot[0] - f["x"]) * fx + (foot[1] - f["y"]) * fy + leg_y   # + forward of rest spot
                sw[k] = clamp(4.5 * rel, -0.7, 0.7)
                ab[k] = 0.12 + 0.25 * run + 2.5 * f.get("breath", 0.0)   # arms lift a touch on the in-breath
            w = smooth(T["to"] - 0.25, T["to"] - 0.08, t)          # wind up: arms back for the hop
            sw = [lerp(v, 0.6, w) for v in sw]
            ab = [lerp(v, 0.3, w) for v in ab]
        elif t < T["clip"]:                                           # hop: reach forward
            sw, ab = [-0.9, -0.9], [0.5, 0.5]
        elif t < T["head"]:                                           # trip: flail
            tau = t - T["clip"]
            sw = [0.6 * math.sin(2 * math.pi * 5 * tau + k * math.pi) for k in range(2)]
            ab = [1.1 + 0.25 * math.sin(2 * math.pi * 5 * tau + k * 1.3) for k in range(2)]
        elif t < T["launch"]:                                         # splat: splayed out flat
            sw, ab = [0.0, 0.0], [1.4, 1.4]
        elif t < T["feet"]:                                           # rebound
            u = (t - T["launch"]) / max(T["feet"] - T["launch"], 1e-6)
            sw = [0.3 * math.sin(2 * math.pi * 3 * u + k * math.pi) for k in range(2)]
            ab = [lerp(1.1, 0.6, u)] * 2
        else:
            tau = t - T["feet"]
            a = 0.15 + 0.45 * math.exp(-tau / 0.25) * math.cos(2 * math.pi * 2.5 * tau)
            droop = smooth(T["frown"], T["frown"] + 0.3, t) * (1 - smooth(T["smile"] - 0.1, T["smile"], t))
            cheer = smooth(T["smile"], T["smile"] + 0.15, t) * (1 - smooth(T["smile"] + 0.7, T["smile"] + 1.1, t))
            a = lerp(a, 0.04, droop)
            sw = [lerp(0.0, 0.18, droop)] * 2
            wig = 0.15 * math.sin(2 * math.pi * 4 * (t - T["smile"]))
            ab = [lerp(a, 1.5 + wig * (1 if k else -1), cheer) for k in range(2)]
            sw = [lerp(v, -0.3, cheer) for v in sw]
        tgt.append((sw, ab))

    # springy follower on all four arm angles
    wn, zeta = 2 * math.pi * 3.0, 0.55
    state = [[tgt[0][0][k], 0.0] for k in range(2)] + [[tgt[0][1][k], 0.0] for k in range(2)]
    for i, f in enumerate(out):
        goals = tgt[i][0] + tgt[i][1]
        for j in range(4):
            x, v = state[j]
            for _ in range(10):
                h = dt / 10
                v += (-wn * wn * (x - goals[j]) - 2 * zeta * wn * v) * h
                x += v * h
            state[j] = [x, v]
        f["swing_R"], f["swing_L"], f["abd_R"], f["abd_L"] = (state[j][0] for j in range(4))

    # chest follow-through
    wn, zeta, gain, cap = 2 * math.pi * 2.2, 0.3, 7.0, 0.15
    th = [0.0, 0.0]
    om = [0.0, 0.0]
    acc = [0.0, 0.0]
    n = len(out)
    for i, f in enumerate(out):
        t = i * dt
        a_raw = [(out[min(i + 1, n - 1)][c] - 2 * f[c] + out[max(i - 1, 0)][c]) * fps * fps for c in ("x", "y")]
        on = 1.0 if f["mode"] == "gait" else smooth(T["feet"], T["feet"] + 0.15, t)
        for k in range(2):
            acc[k] += (a_raw[k] * on - acc[k]) * 0.3
            for _ in range(10):
                h = dt / 10
                om[k] += (-wn * wn * th[k] - 2 * zeta * wn * om[k] - gain * acc[k]) * h
                th[k] += om[k] * h
        m = math.hypot(*th)
        if m > cap:
            th = [c * cap / m for c in th]
        f["lag"] = (th[0] * on, th[1] * on)


def blink(t):
    """Eye openness (1 open .. ~0.08 shut) at time t; build_scene.py squashes the eyes vertically by it."""
    c, h, o = BLINK_T
    shut = 0.0
    for tb in BLINKS:
        u = t - tb
        if 0 <= u < c:
            shut = max(shut, smooth(0.0, c, u))
        elif c <= u < c + h:
            shut = 1.0
        elif c + h <= u < c + h + o:
            shut = max(shut, 1 - smooth(0.0, o, u - c - h))
    return 1 - 0.92 * shut


def spring(x, v, target, dt, sub=10):
    """Advance the squash spring (x = scale - 1) by dt."""
    h = dt / sub
    for _ in range(sub):
        a = -SPRING_W ** 2 * (x - target) - 2 * SPRING_Z * SPRING_W * v
        v += a * h
        x += v * h
    return x, v


if __name__ == "__main__":
    p = plan(24, 0.105, -0.02, 0.58)
    fr = p["frames"]
    print("frames", len(fr), "takeoff", round(p["t_takeoff"], 2), "clip", round(p["t_clip"], 2),
          "head", round(p["t_head"], 2), "feet", round(p["t_feet"], 2),
          "land", round(p["t_land"], 2))
    px = [q[0] for q in p["pin"]]
    print("pin x range", round(min(px), 2), round(max(px), 2), "pin heading", round(p["pin_h"], 2))
    xs = [f["x"] for f in fr]
    ys = [f["y"] for f in fr]
    print("x range", round(min(xs), 2), round(max(xs), 2), "y range", round(min(ys), 2), round(max(ys), 2))
    print("max z", round(max(f["z"] for f in fr), 3), "squash range",
          round(min(f["squash"] for f in fr), 3), round(max(f["squash"] for f in fr), 3))
