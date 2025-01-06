from .base import *

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'rimonim_db',
        'USER': 'rimonim_user',
        'PASSWORD': 'securepassword',
        'HOST': 'localhost',
        'PORT': 5432,
    }
}