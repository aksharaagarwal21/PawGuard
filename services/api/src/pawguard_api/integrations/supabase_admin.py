"""Server-side Supabase Auth admin calls (user provisioning). Uses the secret key; never import from web code."""

from uuid import UUID

import httpx

from pawguard_api.settings import Settings


class AuthAdminError(RuntimeError):
    pass


class SupabaseAuthAdmin:
    def __init__(self, settings: Settings) -> None:
        if settings.supabase_secret_key is None:
            raise AuthAdminError("PAWGUARD_SUPABASE_SECRET_KEY is required for user provisioning")
        self._base = settings.supabase_url.rstrip("/") + "/auth/v1/admin"
        self._headers = {"apikey": settings.supabase_secret_key.get_secret_value()}

    def find_user_id(self, email: str) -> UUID | None:
        page = 1
        while True:
            r = httpx.get(f"{self._base}/users", params={"page": page, "per_page": 200},
                          headers=self._headers, timeout=10)
            if r.status_code != 200:
                raise AuthAdminError(f"listing users failed: HTTP {r.status_code}")
            users = r.json().get("users", [])
            for u in users:
                if (u.get("email") or "").lower() == email.lower():
                    return UUID(u["id"])
            if len(users) < 200:
                return None
            page += 1

    def ensure_user(self, email: str, password: str, *, display_name: str | None = None) -> UUID:
        existing = self.find_user_id(email)
        if existing:
            return existing
        r = httpx.post(f"{self._base}/users", headers=self._headers, timeout=10,
                       json={"email": email, "password": password, "email_confirm": True,
                             "user_metadata": {"display_name": display_name} if display_name else {}})
        if r.status_code not in (200, 201):
            # Do not echo the response body: it can contain the submitted email/password context.
            raise AuthAdminError(f"creating user failed: HTTP {r.status_code} ({r.json().get('error_code', '')})")
        return UUID(r.json()["id"])
