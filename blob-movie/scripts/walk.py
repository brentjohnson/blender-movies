"""Walk-test choreography for the blob. Pure math, no bpy, so it can be checked outside Blender.

plan(fps, leg_x, leg_y, height) returns per-frame poses for: stand, walk a full circle, turn while
speeding up to a run, try to hop a hurdle but clip it with the right foot, tumble forward onto his head,
squash to a third of his height, rebound over the rest of the flip, land on his feet, wobble, settle.

Frames come in two modes. "gait" frames give the body pose plus separate world positions for each foot.
"tumble" frames give a rigid body transform (centre height cz, forward rotation theta about the body's
centre) and a squash anchored at the head, the centre or the feet. The legs move with the body, plus a
tuck, and the right foot can be held back where it caught the bar.

Conventions: meters, seconds, Z up. Heading h is the travel direction in the XY plane (radians from +X).
The blob's front faces local -Y, so his yaw is h + pi/2. His left is local +X; his right leg is at -X.
"""
import math

G = 9.81
V_WALK, V_RUN = 0.45, 1.5             # m/s
A_START, A_RUN = 1.0, 1.5             # m/s^2: start walking, speed up to run
R_CIRCLE, R_TURN = 0.55, 0.7          # walk circle radius, run-up turn radius
START = (-1.0, 0.3)
H0 = -math.pi / 2                     # starts facing -Y, toward the camera
STAND_BEFORE = 0.6                    # s
RUN_IN = 1.4                          # m of straight run before the hurdle
HURDLE_H = 0.24                       # bar height, m
TRIP_LIFT = 0.15                      # the hop is too low: his soles reach ~0.19 m, under the bar
TUCK = 0.04                           # feet pull up under him in the air, m
CLIP_BEFORE = 0.07                    # body this far short of the bar when the right foot catches it
CLIP_POP = 1.2                        # m/s upward kick from the bar as he trips over it
VX_TRIP = 1.8                         # m/s forward while tumbling
HEAD_SQUASH = 1 / 3                   # height at the bottom of the head splat (done by the smoosh deformer)
HEAD_T = (0.08, 0.08, 0.15)           # s: squash down, hold (with a jiggle), ooze back up
VZ_REBOUND = 2.4                      # m/s up off his head
VX_REBOUND = 0.45                     # m/s forward on the rebound
STAND_END = 1.8                       # s on his feet at the end
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
    s_hurdle = s_turn + RUN_IN
    v0 = math.sqrt(2 * G * TRIP_LIFT)
    t_apex = v0 / G
    s_takeoff = s_hurdle - CLIP_BEFORE - V_RUN * t_apex   # top of the hop is where the foot catches

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
                        roll=roll, sway=sway, squash=1 + sq, feet=feet, smoosh=0.0))

    # ---- pass 3: the trip. Straight line along the takeoff heading, phase by phase.
    last = frames[-1]
    x0, y0, h = last["x"], last["y"], last["h"]
    ux, uy = math.cos(h), math.sin(h)
    C = height / 2                                  # rotate about the body's middle
    pitch0 = out[-1]["pitch"]
    hurdle = (x0 + ux * (s_hurdle - last["s"]), y0 + uy * (s_hurdle - last["s"]), h)

    # phase boundaries (seconds after takeoff) and the state at each
    t_clip = t_apex
    d_clip = V_RUN * t_clip
    cz_clip = C + TRIP_LIFT
    # tumble: rotate pi while falling until the (upside-down) head is on the floor, i.e. cz = height - C
    a, b, c = 0.5 * G, -CLIP_POP, (height - C) - cz_clip
    t1 = (-b + math.sqrt(b * b - 4 * a * c)) / (2 * a)
    t_head = t_clip + t1
    d_head = d_clip + VX_TRIP * t1
    t_c = sum(HEAD_T)
    t_launch = t_head + t_c
    d_launch = d_head + 0.35 * t_c
    theta_launch = math.pi + 0.25                   # keeps rolling a little while squashed
    t2 = 2 * VZ_REBOUND / G
    t_feet = t_launch + t2
    d_feet = d_launch + VX_REBOUND * t2
    t_end = t_feet + STAND_END

    sq, sq_v = sq, sq_v + 2.5                       # spring off the ground: stretch
    n_trip = int(math.ceil(t_end * fps))
    for k in range(1, n_trip + 1):
        tt = k / fps
        hold_w = 0.0
        roll = 0.0
        smoosh = 0.0
        if tt < t_clip:                             # rising into the hop, legs tucking
            d = V_RUN * tt
            cz = C + v0 * tt - 0.5 * G * tt * tt
            theta = pitch0 * (1 - tt / t_clip)
            tuck = TUCK * smooth(0.0, 0.1, tt)
            anchor, contact = C, None
            sq, sq_v = spring(sq, sq_v, 0.0, 1.0 / fps)
        elif tt < t_head:                           # foot caught: tumble forward
            tau = tt - t_clip
            d = d_clip + VX_TRIP * tau
            cz = cz_clip + CLIP_POP * tau - 0.5 * G * tau * tau
            theta = math.pi * (tau / t1) ** 1.3
            tuck = TUCK * (1 - smooth(0.0, t1, tau))
            hold_w = 1.0 - smooth(0.06, 0.14, tau)  # the right foot stays at the bar, then snaps free
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
    return dict(frames=out, hurdle=hurdle, t_takeoff=t0, t_clip=t0 + t_clip, t_head=t0 + t_head,
                t_feet=t0 + t_feet, start=START, h0=H0)


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
          "hurdle", [round(c, 2) for c in p["hurdle"]])
    xs = [f["x"] for f in fr]
    ys = [f["y"] for f in fr]
    print("x range", round(min(xs), 2), round(max(xs), 2), "y range", round(min(ys), 2), round(max(ys), 2))
    print("max z", round(max(f["z"] for f in fr), 3), "squash range",
          round(min(f["squash"] for f in fr), 3), round(max(f["squash"] for f in fr), 3))
