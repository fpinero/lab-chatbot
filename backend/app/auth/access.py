import jwt
from jwt import PyJWKClient

from app.config import Settings


class AccessVerifier:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.jwks = PyJWKClient(
            f"{settings.access_issuer}/cdn-cgi/access/certs",
            cache_keys=False,
            lifespan=300,
            timeout=5,
        )

    def verify(self, token: str) -> bool:
        if not token or len(token) > 16384:
            return False
        try:
            key = self.jwks.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                key.key,
                algorithms=["RS256"],
                audience=self.settings.access_audience,
                issuer=self.settings.access_issuer,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
            return claims.get("sub") == self.settings.access_owner_subject
        except (jwt.PyJWTError, ValueError):
            return False
