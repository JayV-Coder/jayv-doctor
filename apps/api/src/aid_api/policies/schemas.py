from pydantic import BaseModel, ConfigDict


class Policies(BaseModel):
    # `extra=forbid`: o payload só muda a política, nunca o tenant.
    model_config = ConfigDict(extra="forbid")

    require_mfa: bool
