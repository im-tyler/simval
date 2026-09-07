"""Ontos gravity reference: independent version-2 stream verifier.

Implements the gravity epoch of the ontos stream spec (ontos
docs/STREAM_SPEC.md Part II) strictly from the spec text and verifies
recorded streams against this reimplementation. Pure stdlib. Float ops
stay in the spec closure (+ - * / sqrt) with fixed order, so this
reference is bit-compatible with the Rust simulator.
"""
from __future__ import annotations

import math
import struct
import sys
from pathlib import Path

from simval.ontos import MAGIC, fnv1a64, parse_stream
from simval.result import DiagnosticResult

G = 1.0
EPS2 = 1.0
DT = 1.0 / 1024.0
WINDOW = 32
DEGREE = 8
SAMPLES = 33
UNMANAGED = 255
TWO_POW_NEG64 = 2.0**-64


class SplitMix64:
    def __init__(self, seed: int) -> None:
        self.state = seed & 0xFFFFFFFFFFFFFFFF

    def next(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
        return z ^ (z >> 31)


def initial_conditions(seed: int, count: int) -> list:
    rng = SplitMix64(seed)
    bodies = []
    for i in range(count):
        u0 = rng.next()
        u1 = rng.next()
        u2 = rng.next()
        u3 = rng.next()
        u4 = rng.next()
        bodies.append(
            {
                "id": i,
                "mass": 0.5 + u0 * TWO_POW_NEG64 * 2.0,
                "x": 32.0 + u1 * TWO_POW_NEG64 * 64.0,
                "y": 32.0 + u2 * TWO_POW_NEG64 * 64.0,
                "vx": (u3 * TWO_POW_NEG64 - 0.5) * 0.5,
                "vy": (u4 * TWO_POW_NEG64 - 0.5) * 0.5,
            }
        )
    return bodies


def region_at(x: float, y: float) -> int:
    if x < 0.0 or x >= 128.0 or y < 0.0 or y >= 128.0:
        return UNMANAGED
    rx = int(x / 64.0)
    ry = int(y / 64.0)
    return ry * 2 + rx


def clenshaw(c, s: float) -> float:
    b1 = 0.0
    b2 = 0.0
    for j in range(DEGREE, 0, -1):
        b0 = c[j] + 2.0 * s * b1 - b2
        b2 = b1
        b1 = b0
    return c[0] + s * b1 - b2


def cheb_table():
    t = [[0.0] * SAMPLES for _ in range(DEGREE + 1)]
    w = [1.0] * SAMPLES
    w[0] = 0.5
    w[SAMPLES - 1] = 0.5
    for k in range(SAMPLES):
        s = -1.0 + k / 16.0
        t[0][k] = 1.0
        t[1][k] = s
        for j in range(2, DEGREE + 1):
            t[j][k] = 2.0 * s * t[j - 1][k] - t[j - 2][k]
    return t, w


CHEB_T, CHEB_W = cheb_table()


def project(ys):
    g = [[0.0] * (DEGREE + 1) for _ in range(DEGREE + 1)]
    for j in range(DEGREE + 1):
        for l in range(DEGREE + 1):
            total = 0.0
            for k in range(SAMPLES):
                total += CHEB_W[k] * CHEB_T[j][k] * CHEB_T[l][k]
            g[j][l] = total
    b = [0.0] * (DEGREE + 1)
    for j in range(DEGREE + 1):
        total = 0.0
        for k in range(SAMPLES):
            total += CHEB_W[k] * ys[k] * CHEB_T[j][k]
        b[j] = total
    return cholesky_solve(g, b)


def cholesky_solve(g, b):
    n = DEGREE + 1
    l = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            total = g[i][j]
            for k in range(j):
                total -= l[i][k] * l[j][k]
            if i == j:
                l[i][j] = math.sqrt(total)
            else:
                l[i][j] = total / l[j][j]
    z = [0.0] * n
    for i in range(n):
        total = b[i]
        for k in range(i):
            total -= l[i][k] * z[k]
        z[i] = total / l[i][i]
    c = [0.0] * n
    for i in range(n - 1, -1, -1):
        total = z[i]
        for k in range(i + 1, n):
            total -= l[k][i] * c[k]
        c[i] = total / l[i][i]
    return c


def subset_energy(bodies) -> float:
    """Section 15 energy over a body list (KE in id order, then PE i<j)."""
    ke = 0.0
    for b in bodies:
        ke += 0.5 * b["mass"] * (b["vx"] * b["vx"] + b["vy"] * b["vy"])
    pe = 0.0
    n = len(bodies)
    for i in range(n):
        for j in range(i + 1, n):
            dx = bodies[j]["x"] - bodies[i]["x"]
            dy = bodies[j]["y"] - bodies[i]["y"]
            s2 = dx * dx + dy * dy + EPS2
            pe -= bodies[i]["mass"] * bodies[j]["mass"] / math.sqrt(s2)
    return ke + pe


class GravityWorld:
    def __init__(self, seed: int, count: int) -> None:
        self.seed = seed
        self.bodies = initial_conditions(seed, count)
        self.coarse = [None] * count
        self.body_region = [UNMANAGED] * count
        self.region_coarse = [False] * 4
        self.region_collapsed = [None] * 4
        self.body_collapsed = [None] * count
        self.reconstructed: set[int] = set()
        self.last_collapses = []
        self.last_expansion = None
        self.expand_count = 0
        self.events: dict[int, list[tuple[int, int]]] = {}
        self.tick = 0
        px = 0.0
        py = 0.0
        for b in self.bodies:
            px += b["mass"] * b["vx"]
            py += b["mass"] * b["vy"]
        self.px = px
        self.py = py

    def schedule(self, tick: int, region: int, level: int) -> None:
        self.events.setdefault(tick, []).append((region, level))

    def _state_at(self, i: int, t: int) -> dict:
        collapsed = self.body_collapsed[i]
        if collapsed is not None:
            rec = self.region_collapsed[collapsed]
            jx, jy = rec["jitter"][i]
            return {
                "id": i,
                "mass": self.bodies[i]["mass"],
                "x": rec["com_x"] + jx,
                "y": rec["com_y"] + jy,
                "vx": rec["vcom_x"],
                "vy": rec["vcom_y"],
            }
        b = dict(self.bodies[i])
        fit = self.coarse[i]
        if fit is not None:
            s = -1.0 + (t - fit["t0"]) / 16.0
            b["x"] = clenshaw(fit["c"][0], s)
            b["y"] = clenshaw(fit["c"][1], s)
            b["vx"] = clenshaw(fit["c"][2], s)
            b["vy"] = clenshaw(fit["c"][3], s)
        return b

    def _leapfrog(self, bodies):
        half = DT * 0.5
        ax, ay = self._accumulate(bodies)
        for i, b in enumerate(bodies):
            b["vx"] += ax[i] * half
            b["vy"] += ay[i] * half
        for b in bodies:
            b["x"] += b["vx"] * DT
            b["y"] += b["vy"] * DT
        ax, ay = self._accumulate(bodies)
        for i, b in enumerate(bodies):
            b["vx"] += ax[i] * half
            b["vy"] += ay[i] * half

    @staticmethod
    def _accumulate(bodies):
        n = len(bodies)
        ax = [0.0] * n
        ay = [0.0] * n
        for i in range(n):
            for j in range(i + 1, n):
                dx = bodies[j]["x"] - bodies[i]["x"]
                dy = bodies[j]["y"] - bodies[i]["y"]
                s2 = dx * dx + dy * dy + EPS2
                inv3 = 1.0 / (s2 * math.sqrt(s2))
                fx = G * inv3 * dx
                fy = G * inv3 * dy
                ax[i] += bodies[j]["mass"] * fx
                ay[i] += bodies[j]["mass"] * fy
                ax[j] -= bodies[i]["mass"] * fx
                ay[j] -= bodies[i]["mass"] * fy
        return ax, ay

    def _pre_integrate(self, bodies):
        samples = [[dict(b) for _ in range(SAMPLES)] for b in bodies]
        cur = [dict(b) for b in bodies]
        for k in range(1, SAMPLES):
            self._leapfrog(cur)
            for i, b in enumerate(cur):
                samples[i][k] = dict(b)
        return samples

    def _fit_members(self, members, t0):
        subset = [self._state_at(i, t0) for i in members]
        samples = self._pre_integrate(subset)
        for slot, i in enumerate(members):
            fits = [
                project([s["x"] for s in samples[slot]]),
                project([s["y"] for s in samples[slot]]),
                project([s["vx"] for s in samples[slot]]),
                project([s["vy"] for s in samples[slot]]),
            ]
            self.coarse[i] = {"c": fits, "t0": t0}

    def _demote(self, region: int, t0: int) -> None:
        x0 = (region % 2) * 64.0
        y0 = (region // 2) * 64.0
        members = [
            i
            for i in range(len(self.bodies))
            if (lambda b: b["x"] >= x0 and b["x"] < x0 + 64.0 and b["y"] >= y0 and b["y"] < y0 + 64.0)(
                self._state_at(i, t0)
            )
        ]
        self.region_coarse[region] = True
        if not members:
            return
        self._fit_members(members, t0)
        for i in members:
            self.body_region[i] = region

    def _promote(self, region: int, t: int) -> None:
        for i in range(len(self.bodies)):
            if self.coarse[i] is not None and self.body_region[i] == region:
                self.bodies[i] = self._state_at(i, t)
                self.coarse[i] = None
                self.body_region[i] = UNMANAGED
        self.region_coarse[region] = False

    def _collapse(self, region: int, t: int) -> None:
        for i in range(len(self.bodies)):
            if self.coarse[i] is not None and self.body_region[i] == region:
                self.bodies[i] = self._state_at(i, t)
                self.coarse[i] = None
                self.body_region[i] = UNMANAGED
        self.region_coarse[region] = False
        x0 = (region % 2) * 64.0
        y0 = (region // 2) * 64.0
        members = [
            i
            for i in range(len(self.bodies))
            if self.bodies[i]["x"] >= x0
            and self.bodies[i]["x"] < x0 + 64.0
            and self.bodies[i]["y"] >= y0
            and self.bodies[i]["y"] < y0 + 64.0
        ]
        mass = 0.0
        mx = 0.0
        my = 0.0
        px = 0.0
        py = 0.0
        for i in members:
            b = self.bodies[i]
            mass += b["mass"]
            mx += b["mass"] * b["x"]
            my += b["mass"] * b["y"]
            px += b["mass"] * b["vx"]
            py += b["mass"] * b["vy"]
        if members:
            com_x = mx / mass
            com_y = my / mass
            vcom_x = px / mass
            vcom_y = py / mass
        else:
            com_x = 0.0
            com_y = 0.0
            vcom_x = 0.0
            vcom_y = 0.0
        rng = SplitMix64(self.seed ^ ((region * 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF))
        jitter = {}
        for i in members:
            jx = (rng.next() * TWO_POW_NEG64 - 0.5) * 8.0
            jy = (rng.next() * TWO_POW_NEG64 - 0.5) * 8.0
            jitter[i] = (jx, jy)
        spread = {}
        for i in members[:-1]:
            sx = (rng.next() * TWO_POW_NEG64 - 0.5) * 0.1
            sy = (rng.next() * TWO_POW_NEG64 - 0.5) * 0.1
            spread[i] = (sx, sy)
        syn = [
            {
                "id": i,
                "mass": self.bodies[i]["mass"],
                "x": com_x + jitter[i][0],
                "y": com_y + jitter[i][1],
                "vx": vcom_x,
                "vy": vcom_y,
            }
            for i in members
        ]
        rec = {
            "tick": t,
            "region": region,
            "count": len(members),
            "mass": mass,
            "com_x": com_x,
            "com_y": com_y,
            "vcom_x": vcom_x,
            "vcom_y": vcom_y,
            "px": px,
            "py": py,
            "energy": subset_energy([self.bodies[i] for i in members]) if members else 0.0,
            "syn_energy": subset_energy(syn),
            "members": members,
            "jitter": jitter,
            "spread": spread,
        }
        self.region_collapsed[region] = rec
        self.last_collapses.append(rec)
        for i in members:
            self.body_collapsed[i] = region
            self.body_region[i] = region

    def _expand(self, region: int, t: int) -> None:
        rec = self.region_collapsed[region]
        members = rec["members"]
        states = []
        if members:
            sum_mvx = 0.0
            sum_mvy = 0.0
            for i in members[:-1]:
                jx, jy = rec["jitter"][i]
                sx, sy = rec["spread"][i]
                b = {
                    "id": i,
                    "mass": self.bodies[i]["mass"],
                    "x": rec["com_x"] + jx,
                    "y": rec["com_y"] + jy,
                    "vx": rec["vcom_x"] + sx,
                    "vy": rec["vcom_y"] + sy,
                }
                states.append(b)
                sum_mvx += b["mass"] * b["vx"]
                sum_mvy += b["mass"] * b["vy"]
            last = members[-1]
            m_last = self.bodies[last]["mass"]
            states.append(
                {
                    "id": last,
                    "mass": m_last,
                    "x": rec["com_x"] + rec["jitter"][last][0],
                    "y": rec["com_y"] + rec["jitter"][last][1],
                    "vx": (rec["px"] - sum_mvx) / m_last,
                    "vy": (rec["py"] - sum_mvy) / m_last,
                }
            )
            for b in states:
                self.bodies[b["id"]] = b
                self.body_collapsed[b["id"]] = None
                self.body_region[b["id"]] = UNMANAGED
                self.reconstructed.add(b["id"])
        self.region_collapsed[region] = None
        self.expand_count += 1
        self.last_expansion = {
            "tick": t,
            "region": region,
            "target_px": rec["px"],
            "target_py": rec["py"],
            "bodies": [dict(b) for b in states],
        }

    def _refit(self, region: int, t: int) -> None:
        x0 = (region % 2) * 64.0
        y0 = (region // 2) * 64.0
        members = [
            i for i in range(len(self.bodies)) if self.coarse[i] is not None and self.body_region[i] == region
        ]
        for i in members:
            self.bodies[i] = self._state_at(i, t)
        keep = [
            i
            for i in members
            if self.bodies[i]["x"] >= x0
            and self.bodies[i]["x"] < x0 + 64.0
            and self.bodies[i]["y"] >= y0
            and self.bodies[i]["y"] < y0 + 64.0
        ]
        for i in members:
            if i not in keep:
                self.coarse[i] = None
                self.body_region[i] = UNMANAGED
        if not keep:
            self.region_coarse[region] = False
            return
        self._fit_members(keep, t)
        for i in keep:
            self.body_region[i] = region

    def step(self) -> None:
        entering = self.tick + 1
        for region, level in self.events.pop(entering, []):
            if level == 0:
                if self.region_collapsed[region] is None:
                    self._demote(region, entering)
            elif level == 1:
                if self.region_collapsed[region] is not None:
                    self._expand(region, entering)
                else:
                    self._promote(region, entering)
            elif self.region_collapsed[region] is None:
                self._collapse(region, entering)
        for region in range(4):
            if self.region_coarse[region] and self.region_collapsed[region] is None:
                ended = any(
                    self.body_region[i] == region
                    and self.coarse[i] is not None
                    and entering == self.coarse[i]["t0"] + WINDOW
                    for i in range(len(self.bodies))
                )
                if ended:
                    self._refit(region, entering)

        n = len(self.bodies)
        coarse = [self.coarse[i] is not None for i in range(n)]
        frozen = [coarse[i] or self.body_collapsed[i] is not None for i in range(n)]
        monopoles = [
            self.region_collapsed[r]
            for r in range(4)
            if self.region_collapsed[r] is not None and self.region_collapsed[r]["mass"] > 0.0
        ]
        half = DT * 0.5
        view = [self._state_at(i, entering) for i in range(n)]
        ax_ff, ay_ff, ax_fc, ay_fc = accel_split(view, coarse, self.body_collapsed, monopoles)
        for i in range(n):
            if not frozen[i]:
                self.bodies[i]["vx"] += ax_ff[i] * half
                self.bodies[i]["vy"] += ay_ff[i] * half
        for i in range(n):
            if not frozen[i]:
                self.bodies[i]["vx"] += ax_fc[i] * half
                self.bodies[i]["vy"] += ay_fc[i] * half
                self.px += self.bodies[i]["mass"] * (ax_fc[i] * half)
                self.py += self.bodies[i]["mass"] * (ay_fc[i] * half)
        for i in range(n):
            if not frozen[i]:
                self.bodies[i]["x"] += self.bodies[i]["vx"] * DT
                self.bodies[i]["y"] += self.bodies[i]["vy"] * DT
        view = [self._state_at(i, entering) for i in range(n)]
        ax_ff, ay_ff, ax_fc, ay_fc = accel_split(view, coarse, self.body_collapsed, monopoles)
        for i in range(n):
            if not frozen[i]:
                self.bodies[i]["vx"] += ax_ff[i] * half
                self.bodies[i]["vy"] += ay_ff[i] * half
        for i in range(n):
            if not frozen[i]:
                self.bodies[i]["vx"] += ax_fc[i] * half
                self.bodies[i]["vy"] += ay_fc[i] * half
                self.px += self.bodies[i]["mass"] * (ax_fc[i] * half)
                self.py += self.bodies[i]["mass"] * (ay_fc[i] * half)
        self.tick = entering

    def totals(self):
        n = len(self.bodies)
        view = [self._state_at(i, self.tick) for i in range(n)]
        fine = 0
        coarse_n = 0
        mass = 0.0
        for b in view:
            if self.coarse[b["id"]] is not None or self.body_collapsed[b["id"]] is not None:
                coarse_n += 1
            else:
                fine += 1
            mass += b["mass"]
        return fine, coarse_n, mass, self.px, self.py, subset_energy(view)

    def state_bytes(self, i: int) -> bytes:
        b = self._state_at(i, self.tick)
        if self.body_collapsed[i] is not None:
            level = 2
        elif self.coarse[i] is not None:
            level = 0
        else:
            level = 1
        return struct.pack(
            "<IdddddB", b["id"], b["x"], b["y"], b["vx"], b["vy"], b["mass"], level
        )

    def emitted_state(self, i: int):
        b = self._state_at(i, self.tick)
        if self.body_collapsed[i] is not None:
            level = 2
            region = self.body_collapsed[i]
        elif self.coarse[i] is not None:
            level = 0
            region = self.body_region[i]
        else:
            level = 1
            region = region_at(b["x"], b["y"])
        return b, region, level

    def region_hash(self, region: int):
        members = []
        for i in range(len(self.bodies)):
            if self.body_collapsed[i] is not None:
                if self.body_collapsed[i] == region:
                    members.append(i)
            elif self.coarse[i] is not None:
                if self.body_region[i] == region:
                    members.append(i)
            else:
                b = self._state_at(i, self.tick)
                if region_at(b["x"], b["y"]) == region:
                    members.append(i)
        if self.region_collapsed[region] is not None:
            level = 2
        elif self.region_coarse[region]:
            level = 0
        else:
            level = 1
        payload = bytes([level])
        for i in sorted(members):
            payload += self.state_bytes(i)
        return level, len(members), fnv1a64(payload)

    def world_hash(self) -> int:
        payload = struct.pack("<Q", self.tick)
        for i in range(len(self.bodies)):
            payload += self.state_bytes(i)
        return fnv1a64(payload)


def accel_split(view, coarse, body_collapsed=None, monopoles=None):
    n = len(view)
    ax_ff = [0.0] * n
    ay_ff = [0.0] * n
    ax_fc = [0.0] * n
    ay_fc = [0.0] * n
    for i in range(n):
        for j in range(i + 1, n):
            if body_collapsed is not None and (body_collapsed[i] is not None or body_collapsed[j] is not None):
                continue
            dx = view[j]["x"] - view[i]["x"]
            dy = view[j]["y"] - view[i]["y"]
            s2 = dx * dx + dy * dy + EPS2
            inv3 = 1.0 / (s2 * math.sqrt(s2))
            fx = G * inv3 * dx
            fy = G * inv3 * dy
            ci, cj = coarse[i], coarse[j]
            if not ci and not cj:
                ax_ff[i] += view[j]["mass"] * fx
                ay_ff[i] += view[j]["mass"] * fy
                ax_ff[j] -= view[i]["mass"] * fx
                ay_ff[j] -= view[i]["mass"] * fy
            elif not ci and cj:
                ax_fc[i] += view[j]["mass"] * fx
                ay_fc[i] += view[j]["mass"] * fy
            elif ci and not cj:
                ax_fc[j] -= view[i]["mass"] * fx
                ay_fc[j] -= view[i]["mass"] * fy
    if monopoles:
        for m in monopoles:
            for i in range(n):
                if coarse[i] or (body_collapsed is not None and body_collapsed[i] is not None):
                    continue
                dx = m["com_x"] - view[i]["x"]
                dy = m["com_y"] - view[i]["y"]
                s2 = dx * dx + dy * dy + EPS2
                inv3 = 1.0 / (s2 * math.sqrt(s2))
                fx = G * inv3 * dx
                fy = G * inv3 * dy
                ax_fc[i] += m["mass"] * fx
                ay_fc[i] += m["mass"] * fy
    return ax_ff, ay_ff, ax_fc, ay_fc


def expected_zoom_policy(seed: int, offset: int, ticks: int, cli_events=None):
    """Recompute the spec section 18 zoom-policy event sequence.

    cli_events: scheduled (tick, region, level) triples applied to the
    level-state machine in stream order before the policy evaluates at
    each boundary (levels: 0 fine, 1 coarse, 2 collapsed; demote on a
    collapsed region is a no-op per spec 19).
    """
    rng = SplitMix64(seed ^ offset)
    points = []
    for _ in range(2):
        u0 = rng.next()
        u1 = rng.next()
        points.append((16.0 + u0 * TWO_POW_NEG64 * 96.0, 16.0 + u1 * TWO_POW_NEG64 * 96.0))

    def focus(t):
        k = (t - 1) // 64
        while len(points) < k + 2:
            u0 = rng.next()
            u1 = rng.next()
            points.append((16.0 + u0 * TWO_POW_NEG64 * 96.0, 16.0 + u1 * TWO_POW_NEG64 * 96.0))
        p0, p1 = points[k], points[k + 1]
        f = (t - (1 + 64 * k)) / 64.0
        return (p0[0] + (p1[0] - p0[0]) * f, p0[1] + (p1[1] - p0[1]) * f)

    cli = {}
    for ev in cli_events or []:
        t, region, lv = ev
        cli.setdefault(t, []).append((region, lv))
    modes = [0, 0, 0, 0]
    events = []
    pending_cli = sorted(cli.items())
    for t in range(17, ticks + 1, 16):
        while pending_cli and pending_cli[0][0] <= t:
            for region, lv in pending_cli.pop(0)[1]:
                if lv == 2:
                    modes[region] = 2
                elif lv == 0:
                    if modes[region] == 0:
                        modes[region] = 1
                else:
                    modes[region] = 0
        fx, fy = focus(t)
        for region in range(4):
            x0 = (region % 2) * 64.0
            y0 = (region // 2) * 64.0
            cx = min(max(fx, x0), x0 + 64.0)
            cy = min(max(fy, y0), y0 + 64.0)
            d = math.sqrt((fx - cx) * (fx - cx) + (fy - cy) * (fy - cy))
            if modes[region] == 0 and d > 48.0:
                modes[region] = 1
                events.append((t, region, 0))
            elif modes[region] != 0 and d < 24.0:
                modes[region] = 0
                events.append((t, region, 1))
    return events


def check_zoom_policy(records, seed: int, offset: int, *, cli_events=None) -> DiagnosticResult:
    """Verify the stream's RegionLevel sequence matches the zoom policy.

    cli_events: optional iterable of (tick, region, level) events scheduled
    via --demote-at/--promote-at; they are interleaved with policy events
    in stream order and excluded from the policy expectation.
    """
    stream_events = []
    pending = []
    last_tick = 0
    for record in records:
        if record[0] == "level":
            pending.append((record[1], record[2], record[3]))
        elif record[0] == "tick":
            _, tick = record
            for rx, ry, lv in pending:
                stream_events.append((tick, ry * 2 + rx, lv))
            pending.clear()
            last_tick = tick
    policy = expected_zoom_policy(seed, offset, last_tick, cli_events=cli_events)
    policy_set = set(policy)
    cli_set = set(cli_events or [])
    ok = True
    detail = {"stream_events": len(stream_events), "policy_events": len(policy)}
    for ev in stream_events:
        if ev in policy_set or ev in cli_set:
            continue
        ok = False
        detail["unexpected"] = ev
        break
    for ev in policy:
        if ev not in stream_events:
            ok = False
            detail["missing"] = ev
            break
    return DiagnosticResult(
        name="ontos_zoom_policy",
        passed=ok,
        threshold=0.0,
        value=0.0 if ok else 1.0,
        detail=detail,
    )


def rebound_positions(seed: int, body_count: int, ticks: int):
    """REBOUND anchor: same ICs, same softening/dt, independent integrator."""
    import rebound as rb

    ics = initial_conditions(seed, body_count)
    sim = rb.Simulation()
    sim.G = 1.0
    sim.softening = 1.0
    sim.dt = DT
    sim.integrator = "LEAPFROG"
    for b in ics:
        sim.add(m=b["mass"], x=b["x"], y=b["y"], z=0.0, vx=b["vx"], vy=b["vy"], vz=0.0)
    sim.integrate(ticks * DT)
    return [(p.x, p.y) for p in sim.particles]


def check_rebound_anchor(records, seed: int, body_count: int, *, ticks: int = None, tol: float = 1e-4) -> DiagnosticResult:
    """Compare the stream's final tick positions against a REBOUND run."""
    last_tick = 0
    positions = {}
    for record in records:
        if record[0] == "tick":
            last_tick = record[1]
        elif record[0] == "body":
            _, tick, bid, region, level, x, y, vx, vy, mass = record
            positions[bid] = (x, y)
    if not positions:
        raise ValueError("stream carries no BodyState records")
    if len(positions) != body_count:
        raise ValueError(f"stream has {len(positions)} bodies, expected {body_count}")
    ref = rebound_positions(seed, body_count, ticks if ticks is not None else last_tick)
    max_dev = 0.0
    scale = 0.0
    for bid, (rx, ry) in enumerate(ref):
        sx, sy = positions[bid]
        max_dev = max(max_dev, abs(sx - rx), abs(sy - ry))
        scale = max(scale, abs(rx), abs(ry))
    rel = max_dev / (scale if scale > 1e-30 else 1e-30)
    return DiagnosticResult(
        name="ontos_rebound_anchor",
        passed=rel <= tol,
        threshold=float(tol),
        value=float(rel),
        detail={"ticks": last_tick, "max_abs_deviation": max_dev, "relative": rel},
    )


def parse_stream_v2(path):
    data = Path(path).read_bytes()
    if len(data) < 20 or data[:4] != MAGIC:
        raise ValueError("not an ontos stream: bad magic")
    version = struct.unpack_from("<I", data, 4)[0]
    if version != 2:
        raise ValueError(f"not a gravity stream (version {version})")
    world_w, world_h, body_count = struct.unpack_from("<III", data, 8)
    records = []
    offset = 20
    while offset < len(data):
        tag = data[offset]
        offset += 1
        if tag == 1:
            (tick,) = struct.unpack_from("<Q", data, offset)
            offset += 8
            records.append(("tick", tick))
        elif tag == 2:
            (population,) = struct.unpack_from("<Q", data, offset)
            offset += 8
            records.append(("snapshot", population))
        elif tag == 3:
            tick, x, y = struct.unpack_from("<QII", data, offset)
            offset += 16
            records.append(("flip", tick, x, y))
        elif tag == 4:
            region_x, region_y, level = struct.unpack_from("<IIB", data, offset)
            if level > 2:
                raise ValueError(f"invalid region level {level} at offset {offset - 1}")
            offset += 9
            records.append(("level", region_x, region_y, level))
        elif tag == 5:
            vals = struct.unpack_from("<QIIBQQ", data, offset)
            offset += 33
            records.append(("state", *vals))
        elif tag == 6:
            vals = struct.unpack_from("<QIBBddddd", data, offset)
            offset += 54
            records.append(("body", *vals))
        elif tag == 7:
            vals = struct.unpack_from("<QQQdddd", data, offset)
            offset += 56
            records.append(("totals", *vals))
        elif tag == 8:
            vals = struct.unpack_from("<QIIQdddddd", data, offset)
            offset += 72
            records.append(("collapsed", *vals))
        else:
            raise ValueError(f"unknown record tag {tag} at offset {offset - 1}")
    return (world_w, world_h, body_count), records


def verify_stream_gravity(path, seed: int) -> dict:
    (world_w, world_h, body_count), records = parse_stream_v2(path)
    if world_w != 128 or world_h != 128:
        raise ValueError(f"unsupported world size {world_w}x{world_h}")
    world = GravityWorld(seed, body_count)
    reference = GravityWorld(seed, body_count)

    mismatches = []
    compared = 0
    last_tick = 0
    pending = []
    pending_collapsed = []
    max_pos_dev = 0.0
    post_exp_dev = 0.0
    collapse_events = 0
    collapse_energy_deltas = []

    for record in records:
        kind = record[0]
        if kind == "level":
            _, rx, ry, level = record
            pending.append((ry * 2 + rx, level))
        elif kind == "collapsed":
            pending_collapsed.append(record)
        elif kind == "tick":
            _, tick = record
            for region, level in pending:
                world.schedule(world.tick + 1, region, level)
            pending.clear()
            world.step()
            reference.step()
            last_tick = tick
            if tick != world.tick:
                mismatches.append({"tick": tick, "field": "tick", "expected": tick, "actual": world.tick})
            for i in range(len(world.bodies)):
                if world.body_collapsed[i] is not None:
                    continue
                b = world._state_at(i, world.tick)
                r = reference.bodies[i]
                dev = max(abs(b["x"] - r["x"]), abs(b["y"] - r["y"]))
                if world.expand_count > 0 and dev > post_exp_dev:
                    post_exp_dev = dev
                if i not in world.reconstructed and dev > max_pos_dev:
                    max_pos_dev = dev
            for cres in pending_collapsed:
                _, tick_c, rx, ry, count, mass, com_x, com_y, px, py, energy = cres
                compared += 1
                collapse_events += 1
                region = ry * 2 + rx
                local = next((c for c in world.last_collapses if c["region"] == region), None)
                if local is None:
                    mismatches.append(
                        {
                            "tick": tick_c,
                            "field": "collapse_record",
                            "expected": "no local collapse",
                            "actual": None,
                        }
                    )
                    continue
                world.last_collapses.remove(local)
                if count != local["count"]:
                    mismatches.append(
                        {"tick": tick_c, "field": "collapse_count", "expected": count, "actual": local["count"]}
                    )
                for name, got, want in (
                    ("collapse_mass", mass, local["mass"]),
                    ("collapse_com_x", com_x, local["com_x"]),
                    ("collapse_com_y", com_y, local["com_y"]),
                    ("collapse_px", px, local["px"]),
                    ("collapse_py", py, local["py"]),
                    ("collapse_energy", energy, local["energy"]),
                ):
                    if struct.pack("<d", got) != struct.pack("<d", want):
                        mismatches.append({"tick": tick_c, "field": name, "expected": got, "actual": want})
                collapse_energy_deltas.append((tick_c, region, energy, local["syn_energy"]))
            pending_collapsed.clear()
            for local in world.last_collapses:
                mismatches.append(
                    {
                        "tick": tick,
                        "field": "collapse_record",
                        "expected": None,
                        "actual": f"missing RegionCollapsed for region {local['region']}",
                    }
                )
            world.last_collapses.clear()
        elif kind == "snapshot":
            compared += 1
        elif kind == "totals":
            _, tick, fine, coarse_n, mass, px, py, energy = record
            compared += 1
            w_fine, w_coarse, w_mass, w_px, w_py, w_energy = world.totals()
            if fine != w_fine:
                mismatches.append({"tick": tick, "field": "fine_count", "expected": fine, "actual": w_fine})
            if coarse_n != w_coarse:
                mismatches.append({"tick": tick, "field": "coarse_count", "expected": coarse_n, "actual": w_coarse})
            for name, got, want in (
                ("mass", mass, w_mass),
                ("px", px, w_px),
                ("py", py, w_py),
                ("energy", energy, w_energy),
            ):
                if struct.pack("<d", got) != struct.pack("<d", want):
                    mismatches.append({"tick": tick, "field": name, "expected": got, "actual": want})
        elif kind == "state":
            _, tick, rx, ry, level, population, rhash = record
            compared += 1
            w_level, w_pop, w_hash = world.region_hash(ry * 2 + rx)
            if (level, population) != (w_level, w_pop) or rhash != w_hash:
                mismatches.append(
                    {
                        "tick": tick,
                        "field": "region_state",
                        "expected": (level, population, rhash),
                        "actual": (w_level, w_pop, w_hash),
                    }
                )
        elif kind == "body":
            _, tick, bid, region, level, x, y, vx, vy, mass = record
            compared += 1
            b, w_region, w_level = world.emitted_state(bid)
            ok = (
                region == w_region
                and level == w_level
                and struct.pack("<ddddd", x, y, vx, vy, mass)
                == struct.pack("<ddddd", b["x"], b["y"], b["vx"], b["vy"], b["mass"])
            )
            if not ok:
                mismatches.append(
                    {
                        "tick": tick,
                        "field": f"body_{bid}",
                        "expected": (region, level, x, y, vx, vy),
                        "actual": (w_region, w_level, b["x"], b["y"], b["vx"], b["vy"]),
                    }
                )

    tracked = [
        i
        for i in range(len(world.bodies))
        if world.body_collapsed[i] is None and i not in world.reconstructed
    ]
    if len(tracked) == len(world.bodies):
        _, _, ref_mass, ref_px, ref_py, ref_e0 = reference.totals()
        _, _, _, end_px, end_py, end_e = world.totals()
    else:
        wsub = [world._state_at(i, world.tick) for i in tracked]
        rsub = [reference.bodies[i] for i in tracked]
        end_px = 0.0
        end_py = 0.0
        for b in wsub:
            end_px += b["mass"] * b["vx"]
            end_py += b["mass"] * b["vy"]
        ref_px = 0.0
        ref_py = 0.0
        for b in rsub:
            ref_px += b["mass"] * b["vx"]
            ref_py += b["mass"] * b["vy"]
        end_e = subset_energy(wsub)
        ref_e0 = subset_energy(rsub)
    ref_scale = max(abs(ref_px), abs(ref_py), 1e-30)
    return {
        "ticks_verified": last_tick,
        "records_compared": compared,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches[:20],
        "max_position_deviation": max_pos_dev,
        "momentum_drift": max(abs(end_px - ref_px), abs(end_py - ref_py)) / ref_scale,
        "energy_drift": abs(end_e - ref_e0) / abs(ref_e0),
        "collapse_events": collapse_events,
        "expand_events": world.expand_count,
        "collapse_energy_deltas": collapse_energy_deltas,
        "post_expansion_deviation": post_exp_dev,
        "final_world_hash": world.world_hash(),
    }


def check_reference_match_gravity(summary: dict, *, threshold: float = 0.0) -> DiagnosticResult:
    count = summary["mismatch_count"]
    return DiagnosticResult(
        name="ontos_reference_match",
        passed=count <= threshold,
        threshold=float(threshold),
        value=float(count),
        detail={
            "ticks_verified": summary["ticks_verified"],
            "records_compared": summary["records_compared"],
            "first_mismatches": summary["mismatches"],
        },
    )


def check_bounded_drift(summary: dict, *, pos_tol: float = 5e-2, mom_tol: float = 5e-2, energy_tol: float = 1e-3) -> DiagnosticResult:
    pos = summary["max_position_deviation"]
    mom = summary["momentum_drift"]
    energy = summary["energy_drift"]
    return DiagnosticResult(
        name="ontos_window_drift",
        passed=pos <= pos_tol and mom <= mom_tol and energy <= energy_tol,
        threshold=float(pos_tol),
        value=float(max(pos, mom, energy)),
        detail={
            "max_position_deviation": pos,
            "momentum_drift_relative": mom,
            "energy_drift_relative": energy,
            "tolerances": {"position": pos_tol, "momentum": mom_tol, "energy": energy_tol},
        },
    )


def check_reconstruction_error(summary: dict, *, pos_tol: float = 64.0) -> DiagnosticResult:
    """Spec section 19: post-expansion continuation vs the all-fine reference.

    Reconstruction positions are com + jitter, so the honest bound is
    region-scale. Bodies that were never reconstructed are excluded (their
    deviation is window/monopole drift, owned by check_bounded_drift).
    """
    expanded = summary.get("expand_events", 0) > 0
    dev = summary.get("post_expansion_deviation", 0.0)
    return DiagnosticResult(
        name="ontos_reconstruction_error",
        passed=(not expanded) or dev <= pos_tol,
        threshold=float(pos_tol),
        value=float(dev),
        detail={
            "post_expansion_deviation": dev,
            "expansions": summary.get("expand_events", 0),
            "note": None if expanded else "no expansion in stream; reconstruction error unmeasured",
        },
    )


def check_collapse_energy(summary: dict, *, tol: float = 8.0) -> DiagnosticResult:
    """Spec section 19: synthesized-set energy vs the collapse record's energy."""
    worst = 0.0
    deltas = summary.get("collapse_energy_deltas", [])
    for _, _, rec_e, syn_e in deltas:
        rel = abs(syn_e - rec_e) / max(abs(rec_e), 1.0)
        worst = max(worst, rel)
    return DiagnosticResult(
        name="ontos_collapse_energy",
        passed=worst <= tol,
        threshold=float(tol),
        value=float(worst),
        detail={"collapse_events": len(deltas), "worst_relative_delta": worst},
    )


def _main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m simval.ontos",
        description="Verify an ontos record stream (life or gravity) against this independent reference",
    )
    parser.add_argument("stream", help="path to a .stream file")
    parser.add_argument("seed", type=int, help="world seed the stream was produced with")
    args = parser.parse_args(argv)
    try:
        data = Path(args.stream).read_bytes()
        if len(data) >= 8 and data[4:8] == struct.pack("<I", 2):
            summary = verify_stream_gravity(args.stream, args.seed)
            ok = summary["mismatch_count"] == 0
            print(
                f"ontos gravity stream: {'OK' if ok else 'MISMATCH'} | ticks={summary['ticks_verified']} "
                f"records={summary['records_compared']} mismatches={summary['mismatch_count']} "
                f"max_pos_dev={summary['max_position_deviation']:.3e} "
                f"mom_drift={summary['momentum_drift']:.3e} energy_drift={summary['energy_drift']:.3e} "
                f"final_world_hash={summary['final_world_hash']:016x}"
            )
            for m in summary["mismatches"]:
                print(f"  MISMATCH: {m}")
            return 0 if ok else 1
        from simval.ontos import verify_stream

        summary = verify_stream(args.stream, args.seed)
        ok = summary["mismatch_count"] == 0 and summary["tick_monotonic"]
        print(
            f"ontos stream: {'OK' if ok else 'MISMATCH'} | ticks={summary['ticks_verified']} "
            f"records={summary['records_compared']} mismatches={summary['mismatch_count']} "
            f"final_population={summary['final_population']} "
            f"final_world_hash={summary['final_world_hash']:016x}"
        )
        for m in summary["mismatches"]:
            print(f"  MISMATCH: {m}")
        return 0 if ok else 1
    except (FileNotFoundError, ValueError) as e:
        print(f"simval.ontos: error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(_main())
