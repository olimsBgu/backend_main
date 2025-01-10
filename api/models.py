import uuid

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from datetime import timedelta
from django.contrib.auth.hashers import make_password, check_password


class UserManager(BaseUserManager):
    def create_user(self, email, **extra_fields):
        if not email:
            raise ValueError(_('The Email field must be set'))
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_unusable_password()  # Disable password functionality
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if password is None:
            raise ValueError("Superusers must have a password.")

        user = self.model(email=self.normalize_email(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user


class User(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('moderator', 'Moderator'),
        ('user', 'User'),
    ]

    email = models.EmailField(unique=True)
    name = models.CharField(max_length=255)
    surname = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, blank=True, null=True)
    personal_id = models.CharField(max_length=50)
    user_type = models.CharField(max_length=50, choices=[('repatriate', 'Repatriate'), ('mentor', 'Mentor')])
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='user')
    approved = models.BooleanField(default=False)
    active = models.BooleanField(default=False)
    images = models.JSONField(default=list, blank=True)
    birthdate = models.DateField(blank=True, null=True)
    city = models.CharField(max_length=100)
    university = models.CharField(max_length=100)
    field_of_study = models.CharField(max_length=100)
    interests = models.JSONField(default=list, blank=True)
    description = models.TextField(blank=True)
    partner = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='partners')
    date_joined = models.DateTimeField(default=timezone.now)
    hashed_login_code = models.CharField(max_length=128, blank=True, null=True)
    login_code_expires_at = models.DateTimeField(null=True, blank=True)
    is_staff = models.BooleanField(default=False)
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    groups = models.ManyToManyField(
        "auth.Group",
        related_name="api_users",
        blank=True,
        help_text=_("The groups this user belongs to."),
        verbose_name=_("groups"),
    )
    user_permissions = models.ManyToManyField(
        "auth.Permission",
        related_name="api_users",
        blank=True,
        help_text=_("Specific permissions for this user."),
        verbose_name=_("user permissions"),
    )

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['name', 'surname']

    def set_login_code(self, code: str):
        self.hashed_login_code = make_password(code)
        self.login_code_expires_at = timezone.now() + timedelta(minutes=10)

    def check_login_code(self, code: str) -> bool:
        return check_password(code, self.hashed_login_code)

    def is_login_code_valid(self) -> bool:
        return timezone.now() <= self.login_code_expires_at

    def __str__(self):
        return f"{self.email} ({self.role})"

    class Meta:
        app_label = 'api'


class Interest(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name
