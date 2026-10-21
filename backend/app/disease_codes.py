"""Stable disease identifiers shared by parsing and API validation."""
import re
import unicodedata

ALIASES = {"influenza_like_illness": "ili", "acute_gastroenteritis": "age", "covid19": "covid_19"}


def normalize_disease_code(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Provide an explicit disease name or condition_code")
    plain = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    code = re.sub(r"[^a-z0-9]+", "_", plain).strip("_")
    code = ALIASES.get(code, code)
    if not code or len(code) > 80 or not re.fullmatch(r"[a-z][a-z0-9_]*", code):
        raise ValueError("Disease code must start with a letter and contain at most 80 letters, digits or underscores")
    return code
