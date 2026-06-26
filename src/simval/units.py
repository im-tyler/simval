from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Dimension:
    length: int = 0
    mass: int = 0
    time: int = 0
    temperature: int = 0
    amount: int = 0
    current: int = 0

    def _tuple(self):
        return (self.length, self.mass, self.time, self.temperature, self.amount, self.current)

    def __mul__(self, other: "Dimension") -> "Dimension":
        a, b = self._tuple(), other._tuple()
        return Dimension(*(x + y for x, y in zip(a, b)))

    def __truediv__(self, other: "Dimension") -> "Dimension":
        a, b = self._tuple(), other._tuple()
        return Dimension(*(x - y for x, y in zip(a, b)))

    def __pow__(self, n: int) -> "Dimension":
        return Dimension(*(x * n for x in self._tuple()))

    def is_dimensionless(self) -> bool:
        return all(v == 0 for v in self._tuple())


DIMENSIONLESS = Dimension()


UNITS: dict[str, tuple[float, Dimension]] = {
    "":         (1.0, DIMENSIONLESS),
    "nm":       (1e-9, Dimension(length=1)),
    "A":        (1e-10, Dimension(length=1)),
    "pm":       (1e-12, Dimension(length=1)),
    "fs":       (1e-15, Dimension(time=1)),
    "ps":       (1e-12, Dimension(time=1)),
    "ns":       (1e-9, Dimension(time=1)),
    "K":        (1.0, Dimension(temperature=1)),
    "amu":      (1.66053906660e-27, Dimension(mass=1)),
    "kJ/mol":   (1000.0 / 6.02214076e23, Dimension(mass=1, length=2, time=-2, amount=-1)),
    "kcal/mol": (4184.0 / 6.02214076e23, Dimension(mass=1, length=2, time=-2, amount=-1)),
    "J":        (1.0, Dimension(mass=1, length=2, time=-2)),
    "bar":      (1e5, Dimension(mass=1, length=-1, time=-2)),
    "m/s":      (1.0, Dimension(length=1, time=-1)),
}


@dataclass(frozen=True)
class Quantity:
    value: float
    unit: str

    @property
    def dimension(self) -> Dimension:
        if self.unit not in UNITS:
            raise KeyError(f"unknown unit: {self.unit!r}")
        return UNITS[self.unit][1]

    def in_base(self) -> float:
        factor, _ = UNITS[self.unit]
        return self.value * factor


def same_dimension(a: Quantity, b: Quantity) -> bool:
    return a.dimension == b.dimension
