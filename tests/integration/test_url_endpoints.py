from datetime import datetime, timedelta, timezone

import pytest

from app.core.security import create_access_token, hash_password
from app.models.url import Url
from app.models.user import User


async def create_user(
    db_session,
    email="user@example.com",
    user_name="test_user",
    is_email_verified=True,
):
    user = User(
        name="Test User",
        user_name=user_name,
        email=email,
        hashed_password=hash_password("secret123"),
        is_email_verified=is_email_verified,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


def auth_headers(user):
    return {"Authorization": f"Bearer {create_access_token(str(user.id))}"}


async def create_url(
    client,
    user,
    original_url="https://example.com/page",
    custom_alias=None,
    expires_at=None,
):
    payload = {"original_url": original_url}
    if custom_alias is not None:
        payload["custom_alias"] = custom_alias
    if expires_at is not None:
        payload["expires_at"] = expires_at.isoformat()

    response = await client.post(
        "/api/v1/urls",
        headers=auth_headers(user),
        json=payload,
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_create_list_redirect_and_click_count_flow(client, db_session):
    user = await create_user(db_session)

    created = await create_url(client, user, "https://example.com/docs")

    assert created["short_code"] == "1"
    assert created["short_url"].endswith("/1")
    assert created["click_count"] == 0
    assert created["is_active"] is True

    list_response = await client.get(
        "/api/v1/urls?page=1&limit=20", headers=auth_headers(user)
    )
    assert list_response.status_code == 200
    list_body = list_response.json()
    assert list_body["total"] == 1
    assert list_body["page"] == 1
    assert list_body["limit"] == 20
    assert list_body["pages"] == 1
    assert list_body["items"][0]["short_code"] == created["short_code"]

    redirect_response = await client.get(f"/{created['short_code']}", follow_redirects=False)
    assert redirect_response.status_code == 302
    assert redirect_response.headers["location"] == "https://example.com/docs"

    url = await db_session.get(Url, created["id"])
    await db_session.refresh(url)
    assert url.click_count == 1


@pytest.mark.asyncio
async def test_list_urls_uses_page_pagination(client, db_session):
    user = await create_user(db_session)
    first = await create_url(client, user, "https://example.com/1")
    second = await create_url(client, user, "https://example.com/2")
    third = await create_url(client, user, "https://example.com/3")

    page_one = await client.get("/api/v1/urls?page=1&limit=2", headers=auth_headers(user))
    assert page_one.status_code == 200
    assert page_one.json()["total"] == 3
    assert page_one.json()["pages"] == 2
    assert [item["id"] for item in page_one.json()["items"]] == [third["id"], second["id"]]

    page_two = await client.get("/api/v1/urls?page=2&limit=2", headers=auth_headers(user))
    assert page_two.status_code == 200
    assert [item["id"] for item in page_two.json()["items"]] == [first["id"]]


@pytest.mark.asyncio
async def test_get_url_returns_owned_url(client, db_session):
    user = await create_user(db_session)
    created = await create_url(client, user, custom_alias="owned-link")

    response = await client.get(
        f"/api/v1/urls/{created['id']}",
        headers=auth_headers(user),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == created["id"]
    assert body["original_url"] == "https://example.com/page"
    assert body["short_code"] == "owned-link"
    assert body["short_url"].endswith("/owned-link")


@pytest.mark.asyncio
async def test_get_url_returns_404_for_another_users_url(client, db_session):
    owner = await create_user(db_session)
    other_user = await create_user(
        db_session, email="other@example.com", user_name="other_user"
    )
    created = await create_url(client, owner)

    response = await client.get(
        f"/api/v1/urls/{created['id']}",
        headers=auth_headers(other_user),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "URL not found"


@pytest.mark.asyncio
async def test_get_url_returns_404_for_deleted_url(client, db_session):
    user = await create_user(db_session)
    created = await create_url(client, user)
    await client.delete(f"/api/v1/urls/{created['id']}", headers=auth_headers(user))

    response = await client.get(
        f"/api/v1/urls/{created['id']}",
        headers=auth_headers(user),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "URL not found"


@pytest.mark.asyncio
async def test_update_url_updates_original_url_alias_and_expiration(client, db_session):
    user = await create_user(db_session)
    created = await create_url(client, user, custom_alias="old-alias")
    expires_at = datetime.now(timezone.utc) + timedelta(days=3)

    response = await client.patch(
        f"/api/v1/urls/{created['id']}",
        headers=auth_headers(user),
        json={
            "original_url": "https://example.com/updated",
            "custom_alias": "new-alias",
            "expires_at": expires_at.isoformat(),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == created["id"]
    assert body["original_url"] == "https://example.com/updated"
    assert body["short_code"] == "new-alias"
    assert body["short_url"].endswith("/new-alias")
    assert body["expires_at"] is not None

    old_redirect = await client.get("/old-alias", follow_redirects=False)
    assert old_redirect.status_code == 404

    new_redirect = await client.get("/new-alias", follow_redirects=False)
    assert new_redirect.status_code == 302
    assert new_redirect.headers["location"] == "https://example.com/updated"


@pytest.mark.asyncio
async def test_update_url_supports_partial_update_and_clears_expiration(client, db_session):
    user = await create_user(db_session)
    created = await create_url(
        client,
        user,
        custom_alias="partial-alias",
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )

    response = await client.patch(
        f"/api/v1/urls/{created['id']}",
        headers=auth_headers(user),
        json={"expires_at": None},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["original_url"] == created["original_url"]
    assert body["short_code"] == "partial-alias"
    assert body["expires_at"] is None


@pytest.mark.asyncio
async def test_update_url_returns_404_for_another_users_url(client, db_session):
    owner = await create_user(db_session)
    other_user = await create_user(
        db_session, email="other@example.com", user_name="other_user"
    )
    created = await create_url(client, owner)

    response = await client.patch(
        f"/api/v1/urls/{created['id']}",
        headers=auth_headers(other_user),
        json={"original_url": "https://example.com/hijack"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "URL not found"


@pytest.mark.asyncio
async def test_update_url_returns_404_for_deleted_url(client, db_session):
    user = await create_user(db_session)
    created = await create_url(client, user)
    await client.delete(f"/api/v1/urls/{created['id']}", headers=auth_headers(user))

    response = await client.patch(
        f"/api/v1/urls/{created['id']}",
        headers=auth_headers(user),
        json={"original_url": "https://example.com/deleted"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "URL not found"


@pytest.mark.asyncio
async def test_update_url_returns_409_for_duplicate_custom_alias(client, db_session):
    user = await create_user(db_session)
    first = await create_url(client, user, custom_alias="taken-alias")
    second = await create_url(client, user, custom_alias="second-alias")

    response = await client.patch(
        f"/api/v1/urls/{second['id']}",
        headers=auth_headers(user),
        json={"custom_alias": first["short_code"]},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Short code already exists"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"original_url": "not-a-url"},
        {"original_url": None},
        {"custom_alias": None},
        {"custom_alias": "api"},
        {"custom_alias": "bad alias"},
        {"expires_at": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()},
    ],
)
async def test_update_url_rejects_invalid_payloads(client, db_session, payload):
    user = await create_user(db_session)
    created = await create_url(client, user)

    response = await client.patch(
        f"/api/v1/urls/{created['id']}",
        headers=auth_headers(user),
        json=payload,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_url_with_custom_alias_redirects_using_alias(client, db_session):
    user = await create_user(db_session)

    created = await create_url(client, user, custom_alias="my-link_123")

    assert created["short_code"] == "my-link_123"
    assert created["short_url"].endswith("/my-link_123")

    redirect_response = await client.get("/my-link_123", follow_redirects=False)
    assert redirect_response.status_code == 302
    assert redirect_response.headers["location"] == "https://example.com/page"


@pytest.mark.asyncio
async def test_create_url_with_future_expiration_date(client, db_session):
    user = await create_user(db_session)
    expires_at = datetime.now(timezone.utc) + timedelta(days=1)

    created = await create_url(client, user, expires_at=expires_at)

    assert created["expires_at"] is not None
    assert created["expires_at"].startswith(expires_at.date().isoformat())

    redirect_response = await client.get(f"/{created['short_code']}", follow_redirects=False)
    assert redirect_response.status_code == 302

    list_response = await client.get("/api/v1/urls", headers=auth_headers(user))
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["expires_at"] == created["expires_at"]


@pytest.mark.asyncio
async def test_create_url_rejects_past_expiration_date(client, db_session):
    user = await create_user(db_session)

    response = await client.post(
        "/api/v1/urls",
        headers=auth_headers(user),
        json={
            "original_url": "https://example.com",
            "expires_at": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_expired_url_returns_404_and_stays_listed(client, db_session):
    user = await create_user(db_session)
    created = await create_url(
        client,
        user,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    url = await db_session.get(Url, created["id"])
    url.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db_session.commit()

    redirect_response = await client.get(f"/{created['short_code']}", follow_redirects=False)
    assert redirect_response.status_code == 404
    assert redirect_response.json()["detail"] == "URL not found"

    await db_session.refresh(url)
    assert url.click_count == 0

    list_response = await client.get("/api/v1/urls", headers=auth_headers(user))
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1
    assert list_response.json()["items"][0]["expires_at"] is not None


@pytest.mark.asyncio
async def test_duplicate_custom_alias_returns_409(client, db_session):
    user = await create_user(db_session)
    other_user = await create_user(
        db_session, email="other@example.com", user_name="other_user"
    )
    await create_url(client, user, custom_alias="shared-alias")

    response = await client.post(
        "/api/v1/urls",
        headers=auth_headers(other_user),
        json={
            "original_url": "https://example.com/other",
            "custom_alias": "shared-alias",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Short code already exists"


@pytest.mark.asyncio
async def test_soft_deleted_custom_alias_cannot_be_reused(client, db_session):
    user = await create_user(db_session)
    created = await create_url(client, user, custom_alias="keep-reserved")

    delete_response = await client.delete(
        f"/api/v1/urls/{created['id']}", headers=auth_headers(user)
    )
    assert delete_response.status_code == 200

    response = await client.post(
        "/api/v1/urls",
        headers=auth_headers(user),
        json={
            "original_url": "https://example.com/reuse",
            "custom_alias": "keep-reserved",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Short code already exists"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "custom_alias",
    ["api", "docs", "bad alias", "bad.alias", "ab", ""],
)
async def test_create_url_rejects_invalid_or_reserved_custom_alias(
    client, db_session, custom_alias
):
    user = await create_user(db_session)

    response = await client.post(
        "/api/v1/urls",
        headers=auth_headers(user),
        json={"original_url": "https://example.com", "custom_alias": custom_alias},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_url_status_disables_and_activates_url(client, db_session):
    user = await create_user(db_session)
    created = await create_url(client, user)

    disable_response = await client.patch(
        f"/api/v1/urls/{created['id']}/status",
        headers=auth_headers(user),
        json={"is_active": False},
    )
    assert disable_response.status_code == 200
    assert disable_response.json() == {"message": "URL disabled successfully"}

    redirect_response = await client.get(f"/{created['short_code']}", follow_redirects=False)
    assert redirect_response.status_code == 404
    assert redirect_response.json()["detail"] == "URL not found"

    list_response = await client.get("/api/v1/urls", headers=auth_headers(user))
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1
    assert list_response.json()["items"][0]["is_active"] is False

    url = await db_session.get(Url, created["id"])
    await db_session.refresh(url)
    assert url.is_active is False
    assert url.deleted_at is None

    activate_response = await client.patch(
        f"/api/v1/urls/{created['id']}/status",
        headers=auth_headers(user),
        json={"is_active": True},
    )
    assert activate_response.status_code == 200
    assert activate_response.json() == {"message": "URL activated successfully"}

    redirect_response = await client.get(f"/{created['short_code']}", follow_redirects=False)
    assert redirect_response.status_code == 302
    assert redirect_response.headers["location"] == "https://example.com/page"


@pytest.mark.asyncio
async def test_delete_url_soft_deletes_and_hides_it(client, db_session):
    user = await create_user(db_session)
    created = await create_url(client, user)

    delete_response = await client.delete(
        f"/api/v1/urls/{created['id']}", headers=auth_headers(user)
    )
    assert delete_response.status_code == 200
    assert delete_response.json() == {"message": "URL deleted successfully"}

    list_response = await client.get("/api/v1/urls", headers=auth_headers(user))
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 0

    redirect_response = await client.get(f"/{created['short_code']}", follow_redirects=False)
    assert redirect_response.status_code == 404

    url = await db_session.get(Url, created["id"])
    await db_session.refresh(url)
    assert url.is_active is False
    assert url.deleted_at is not None


@pytest.mark.asyncio
async def test_url_endpoints_require_authentication(client):
    create_response = await client.post(
        "/api/v1/urls", json={"original_url": "https://example.com"}
    )
    assert create_response.status_code == 401

    list_response = await client.get("/api/v1/urls")
    assert list_response.status_code == 401

    get_response = await client.get("/api/v1/urls/1")
    assert get_response.status_code == 401

    update_response = await client.patch(
        "/api/v1/urls/1",
        json={"original_url": "https://example.com/updated"},
    )
    assert update_response.status_code == 401

    status_response = await client.patch("/api/v1/urls/1/status", json={"is_active": False})
    assert status_response.status_code == 401

    delete_response = await client.delete("/api/v1/urls/1")
    assert delete_response.status_code == 401


@pytest.mark.asyncio
async def test_url_endpoints_reject_unverified_user_token(client, db_session):
    user = await create_user(
        db_session,
        email="unverified@example.com",
        user_name="unverified_user",
        is_email_verified=False,
    )

    response = await client.post(
        "/api/v1/urls",
        headers=auth_headers(user),
        json={"original_url": "https://example.com"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Verify your email before continuing"


@pytest.mark.asyncio
async def test_user_cannot_update_status_or_delete_another_users_url(client, db_session):
    owner = await create_user(db_session)
    other_user = await create_user(
        db_session, email="other@example.com", user_name="other_user"
    )
    created = await create_url(client, owner)

    disable_response = await client.patch(
        f"/api/v1/urls/{created['id']}/status",
        headers=auth_headers(other_user),
        json={"is_active": False},
    )
    assert disable_response.status_code == 404
    assert disable_response.json()["detail"] == "URL not found"

    delete_response = await client.delete(
        f"/api/v1/urls/{created['id']}", headers=auth_headers(other_user)
    )
    assert delete_response.status_code == 404
    assert delete_response.json()["detail"] == "URL not found"

    redirect_response = await client.get(f"/{created['short_code']}", follow_redirects=False)
    assert redirect_response.status_code == 302


@pytest.mark.asyncio
async def test_deleted_url_cannot_be_activated(client, db_session):
    user = await create_user(db_session)
    created = await create_url(client, user)

    delete_response = await client.delete(
        f"/api/v1/urls/{created['id']}", headers=auth_headers(user)
    )
    assert delete_response.status_code == 200

    activate_response = await client.patch(
        f"/api/v1/urls/{created['id']}/status",
        headers=auth_headers(user),
        json={"is_active": True},
    )
    assert activate_response.status_code == 404
    assert activate_response.json()["detail"] == "URL not found"


@pytest.mark.asyncio
async def test_create_url_validates_original_url(client, db_session):
    user = await create_user(db_session)

    response = await client.post(
        "/api/v1/urls",
        headers=auth_headers(user),
        json={"original_url": "not-a-url"},
    )

    assert response.status_code == 422
