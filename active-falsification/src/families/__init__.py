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


def get_family(name: str, schema_profile: str = "full") -> ProblemFamily:
    if name not in _REGISTRY:
        raise KeyError(f"unknown family {name!r}; known: {ALL_FAMILIES}")
    return _REGISTRY[name](schema_profile)


def all_families(schema_profile: str = "full") -> Dict[str, ProblemFamily]:
    return {name: cls(schema_profile) for name, cls in _REGISTRY.items()}
