import os
import random
import string
import uuid

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.db.models import Q
from django.shortcuts import get_object_or_404
from ninja import Router, Query
from ninja import UploadedFile, File
from ninja.errors import HttpError
from ninja.security import HttpBearer
from ninja_jwt.authentication import JWTAuth
from ninja_jwt.schema import TokenRefreshInputSchema, TokenRefreshOutputSchema
from ninja_jwt.tokens import RefreshToken

from .models import User
from .schemas import ProfileSchema, UpdateProfileSchema, UserListSchema, ImageUploadResponseSchema, \
    RequestApprovalSchema
from .schemas import VerifyEmailSchema, RequestCodeSchema, VerifyCodeSchema, LogoutSchema


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


@router.post("/verify-email/")
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


@router.get("/check-email/", response=dict)
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


@router.post("/request-approval/")
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


@router.post("/request-code/")
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


@router.post("/verify-code/")
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


@router.post("/refresh/", response=TokenRefreshOutputSchema)
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


@router.post("/logout/")
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


@router.get("/profile/", response=ProfileSchema, auth=JWTBearer())
def get_profile(request):
    """Return the authenticated user's profile."""
    user = request.auth
    return user


@router.put("/profile/", response=ProfileSchema, auth=JWTBearer())
def update_profile(request, payload: UpdateProfileSchema):
    """Update the authenticated user's profile."""
    user = request.auth

    # Update the allowed fields directly from the schema
    for field, value in payload.dict(exclude_unset=True).items():
        setattr(user, field, value)
    user.save()

    return user


@router.get("/users/", response=UserListSchema, auth=JWTBearer())
def get_potential_pairs(request):
    """Return a list of users with whom the authenticated user can form a pair."""
    user = request.auth

    # Determine the opposite role
    target_role = "mentor" if user.user_type == "repatriate" else "repatriate"

    # Fetch users who:
    # 1. Have the opposite role.
    # 2. Are not yet paired.
    # 3. Share similar interests or are from the same city.
    potential_pairs = (
        User.objects.filter(
            user_type=target_role,
            partner__isnull=True,  # Ensure the user is not already paired
            active=True,  # Ensure the user is active
            approved=True,  # Ensure the user is approved
        )
        .filter(
            Q(city=user.city) | Q(interests__overlap=user.interests)
        )
        .exclude(id=user.id)  # Exclude the current user
        .distinct()
    )

    return {"users": potential_pairs}


@router.post("/image/", response=ImageUploadResponseSchema, auth=JWTAuth())
def upload_image(request, image: UploadedFile = File(...)):
    """Handle image uploads for the authenticated user."""
    user = request.auth  # Get the authenticated user

    # Generate a unique filename using UUID
    extension = os.path.splitext(image.name)[1]  # Extract the file extension
    filename = f"{uuid.uuid4().hex}{extension}"  # Generate a unique filename
    user_directory = os.path.join(settings.MEDIA_ROOT, f"user_{user.public_id}/images")
    full_path = os.path.join(user_directory, filename)

    # Ensure the directory exists
    os.makedirs(user_directory, exist_ok=True)

    # Save the file
    with open(full_path, "wb") as f:
        for chunk in image.chunks():
            f.write(chunk)

    # Append the filename to the user's image list
    if not user.images:
        user.images = []
    user.images.append(f"user_{user.public_id}/images/{filename}")
    user.save()

    return {"message": "Image uploaded successfully",
            "image_url": f"{settings.MEDIA_URL}user_{user.public_id}/images/{filename}"}
