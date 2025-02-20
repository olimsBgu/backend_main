import os

from django.db.models import Q
from ninja.errors import HttpError
from ninja.files import UploadedFile

from api.models import User, Match, Pending


def validate_image_file(image: UploadedFile, max_size_mb: int = 5):
    """
    Validate extension and file size of the uploaded image.
    Raises ValueError if invalid.

    :param image: The UploadedFile
    :param max_size_mb: The maximum allowed size in MB
    """
    valid_extensions = {".jpg", ".jpeg", ".png"}
    extension = os.path.splitext(image.name)[1].lower()
    if extension not in valid_extensions:
        raise ValueError("Only .jpg, .jpeg, or .png files are allowed.")

    # Check file size
    max_bytes = max_size_mb * 1024 * 1024
    if image.size > max_bytes:
        raise ValueError(f"File size exceeds {max_size_mb} MB limit.")


def handle_dislike(user: User, target_user: User):
    # 1) Block if a match exists
    if Match.objects.filter(
            Q(user_a=user, user_b=target_user) | Q(user_a=target_user, user_b=user)
    ).exists():
        raise HttpError(400, f"Cannot dislike: you already have a Match with {target_user.get_full_name()}.")

    # 2) Block if pending in any direction
    if Pending.objects.filter(
            Q(from_user=user, to_user=target_user) | Q(from_user=target_user, to_user=user)
    ).exists():
        raise HttpError(400, f"Cannot dislike: you already have a pending with {target_user.get_full_name()}.")

    # 3) Block if user is partnered
    if user.partner:
        raise HttpError(400, f"Cannot dislike: you are already partners with {user.partner.get_full_name()}.")

    # 4) "Soft transition": remove from saved if present
    if target_user in user.saved_users.all():
        user.saved_users.remove(target_user)


def handle_save(user: User, target_user: User):
    # 1) Block if a match
    if Match.objects.filter(
            Q(user_a=user, user_b=target_user) | Q(user_a=target_user, user_b=user)
    ).exists():
        raise HttpError(400, f"Cannot save: you already have a Match with {target_user.get_full_name()}.")

    # 2) Block if pending (any direction)
    if Pending.objects.filter(
            Q(from_user=user, to_user=target_user) | Q(from_user=target_user, to_user=user)
    ).exists():
        raise HttpError(400, f"Cannot save: you already have a pending with {target_user.get_full_name()}.")

    # 3) Block if partner
    if user.partner:
        raise HttpError(400, f"Cannot save: you are already partners with {user.partner.get_full_name()}.")

    # 4) Soft transition: remove from viewed if present
    if target_user in user.viewed_users.all():
        user.viewed_users.remove(target_user)


def handle_like(user: User, target_user: User):
    # 1) Block if match
    if Match.objects.filter(
            Q(user_a=user, user_b=target_user) | Q(user_a=target_user, user_b=user)
    ).exists():
        raise HttpError(400, f"Cannot like: you already have a Match with {target_user.get_full_name()}.")

    # 2) Block if user is partnered
    if user.partner:
        raise HttpError(400, f"Cannot like: you are already partners with {user.partner.get_full_name()}.")

    # 3) Check pending
    # If there's a pending from user->target, it means the user *already liked* them => block
    if Pending.objects.filter(from_user=user, to_user=target_user).exists():
        raise HttpError(400, f"You already liked {target_user.get_full_name()}.")

    # If there's a pending from target->user, DO NOT block => that leads to a match scenario
    # handled in the endpoint code. So no raise here.

    # 4) Soft transitions: remove from saved
    if target_user in user.saved_users.all():
        user.saved_users.remove(target_user)
