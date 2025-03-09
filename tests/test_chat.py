import pytest
from django.contrib.auth import get_user_model
from chat.models import Chat, ChatMessage
from ninja_jwt.tokens import AccessToken

User = get_user_model()


@pytest.mark.django_db
def test_get_chats_no_chats(client):
    """Тест: пользователь без чатов получает пустой список."""
    user = User.objects.create_user(email="test@example.com", password="password123")
    token = AccessToken.for_user(user)

    response = client.get("/user/chats", HTTP_AUTHORIZATION=f"Bearer {token}")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.django_db
def test_get_chats_without_messages(client):
    """Тест: чат без сообщений не должен содержать last_message."""
    user1 = User.objects.create_user(email="user1@example.com", password="password123")
    user2 = User.objects.create_user(email="user2@example.com", password="password123")
    token = AccessToken.for_user(user1)

    chat = Chat.objects.create(ws_key="room-1")
    chat.users.add(user1, user2)

    response = client.get("/user/chats", HTTP_AUTHORIZATION=f"Bearer {token}")

    assert response.status_code == 200
    data = response.json()

    assert len(data) == 1
    assert data[0]["ws_key"] == "room-1"
    assert set(data[0]["user_ids"]) == {str(user1.public_id), str(user2.public_id)}
    assert data[0]["last_message"] is None


@pytest.mark.django_db
def test_get_chats_with_messages(client):
    """Тест: чат с сообщениями должен содержать корректный last_message."""
    user1 = User.objects.create_user(email="user1@example.com", password="password123")
    user2 = User.objects.create_user(email="user2@example.com", password="password123")
    token = AccessToken.for_user(user1)

    chat = Chat.objects.create(ws_key="room-1")
    chat.users.add(user1, user2)

    message = ChatMessage.objects.create(chat=chat, sender=user2, content="Привет!")

    response = client.get("/user/chats", HTTP_AUTHORIZATION=f"Bearer {token}")

    assert response.status_code == 200
    data = response.json()

    assert len(data) == 1
    assert data[0]["ws_key"] == "room-1"
    assert set(data[0]["user_ids"]) == {str(user1.public_id), str(user2.public_id)}
    assert data[0]["last_message"] is not None
    assert data[0]["last_message"]["sender_id"] == str(user2.public_id)
    assert data[0]["last_message"]["content"] == "Привет!"


@pytest.mark.django_db
def test_get_chats_unauthorized(client):
    """Тест: анонимный пользователь должен получить 401 Unauthorized."""
    response = client.get("/user/chats")

    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}


@pytest.mark.django_db
def test_get_chats_not_my_chat(client):
    """Тест: авторизованный пользователь не должен видеть чужой чат."""
    user1 = User.objects.create_user(email="user1@example.com", password="password123")
    user2 = User.objects.create_user(email="user2@example.com", password="password123")
    user3 = User.objects.create_user(email="user3@example.com", password="password123")  # Лишний пользователь
    token = AccessToken.for_user(user3)

    chat = Chat.objects.create(ws_key="room-1")
    chat.users.add(user1, user2)

    response = client.get("/user/chats", HTTP_AUTHORIZATION=f"Bearer {token}")

    assert response.status_code == 200
    assert response.json() == []  # Чат не должен появляться
