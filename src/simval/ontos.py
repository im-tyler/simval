"""Ontos adapter: independent Phase-0 reference implementation and stream verifier.

Implements the Ontos stream format and simulation rules strictly from
ontos docs/STREAM_SPEC.md (the normative contract) and verifies recorded
ontos streams against this reimplementation. Pure stdlib, no numpy.

The reference deliberately shares no code with the Rust simulator: any
divergence between the two is a finding, not a nuisance.
"""
from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field
from pathlib import Path

from simval.context import EngineAdapter, RunContext, register_engine
from simval.result import DiagnosticResult

REGION_FINE = 64
REGIONS_PER_AXIS = 2
COARSE_FACTOR = 2
WORLD = REGIONS_PER_AXIS * REGION_FINE
FNV_OFFSET_BASIS = 0xCBF29CE484222325
FNV_PRIME = 0x100000001B3
MAGIC = b"ONTO"


def fnv1a64(data: bytes) -> int:
    h = FNV_OFFSET_BASIS
    for byte in data:
        h = ((h ^ byte) * FNV_PRIME) & 0xFFFFFFFFFFFFFFFF
    return h


@dataclass
class Region:
    level: str  # "fine" | "coarse"
    cells: bytearray

    @classmethod
    def fine(cls) -> "Region":
        return cls("fine", bytearray(REGION_FINE * REGION_FINE))

    @classmethod
    def coarse(cls) -> "Region":
        n = REGION_FINE // COARSE_FACTOR
        return cls("coarse", bytearray(n * n))

    def axis(self) -> int:
        return REGION_FINE if self.level == "fine" else REGION_FINE // COARSE_FACTOR

    def population(self) -> int:
        return sum(self.cells)

    def hash(self) -> int:
        level_byte = 0 if self.level == "coarse" else 1
        return fnv1a64(bytes([level_byte]) + bytes(self.cells))


@dataclass
class ReferenceWorld:
    seed: int
    tick: int = 0
    regions: list = field(default_factory=lambda: [Region.fine() for _ in range(4)])

    def region_index(self, rx: int, ry: int) -> int:
        return ry * REGIONS_PER_AXIS + rx

    def set_fine(self, fx: int, fy: int, alive: bool) -> None:
        rx, ry = fx // REGION_FINE, fy // REGION_FINE
        region = self.regions[self.region_index(rx, ry)]
        if region.level == "fine":
            idx = (fy % REGION_FINE) * REGION_FINE + (fx % REGION_FINE)
        else:
            n = region.axis()
            idx = ((fy % REGION_FINE) // COARSE_FACTOR) * n + ((fx % REGION_FINE) // COARSE_FACTOR)
        region.cells[idx] = 1 if alive else 0

    def seed_r_pentomino(self) -> None:
        c = WORLD // 2
        for dx, dy in ((0, 0), (1, 0), (0, 1), (-1, 1), (0, 2)):
            self.set_fine((c + dx) % WORLD, (c + dy) % WORLD, True)

    def read(self, fx: int, fy: int) -> int:
        fx, fy = fx % WORLD, fy % WORLD
        rx, ry = fx // REGION_FINE, fy // REGION_FINE
        region = self.regions[self.region_index(rx, ry)]
        if region.level == "fine":
            return region.cells[(fy % REGION_FINE) * REGION_FINE + (fx % REGION_FINE)]
        n = region.axis()
        cx, cy = (fx % REGION_FINE) // COARSE_FACTOR, (fy % REGION_FINE) // COARSE_FACTOR
        return region.cells[cy * n + cx]

    def read_block(self, cx: int, cy: int) -> int:
        coarse_world = WORLD // COARSE_FACTOR
        cx, cy = cx % coarse_world, cy % coarse_world
        rx, ry = (cx * COARSE_FACTOR) // REGION_FINE, (cy * COARSE_FACTOR) // REGION_FINE
        region = self.regions[self.region_index(rx, ry)]
        if region.level == "coarse":
            n = region.axis()
            return region.cells[(cy % n) * n + (cx % n)]
        base_fx, base_fy = cx * COARSE_FACTOR, cy * COARSE_FACTOR
        value = 0
        for dy in range(COARSE_FACTOR):
            for dx in range(COARSE_FACTOR):
                value |= self.read(base_fx + dx, base_fy + dy)
        return value

    def expansion_pick(self, gx: int, gy: int) -> int:
        payload = struct.pack("<QII", self.seed, gx, gy)
        return fnv1a64(payload) % 4

    def set_level(self, rx: int, ry: int, level: str) -> None:
        region = self.regions[self.region_index(rx, ry)]
        if region.level == level:
            return
        if level == "fine":
            fine = Region.fine()
            n = region.axis()
            offsets = ((0, 0), (1, 0), (0, 1), (1, 1))
            for cy in range(n):
                for cx in range(n):
                    if region.cells[cy * n + cx] == 0:
                        continue
                    gx = rx * REGION_FINE + cx * COARSE_FACTOR
                    gy = ry * REGION_FINE + cy * COARSE_FACTOR
                    dx, dy = offsets[self.expansion_pick(gx, gy)]
                    fine.cells[(cy * COARSE_FACTOR + dy) * REGION_FINE + (cx * COARSE_FACTOR + dx)] = 1
            self.regions[self.region_index(rx, ry)] = fine
        else:
            coarse = Region.coarse()
            n = coarse.axis()
            for cy in range(n):
                for cx in range(n):
                    alive = 0
                    for dy in range(COARSE_FACTOR):
                        for dx in range(COARSE_FACTOR):
                            alive |= region.cells[
                                (cy * COARSE_FACTOR + dy) * REGION_FINE + (cx * COARSE_FACTOR + dx)
                            ]
                    coarse.cells[cy * n + cx] = alive
            self.regions[self.region_index(rx, ry)] = coarse

    def region_key(self, fx: int, fy: int) -> tuple:
        rx, ry = fx // REGION_FINE, fy // REGION_FINE
        if self.regions[self.region_index(rx, ry)].level == "fine":
            return (0, fx, fy)
        return (1, fx // COARSE_FACTOR, fy // COARSE_FACTOR)

    def fine_neighbors(self, gx: int, gy: int) -> int:
        count = 0
        seen = set()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nx, ny = (gx + dx) % WORLD, (gy + dy) % WORLD
                if self.read(nx, ny) == 0:
                    continue
                key = self.region_key(nx, ny)
                if key in seen:
                    continue
                seen.add(key)
                count += 1
        return count

    def coarse_neighbors(self, gx: int, gy: int) -> int:
        coarse_world = WORLD // COARSE_FACTOR
        count = 0
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                count += self.read_block((gx + dx) % coarse_world, (gy + dy) % coarse_world)
        return count

    def step(self) -> None:
        next_regions = []
        for index, region in enumerate(self.regions):
            rx, ry = index % REGIONS_PER_AXIS, index // REGIONS_PER_AXIS
            nxt = Region.fine() if region.level == "fine" else Region.coarse()
            if region.level == "fine":
                for fy in range(REGION_FINE):
                    for fx in range(REGION_FINE):
                        gx, gy = rx * REGION_FINE + fx, ry * REGION_FINE + fy
                        alive = region.cells[fy * REGION_FINE + fx] == 1
                        n = self.fine_neighbors(gx, gy)
                        nxt.cells[fy * REGION_FINE + fx] = 1 if (alive and n in (2, 3)) or (not alive and n == 3) else 0
            else:
                n_axis = region.axis()
                for cy in range(n_axis):
                    for cx in range(n_axis):
                        gx = rx * (REGION_FINE // COARSE_FACTOR) + cx
                        gy = ry * (REGION_FINE // COARSE_FACTOR) + cy
                        alive = region.cells[cy * n_axis + cx] == 1
                        n = self.coarse_neighbors(gx, gy)
                        nxt.cells[cy * n_axis + cx] = 1 if (alive and n in (2, 3)) or (not alive and n == 3) else 0
            next_regions.append(nxt)
        self.regions = next_regions
        self.tick += 1

    def population(self) -> int:
        return sum(region.population() for region in self.regions)

    def region_hash(self, rx: int, ry: int) -> int:
        return self.regions[self.region_index(rx, ry)].hash()

    def world_hash(self) -> int:
        payload = struct.pack("<Q", self.tick)
        for ry in range(REGIONS_PER_AXIS):
            for rx in range(REGIONS_PER_AXIS):
                payload += struct.pack("<Q", self.region_hash(rx, ry))
        return fnv1a64(payload)


@dataclass
class StreamHeader:
    world_w: int
    world_h: int
    version: int


def parse_stream(path) -> tuple:
    data = Path(path).read_bytes()
    if len(data) < 16 or data[:4] != MAGIC:
        raise ValueError("not an ontos stream: bad magic")
    version, world_w, world_h = struct.unpack_from("<III", data, 4)
    if version != 1:
        raise ValueError(f"unsupported ontos stream version {version}")
    records = []
    offset = 16
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
            offset += 9
            records.append(("level", region_x, region_y, level))
        elif tag == 5:
            tick, region_x, region_y, level, population, rhash = struct.unpack_from("<QIIBQQ", data, offset)
            offset += 33
            records.append(("state", tick, region_x, region_y, level, population, rhash))
        else:
            raise ValueError(f"unknown record tag {tag} at offset {offset - 1}")
    return StreamHeader(world_w, world_h, version), records


def verify_stream(path, seed: int) -> dict:
    """Replay a stream against the independent reference implementation."""
    header, records = parse_stream(path)
    if header.world_w != WORLD or header.world_h != WORLD:
        raise ValueError(f"unsupported world size {header.world_w}x{header.world_h}")
    world = ReferenceWorld(seed=seed)
    world.seed_r_pentomino()

    mismatches = []
    records_compared = 0
    last_tick = 0
    tick_monotonic = True

    for record in records:
        if record[0] == "level":
            _, rx, ry, level = record
            world.set_level(rx, ry, "fine" if level == 1 else "coarse")
        elif record[0] == "tick":
            _, tick = record
            if tick != last_tick + 1:
                tick_monotonic = False
            last_tick = tick
            world.step()
            if tick != world.tick:
                mismatches.append({"tick": tick, "region": None, "field": "tick",
                                   "expected": tick, "actual": world.tick})
        elif record[0] == "snapshot":
            _, population = record
            records_compared += 1
            if population != world.population():
                mismatches.append({"tick": world.tick, "region": None, "field": "population",
                                   "expected": population, "actual": world.population()})
        elif record[0] == "state":
            _, tick, rx, ry, level, population, rhash = record
            records_compared += 1
            region = world.regions[world.region_index(rx, ry)]
            actual_level = 1 if region.level == "fine" else 0
            if level != actual_level:
                mismatches.append({"tick": tick, "region": (rx, ry), "field": "level",
                                   "expected": level, "actual": actual_level})
            if population != region.population():
                mismatches.append({"tick": tick, "region": (rx, ry), "field": "population",
                                   "expected": population, "actual": region.population()})
            if rhash != region.hash():
                mismatches.append({"tick": tick, "region": (rx, ry), "field": "hash",
                                   "expected": rhash, "actual": region.hash()})

    return {
        "ticks_verified": last_tick,
        "records_compared": records_compared,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches[:20],
        "tick_monotonic": tick_monotonic,
        "final_population": world.population(),
        "final_world_hash": world.world_hash(),
    }


def check_reference_match(summary: dict, *, threshold: float = 0.0) -> DiagnosticResult:
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


def check_tick_monotonicity(summary: dict) -> DiagnosticResult:
    ok = summary["tick_monotonic"]
    return DiagnosticResult(
        name="ontos_tick_monotonicity",
        passed=ok,
        threshold=1.0,
        value=1.0 if ok else 0.0,
        detail={"ticks_verified": summary["ticks_verified"]},
    )


class OntosEngine(EngineAdapter):
    name = "ontos"

    def detect(self, run: Path) -> bool:
        return (run / "ontos.stream").exists() and (run / "ontos.json").exists()

    def load_context(self, run: Path, selection: str) -> RunContext:
        meta = json.loads((run / "ontos.json").read_text())
        if "seed" not in meta:
            raise ValueError("ontos.json must contain an integer 'seed'")
        summary = verify_stream(run / "ontos.stream", int(meta["seed"]))
        ctx = RunContext(run_dir=run, engine=self.name, selection=selection)
        ctx.extra = {"ontos_summary": summary}
        ctx.run_params = {
            "engine": self.name,
            "seed": int(meta["seed"]),
            "domain": "discrete-multiscale",
            "ticks": summary["ticks_verified"],
        }
        return ctx


register_engine(OntosEngine())


def _main(argv=None) -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        prog="python -m simval.ontos",
        description="Verify an ontos record stream against this independent reference",
    )
    parser.add_argument("stream", help="path to a .stream file")
    parser.add_argument("seed", type=int, help="world seed the stream was produced with")
    args = parser.parse_args(argv)
    try:
        summary = verify_stream(args.stream, args.seed)
    except (FileNotFoundError, ValueError) as e:
        print(f"simval.ontos: error: {e}", file=sys.stderr)
        return 2
    ok = summary["mismatch_count"] == 0 and summary["tick_monotonic"]
    print(
        f"ontos stream: {'OK' if ok else 'MISMATCH'} | ticks={summary['ticks_verified']} "
        f"records={summary['records_compared']} mismatches={summary['mismatch_count']} "
        f"final_population={summary['final_population']} "
        f"final_world_hash={summary['final_world_hash']:016x}"
    )
    for m in summary["mismatches"]:
        print(f"  MISMATCH: tick={m['tick']} region={m['region']} field={m['field']} "
              f"stream={m['expected']} computed={m['actual']}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(_main())
