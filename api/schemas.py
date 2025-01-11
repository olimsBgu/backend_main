import re
import uuid
from datetime import date
from typing import Optional, List

from ninja import Schema
from pydantic import EmailStr, constr, validator


def validate_letters(value, field_name: str):
    if not value.isalpha():
        raise ValueError(f'Field {field_name} must contain only letters.')
    return value.capitalize()


class VerifyEmailSchema(Schema):
    email: EmailStr  # Email validation


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
    name: Optional[constr(min_length=2, max_length=50)] = None
    surname: Optional[constr(min_length=2, max_length=50)] = None
    phone: Optional[str] = None
    birthdate: Optional[date] = None
    city: Optional[constr(min_length=2, max_length=100)] = None
    university: Optional[str] = None
    field_of_study: Optional[str] = None
    interests: Optional[List[str]] = None
    description: Optional[str] = None

    # Additional validators
    @validator('name')  # Name validation
    def validate_name(cls, value):
        return validate_letters(value, 'Name')

    @validator('surname')  # Surname validation
    def validate_surname(cls, value):
        return validate_letters(value, 'Surname')

    @validator('phone')  # Phone number validation
    def validate_phone(cls, value):
        if not re.fullmatch(r'^\+972\d{9}$', value):
            raise ValueError('The phone number must be in the correct form: +972********* (9 digits)')
        return value

    @validator('birthdate')  # Birthdate validation
    def validate_birth_date(cls, value):
        today = date.today()
        if value >= today:
            raise ValueError('The birthdate must be in the past.')
        if (today.year - value.year) > 120:
            raise ValueError('The birthdate is too old.')
        return value

    @validator('city')  # City validation
    def validate_city(cls, value):
        return validate_letters(value, 'City')

    @validator('interests', each_item=True)  # Interests validation
    def validate_interest(cls, value):
        return validate_letters(value, 'Interests')


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


class InterestSchema(Schema):
    id: int
    name: str


class UniversitySchema(Schema):
    id: int
    name: str
