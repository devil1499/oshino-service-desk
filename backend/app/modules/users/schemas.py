from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

Username = Annotated[
    str, StringConstraints(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")
]
DisplayName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Password = Annotated[str, StringConstraints(min_length=8, max_length=128)]


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    username: Username
    password: Password


class UserCreate(LoginRequest):
    display_name: DisplayName


class UserState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_active: bool


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    display_name: str
    role: Literal["admin", "staff", "customer"]
    customer_tier: int
    staff_level: int
    is_active: bool


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserResponse
