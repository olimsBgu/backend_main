import os
import shutil

import pytest
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.urls import reverse
from ninja_jwt.tokens import RefreshToken

from api.models import User


@pytest.mark.django_db
def test_verify_email(client, mocker):
    email = "testuser@example.com"

    # Mock send_mail to avoid actually sending an email
    mock_send_mail = mocker.patch("django.core.mail.send_mail", autospec=True)

    # Use the correct reverse path for the API
    response = client.post(reverse("api:verify_email"), {"email": email}, content_type="application/json")

    assert response.status_code == 200
    assert response.json() == {"message": "Email verification sent."}

    # Ensure the user is created
    user = User.objects.get(email=email)
    assert user.email == email

    # Ensure send_mail was called
    mock_send_mail.assert_called_once()
    assert f"/confirm-email/{user.pk}" in mail.send_mail.call_args[0][1]  # Check email contains confirmation link

    # Reset mocks after the test
    mock_send_mail.reset_mock()


@pytest.mark.django_db
def test_check_email(client):
    email = "testuser@example.com"

    # Create a user with email not confirmed
    user = User.objects.create(email=email, active=False)

    # Test when email is not confirmed
    url = reverse("api:check_email")  # Use the named route here
    response = client.get(url, {"email": email}, content_type="application/json")
    assert response.status_code == 200
    assert response.json() == {"email": email, "is_confirmed": False}

    # Mark the user as active
    user.active = True
    user.save()

    # Test when email is confirmed
    response = client.get(url, {"email": email}, content_type="application/json")
    assert response.status_code == 200
    assert response.json() == {"email": email, "is_confirmed": True}

    # Test for an email that does not exist
    response = client.get(url, {"email": "nonexistent@example.com"}, content_type="application/json")
    assert response.status_code == 200
    assert response.json() == {"email": "nonexistent@example.com", "is_confirmed": False}


@pytest.mark.django_db
def test_confirm_email(client, mocker):
    # Create a user
    user = User.objects.create(email="testuser@example.com")
    token = default_token_generator.make_token(user)

    url = reverse("api:confirm_email", args=[user.pk, token])
    response = client.get(url)
    assert response.status_code == 200
    assert response.json() == {"message": "Email confirmed successfully."}

    # Ensure the user is marked as active
    user.refresh_from_db()
    assert user.active is True


@pytest.mark.django_db(transaction=True)
def test_request_login_code(client, mocker):
    # Create an active and approved user
    user = User.objects.create(email="testuser@example.com", active=True, approved=True)

    # Mock send_mail
    mock_send_mail = mocker.patch("django.core.mail.send_mail", autospec=True)

    response = client.post(
        reverse("api:send_login_code"),
        {"email": user.email},
        content_type="application/json"
    )

    # Assert the response status code
    assert response.status_code == 200
    assert response.json() == {"message": "Login code sent."}

    # Ensure the login code is hashed
    user.refresh_from_db()
    assert user.hashed_login_code is not None

    # Ensure the mocked send_mail was called exactly once
    mock_send_mail.assert_called_once()

    # Reset mocks after the test
    mock_send_mail.reset_mock()


@pytest.mark.django_db
def test_login(client):
    # Create a user and set a login code
    user = User.objects.create(email="testuser@example.com", active=True, approved=True)
    code = "123456"
    user.set_login_code(code)
    user.save()

    response = client.post(reverse("api:login"), {"email": user.email, "code": code}, content_type="application/json")
    assert response.status_code == 200

    # Validate tokens in the response
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data

    # Ensure the login code is cleared
    user.refresh_from_db()
    assert user.hashed_login_code is None


@pytest.mark.django_db
def test_refresh_token(client):
    # Create a test user
    user = User.objects.create(email="testuser@example.com", active=True, approved=True)

    # Generate a refresh token for the user
    refresh = RefreshToken.for_user(user)

    # Call the /refresh endpoint
    url = reverse("api:refresh_token")
    response = client.post(
        url,
        {"refresh": str(refresh)},
        content_type="application/json"
    )

    assert response.status_code == 200
    assert "access" in response.json()  # Ensure the access token is returned
    assert "refresh" in response.json()  # Ensure the refresh token is returned


@pytest.mark.django_db
def test_logout(client):
    # Create a test user
    user = User.objects.create(email="testuser@example.com", active=True, approved=True)

    # Generate a refresh token for the user
    refresh = RefreshToken.for_user(user)

    # Call the /logout endpoint
    url = reverse("api:logout")
    response = client.post(
        url,
        {"refresh": str(refresh)},
        content_type="application/json"
    )

    assert response.status_code == 200
    assert response.json() == {"message": "Successfully logged out"}

    # Test that the refresh token is invalidated
    with pytest.raises(Exception):
        RefreshToken(str(refresh)).check_blacklist()


@pytest.mark.django_db
def test_get_profile(client):
    user = User.objects.create(
        email="test@example.com", name="Test", surname="User", active=True, approved=True
    )
    refresh = RefreshToken.for_user(user)
    access_token = str(refresh.access_token)

    response = client.get(
        reverse("api:get_profile"),
        HTTP_AUTHORIZATION=f"Bearer {access_token}"
    )

    assert response.status_code == 200
    assert response.json()["email"] == "test@example.com"


@pytest.mark.django_db
def test_update_profile(client):
    # Create a test user
    user = User.objects.create(
        email="test@example.com",
        name="Test",
        surname="User",
        active=True,
        approved=True,
        personal_id="123456789",
        images=[],
    )

    # Generate a JWT token for the user
    refresh = RefreshToken.for_user(user)
    access_token = str(refresh.access_token)

    # Send a PUT request with the updated data
    response = client.put(
        reverse("api:update_profile"),
        data={"name": "Updated Name", "description": "Updated description"},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {access_token}"  # Bearer token in header
    )

    # Assert the response
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["name"] == "Updated Name"
    assert response_data["description"] == "Updated description"

    # Verify that the user's data is updated in the database
    user.refresh_from_db()
    assert user.name == "Updated Name"
    assert user.description == "Updated description"


@pytest.mark.django_db
def test_get_potential_pairs(client):
    # Create a test user (repatriate)
    user = User.objects.create(
        email="repatriate@example.com",
        name="Repatriate",
        surname="Test",
        user_type="repatriate",
        city="CityA",
        interests=["hiking", "reading"],
        active=True,
        approved=True,
        personal_id="123456789"
    )

    # Create potential mentors
    User.objects.create(
        email="mentor1@example.com",
        name="Mentor",
        surname="One",
        user_type="mentor",
        city="CityA",
        interests=["hiking", "coding"],
        active=True,
        approved=True,
        personal_id="123456798"
    )
    User.objects.create(
        email="mentor2@example.com",
        name="Mentor",
        surname="Two",
        user_type="mentor",
        city="CityB",
        interests=["reading"],
        active=True,
        approved=True,
        personal_id="123456879"
    )

    # Generate a JWT token for the user
    refresh = RefreshToken.for_user(user)
    access_token = str(refresh.access_token)

    # Call the /users endpoint with the Authorization header
    url = reverse("api:get_potential_pairs")
    response = client.get(
        url,
        HTTP_AUTHORIZATION=f"Bearer {access_token}"  # Include the token in the headers
    )

    # Assert the response
    assert response.status_code == 200
    data = response.json()
    assert len(data["users"]) == 1  # Only one mentor matches the city and interests
    assert data["users"][0]["name"] == "Mentor"
    assert data["users"][0]["user_type"] == "mentor"
    assert data["users"][0]["interests"] == ['hiking', 'coding']


@pytest.mark.django_db
def test_upload_image(client, tmpdir):
    # Create a test user
    user = User.objects.create(
        email="testuser@example.com",
        name="Test",
        surname="User",
        user_type="repatriate",
        city="CityA",
        interests=["hiking", "reading"],
        active=True,
        approved=True,
        personal_id="123456789",
        images=[]
    )

    # Generate a JWT token for the user
    refresh = RefreshToken.for_user(user)
    access_token = str(refresh.access_token)

    # Simulate an image upload
    url = reverse("api:upload_image")
    image_path = tmpdir.join("test_image.jpg")
    image_path.write(b"fake image content")  # Create a fake image for testing

    uploaded_file_path = None  # Initialize for cleanup later

    try:
        with open(image_path, "rb") as image_file:
            response = client.post(
                url,
                {"image": image_file},
                HTTP_AUTHORIZATION=f"Bearer {access_token}"
            )

        # Assert the response
        assert response.status_code == 200
        assert response.json() == {"message": "Image uploaded successfully"}

        # Verify that the image is added to the user's images field
        user.refresh_from_db()
        assert len(user.images) == 1
        assert f"user_{user.public_id}/images/" in user.images[0]

    finally:
        user_folder = os.path.join(settings.MEDIA_ROOT, f"user_{user.public_id}")
        if user_folder and os.path.exists(user_folder):
            shutil.rmtree(user_folder, ignore_errors=True)


@pytest.mark.django_db
def test_request_approval_existing_user(client):
    # Create a test user with some fields already filled
    _ = User.objects.create(
        email="testuser@example.com",
        active=True,
        name="Existing",
        surname="User",
        personal_id="123456789",
    )

    # Attempt to update the account
    payload = {
        "name": "New",
        "surname": "Name",
        "phone": "1234567890",
        "personal_id": "987654321",
        "user_type": "repatriate",
        "email": "testuser@example.com",
    }
    url = reverse("api:request_approval")
    response = client.post(url, payload, content_type="application/json")

    # Assert the response
    assert response.status_code == 400
    assert response.json() == {"detail": "Account already registered. Please contact support for changes."}


@pytest.mark.django_db
def test_request_approval_new_user(client):
    # Create a test user with minimal fields
    user = User.objects.create(
        email="testuser@example.com",
        active=True,
        approved=False,
    )

    # Attempt to update the account
    payload = {
        "name": "New",
        "surname": "Name",
        "phone": "1234567890",
        "personal_id": "987654321",
        "user_type": "repatriate",
        "email": "testuser@example.com",
    }
    url = reverse("api:request_approval")
    response = client.post(url, payload, content_type="application/json")

    # Assert the response
    assert response.status_code == 200
    assert response.json() == {"message": "Account update request sent. Awaiting admin approval."}

    # Verify the user details were updated
    user.refresh_from_db()
    assert user.name == "New"
    assert user.surname == "Name"
    assert user.phone == "1234567890"
    assert user.personal_id == "987654321"
    assert user.user_type == "repatriate"
    assert not user.approved
