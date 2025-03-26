import re
from datetime import date
from typing import Optional, List
from uuid import UUID

from ninja import ModelSchema, Schema, Field
from pydantic import EmailStr, constr, validator

from api.models import User


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


class UserProfileSchema(ModelSchema):
    """
    For a user's detailed profile, including images,
    plus references to city/university/field_of_study by name or ID.
    """
    public_id: UUID
    images: list[dict[str, str]] = Field(default_factory=list[Field(default_factory=dict)])

    city: Optional[str] = None
    university: Optional[str] = None
    field_of_study: Optional[str] = None
    interests: dict[int, str] = Field(default_factory=dict)
    partner: Optional[UUID] = None
    saved_users: Optional[list[UUID]] = None

    class Config:
        model = User
        model_fields = [
            "public_id", "name", "surname", "phone", "email",
            "approved", "active", "birthdate",
            "city", "university", "field_of_study",
            "description", "partner", "user_type"
        ]

    @staticmethod
    def resolve_images(obj: User) -> list[dict[str, str]]:
        return [{"id": str(img.id), "path": img.file.url} for img in obj.images.all()]

    @staticmethod
    def resolve_city(obj: User) -> Optional[str]:
        return obj.city.name if obj.city else None

    @staticmethod
    def resolve_university(obj: User) -> Optional[str]:
        return obj.university.name if obj.university else None

    @staticmethod
    def resolve_field_of_study(obj: User) -> Optional[str]:
        return obj.field_of_study.name if obj.field_of_study else None

    @staticmethod
    def resolve_interests(obj: User) -> dict[int, str]:
        return {i.id: i.name for i in obj.interests.all()}

    @staticmethod
    def resolve_partner(obj: User) -> Optional[UUID]:
        return obj.partner.public_id if obj.partner else None

    @staticmethod
    def resolve_saved_users(obj: User) -> list[UUID]:
        return [user.public_id for user in obj.saved_users.all()]


class UpdateProfileSchema(Schema):
    name: Optional[constr(min_length=2, max_length=50)] = None
    surname: Optional[constr(min_length=2, max_length=50)] = None
    phone: Optional[str] = None
    birthdate: Optional[date] = None
    city: Optional[int] = None
    university: Optional[int] = None
    field_of_study: Optional[int] = None
    interests: Optional[List[int]] = None
    description: Optional[str] = None
    user_type: Optional[str] = None

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


class SimpleUserSchema(ModelSchema):
    """
    A "simple" schema with fewer fields, e.g., used for user lists / "potential pairs".
    """
    images: list[dict[str, str]] = Field(default_factory=list)

    city: Optional[str] = None
    university: Optional[str] = None
    field_of_study: Optional[str] = None
    interests: dict[int, str] = Field(default_factory=dict)

    class Config:
        model = User
        model_fields = [
            "public_id", "name", "surname", "city", "university", "field_of_study", "user_type",
            "description", "interests"
        ]

    @staticmethod
    def resolve_images(obj: User) -> list[dict[str, str]]:
        return [{"id": img.id, "path": img.file.url} for img in obj.images.all()]

    @staticmethod
    def resolve_city(obj: User) -> Optional[str]:
        return obj.city.name if obj.city else None

    @staticmethod
    def resolve_university(obj: User) -> Optional[str]:
        return obj.university.name if obj.university else None

    @staticmethod
    def resolve_field_of_study(obj: User) -> Optional[str]:
        return obj.field_of_study.name if obj.field_of_study else None

    @staticmethod
    def resolve_interests(obj: User) -> dict[int, str]:
        return {i.id: i.name for i in obj.interests.all()}


class UserListSchema(Schema):
    users: List[SimpleUserSchema]
    current_page: int
    total_pages: int
    has_next: bool


class ImageResponseSchema(Schema):
    message: str
    image_id: int
    image_url: str


class MessageSchema(Schema):
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


class CitySchema(Schema):
    id: int
    name: str


class FieldOfStudySchema(Schema):
    id: int
    name: str


class PublicIdSchema(Schema):
    public_id: UUID


class MatchCreationSchema(Schema):
    message: str


class PaginationQuery(Schema):
    page: Optional[int] = 1


class ChatMessageSchema(Schema):
    sender_id: UUID
    content: str
    created_at: str
    is_viewed: bool


class ChatSchema(Schema):
    ws_key: str
    user_ids: List[UUID]
    last_message: Optional[ChatMessageSchema]
    partner_name: str
    partner_image: Optional[str]
