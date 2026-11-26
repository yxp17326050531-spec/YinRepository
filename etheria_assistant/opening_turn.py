"""Estimate the first 100% crossing from the opening snapshot and Dreamguide inputs."""
from dataclasses import dataclass
from fractions import Fraction
from math import isfinite


# Base and default appearance mappings for this playable character.
FREYA_IDS = frozenset((31251, 31252, 31253))


@dataclass(frozen=True)
class OpeningUnit:
    team: str
    unit: dict
    speed: Fraction | None
    advance: int

    @property
    def arrival(self):
        return (100 - self.advance) / self.speed if self.speed else None


def has_opening_bulwark(unit):
    manual = (unit.get('manual') or {}).get('matrices')
    if manual is not None:
        return any(item['name'] == '戍卫' and (item.get('points') or 0) >= 8 for item in manual)
    return any(item['name'] == '戍卫' and (item.get('threshold') or 0) >= 8
               and item.get('confidence') in ('已对照样本', '用户映射')
               for item in unit.get('matrix_effects_candidates', ()))


def opening_units(teams):
    rows = []
    for team, units in teams.items():
        has_freya = any(unit['hero_id'] in FREYA_IDS for unit in units)
        for unit in units:
            speed = (unit.get('stats') or {}).get('speed')
            speed = (Fraction(str(speed))
                     if isinstance(speed, (int, float)) and not isinstance(speed, bool)
                     and isfinite(speed) and speed >= 0 else None)
            advance = 0
            if has_freya and has_opening_bulwark(unit):
                advance = 8 if unit['hero_id'] in FREYA_IDS else 4
            rows.append(OpeningUnit(team, unit, speed, advance))
    return rows


def first_arrival(rows):
    if not rows or any(row.speed is None for row in rows):
        return None
    return min((row.arrival for row in rows if row.speed), default=None)
