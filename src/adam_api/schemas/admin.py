from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel


class SettingIn(BaseModel):
    value: Any


class SettingOut(BaseModel):
    key: str
    value: Any = None
    default: Any = None
    effective: Any = None
    source: Literal["db", "default", "env"]
    description: Optional[str] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[str] = None
    managed_by_worker: bool = False


class EnvVarOut(BaseModel):
    name: str
    #: Nul pour un secret : seul `secret` dit s'il est defini (valeur masquee) ou non.
    value: Optional[str] = None
    secret: bool
    #: Le secret est-il renseigne ? Toujours vrai pour une valeur non secrete.
    defined: bool
    group: str
