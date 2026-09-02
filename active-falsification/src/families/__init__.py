"""Family registry."""

from typing import Dict, List

from families.base import ProblemFamily, UnsatisfiableConstraints  # noqa: F401
from families.lte_valuation import LteValuationFamily
from families.order_minus_one import OrderMinusOneFamily
from families.recurrence_substitution import RecurrenceSubstitutionFamily

_REGISTRY = {
    OrderMinusOneFamily.name: OrderMinusOneFamily,
    LteValuationFamily.name: LteValuationFamily,
    RecurrenceSubstitutionFamily.name: RecurrenceSubstitutionFamily,
}

ALL_FAMILIES: List[str] = list(_REGISTRY)


def get_family(name: str) -> ProblemFamily:
    if name not in _REGISTRY:
        raise KeyError(f"unknown family {name!r}; known: {ALL_FAMILIES}")
    return _REGISTRY[name]()


def all_families() -> Dict[str, ProblemFamily]:
    return {name: cls() for name, cls in _REGISTRY.items()}
