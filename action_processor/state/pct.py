from pydantic import BeforeValidator, PlainSerializer
from typing import Annotated, Any


def validate_pct_str(v: Any) -> float:

    if not isinstance(v, str) or not v.strip().endswith('%'):
        raise ValueError(
            f"Value must be string with %, e.g. '0.5%', got '{v}'"
        )

    try:
        return float(v.replace('%', '').strip().replace(',', '.'))
    except ValueError:
        raise ValueError(f"Invalid percent number '{v}'")


def serialize_pct_str(v: float) -> str:
    return f"{v}%"


Pct = Annotated[
    float,
    BeforeValidator(validate_pct_str),
    PlainSerializer(serialize_pct_str, return_type=str)
]