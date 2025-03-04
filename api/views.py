import random
import string
from uuid import UUID

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.files.base import ContentFile
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404
from ninja import Router, Query, Form
from ninja import UploadedFile, File
from ninja.errors import HttpError
from ninja.security import HttpBearer
from ninja_jwt.authentication import JWTAuth
from ninja_jwt.schema import TokenRefreshInputSchema, TokenRefreshOutputSchema
from ninja_jwt.tokens import RefreshToken
from typing import List

from .models import User, Interest, University, City, FieldOfStudy, Image, Pending, Match
from chat.models import Chat, ChatMessage
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
    Exclude users:
      - already viewed
      - in pending relationship (any direction)
      - in match relationship (any status)
    """
    user = request.auth
    page_number = pagination.page or 1  # Ensure default=1

    # 1) Determine the opposite role
    target_role = "mentor" if user.user_type == "repatriate" else "repatriate"

    # 2) Base queryset: potential users
    base_qs = User.objects.filter(
        user_type=target_role,
        partner__isnull=True,  # not already paired
        active=True,
        approved=True,
    ).filter(
        Q(city=user.city) | Q(interests__in=user.interests.all())
    ).exclude(id=user.id).distinct()

    # 3) Gather IDs that should be excluded

    # (a) already viewed
    viewed_ids = user.viewed_users.values_list('id', flat=True)

    # (b) pending (either from_user=user or to_user=user)
    pending_from = Pending.objects.filter(from_user=user).values_list('to_user_id', flat=True)
    pending_to = Pending.objects.filter(to_user=user).values_list('from_user_id', flat=True)

    # (c) matched (either user_a=user or user_b=user)
    #  We'll collect the "other" user's IDs from all matches involving me
    matched_qs = Match.objects.filter(Q(user_a=user) | Q(user_b=user))
    matched_ids = set()
    for m in matched_qs:
        matched_ids.add(m.user_a_id)
        matched_ids.add(m.user_b_id)

    # Build a single set of excluded IDs
    excluded_ids = set(viewed_ids) | set(pending_from) | set(pending_to) | matched_ids

    # 4) Exclude them
    potential_qs = base_qs.exclude(id__in=excluded_ids)

    # 5) Pagination
    paginator = Paginator(potential_qs, 10)  # 10 users per page
    page_obj = paginator.get_page(page_number)

    # 6) Return the paginated users
    users_page = list(page_obj.object_list)  # the actual User objects

    # "UserListSchema" typically expects {"users": [ <serialized users> ]}
    # We'll rely on your existing logic to convert them to the schema shape
    return {
        "users": users_page,
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
        return {"message": "It's a match!", "match_id": new_match.id}
    else:
        # otherwise create or reuse pending from user->target
        if not Pending.objects.filter(from_user=user, to_user=target_user).exists():
            Pending.objects.create(from_user=user, to_user=target_user)
        return {"message": f"Like saved for {target_user.get_full_name()}. Waiting for them to like you back."}


def generate_ws_key_for_users(user1: User, user2: User) -> str:
    """
    Generate a consistent key based on user public_ids.
    """
    sorted_ids = sorted([str(user1.public_id), str(user2.public_id)])
    return f"chat_{'_'.join(sorted_ids)}"


@router.get("/user/get_all_chats", response=List[ChatSchema], auth=JWTAuth())
def get_all_chats(request):
    """
    Get list of the authenticated user's chats.
    """
    user = request.auth

    # logger = logging.getLogger("django")
    # logger.info("chlen")

    if not isinstance(user, User):
        return []

    user_chats = Chat.objects.filter(users=user)
    result = []
    for c in user_chats:
        user_ids = [u.public_id for u in c.users.all()]
        result.append(ChatSchema(ws_key=c.ws_key, user_ids=user_ids))
    return result


@router.post("/make_chat/{target_public_id}", response=ChatSchema, auth=JWTAuth())
def make_chat(request, target_public_id: UUID):
    """
    Create or retrieve a WebSocket-based chat between the authenticated user and target_public_id.
    """
    user1 = request.auth
    user2 = get_object_or_404(User, public_id=target_public_id)

    if user1.id == user2.id:
        raise HttpError(400, "Cannot create a chat with yourself.")

    # Generate or retrieve the ws_key
    ws_key = generate_ws_key_for_users(user1, user2)
    chat_obj, created = Chat.objects.get_or_create(ws_key=ws_key)
    chat_obj.users.add(user1, user2)

    user_ids = [u.public_id for u in chat_obj.users.all()]
    return ChatSchema(ws_key=chat_obj.ws_key, user_ids=user_ids)


@router.post("/send_message/{target_public_id}", response=ChatMessageSchema, auth=JWTAuth())
def send_message(request, target_public_id: UUID, message: str = Form(...)):
    """
    Sends a message from the authenticated user to target_public_id.
    Must check if they have a chat together first.
    """
    sender = request.auth
    receiver = get_object_or_404(User, public_id=target_public_id)

    # Find an existing chat that has both users
    chat_obj = Chat.objects.filter(users=sender).filter(users=receiver).distinct().first()
    if not chat_obj:
        raise HttpError(400, "No chat found between these users. Create one first.")

    new_message = ChatMessage.objects.create(chat=chat_obj, sender=sender, content=message)
    return ChatMessageSchema(
        sender_id=sender.public_id,
        content=new_message.content,
        created_at=str(new_message.created_at)
    )


@router.get("/make_ws_key/{target_public_id}", response=dict, auth=JWTAuth())
def make_ws_key(request, target_public_id: UUID):
    """
    Generate a union WebSocket key between request.auth and target_public_id.
    (Does not create a Chat record; just returns the key.)
    """
    user1 = request.auth
    user2 = get_object_or_404(User, public_id=target_public_id)

    if user1.id == user2.id:
        raise HttpError(400, "Cannot generate a key for the same user.")

    ws_key = generate_ws_key_for_users(user1, user2)
    return {"ws_key": ws_key}


@router.get("/get_users_from_key/{ws_key}", response=List[UUID])
def get_users_from_key(request, ws_key: str):
    """
    Return the list of users' public_ids that are in this ws_key.
    """
    chat_obj = Chat.objects.filter(ws_key=ws_key).first()
    if not chat_obj:
        return []
    return [u.public_id for u in chat_obj.users.all()]

