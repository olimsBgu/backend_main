import json
import random
import string
from typing import List
from uuid import UUID

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.files.base import ContentFile
from django.core.paginator import Paginator
from django.db.models import Q, Case, When, IntegerField, Count
from django.db.models.functions import TruncMonth
from django.shortcuts import get_object_or_404
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from ninja import Router, Query, Form
from ninja import UploadedFile, File
from ninja.errors import HttpError
from ninja.security import HttpBearer
from ninja_jwt.authentication import JWTAuth
from ninja_jwt.schema import TokenRefreshInputSchema, TokenRefreshOutputSchema
from ninja_jwt.tokens import RefreshToken

from chat.models import Chat
from .models import User, Interest, University, City, FieldOfStudy, Image, Pending, Match
from .schemas import UpdateProfileSchema, UserListSchema, ImageResponseSchema, \
    RequestApprovalSchema, MessageSchema, UserProfileSchema, MatchCreationSchema, SimpleUserSchema, PaginationQuery
from .schemas import VerifyEmailSchema, RequestCodeSchema, VerifyCodeSchema, LogoutSchema, InterestSchema, \
    UniversitySchema, CitySchema, FieldOfStudySchema, ChatMessageSchema, ChatSchema
from .utilities.validators import validate_image_file, handle_like, handle_save, \
    handle_dislike


# Security class for token-based authentication
class JWTBearer(HttpBearer):
    def authenticate(self, request, token: str):
        user = JWTAuth().authenticate(request, token)
        if not user:
            raise HttpError(401, "NOT_AUTH")
        return user


def generate_login_code():
    return ''.join(random.choices(string.digits, k=6))


router = Router()


@router.post("/verify-email")
def verify_email(request, payload: VerifyEmailSchema):
    email = payload.email
    # Create or fetch the user
    user, created = User.objects.get_or_create(
        email=email
    )
    if user.active:
        raise HttpError(409, f"EMAIL_VERIFIED")

    # Generate email confirmation token
    token = default_token_generator.make_token(user)
    confirmation_link = f"{request.site_url}/confirm-email/{user.pk}/{token}"

    # Send email
    # send_mail(
    #     'Verify Your Email',
    #     f'Click this link to confirm your email: {confirmation_link}',
    #     'no-reply@example.com',
    #     [email],
    # )

    return {"message": "Email verification sent.", "link": confirmation_link}


@router.get("/check-email", response=dict)
def check_email(request, query: VerifyEmailSchema = Query(...)):
    user = User.objects.filter(email=query.email).first()
    if user:
        return {"email": query.email, "is_confirmed": user.active}
    return {"email": query.email, "is_confirmed": False}


@router.get("/confirm-email/{user_id}/{token}")
def confirm_email(request, user_id: int, token: str):
    user = get_object_or_404(User, pk=user_id)

    if not default_token_generator.check_token(user, token):
        return {"error": "Invalid or expired token."}

    user.active = True
    user.save()

    return {"message": "Email confirmed successfully."}


@router.post("/request-approval")
def request_approval(request, payload: RequestApprovalSchema):
    """
    Endpoint for users to request account approval after confirming their email.
    """
    # Fetch the user by email
    user = User.objects.filter(email=payload.email).first()

    if not user:
        raise HttpError(400, "NOT_EXIST")

    # Ensure the email is confirmed
    if not user.active:
        raise HttpError(400, "NOT_VERIFIED")

    # Check if the user has already registered details
    if user.name or user.surname or user.personal_id or user.phone or user.user_type or user.approved:
        raise HttpError(400, "USER_REGISTERED")

    # Update user details
    user.name = payload.name
    user.surname = payload.surname
    user.phone = payload.phone
    user.personal_id = payload.personal_id
    user.user_type = payload.user_type
    user.approved = False  # Mark the account as pending approval
    user.save()

    return {"message": "Account update request sent. Awaiting admin approval."}


@router.post("/request-code")
def send_login_code(request, payload: RequestCodeSchema):
    email = payload.email
    user = get_object_or_404(User, email=email)

    if not user.active:
        raise HttpError(401, "NOT_VERIFIED")

    if not user.approved:
        raise HttpError(401, "NOT_APPROVED")

    # Generate and hash the login code
    # TODO: Enable creation of login code after login ui will be done
    # login_code = generate_login_code()
    login_code = '123456'
    user.set_login_code(login_code)
    user.save()

    # Send the login code via email
    # send_mail(
    #     'Your Login Code',
    #     f'Your login code is: {login_code}',
    #     'no-reply@example.com',
    #     [email],
    # )

    return {"message": "Login code sent.", "login_code": login_code}


@router.post("/verify-code")
def login(request, payload: VerifyCodeSchema):
    email = payload.email
    code = payload.code
    user = get_object_or_404(User, email=email)

    if not user.is_login_code_valid():
        raise HttpError(410, "CODE_EXPIRED")

    if not user.check_login_code(code):
        raise HttpError(400, "CODE_INVALID")

    # Clear the hashed login code after successful login
    # TODO: Enable deletion of login code after login ui will be done
    # user.hashed_login_code = None
    # user.save()

    refresh = RefreshToken.for_user(user)
    return {
        "access_token": str(refresh.access_token),
        "refresh_token": str(refresh),
    }


@router.post("/refresh", response=TokenRefreshOutputSchema)
def refresh_token(request, payload: TokenRefreshInputSchema):
    """
    Refresh the access token using the refresh token.
    """
    try:
        refresh = RefreshToken(payload.refresh)  # Validate the refresh token
        data = {
            "access": str(refresh.access_token),  # Generate the new access token
            "refresh": str(refresh),  # Optionally include a rotated refresh token
        }
        return data
    except Exception as e:
        raise HttpError(400, f"CODE_INVALID")


@router.post("/logout")
def logout(request, payload: LogoutSchema):
    """
    Log out a user by blacklisting their refresh token.
    """
    try:
        # Attempt to blacklist the provided refresh token
        token = RefreshToken(payload.refresh)
        token.blacklist()
        return {"message": "Successfully logged out"}
    except Exception as e:
        raise HttpError(400, f"LOGIN_FAILED")


@router.get("/profile", response=UserProfileSchema, auth=JWTBearer())
def get_profile(request):
    """
    Return the authenticated user's profile, including images and partner ID, etc.
    """
    return request.auth  # Ninja will apply UserProfileSchema on this user instance


@router.put("/profile", response=UserProfileSchema, auth=JWTBearer())
def update_profile(request, payload: UpdateProfileSchema):
    """
    Update the authenticated user's profile.

    The request payload may contain:
    - normal fields (name, surname, phone, birthdate, description, user_type)
    - foreign key IDs for city, university, field_of_study
    - a list of interest IDs for the interests M2M
    """
    user = request.auth
    data = payload.dict(exclude_unset=True)

    # 1) Update "normal" fields
    normal_fields = ["name", "surname", "phone", "birthdate", "description", "user_type"]
    for field in normal_fields:
        if field in data:
            setattr(user, field, data[field])

    # 2) Generic approach for foreign key fields
    #    Each entry: field_name -> (ModelClass, error_message_if_null_or_zero)
    FOREIGN_KEY_MAPPING = {
        "city": (City, "City must exist in predefined list"),
        "university": (University, "University must exist in predefined list"),
        "field_of_study": (FieldOfStudy, "Field of study must exist in predefined list")
    }

    for field_name, (model_cls, error_msg) in FOREIGN_KEY_MAPPING.items():
        if field_name in data:
            fk_id = data[field_name]
            if not fk_id or fk_id == 0:
                raise HttpError(400, error_msg)
            obj = get_object_or_404(model_cls, pk=fk_id)
            setattr(user, field_name, obj)

    # 3) Many-to-many: interests
    if "interests" in data:
        new_interest_ids = data["interests"] or []
        valid_count = Interest.objects.filter(pk__in=new_interest_ids).count()
        if valid_count != len(new_interest_ids):
            raise HttpError(400, "One or more provided interest IDs do not exist.")

        user.interests.set(new_interest_ids)

    user.save()
    return user


@router.get("/users", response=UserListSchema, auth=JWTBearer())
def get_potential_pairs(request, pagination: PaginationQuery = Query(...)):
    """
    Return a paginated list of users with whom the authenticated user can form a pair.
    Show first those who match city or share interests, then everyone else,
    but always ensuring:
      - opposite user_type (mentor vs repatriate)
      - partner is null
      - active, approved
      - exclude viewed, pending, matched
    """
    user = request.auth  # current user
    page_number = pagination.page or 1
    target_role = "mentor" if user.user_type == "repatriate" else "repatriate"

    # Base queryset: all users of the opposite role
    base_qs = User.objects.filter(
        user_type=target_role,
        partner__isnull=True,
        active=True,
        approved=True
    ).exclude(id=user.id)

    # Exclude users who are "viewed", "pending", or "matched"
    viewed_ids = user.viewed_users.values_list('id', flat=True)

    # Pending (either from_user=user or to_user=user)
    pending_from = Pending.objects.filter(from_user=user).values_list('to_user_id', flat=True)
    pending_to = Pending.objects.filter(to_user=user).values_list('from_user_id', flat=True)

    # (matched (either user_a=user or user_b=user)
    # We'll collect the "other" user's IDs from all matches involving me
    matched_qs = Match.objects.filter(Q(user_a=user) | Q(user_b=user))
    matched_ids = set()
    for m in matched_qs:
        matched_ids.add(m.user_a_id)
        matched_ids.add(m.user_b_id)

    # Build a single set of excluded IDs
    excluded_ids = set(viewed_ids) | set(pending_from) | set(pending_to) | matched_ids
    base_qs = base_qs.exclude(id__in=excluded_ids)

    # Annotate priority: same city, shared interests
    base_qs = base_qs.annotate(
        same_city=Case(
            When(city=user.city, then=1),
            default=0,
            output_field=IntegerField()
        ),
        common_interests=Count(
            'interests',
            filter=Q(interests__in=user.interests.all()),
            distinct=True
        )
    ).order_by('-same_city', '-common_interests', 'public_id')
    # ^ 'id' at the end just for a stable ordering among ties

    # Paginate (10 users per page)
    paginator = Paginator(base_qs, 10)
    page_obj = paginator.get_page(page_number)

    return {
        "users": list(page_obj.object_list),
        "current_page": page_obj.number,
        "total_pages": paginator.num_pages,
        "has_next": page_obj.has_next(),
    }


@router.get("/user/id_{target_public_id}", response=SimpleUserSchema, auth=JWTAuth())
def get_user(request, target_public_id: UUID):
    """
    Get minimal user info by his public id
    """
    target_user = get_object_or_404(User, public_id=target_public_id)
    return target_user


@router.post("/image", response=ImageResponseSchema, auth=JWTAuth())
def upload_image(request, image: UploadedFile = File(...)):
    """
    Upload a new image for the authenticated user.
    """
    user = request.auth  # The authenticated user from your JWTAuth

    # Check max images
    if user.images.count() >= settings.MAX_IMAGES_PER_USER:
        raise HttpError(400, f"Cannot upload more than {settings.MAX_IMAGES_PER_USER} images.")

    # Validate extension and size
    try:
        validate_image_file(image, max_size_mb=settings.MAX_IMAGE_SIZE)
    except ValueError as e:
        raise HttpError(400, str(e))

    # Create the Image instance but don't save to DB yet
    new_image = Image(user=user)
    # We only need the *content* of the file + a filename
    # (ImageField will handle saving to storage)
    content = ContentFile(image.read())
    filename = image.name

    # Save the file via Django's storage
    new_image.file.save(filename, content, save=True)

    # The "new_image.file.url" property is automatically created by Django storage
    # e.g., /media/user_<public_id>/images/xxx.jpg
    return {
        "message": "Image uploaded successfully",
        "image_id": new_image.id,
        "image_url": new_image.file.url,
    }


@router.post("/replace-image", response=ImageResponseSchema, auth=JWTAuth())
def replace_image(
        request,
        image_id: int = Form(...),
        image: UploadedFile = File(...)
):
    """
    Replace an existing image (by image_id) with a new file.
    """
    user = request.auth
    user_image = get_object_or_404(Image, id=image_id, user=user)

    # Validate the file
    try:
        validate_image_file(image, max_size_mb=settings.MAX_IMAGE_SIZE)
    except ValueError as e:
        raise HttpError(400, str(e))

    # Remove old file from storage
    if user_image.file and user_image.file.name:
        user_image.file.delete(save=False)

    # Save the new file content
    content = ContentFile(image.read())
    user_image.file.save(image.name, content, save=True)

    return {
        "message": "Image replaced successfully",
        "image_id": user_image.id,
        "image_url": user_image.file.url,
    }


@router.delete("/image/{image_id}", response=MessageSchema, auth=JWTAuth())
def delete_image(request, image_id: int):
    user = request.auth
    user_image = get_object_or_404(Image, id=image_id, user=user)

    # Deleting `user_image` triggers the post_delete signal on Image,
    # which removes the file from FS automatically
    user_image.delete()

    return {"message": f"Image {image_id} deleted successfully."}


@router.get("/interests", response=list[InterestSchema])
def get_interests(request):
    interests = Interest.objects.all()
    return [{"id": interest.id, "name": interest.name} for interest in interests]


@router.get("/universities", response=list[UniversitySchema])
def get_universities(request):
    universities = University.objects.all()
    return universities


@router.get("/cities", response=list[CitySchema])
def get_cities(request):
    cities = City.objects.all()
    return cities


@router.get("/fields-of-study", response=list[FieldOfStudySchema])
def get_fields_of_study(request):
    fields_of_study = FieldOfStudy.objects.all()
    return fields_of_study


@router.post("/dislike/{target_public_id}", response=MessageSchema, auth=JWTAuth())
def mark_as_viewed(request, target_public_id: UUID):
    user = request.auth
    target_user = get_object_or_404(User, public_id=target_public_id)

    handle_dislike(user, target_user)
    # Add to 'viewed_users'
    user.viewed_users.add(target_user)

    return {"message": f"You disliked {target_user.get_full_name()}"}


@router.post("/save/{target_public_id}", response=MessageSchema, auth=JWTAuth())
def save_user(request, target_public_id: UUID):
    user = request.auth
    target_user = get_object_or_404(User, public_id=target_public_id)

    handle_save(user, target_user)
    # Add to 'saved_users'
    user.saved_users.add(target_user)

    return {"message": f"You saved {target_user.get_full_name()}"}


@router.post("/like/{target_public_id}", response=MatchCreationSchema, auth=JWTAuth())
def like_user(request, target_public_id: UUID):
    user = request.auth
    target_user = get_object_or_404(User, public_id=target_public_id)

    handle_like(user, target_user)

    # Next, check if there's a pending from target->user => form a match
    existing = Pending.objects.filter(from_user=target_user, to_user=user).first()
    if existing:
        existing.delete()
        new_match = Match.objects.create(
            user_a=user,
            user_b=target_user,
            status="not_final"
        )

        if user.id == target_user.id:
            raise HttpError(400, "Cannot create a chat with yourself.")

        # Generate or retrieve the ws_key
        sorted_ids = sorted([str(user.public_id), str(target_user.public_id)])
        ws_key = f"chat_{'_'.join(sorted_ids)}"
        chat_obj, created = Chat.objects.get_or_create(ws_key=ws_key)
        chat_obj.users.add(user, target_user)

        return {"message": "It's a match!", "match_id": new_match.id}
    else:
        # otherwise create or reuse pending from user->target
        if not Pending.objects.filter(from_user=user, to_user=target_user).exists():
            Pending.objects.create(from_user=user, to_user=target_user)
        return {"message": f"Like saved for {target_user.get_full_name()}. Waiting for them to like you back."}


@router.get("/user/chats", response=List[ChatSchema], auth=JWTAuth())
def chats(request):
    """
    Get list of the authenticated user's chats.
    """
    user = request.auth

    if not isinstance(user, User):
        return []

    user_chats = Chat.objects.filter(users=user)
    result = []
    for chat in user_chats:
        user_ids = [u.public_id for u in chat.users.all()]

        # Берём последнее сообщение, если оно есть
        last_message = chat.messages.order_by("-created_at").first()
        last_message_data = None
        if last_message:
            last_message_data = ChatMessageSchema(
                sender_id=last_message.sender.public_id,
                content=last_message.content,
                created_at=last_message.created_at.isoformat(),
                is_viewed=last_message.is_viewed,
            )

        result.append(ChatSchema(ws_key=chat.ws_key, user_ids=user_ids, last_message=last_message_data))

    return result


@router.get("/user/saved", response=UserListSchema, auth=JWTBearer())
def get_saved_users(request, pagination: PaginationQuery = Query(...)):
    """
    Return a paginated list of users that the authenticated user has saved.
    """
    user = request.auth  # the currently authenticated user
    page_number = pagination.page or 1

    # Query all saved users
    base_qs = user.saved_users.all()
    base_qs = base_qs.filter(active=True, approved=True)

    # Paginate (10 per page)
    paginator = Paginator(base_qs, 10)
    page_obj = paginator.get_page(page_number)

    # Return the data matching your existing UserListSchema shape
    return {
        "users": list(page_obj.object_list),
        "current_page": page_obj.number,
        "total_pages": paginator.num_pages,
        "has_next": page_obj.has_next(),
    }


def dashboard_callback(request, context):
    WEEKDAYS = [
        "Mon",
        "Tue",
        "Wed",
        "Thu",
        "Fri",
        "Sat",
        "Sun",
    ]
    positive = [[1, random.randrange(8, 28)] for i in range(1, 28)]
    performance_positive = [[1, random.randrange(8, 28)] for i in range(1, 28)]
    performance_negative = [[-1, -random.randrange(8, 28)] for i in range(1, 28)]

    user_data = (
        User.objects
        .annotate(month=TruncMonth("date_joined"))
        .values("month")
        .annotate(count=Count("id"))
        .order_by("month")
    )

    match_data = (
        Match.objects
        .annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(count=Count("id"))
        .order_by("month")
    )

    performance = [
        {
            "title": _("Likes"),
            "metric": "1234",
            "footer": mark_safe(
                '<strong class="text-green-600 font-medium">+3.14%</strong>&nbsp;progress from last week'
            ),
            "chart": json.dumps(
                {
                    "labels": [WEEKDAYS[day % 7] for day in range(1, 28)],
                    "datasets": [
                        {
                            "data": performance_positive,
                            "borderColor": "var(--color-primary-700)",
                        }
                    ],
                }
            ),
        },
        {
            "title": _("Matches"),
            "metric": "123",
            "footer": mark_safe(
                '<strong class="text-green-600 font-medium">+3.14%</strong>&nbsp;progress from last week'
            ),
            "chart": json.dumps(
                {
                    "labels": [WEEKDAYS[day % 7] for day in range(1, 28)],
                    "datasets": [
                        {
                            "data": performance_positive,
                            "borderColor": "var(--color-primary-300)",
                        }
                    ],
                }
            ),
        },
    ]
    context.update({
        "chart_labels": [x["month"].strftime("%b %Y") for x in user_data],
        "chart_data": [x["count"] for x in user_data],
        "match_chart_labels": [x["month"].strftime("%b %Y") for x in match_data],
        "match_chart_data": [x["count"] for x in match_data],
        "total_users": User.objects.count(),
        "total_matches": Match.objects.count(),
        "total_likes": Pending.objects.count(),
        "performance": performance,
    })

    return context
