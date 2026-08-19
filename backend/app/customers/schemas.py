import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

EMAIL_PATTERN = re.compile(
    r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    re.IGNORECASE,
)
PHONE_ALLOWED_PATTERN = re.compile(r"^[+0-9().\-\s]+$")


def normalize_phone_to_e164(value: object) -> object:
    if not isinstance(value, str):
        return value
    candidate = value.strip()
    if not PHONE_ALLOWED_PATTERN.fullmatch(candidate):
        raise ValueError("phone contains unsupported characters.")
    digits = "".join(character for character in candidate if character.isdigit())
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    raise ValueError("phone must be a 10-digit North American number.")


class GuestCustomerInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320)
    phone: str = Field(min_length=7, max_length=30)

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = " ".join(value.strip().split())
            if len(normalized.split()) < 2:
                raise ValueError("name must include first and last name.")
            return normalized
        return value

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        if not EMAIL_PATTERN.fullmatch(value):
            raise ValueError("email must be a valid address.")
        return value

    @field_validator("phone", mode="before")
    @classmethod
    def normalize_phone(cls, value: object) -> object:
        return normalize_phone_to_e164(value)
