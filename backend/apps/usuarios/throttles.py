import hashlib

from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle


class LoginIPRateThrottle(AnonRateThrottle):
    scope = "login_ip"


class LoginEmailRateThrottle(SimpleRateThrottle):
    scope = "login_email"

    def get_cache_key(self, request, view):
        email = str(
            request.data.get("email", "")
        ).strip().lower()

        if not email:
            return None

        email_hash = hashlib.sha256(
            email.encode("utf-8")
        ).hexdigest()

        return self.cache_format % {
            "scope": self.scope,
            "ident": email_hash,
        }


class RefreshIPRateThrottle(AnonRateThrottle):
    scope = "refresh_ip"