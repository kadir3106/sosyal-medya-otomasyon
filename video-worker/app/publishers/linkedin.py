import os

from app.http_client import session

TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
INITIALIZE_URL = "https://api.linkedin.com/rest/images"
POSTS_URL = "https://api.linkedin.com/rest/posts"


def upload_to_linkedin(
    image_path: str,
    caption: str,
    client_id: str,
    client_secret: str,
    refresh_token: str,
    author_urn: str,
) -> dict:
    """LinkedIn'e görselli gönderi atar (personal veya organization author)."""
    try:
        access_token = _get_access_token(client_id, client_secret, refresh_token)

        init_response = session.post(
            f"{INITIALIZE_URL}?action=initializeUpload",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "LinkedIn-Version": "202409",
            },
            json={"initializeUploadRequest": {"owner": author_urn}},
            timeout=30,
        )
        init_response.raise_for_status()
        init_data = init_response.json()["value"]
        upload_url = init_data["uploadUrl"]
        image_urn = init_data["image"]

        with open(image_path, "rb") as image_file:
            put_response = session.put(
                upload_url,
                headers={"Content-Type": "image/png"},
                data=image_file.read(),
                timeout=120,
            )
        put_response.raise_for_status()

        post_response = session.post(
            POSTS_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "LinkedIn-Version": "202409",
            },
            json={
                "author": author_urn,
                "commentary": caption,
                "visibility": "PUBLIC",
                "distribution": {
                    "feedDistribution": "MAIN_FEED",
                    "targetEntities": [],
                    "thirdPartyDistributionChannels": [],
                },
                "content": {"media": {"id": image_urn}},
                "lifecycleState": "PUBLISHED",
                "isReshareDisabledByAuthor": False,
            },
            timeout=30,
        )
        post_response.raise_for_status()
        post_urn = post_response.headers.get("x-restli-id") or ""

        return {
            "platform": "linkedin",
            "status": "success",
            "post_id": post_urn,
        }
    except Exception as exc:
        return {"platform": "linkedin", "status": "error", "error": str(exc)}


def _get_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    response = session.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["access_token"]
