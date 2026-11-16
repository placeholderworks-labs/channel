from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str
    password: str


class OtpVerifyRequest(BaseModel):
    challenge: str
    code: str


class OtpResendRequest(BaseModel):
    challenge: str


class LoginResponse(BaseModel):
    token: str
    expiresAt: int
    user: dict


class SettingsUpdateRequest(BaseModel):
    values: dict[str, str | int | float | bool | None] = Field(
        ..., description="Setting key to new value. Only the keys you send are touched."
    )
    apply: bool = Field(
        default=True,
        description="Re-read the saved settings into the running process straight away. "
        "False saves them for the next restart instead.",
    )


class SettingsResetRequest(BaseModel):
    keys: list[str] = Field(
        ..., description="Settings to put back on their defaults by deleting their stored values."
    )


class SettingsUpdateResponse(BaseModel):
    saved: list[str]
    applied: bool
    restartRequired: list[str]
    message: str


class CreateUserRequest(BaseModel):
    email: str
    name: str = ""
    role: str = "operator"
    sendInvite: bool = True
    password: str | None = Field(
        default=None, description="Leave out to generate a temporary one."
    )


class UpdateUserRequest(BaseModel):
    name: str | None = None
    role: str | None = None
    isActive: bool | None = None


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    newPassword: str


class CreateRoleRequest(BaseModel):
    name: str
    label: str = ""
    description: str = ""
    permissions: list[str] = Field(default_factory=list)


class UpdateRoleRequest(BaseModel):
    label: str | None = None
    description: str | None = None
    permissions: list[str] | None = None


class ChangePasswordRequest(BaseModel):
    currentPassword: str
    newPassword: str


class TestCallRequest(BaseModel):

    channel: str = Field(..., description="acefone")
    delay_secs: float | None = None

    reference_id: str = ""
    customer_name: str = ""
    phone_number: str = ""
    booking_type: str = ""
    origin: str = ""
    destination: str = ""
    travel_date: str = ""
    trip_type: str = ""
    return_date: str = ""
    passengers: int | float | str | None = None
    total_amount_inr: int | float | str | None = None
    status: str = ""

    trip_summary: str = ""
    use_case: str = ""
    intake: str = ""
    record: dict | None = None
    booking_url: str = ""
    discount_amount_inr: int | float | str | None = None
