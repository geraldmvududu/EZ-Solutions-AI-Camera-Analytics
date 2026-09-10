from typing import Annotated

from pydantic import BaseModel, StringConstraints

# A plain-syntax email type (no reserved-TLD/deliverability checks). Lab and on-prem
# security deployments commonly use internal-only domains such as .local/.lan/.internal
# (e.g. Active Directory's default .local), which pydantic.EmailStr's underlying
# email-validator library rejects as "special-use" — too strict for this platform.
SimpleEmailStr = Annotated[
    str,
    StringConstraints(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", strip_whitespace=True, to_lower=True),
]


class Msg(BaseModel):
    detail: str


class Paginated(BaseModel):
    total: int
    limit: int
    offset: int
