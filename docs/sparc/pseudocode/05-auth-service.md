# Pseudocode: Authentication Service

**SPARC Phase**: Pseudocode
**Module**: `v3/src/services/auth_service.py`
**Implements**: FUT-001 to FUT-006 (Platform-Agnostic Auth)

---

## 1. Service Interface

```pseudocode
SERVICE AuthService:
    DEPENDENCIES:
        user_repo: UserRepository
        workspace_repo: WorkspaceRepository
        token_service: TokenService
        oauth_providers: Dict<AuthProvider, OAuthAdapter>
        event_bus: EventBus

    CONFIG:
        access_token_ttl: Integer = 3600       # 1 hour
        refresh_token_ttl: Integer = 2592000   # 30 days
        session_ttl: Integer = 86400           # 24 hours
```

## 2. OAuth Flow

```pseudocode
FUNCTION get_oauth_url(provider: AuthProvider, redirect_uri: String, state: String) -> String:
    """Generate OAuth authorization URL."""

    adapter = oauth_providers.get(provider)
    IF adapter IS NULL:
        RAISE UnsupportedProviderError(provider)

    RETURN adapter.get_authorization_url(
        redirect_uri=redirect_uri,
        state=state,
        scopes=get_scopes_for_provider(provider)
    )


ASYNC FUNCTION handle_oauth_callback(
    provider: AuthProvider,
    code: String,
    state: String
) -> AuthResult:
    """Handle OAuth callback and authenticate user."""

    # Step 1: Validate state (CSRF protection)
    IF NOT validate_state(state):
        RAISE InvalidStateError()

    # Step 2: Exchange code for tokens
    adapter = oauth_providers.get(provider)
    TRY:
        oauth_tokens = AWAIT adapter.exchange_code(code)
    CATCH OAuthError as e:
        RAISE AuthenticationFailedError(f"OAuth exchange failed: {e}")

    # Step 3: Get user info from provider
    provider_user = AWAIT adapter.get_user_info(oauth_tokens.access_token)

    # Step 4: Find or create user
    user = AWAIT find_or_create_user(provider, provider_user)

    # Step 5: Get accessible workspaces
    workspaces = AWAIT get_user_workspaces(user, provider, oauth_tokens)

    # Step 6: Generate tokens
    access_token = token_service.create_access_token(user, workspaces)
    refresh_token = token_service.create_refresh_token(user)

    # Step 7: Store refresh token
    AWAIT token_service.store_refresh_token(user.id, refresh_token, oauth_tokens)

    # Step 8: Emit event
    AWAIT event_bus.publish(UserAuthenticated(
        user_id=user.id,
        provider=provider,
        timestamp=NOW()
    ))

    RETURN AuthResult(
        user=user,
        workspaces=workspaces,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=access_token_ttl
    )
```

## 3. User Management

```pseudocode
ASYNC FUNCTION find_or_create_user(
    provider: AuthProvider,
    provider_user: ProviderUserInfo
) -> User:
    """Find existing user or create new one."""

    # Try to find by provider identity
    user = AWAIT user_repo.get_by_identity(provider, provider_user.id)

    IF user IS NOT NULL:
        # Update user info from provider
        user.name = provider_user.name OR user.name
        user.avatar_url = provider_user.avatar_url OR user.avatar_url
        user.last_login_at = NOW()
        AWAIT user_repo.save(user)
        RETURN user

    # Try to find by email (for linking accounts)
    IF provider_user.email IS NOT NULL:
        user = AWAIT user_repo.get_by_email(provider_user.email)
        IF user IS NOT NULL:
            # Link new identity to existing user
            user.add_identity(provider, provider_user.id, {
                username: provider_user.username,
                avatar_url: provider_user.avatar_url
            })
            user.last_login_at = NOW()
            AWAIT user_repo.save(user)

            AWAIT event_bus.publish(IdentityLinked(
                user_id=user.id,
                provider=provider,
                provider_id=provider_user.id
            ))

            RETURN user

    # Create new user
    user = User(
        id=generate_uuid(),
        name=provider_user.name OR provider_user.username,
        email=provider_user.email,
        avatar_url=provider_user.avatar_url,
        identities=[
            UserIdentity(
                provider=provider,
                provider_id=provider_user.id,
                provider_username=provider_user.username,
                metadata={avatar_url: provider_user.avatar_url},
                linked_at=NOW()
            )
        ],
        created_at=NOW()
    )

    AWAIT user_repo.save(user)

    AWAIT event_bus.publish(UserCreated(
        user_id=user.id,
        provider=provider,
        timestamp=NOW()
    ))

    RETURN user
```

## 4. Workspace Discovery

```pseudocode
ASYNC FUNCTION get_user_workspaces(
    user: User,
    provider: AuthProvider,
    oauth_tokens: OAuthTokens
) -> List<Workspace>:
    """Get workspaces accessible to user via provider."""

    # Step 1: Get existing workspaces user owns/has access to
    existing = AWAIT workspace_repo.get_by_user(user.id)

    # Step 2: Discover new workspaces from provider
    adapter = oauth_providers.get(provider)
    provider_workspaces = AWAIT adapter.get_user_workspaces(oauth_tokens.access_token)

    # Step 3: Create or update workspace connections
    workspaces = []

    FOR pw IN provider_workspaces:
        # Check if workspace already exists
        workspace = AWAIT workspace_repo.get_by_connection(provider, pw.id)

        IF workspace IS NULL:
            # Create new workspace
            workspace = Workspace(
                id=generate_uuid(),
                name=pw.name,
                owner_id=user.id,
                connections=[
                    PlatformConnection(
                        id=generate_uuid(),
                        platform=provider_to_platform(provider),
                        platform_id=pw.id,
                        platform_name=pw.name,
                        access_token=encrypt(oauth_tokens.access_token),
                        refresh_token=encrypt(oauth_tokens.refresh_token) IF oauth_tokens.refresh_token ELSE NULL,
                        token_expires_at=oauth_tokens.expires_at,
                        connected_at=NOW(),
                        connected_by=user.id
                    )
                ],
                created_at=NOW()
            )
            AWAIT workspace_repo.save(workspace)

            AWAIT event_bus.publish(WorkspaceCreated(
                workspace_id=workspace.id,
                platform=provider,
                platform_id=pw.id,
                owner_id=user.id
            ))
        ELSE:
            # Update connection tokens
            connection = workspace.get_connection(provider_to_platform(provider))
            IF connection:
                connection.access_token = encrypt(oauth_tokens.access_token)
                IF oauth_tokens.refresh_token:
                    connection.refresh_token = encrypt(oauth_tokens.refresh_token)
                connection.token_expires_at = oauth_tokens.expires_at
                AWAIT workspace_repo.save(workspace)

        workspaces.append(workspace)

    RETURN workspaces
```

## 5. Token Management

```pseudocode
SERVICE TokenService:
    DEPENDENCIES:
        token_repo: RefreshTokenRepository
        secret_key: String
        encryption_key: String

    FUNCTION create_access_token(user: User, workspaces: List<Workspace>) -> String:
        """Create JWT access token."""

        payload = {
            sub: user.id,
            name: user.name,
            email: user.email,
            workspaces: [w.id FOR w IN workspaces],
            iat: NOW().timestamp(),
            exp: (NOW() + access_token_ttl.seconds).timestamp()
        }

        RETURN jwt.encode(payload, secret_key, algorithm="HS256")


    FUNCTION create_refresh_token(user: User) -> String:
        """Create opaque refresh token."""
        RETURN generate_secure_token(32)


    ASYNC FUNCTION store_refresh_token(
        user_id: UUID,
        refresh_token: String,
        oauth_tokens: Optional<OAuthTokens>
    ):
        """Store refresh token with associated OAuth tokens."""

        hashed = hash_token(refresh_token)
        AWAIT token_repo.save(RefreshTokenRecord(
            token_hash=hashed,
            user_id=user_id,
            oauth_access_token=encrypt(oauth_tokens.access_token) IF oauth_tokens ELSE NULL,
            oauth_refresh_token=encrypt(oauth_tokens.refresh_token) IF oauth_tokens ELSE NULL,
            oauth_expires_at=oauth_tokens.expires_at IF oauth_tokens ELSE NULL,
            created_at=NOW(),
            expires_at=NOW() + refresh_token_ttl.seconds
        ))


    ASYNC FUNCTION refresh(refresh_token: String) -> AuthResult:
        """Refresh access token using refresh token."""

        hashed = hash_token(refresh_token)
        record = AWAIT token_repo.get_by_hash(hashed)

        IF record IS NULL:
            RAISE InvalidRefreshTokenError()

        IF record.expires_at < NOW():
            AWAIT token_repo.delete(hashed)
            RAISE RefreshTokenExpiredError()

        # Get user and workspaces
        user = AWAIT user_repo.get_by_id(record.user_id)
        IF user IS NULL:
            RAISE UserNotFoundError()

        workspaces = AWAIT workspace_repo.get_by_user(user.id)

        # Refresh OAuth tokens if needed
        IF record.oauth_expires_at AND record.oauth_expires_at < NOW():
            AWAIT refresh_oauth_tokens(record)

        # Generate new access token
        access_token = create_access_token(user, workspaces)

        RETURN AuthResult(
            user=user,
            workspaces=workspaces,
            access_token=access_token,
            refresh_token=refresh_token,  # Reuse
            expires_in=access_token_ttl
        )


    FUNCTION verify_access_token(token: String) -> TokenPayload:
        """Verify and decode access token."""

        TRY:
            payload = jwt.decode(token, secret_key, algorithms=["HS256"])
            RETURN TokenPayload(
                user_id=payload["sub"],
                name=payload["name"],
                email=payload.get("email"),
                workspace_ids=payload["workspaces"]
            )
        CATCH jwt.ExpiredSignatureError:
            RAISE AccessTokenExpiredError()
        CATCH jwt.InvalidTokenError:
            RAISE InvalidAccessTokenError()
```

## 6. Provider Adapters

```pseudocode
ABSTRACT CLASS OAuthAdapter:
    @abstractmethod
    FUNCTION get_authorization_url(redirect_uri, state, scopes) -> String

    @abstractmethod
    ASYNC FUNCTION exchange_code(code) -> OAuthTokens

    @abstractmethod
    ASYNC FUNCTION get_user_info(access_token) -> ProviderUserInfo

    @abstractmethod
    ASYNC FUNCTION get_user_workspaces(access_token) -> List<ProviderWorkspace>

    @abstractmethod
    ASYNC FUNCTION refresh_token(refresh_token) -> OAuthTokens


CLASS DiscordOAuthAdapter(OAuthAdapter):
    BASE_URL = "https://discord.com/api/v10"
    AUTH_URL = "https://discord.com/oauth2/authorize"
    TOKEN_URL = "https://discord.com/api/oauth2/token"

    FUNCTION get_authorization_url(redirect_uri, state, scopes) -> String:
        params = {
            client_id: self.client_id,
            redirect_uri: redirect_uri,
            response_type: "code",
            scope: " ".join(scopes),
            state: state
        }
        RETURN f"{AUTH_URL}?{urlencode(params)}"

    ASYNC FUNCTION get_user_workspaces(access_token) -> List<ProviderWorkspace>:
        # Get guilds user is member of
        guilds = AWAIT http.get(
            f"{BASE_URL}/users/@me/guilds",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        RETURN [
            ProviderWorkspace(
                id=g["id"],
                name=g["name"],
                icon_url=get_guild_icon_url(g)
            )
            FOR g IN guilds
            IF has_manage_permission(g["permissions"])
        ]


CLASS SlackOAuthAdapter(OAuthAdapter):
    # Similar implementation for Slack OAuth 2.0


CLASS GoogleOAuthAdapter(OAuthAdapter):
    # Similar implementation for Google OAuth 2.0
```

## 7. Permission Checking

```pseudocode
ASYNC FUNCTION check_workspace_access(
    user_id: UUID,
    workspace_id: UUID,
    required_permission: Permission = Permission.READ
) -> Boolean:
    """Check if user has access to workspace."""

    workspace = AWAIT workspace_repo.get_by_id(workspace_id)
    IF workspace IS NULL:
        RETURN FALSE

    # Owner has all permissions
    IF workspace.owner_id == user_id:
        RETURN TRUE

    # Check membership
    membership = AWAIT workspace_repo.get_membership(workspace_id, user_id)
    IF membership IS NULL:
        RETURN FALSE

    RETURN membership.has_permission(required_permission)


FUNCTION require_workspace_access(required_permission: Permission):
    """Decorator for route handlers requiring workspace access."""

    FUNCTION decorator(handler):
        ASYNC FUNCTION wrapper(request, workspace_id, *args, **kwargs):
            user = get_current_user(request)
            IF NOT AWAIT check_workspace_access(user.id, workspace_id, required_permission):
                RAISE ForbiddenError(f"No {required_permission} access to workspace")
            RETURN AWAIT handler(request, workspace_id, *args, **kwargs)
        RETURN wrapper
    RETURN decorator
```

---

*Next: `06-delivery-adapters.md`*
