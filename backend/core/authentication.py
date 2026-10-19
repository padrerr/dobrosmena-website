import hashlib
from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from .models import AuthToken


class BearerAuthentication(BaseAuthentication):
    keyword = 'Bearer'

    def authenticate(self, request):
        header = request.headers.get('Authorization', '')
        if not header.startswith(self.keyword + ' '):
            return None
        raw = header[len(self.keyword) + 1:].strip()
        if not raw:
            raise AuthenticationFailed('Токен не указан.')
        token_hash = hashlib.sha256(raw.encode()).hexdigest()
        token = AuthToken.objects.select_related('user').filter(
            token_hash=token_hash,
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
            user__is_active=True,
        ).first()
        if not token:
            raise AuthenticationFailed('Недействительный или истёкший токен.')
        return (token.user, token)
