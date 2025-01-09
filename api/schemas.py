import uuid
from datetime import date
from typing import Optional, List

from ninja import Schema
from pydantic import EmailStr


class VerifyEmailSchema(Schema):
    email: EmailStr


class RequestCodeSchema(Schema):
    email: str


class VerifyCodeSchema(Schema):
    email: str
    code: str


class LogoutSchema(Schema):
    refresh: str


class ProfileSchema(Schema):
    name: str
    surname: str
    phone: Optional[str]
    email: str
    approved: bool
    active: bool
    images: List[str]
    birthdate: Optional[date]
    city: str
    university: str
    field_of_study: str
    interests: List[str]
    description: str
    partner: Optional[int]


class UpdateProfileSchema(Schema):
    name: Optional[str] = None
    surname: Optional[str] = None
    phone: Optional[str] = None
    birthdate: Optional[date] = None
    city: Optional[str] = None
    university: Optional[str] = None
    field_of_study: Optional[str] = None
    interests: Optional[List[str]] = None
    description: Optional[str] = None


class SimpleUserSchema(Schema):
    public_id: uuid.UUID
    name: str
    surname: str
    city: str
    user_type: str
    description: str
    interests: List[str]
    images: List[str]


class UserListSchema(Schema):
    users: List[SimpleUserSchema]


class ImageUploadResponseSchema(Schema):
    message: str


class RequestApprovalSchema(Schema):
    name: str
    surname: str
    phone: str
    email: str
    personal_id: str  # Teudat Zeut
    user_type: str  # 'repatriate' or 'mentor'
