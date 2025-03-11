import random
import requests
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from django.utils import timezone
from api.models import (
    User, Image,
    City, University, FieldOfStudy, Interest
)

# Sample name data
FIRST_NAMES = [
    "Alice", "Bob", "Charlie", "David", "Eve", "Frank", "Grace",
    "Hannah", "Irene", "Jack", "Karen", "Leo", "Mona", "Nancy",
    "Oliver", "Peter", "Queenie", "Robert", "Susan", "Tom"
]
LAST_NAMES = [
    "Smith", "Johnson", "Brown", "Davis", "Miller", "Wilson",
    "Moore", "Taylor", "Anderson", "Thomas", "Jackson", "White",
    "Harris", "Martin", "Thompson", "Garcia", "Martinez", "Clark",
    "Rodriguez", "Lewis"
]

USER_TYPES = ["repatriate", "mentor"]  # from your User model
SEX_CHOICES = ["male", "female"]

class Command(BaseCommand):
    help = "Generate 20 test users from a small subset (5) of City/Uni/FieldOfStudy/Interests, each with two images."

    def handle(self, *args, **options):
        num_users = 20
        self.stdout.write(self.style.NOTICE(f"Generating {num_users} test users..."))

        # Only pick from the first 5 of each table
        # (Adjust the .order_by('id') or other fields to ensure consistent ordering)
        all_cities = list(City.objects.order_by('id')[:5])
        all_universities = list(University.objects.order_by('id')[:5])
        all_fields = list(FieldOfStudy.objects.order_by('id')[:5])
        all_interests = list(Interest.objects.order_by('id')[:5])

        # Check we have at least 1 record in each
        if not all_cities or not all_universities or not all_fields or not all_interests:
            self.stdout.write(self.style.ERROR(
                "Ensure there are at least 5 records in City, University, FieldOfStudy, and Interest!"
            ))
            return

        for i in range(num_users):
            first = random.choice(FIRST_NAMES)
            last = random.choice(LAST_NAMES)
            email = f"testuser{i+1}@example.com"

            user = User.objects.create_user(
                email=email,
                name=first,
                surname=last,
                user_type=random.choice(USER_TYPES),
                role='user',
                sex=random.choice(SEX_CHOICES),
                approved=True,
                active=True,
                birthdate=timezone.datetime(
                    year=random.randint(1980, 2000),
                    month=random.randint(1, 12),
                    day=random.randint(1, 28)
                ),
                phone=str(random.randint(1000000000, 9999999999)),
                personal_id=f"PID{i+1}"
            )

            # Randomly pick city, university, field
            user.city = random.choice(all_cities)
            user.university = random.choice(all_universities)
            user.field_of_study = random.choice(all_fields)

            # Assign 1–3 random interests from the first 5
            k = random.randint(1, min(3, len(all_interests)))
            chosen_interests = random.sample(all_interests, k=k)
            user.save()
            user.interests.set(chosen_interests)

            # Fetch two placeholder images from picsum.photos
            for j in range(2):
                try:
                    response = requests.get("https://picsum.photos/400", timeout=5)
                    response.raise_for_status()

                    filename = f"user_{user.id}_img_{j+1}.jpg"
                    image_content = ContentFile(response.content, name=filename)

                    Image.objects.create(
                        user=user,
                        file=image_content,
                        uploaded_at=timezone.now()
                    )
                except Exception as e:
                    self.stdout.write(self.style.ERROR(
                        f"Failed to fetch/create image for {email}: {e}"
                    ))

        self.stdout.write(self.style.SUCCESS(
            f"Done creating {num_users} test users and images!"
        ))