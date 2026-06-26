import pytest

from simval.units import DIMENSIONLESS, Dimension, Quantity, same_dimension


def test_known_dimensions():
    assert Quantity(2, "fs").dimension == Dimension(time=1)
    assert Quantity(300, "K").dimension == Dimension(temperature=1)
    assert Quantity(0.002, "ps").dimension == Quantity(2, "fs").dimension
    assert Quantity(1, "nm").dimension != Quantity(1, "K").dimension


def test_energy_dimension():
    assert Quantity(1, "kJ/mol").dimension == Dimension(mass=1, length=2, time=-2, amount=-1)
    assert Quantity(1, "kJ/mol").dimension == Quantity(1, "kcal/mol").dimension


def test_same_dimension_helper():
    assert same_dimension(Quantity(1, "nm"), Quantity(2, "A"))
    assert not same_dimension(Quantity(1, "nm"), Quantity(1, "ps"))


def test_dimension_composition():
    length = Dimension(length=1)
    time = Dimension(time=1)
    velocity = length / time
    assert velocity == Dimension(length=1, time=-1)
    assert (velocity * time) == length
    assert DIMENSIONLESS.is_dimensionless()


def test_base_conversion():
    assert abs(Quantity(1, "nm").in_base() - 1e-9) < 1e-30
    assert abs(Quantity(2, "ps").in_base() - 2e-12) < 1e-30


def test_unknown_unit_raises():
    with pytest.raises(KeyError):
        Quantity(1, "smoot").dimension
