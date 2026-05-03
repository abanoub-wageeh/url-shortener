from sqlalchemy import select

import pytest

from app.core.security import create_access_token, hash_password
from app.models.user import User
from app.services import auth_service


async def sign_up_user(client, email="user@example.com", user_name="test_user"):
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "name": "Test User",
            "user_name": user_name,
            "email": email,
            "password": "secret123",
        },
    )
    assert response.status_code == 201
    return response


@pytest.mark.asyncio
async def test_signup_verify_login_me_refresh_and_logout_flow(client, monkeypatch):
    sent_tokens = []

    def fake_send_verification_email(recipient_email, recipient_name, token):
        sent_tokens.append(token)

    monkeypatch.setattr(auth_service, "send_verification_email", fake_send_verification_email)

    signup_response = await sign_up_user(client)
    assert signup_response.json() == {
        "message": "Account created. Check your email to verify your account."
    }
    assert len(sent_tokens) == 1

    login_before_verify = await client.post(
        "/api/v1/auth/login",
        json={"identifier": "user@example.com", "password": "secret123"},
    )
    assert login_before_verify.status_code == 403
    assert login_before_verify.json()["detail"] == "Verify your email before logging in"

    verify_response = await client.get(
        "/api/v1/auth/verify-email",
        params={"token": sent_tokens[0]},
    )
    assert verify_response.status_code == 200
    assert verify_response.json() == {"message": "Email verified successfully"}

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"identifier": "user@example.com", "password": "secret123"},
    )
    assert login_response.status_code == 200
    login_body = login_response.json()
    assert login_body["token_type"] == "bearer"
    assert login_body["user"]["email"] == "user@example.com"

    me_response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {login_body['access_token']}"},
    )
    assert me_response.status_code == 200
    assert me_response.json()["user_name"] == "test_user"

    refresh_response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": login_body["refresh_token"]},
    )
    assert refresh_response.status_code == 200
    refresh_body = refresh_response.json()
    assert refresh_body["refresh_token"] != login_body["refresh_token"]

    logout_response = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh_body["refresh_token"]},
    )
    assert logout_response.status_code == 200
    assert logout_response.json() == {"message": "Signed out successfully"}

    refresh_after_logout = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_body["refresh_token"]},
    )
    assert refresh_after_logout.status_code == 401
    assert refresh_after_logout.json()["detail"] == "Refresh token has expired"


@pytest.mark.asyncio
async def test_change_password_updates_credentials(client, monkeypatch):
    sent_tokens = []

    def fake_send_verification_email(recipient_email, recipient_name, token):
        sent_tokens.append(token)

    monkeypatch.setattr(auth_service, "send_verification_email", fake_send_verification_email)

    await sign_up_user(client, email="change@example.com", user_name="change_user")
    await client.get("/api/v1/auth/verify-email", params={"token": sent_tokens[0]})

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"identifier": "change_user", "password": "secret123"},
    )
    access_token = login_response.json()["access_token"]

    change_response = await client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "current_password": "secret123",
            "new_password": "newsecret123",
            "new_password_confirm": "newsecret123",
        },
    )
    assert change_response.status_code == 200
    assert change_response.json() == {"message": "Password changed successfully"}

    old_login_response = await client.post(
        "/api/v1/auth/login",
        json={"identifier": "change@example.com", "password": "secret123"},
    )
    assert old_login_response.status_code == 401

    new_login_response = await client.post(
        "/api/v1/auth/login",
        json={"identifier": "change_user", "password": "newsecret123"},
    )
    assert new_login_response.status_code == 200


@pytest.mark.asyncio
async def test_protected_auth_endpoint_rejects_unverified_user_token(client, db_session):
    user = User(
        name="Unverified User",
        user_name="unverified_user",
        email="unverified@example.com",
        hashed_password=hash_password("secret123"),
        is_email_verified=False,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {create_access_token(str(user.id))}"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Verify your email before continuing"


@pytest.mark.asyncio
async def test_forgot_password_and_reset_password_flow(client, db_session, monkeypatch):
    sent_tokens = []

    def fake_send_password_reset_email(recipient_email, recipient_name, token):
        sent_tokens.append(token)

    monkeypatch.setattr(auth_service, "send_password_reset_email", fake_send_password_reset_email)

    user = User(
        name="Reset User",
        user_name="reset_user",
        email="reset@example.com",
        hashed_password=hash_password("secret123"),
        is_email_verified=True,
    )
    db_session.add(user)
    await db_session.commit()

    forgot_response = await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "reset@example.com"},
    )
    assert forgot_response.status_code == 200
    assert forgot_response.json() == {
        "message": "If an account with that email exists, a password reset email has been sent."
    }
    assert len(sent_tokens) == 1

    reset_response = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": sent_tokens[0], "new_password": "newsecret123"},
    )
    assert reset_response.status_code == 200
    assert reset_response.json() == {"message": "Password reset successfully"}

    old_login_response = await client.post(
        "/api/v1/auth/login",
        json={"identifier": "reset@example.com", "password": "secret123"},
    )
    assert old_login_response.status_code == 401

    new_login_response = await client.post(
        "/api/v1/auth/login",
        json={"identifier": "reset_user", "password": "newsecret123"},
    )
    assert new_login_response.status_code == 200


@pytest.mark.asyncio
async def test_resend_verification_email_only_resends_for_unverified_accounts(
    client, db_session, monkeypatch
):
    sent_tokens = []

    def fake_send_verification_email(recipient_email, recipient_name, token):
        sent_tokens.append(token)

    monkeypatch.setattr(auth_service, "send_verification_email", fake_send_verification_email)

    user = User(
        name="Pending User",
        user_name="pending_user",
        email="pending@example.com",
        hashed_password=hash_password("secret123"),
        is_email_verified=False,
    )
    db_session.add(user)
    await db_session.commit()

    resend_response = await client.post(
        "/api/v1/auth/resend-verification-email",
        json={"email": "pending@example.com"},
    )
    assert resend_response.status_code == 200
    assert resend_response.json() == {
        "message": "If an unverified account with that email exists, a verification email has been sent."
    }
    assert len(sent_tokens) == 1

    await db_session.refresh(user)
    assert user.email_verification_token_hash is not None

    verified_user = User(
        name="Verified User",
        user_name="verified_user",
        email="verified@example.com",
        hashed_password=hash_password("secret123"),
        is_email_verified=True,
    )
    db_session.add(verified_user)
    await db_session.commit()

    verified_resend_response = await client.post(
        "/api/v1/auth/resend-verification-email",
        json={"email": "verified@example.com"},
    )
    assert verified_resend_response.status_code == 200
    assert verified_resend_response.json() == {
        "message": "If an unverified account with that email exists, a verification email has been sent."
    }
    assert len(sent_tokens) == 1
