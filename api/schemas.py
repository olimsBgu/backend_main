import uuid
from datetime import date
from typing import Optional, List

from ninja import Schema
from ninja.errors import ValidationError
from pydantic import EmailStr, constr, validator

import re


class VerifyEmailSchema(Schema):
    email: str


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
    name: constr(min_length=2, max_length=50)  # Имя
    surname: constr(min_length=2, max_length=50)  #
    phone: str  # Валидация номера телефона
    birthdate: date
    city: constr(min_length=2, max_length=100)
    university: Optional[str] = None
    field_of_study: Optional[str] = None
    interests: Optional[List[str]] = None
    description: Optional[str] = None

    # Дополнительные валидаторы
    @validator('name')
    def name_no_special_characters(cls, value):
        if not value.isalpha():
            raise ValueError('Имя должно содержать только буквы')
        return value

    @validator('surname')
    def surname_no_special_characters(cls, value):
        if not value.isalpha():
            raise ValueError('Фамилия должна содержать только буквы')
        return value

    @validator('phone')
    def validate_phone(cls, value):
        if not re.fullmatch(r'^0\d{9}$', value):
            raise ValueError('Номер телефона должен быть в формате 0********* (9 цифр)')
        return value

    @validator('birthdate')
    def validate_birth_date(cls, value):
        today = date.today()
        if value >= today:
            raise ValueError('Дата рождения должна быть в прошлом')
        if (today.year - value.year) > 120:
            raise ValueError('Дата рождения слишком старая')
        return value

    @validator('city')
    def validate_city(cls, value):
        if not value.isalpha():
            raise ValueError('Название города должно содержать только буквы')
        return value.capitalize()

    @validator('interests', each_item=True)
    def validate_interest(cls, value):
        if not value.isalpha():
            raise ValueError('Интересы должны содержать только буквы')
        return value.capitalize()



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
