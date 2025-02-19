import os

from django.conf import settings
from django.db.models.signals import post_delete
from django.dispatch import receiver

from api.models import Image, User


@receiver(post_delete, sender=User)
def remove_user_images_from_fs(sender, instance, **kwargs):
    """
    After a User record is deleted, remove the files for all related Images
    from the filesystem.
    """

    # If the images are already gone from the DB, you can manually remove the user_{public_id} folder:
    user_folder = os.path.join(settings.MEDIA_ROOT, f"user_{instance.public_id}", "images")
    if os.path.exists(user_folder):
        # Remove the entire directory
        import shutil
        shutil.rmtree(user_folder, ignore_errors=True)


@receiver(post_delete, sender=Image)
def remove_file_on_image_delete(sender, instance, **kwargs):
    """
    Remove the physical file from storage when the Image object is deleted.
    """
    if instance.file and instance.file.name:
        instance.file.delete(save=False)