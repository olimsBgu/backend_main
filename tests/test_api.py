import datetime
import os
import shutil

import pytest
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.urls import reverse
from ninja_jwt.tokens import RefreshToken
from ninja.errors import HttpError

from api.models import (
    User, City, University, FieldOfStudy, Interest, Image, Pending, Match
)


@pytest.mark.django_db
def test_verify_email(client, mocker):
    email = "testuser@example.com"

    # # Mock send_mail to avoid actually sending an email
    # mock_send_mail = mocker.patch("api.views.send_mail", autospec=True)

    # Use the correct reverse path for the API
    response = client.post(reverse("api:verify_email"), {"email": email}, content_type="application/json")
    assert response.status_code == 200

    response_json = response.json()
    assert response_json.get("message") == 'Email verification sent.'
    assert response_json.get("link", None) is not None

    # # Ensure the user is created
    # user = User.objects.get(email=email)
    # assert user.email == email
    #
    # # Ensure send_mail was called
    # mock_send_mail.assert_called_once()
    # assert f"/confirm-email/{user.pk}" in mock_send_mail.call_args[0][1]  # Check email contains confirmation link
    #
    # # Reset mocks after the test
    # mock_send_mail.reset_mock()


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

    # Confirm
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
def test_confirm_email(client):
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
    code = "123456"
    user.set_login_code(code)
    user.save()

    # # Mock send_mail
    # mock_send_mail = mocker.patch("api.views.send_mail", autospec=True)

    response = client.post(
        reverse("api:send_login_code"),
        {"email": user.email},
        content_type="application/json"
    )

    # Assert the response status code
    assert response.status_code == 200
    response_json = response.json()
    assert response_json.get('message') == "Login code sent."
    assert response_json.get("login_code") is not None

    # Ensure the login code is hashed
    user.refresh_from_db()
    assert user.hashed_login_code is not None

    # Ensure the mocked send_mail was called exactly once
    # mock_send_mail.assert_called_once()
    #
    # # Reset mocks after the test
    # mock_send_mail.reset_mock()


@pytest.mark.django_db
def test_login(client):
    # Create a user and set a login code
    user = User.objects.create(email="testuser@example.com", active=True, approved=True)
    code = "123456"
    user.set_login_code(code)
    user.save()

    response = client.post(
        reverse("api:login"),
        {"email": user.email, "code": code},
        content_type="application/json"
    )
    assert response.status_code == 200

    # Validate tokens in the response
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data

    # Ensure the login code is cleared
    # TODO: Enable deletion of login code after login ui will be done
    # user.refresh_from_db()
    # assert user.hashed_login_code is None


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
    data = response.json()
    assert "access" in data  # Ensure the access token is returned
    assert "refresh" in data  # Ensure the refresh token is returned


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
        # The token should now be invalid
        RefreshToken(str(refresh)).check_blacklist()


@pytest.mark.django_db
def test_get_profile(client):
    user = User.objects.create(
        email="test@example.com",
        name="Test",
        surname="User",
        active=True,
        approved=True
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
        personal_id="123456789"
    )

    # Generate a JWT token for the user
    refresh = RefreshToken.for_user(user)
    access_token = str(refresh.access_token)

    # Send a PUT request with the updated data
    response = client.put(
        reverse("api:update_profile"),
        data={"name": "Semen", "description": "Updated description", "phone": "+972559633414"},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {access_token}"  # Bearer token in header
    )

    # Assert the response
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Semen"
    assert data["description"] == "Updated description"
    assert data["phone"] == "+972559633414"

    # Verify that the user's data is updated in the database
    user.refresh_from_db()
    assert user.name == "Semen"
    assert user.description == "Updated description"
    assert user.phone == "+972559633414"


@pytest.mark.django_db
def test_update_profile_valid_data(client):
    # Create a test user
    user = User.objects.create(
        email="test@example.com",
        name="Test",
        surname="User",
        active=True,
        approved=True,
        personal_id="123456789",
    )

    # Generate a JWT token for the user
    refresh = RefreshToken.for_user(user)
    access_token = str(refresh.access_token)

    city = City.objects.create(name="Telaviv")
    university = University.objects.create(name="BGU")
    field_of_study = FieldOfStudy.objects.create(name="Computer Science")
    interests_1 = Interest.objects.create(name="Programming")
    interests_2 = Interest.objects.create(name="Gaming")

    # Send a PUT request with the updated data
    response = client.put(
        reverse("api:update_profile"),
        data={
            "name": "Semen",
            "surname": "Goyda",
            "description": "Updated description",
            "phone": "+972559633414",
            "birthdate": "1990-01-01",
            "city": city.id,
            "university": university.id,
            "field_of_study": field_of_study.id,
            "interests": [interests_1.id, interests_2.id]
        },
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {access_token}",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Semen"
    assert data["surname"] == "Goyda"
    assert data["description"] == "Updated description"
    assert data["phone"] == "+972559633414"
    assert data["birthdate"] == "1990-01-01"
    assert data["city"] == "Telaviv"
    assert data["university"] == "BGU"
    assert data["field_of_study"] == "Computer Science"

    user.refresh_from_db()
    assert user.name == "Semen"
    assert user.surname == "Goyda"
    assert user.description == "Updated description"
    assert user.phone == "+972559633414"
    assert user.birthdate == datetime.date(1990, 1, 1)
    assert user.city.name == "Telaviv"
    assert user.university.name == "BGU"
    assert user.field_of_study.name == "Computer Science"
    assert user.interests.count() == 2


@pytest.mark.django_db
def test_update_profile_invalid_phone(client):
    user = User.objects.create(
        email="test@example.com",
        name="Test",
        surname="User",
        active=True,
        approved=True,
        personal_id="123456789",
    )
    refresh = RefreshToken.for_user(user)
    access_token = str(refresh.access_token)

    # Sending wrong phone field
    response = client.put(
        reverse("api:update_profile"),
        data={"phone": "559633414"},  # Fails phone regex
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {access_token}",
    )

    # Pydantic validator raises 422 by default
    assert response.status_code == 422
    response_data = response.json()
    assert 'detail' in response_data
    assert 'value_error' == response_data['detail'][0]['type']
    assert 'phone' == response_data['detail'][0]['loc'][2]


@pytest.mark.django_db
def test_update_profile_invalid_name(client):
    user = User.objects.create(
        email="test@example.com",
        name="Test",
        surname="User",
        active=True,
        approved=True,
        personal_id="123456789",
    )
    refresh = RefreshToken.for_user(user)
    access_token = str(refresh.access_token)

    response = client.put(
        reverse("api:update_profile"),
        data={"name": "a4"},  # Fails name validator
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {access_token}",
    )

    assert response.status_code == 422
    response_data = response.json()
    assert 'detail' in response_data
    assert 'value_error' == response_data['detail'][0]['type']
    assert 'name' == response_data['detail'][0]['loc'][2]


@pytest.mark.django_db
def test_update_profile_invalid_birthdate(client):
    user = User.objects.create(
        email="test@example.com",
        name="Test",
        surname="User",
        active=True,
        approved=True,
        personal_id="123456789",
    )
    refresh = RefreshToken.for_user(user)
    access_token = str(refresh.access_token)

    response = client.put(
        reverse("api:update_profile"),
        data={"birthdate": "2050-01-01"},  # Future date
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {access_token}",
    )
    assert response.status_code == 422
    response_data = response.json()
    assert 'detail' in response_data
    assert 'value_error' == response_data['detail'][0]['type']
    assert 'birthdate' == response_data['detail'][0]['loc'][2]


@pytest.mark.django_db
def test_update_profile_invalid_city(client):
    """Test sending a string for city instead of an integer ID, which fails the Pydantic validator."""
    user = User.objects.create(
        email="test@example.com",
        name="Test",
        surname="User",
        active=True,
        approved=True,
        personal_id="123456789",
    )
    refresh = RefreshToken.for_user(user)
    access_token = str(refresh.access_token)

    response = client.put(
        reverse("api:update_profile"),
        data={"city": "town1"},  # Should be an integer, this triggers a 422
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {access_token}",
    )
    assert response.status_code == 422
    response_data = response.json()
    assert 'detail' in response_data
    assert 'int_parsing' == response_data['detail'][0]['type']
    assert 'city' == response_data['detail'][0]['loc'][2]


@pytest.mark.django_db
def test_get_potential_pairs(client):
    """
    Test the GET /users endpoint with pagination,
    verifying that viewed/pending/matched are excluded.
    """
    city_a = City.objects.create(name="CityA")
    city_b = City.objects.create(name="CityB")

    # interests
    hiking = Interest.objects.create(name="hiking")
    coding = Interest.objects.create(name="coding")

    # Create a 'repatriate' user
    repatriate = User.objects.create(
        email="repatriate@example.com",
        name="Repatriate",
        surname="Test",
        user_type="repatriate",
        city=city_a,
        active=True,
        approved=True,
        personal_id="111"
    )
    repatriate.interests.add(hiking)

    # Create mentor1 (same city, shared interest)
    mentor1 = User.objects.create(
        email="mentor1@example.com",
        name="Mentor",
        surname="One",
        user_type="mentor",
        city=city_a,
        active=True,
        approved=True,
        personal_id="222"
    )
    mentor1.interests.add(hiking, coding)

    # Create mentor2 (diff city, partial interest)
    mentor2 = User.objects.create(
        email="mentor2@example.com",
        name="Mentor",
        surname="Two",
        user_type="mentor",
        city=city_b,
        active=True,
        approved=True,
        personal_id="333"
    )
    mentor2.interests.add(coding)

    # login repatriate
    refresh = RefreshToken.for_user(repatriate)
    access_token = str(refresh.access_token)

    url = reverse("api:get_potential_pairs")  # GET /users

    # 1) No exclusions yet
    resp = client.get(url, HTTP_AUTHORIZATION=f"Bearer {access_token}")
    assert resp.status_code == 200
    data = resp.json()
    users_list = data["users"]
    assert len(users_list) == 2
    assert data["users"][0]["surname"] == "One"
    assert data["users"][1]["surname"] == "Two"

    # 2) Mark mentor1 as viewed => should exclude mentor1 now
    repatriate.viewed_users.add(mentor1)

    resp2 = client.get(url, HTTP_AUTHORIZATION=f"Bearer {access_token}")
    assert resp2.status_code == 200
    data2 = resp2.json()
    # Now mentor1 is excluded, so 1
    assert len(data2["users"]) == 1

    # 3) Create a mentor3 in same city => see if we get pagination
    for i in range(3, 15):
        m = User.objects.create(
            email=f"mentor{i}@example.com",
            name=f"Mentor{i}",
            surname="Paginated",
            user_type="mentor",
            city=city_a,
            active=True,
            approved=True,
            personal_id=f"900{i}"
        )
        m.interests.add(hiking)

    resp3 = client.get(url, HTTP_AUTHORIZATION=f"Bearer {access_token}")
    data3 = resp3.json()
    # By default, 10 items per page
    assert data3["current_page"] == 1
    assert data3["total_pages"] > 1
    assert len(data3["users"]) == 10  # first page

    # page=2
    resp4 = client.get(url + "?page=2", HTTP_AUTHORIZATION=f"Bearer {access_token}")
    data4 = resp4.json()
    assert data4["current_page"] == 2
    assert len(data4["users"]) == 3


@pytest.mark.django_db
def test_upload_image(client, tmpdir):
    """
    Test the POST /image endpoint with the new logic:
    - We no longer store 'images' as JSON on User; we store them in the Image model (FK to User).
    - The endpoint should return {message, image_url}.
    """
    user = User.objects.create(
        email="testuser@example.com",
        name="Test",
        surname="User",
        user_type="repatriate",
        active=True,
        approved=True,
        personal_id="123456789",
    )
    refresh = RefreshToken.for_user(user)
    access_token = str(refresh.access_token)

    url = reverse("api:upload_image")
    image_path = tmpdir.join("test_image.jpg")
    image_path.write(b"fake image content")  # create a fake "image"

    try:
        with open(image_path, "rb") as image_file:
            response = client.post(
                url,
                {"image": image_file},
                HTTP_AUTHORIZATION=f"Bearer {access_token}"
            )
        assert response.status_code == 200
        res_data = response.json()
        assert res_data["message"] == "Image uploaded successfully"
        assert "image_id" in res_data
        assert "image_url" in res_data

        # Check in DB
        user.refresh_from_db()
        # Now images are in the Image model, related_name="images"
        assert user.images.count() == 1
        img_obj = user.images.first()
        assert img_obj.file  # An ImageField should have a file
        assert f"user_{user.public_id}/images/" in img_obj.file.name  # or .file.path
    finally:
        user_folder = os.path.join(settings.MEDIA_ROOT, f"user_{user.public_id}")
        if os.path.exists(user_folder):
            shutil.rmtree(user_folder, ignore_errors=True)


@pytest.mark.django_db
def test_replace_image(client, tmpdir):
    """
    Test the POST /replace-image endpoint:
      1) Upload an image
      2) Replace it with a new file by posting {image_id, image}
    """
    user = User.objects.create(
        email="testuser@example.com", active=True, approved=True,
        personal_id="123456789"
    )
    refresh = RefreshToken.for_user(user)
    access_token = str(refresh.access_token)
    try:
        # 1) Upload initial image
        url_upload = reverse("api:upload_image")
        image_path = tmpdir.join("test_image.jpg")
        image_path.write(b"fake image content")

        with open(image_path, "rb") as image_file:
            resp = client.post(
                url_upload,
                {"image": image_file},
                HTTP_AUTHORIZATION=f"Bearer {access_token}"
            )
        assert resp.status_code == 200
        old_img_obj = user.images.first()
        assert old_img_obj is not None

        # 2) Replace via POST /replace-image
        url_replace = reverse("api:replace_image")  # no args; we're passing image_id in form data
        new_image_path = tmpdir.join("test_image2.jpg")
        new_image_path.write(b"another fake content")

        with open(new_image_path, "rb") as image_file:
            resp2 = client.post(
                url_replace,
                {
                    "image_id": str(old_img_obj.id),  # must be a string if going into form data
                    "image": image_file,
                },
                HTTP_AUTHORIZATION=f"Bearer {access_token}"
            )

        assert resp2.status_code == 200
        res2 = resp2.json()
        assert res2["message"] == "Image replaced successfully"
        assert "image_url" in res2

        user.refresh_from_db()
        # Still only 1 image in DB, but replaced with new file
        assert user.images.count() == 1
        replaced_img_obj = user.images.first()
        assert replaced_img_obj.id == old_img_obj.id  # same DB object
        assert replaced_img_obj.file != old_img_obj.file  # updated file name
    finally:
        user_folder = os.path.join(settings.MEDIA_ROOT, f"user_{user.public_id}")
        if os.path.exists(user_folder):
            shutil.rmtree(user_folder, ignore_errors=True)


@pytest.mark.django_db
def test_delete_image(client, tmpdir):
    """
    Test the DELETE /image/{image_id} endpoint:
    - Upload an image, then delete it.
    """
    user = User.objects.create(email="deleteuser@example.com", active=True, approved=True)
    refresh = RefreshToken.for_user(user)
    access_token = str(refresh.access_token)
    try:
        # 1. Upload an image
        url_upload = reverse("api:upload_image")
        image_path = tmpdir.join("delete_image.jpg")
        image_path.write(b"delete image content")

        with open(image_path, "rb") as image_file:
            resp = client.post(url_upload, {"image": image_file}, HTTP_AUTHORIZATION=f"Bearer {access_token}")
        assert resp.status_code == 200

        user.refresh_from_db()
        assert user.images.count() == 1
        img_obj = user.images.first()

        # 2. Delete the image
        url_delete = reverse("api:delete_image", args=[img_obj.id])
        resp2 = client.delete(url_delete, HTTP_AUTHORIZATION=f"Bearer {access_token}")
        assert resp2.status_code == 200
        assert resp2.json() == {"message": f"Image {img_obj.id} deleted successfully."}

        user.refresh_from_db()
        assert user.images.count() == 0  # image record is gone
    finally:
        user_folder = os.path.join(settings.MEDIA_ROOT, f"user_{user.public_id}")
        if os.path.exists(user_folder):
            shutil.rmtree(user_folder, ignore_errors=True)


@pytest.mark.django_db
def test_get_user(client):
    """
    Test GET /user/{public_id} returns the minimal user info by public id.
    """
    user = User.objects.create(
        email="test@example.com",
        name="Test",
        surname="User",
        user_type="repatriate",
        active=True,
        approved=True,
        personal_id="999"
    )
    refresh = RefreshToken.for_user(user)
    access_token = str(refresh.access_token)

    url = reverse("api:get_user", args=[user.public_id])

    resp = client.get(url, HTTP_AUTHORIZATION=f"Bearer {access_token}")
    assert resp.status_code == 200
    data = resp.json()
    # Should match user info
    assert data["surname"] == "User"
    assert data["public_id"] == str(user.public_id)


@pytest.mark.django_db
def test_dislike_soft_transition(client):
    """
    Test POST /dislike/{public_id} with "soft transition":
      - if user already saved the target, remove from 'saved_users' automatically
    """
    city = City.objects.create(name="TestCity")
    user = User.objects.create(
        email="user1@example.com",
        user_type="repatriate",
        active=True,
        approved=True,
        city=city,
        personal_id="123"
    )
    target = User.objects.create(
        email="user2@example.com",
        user_type="mentor",
        active=True,
        approved=True,
        city=city,
        personal_id="456"
    )

    # user "save" the target
    user.saved_users.add(target)
    assert target in user.saved_users.all()

    # login
    refresh = RefreshToken.for_user(user)
    access_token = str(refresh.access_token)

    url = reverse("api:mark_as_viewed", args=[target.public_id])

    resp = client.post(url, HTTP_AUTHORIZATION=f"Bearer {access_token}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["message"] == f"You disliked {target.get_full_name()}"

    user.refresh_from_db()
    # "soft transition": target should no longer be in saved_users
    assert target not in user.saved_users.all()
    # Instead target is in viewed_users
    assert target in user.viewed_users.all()


@pytest.mark.django_db
def test_save_soft_transition(client):
    """
    Test POST /save/{public_id}:
      - if user disliked the target, remove from 'viewed_users' automatically
    """
    user = User.objects.create(
        email="user1@example.com", user_type="repatriate",
        active=True, approved=True, personal_id="123"
    )
    target = User.objects.create(
        email="user2@example.com", user_type="mentor",
        active=True, approved=True, personal_id="456"
    )

    # user disliked target
    user.viewed_users.add(target)
    assert target in user.viewed_users.all()

    refresh = RefreshToken.for_user(user)
    access_token = str(refresh.access_token)

    url = reverse("api:save_user", args=[target.public_id])
    resp = client.post(url, HTTP_AUTHORIZATION=f"Bearer {access_token}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["message"] == f"You saved {target.get_full_name()}"

    user.refresh_from_db()
    # target removed from viewed_users
    assert target not in user.viewed_users.all()
    # now in saved_users
    assert target in user.saved_users.all()


@pytest.mark.django_db
def test_like_soft_transition(client):
    """
    Test POST /like/{public_id}:
      - if user disliked or saved the target, remove them from old set
      - create or reuse a Pending, unless the other user already liked me => Match.
    """
    user = User.objects.create(
        email="user1@example.com", user_type="repatriate",
        active=True, approved=True, personal_id="111"
    )
    target = User.objects.create(
        email="user2@example.com", user_type="mentor",
        active=True, approved=True, personal_id="222"
    )

    # Let's mark user disliked + saved target for some reason
    user.viewed_users.add(target)
    user.saved_users.add(target)
    assert target in user.viewed_users.all()
    assert target in user.saved_users.all()

    refresh = RefreshToken.for_user(user)
    access_token = str(refresh.access_token)

    url = reverse("api:like_user", args=[target.public_id])

    # 1) Like => remove from both sets, create pending
    resp = client.post(url, HTTP_AUTHORIZATION=f"Bearer {access_token}")
    assert resp.status_code == 200
    data = resp.json()
    assert "Like saved for" in data["message"]
    user.refresh_from_db()
    # removed from viewed_users/saved_users
    assert target not in user.saved_users.all()
    # pending from user->target
    assert Pending.objects.filter(from_user=user, to_user=target).exists()

    # 2) Let the target user now "like" me => match
    refresh2 = RefreshToken.for_user(target)
    access_token2 = str(refresh2.access_token)
    url2 = reverse("api:like_user", args=[user.public_id])
    resp2 = client.post(url2, HTTP_AUTHORIZATION=f"Bearer {access_token2}")
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["message"] == "It's a match!"
    # The pending from target->me => doesn't exist,
    # but we do see user had a pending user->target, so the second user's like triggers a match
    # that line might be slightly different if your logic is reversed

    # confirm a match is created
    m = Match.objects.all()[0]
    # user is user_a, target is user_b
    assert m.user_a == target or m.user_b == target
    assert m.user_a == user or m.user_b == user
    assert m.status == "not_final"


@pytest.mark.django_db
def test_like_block_if_pending(client):
    """
    If there's already a pending in any direction, we should block or fail with 400
    """
    user = User.objects.create(
        email="user1@example.com", user_type="repatriate",
        active=True, approved=True, personal_id="111"
    )
    target = User.objects.create(
        email="user2@example.com", name='Semen', surname='Igor', user_type="mentor",
        active=True, approved=True, personal_id="222"
    )
    # create a pending from user->target
    Pending.objects.create(from_user=user, to_user=target)

    refresh = RefreshToken.for_user(user)
    access_token = str(refresh.access_token)
    url = reverse("api:like_user", args=[target.public_id])

    resp = client.post(url, HTTP_AUTHORIZATION=f"Bearer {access_token}")
    # Because your "check_and_transition_state('like', ...)" sees a pending with from_user=user->target
    assert resp.status_code == 400
    assert 'You already liked Semen Igor.' in resp.json()["detail"]


@pytest.mark.django_db
def test_dislike_block_if_match(client):
    """
    If the user is already in a Match, we block new actions.
    """
    user = User.objects.create(
        email="u1@example.com", user_type="repatriate",
        active=True, approved=True, personal_id="111"
    )
    target = User.objects.create(
        email="u2@example.com", user_type="mentor",
        active=True, approved=True, personal_id="222"
    )
    Match.objects.create(user_a=user, user_b=target, status="not_final")

    refresh = RefreshToken.for_user(user)
    access_token = str(refresh.access_token)
    url = reverse("api:mark_as_viewed", args=[target.public_id])  # /dislike/

    resp = client.post(url, HTTP_AUTHORIZATION=f"Bearer {access_token}")
    assert resp.status_code == 400
    assert "already have a Match" in resp.json()["detail"]


@pytest.mark.django_db
def test_save_block_if_partner(client):
    """
    If user.partner == target or vice versa, block new actions
    """
    user = User.objects.create(
        email="u1@example.com", user_type="repatriate",
        active=True, approved=True, personal_id="111"
    )
    target = User.objects.create(
        email="u2@example.com", user_type="mentor",
        active=True, approved=True, personal_id="222"
    )
    # set partner
    user.partner = target
    user.save()

    refresh = RefreshToken.for_user(user)
    access_token = str(refresh.access_token)
    url = reverse("api:save_user", args=[target.public_id])  # /save/

    resp = client.post(url, HTTP_AUTHORIZATION=f"Bearer {access_token}")
    assert resp.status_code == 400
    assert "already partners" in resp.json()["detail"]

@pytest.mark.django_db
def test_get_saved_users(client):
    # 1) Create users
    u1 = User.objects.create(
        email="u1@example.com", user_type="repatriate",
        active=True, approved=True, personal_id="111"
    )
    u2 = User.objects.create(
        email="u2@example.com", user_type="mentor",
        active=True, approved=True, personal_id="222"
    )
    u3 = User.objects.create(
        email="u3@example.com", user_type="mentor",
        active=True, approved=True, personal_id="333"
    )

    # 2) u1 saves u2
    u1.saved_users.add(u2)

    # 3) Authenticate as u1
    refresh = RefreshToken.for_user(u1)
    access_token = str(refresh.access_token)

    # 4) Call the /user/saved endpoint
    url = reverse("api:get_saved_users")
    response = client.get(url, HTTP_AUTHORIZATION=f"Bearer {access_token}")

    assert response.status_code == 200

    # 5) Verify that only u2 is returned in the "users" list
    data = response.json()
    returned_ids = [item["public_id"] for item in data["users"]]

    assert str(u2.public_id) in returned_ids
    assert str(u3.public_id) not in returned_ids