from rest_framework_simplejwt.authentication import JWTAuthentication
from django.conf import settings
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from django.contrib.auth import get_user_model

User = get_user_model()

class CookieJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        # First try to get token from Authorization header
        auth_header = request.META.get('HTTP_AUTHORIZATION')
        if auth_header and auth_header.startswith('Bearer '):
            raw_token = auth_header.split(' ')[1]
            try:
                validated_token = self.get_validated_token(raw_token)
                user = self.get_user(validated_token)
                
                # Check if user exists and is active
                if not user or not user.is_active:
                    return None
                    
                return user, validated_token
            except (InvalidToken, TokenError) as e:
                print(f"JWT Token validation error from header: {e}")
                # Fall through to cookie authentication
        
        # Fallback to cookie authentication
        cookie_name = settings.SIMPLE_JWT.get("AUTH_COOKIE", "access_token")
        raw_token = request.COOKIES.get(cookie_name)

        if raw_token is None:
            return None
        
        try:
            validated_token = self.get_validated_token(raw_token)
            user = self.get_user(validated_token)
            
            # Check if user exists and is active
            if not user or not user.is_active:
                return None
                
            return user, validated_token
        except (InvalidToken, TokenError) as e:
            print(f"JWT Token validation error from cookie: {e}")
            return None
        except Exception as e:
            print(f"Unexpected error in JWT authentication: {e}")
            return None 