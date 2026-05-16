"""User model - imported by main."""

from .base import BaseModel


class User(BaseModel):
    pass


class AdminUser(User):
    pass
