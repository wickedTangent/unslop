"""User service — business logic for user CRUD operations."""

import logging

logger = logging.getLogger(__name__)


class UserService:
    """Manage user lifecycle: create, read, update, delete, search."""

    def __init__(self, db, cache_ttl: int = 300) -> None:
        self.db = db
        self._cache: Dict[str, dict] = {}
        self._cache_ttl = cache_ttl

    def find_user_by_id(self, user_id: str) -> Optional[dict]:
        """Return a single user by ID, cached for up to 5 minutes."""
        cached = self._cache.get(user_id)
        if cached:
            return cached

        user = self.db.fetch_one(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        )
        if user:
            self._cache[user_id] = self._normalize_user(user)
        return self._cache.get(user_id)

    def list_users(self, *, page: int = 1, page_size: int = 50) -> list[dict]:
        """Return a page of users."""
        offset = (page - 1) * page_size
        rows = self.db.fetch_all(
            "SELECT * FROM users LIMIT ? OFFSET ?", (page_size, offset)
        )
        return [self._normalize_user(row) for row in rows]

    def create_user(self, username: str, email: str, password: str) -> dict:
        """Create a new user. Raises ValueError on invalid input."""
        if not username or not email or not password:
            raise ValueError("username, email, and password are required")

        user_id = self.db.insert(
            "INSERT INTO users (id, username, email, password_hash) VALUES (?, ?, ?, ?)",
            (str(self.db.gen_uuid()), username, email, self._hash_password(password)),
        )
        return {"id": user_id, "username": username, "email": email}

    def update_user(self, user_id: str, updates: dict) -> dict:
        """Update specific fields on an existing user."""
        if not updates:
            raise ValueError("No fields to update")

        allowed_fields = {"username", "email", "password"}
        fields_to_update = {k: v for k, v in updates.items() if k in allowed_fields}

        if not fields_to_update:
            raise ValueError(f"No valid fields to update. Allowed: {allowed_fields}")

        set_clause = ", ".join(f"{k} = ?" for k in fields_to_update)
        values = list(fields_to_update.values()) + [user_id]

        self.db.execute(f"UPDATE users SET {set_clause} WHERE id = ?", values)
        self._cache.pop(user_id, None)  # Invalidate stale cache entry

        return {"updated": True}

    def delete_user(self, user_id: str) -> bool:
        """Delete a user. Returns True on success."""
        self.db.execute("DELETE FROM users WHERE id = ?", (user_id,))
        self._cache.pop(user_id, None)
        return True

    def search_users(self, term: str) -> list[dict]:
        """Search users by username or email (case-insensitive)."""
        pattern = f"%{term}%"
        rows = self.db.fetch_all(
            "SELECT * FROM users WHERE username LIKE ? OR email LIKE ?",
            (pattern, pattern),
        )
        return [self._normalize_user(row) for row in rows]

    def user_stats(self, user_id: str) -> dict | None:
        """Return login statistics for a user."""
        user = self.find_user_by_id(user_id)
        if not user:
            return None

        return {
            "user_id": user_id,
            "total_logins": user.get("login_count", 0),
            "last_login": user.get("last_login"),
            "status": "active",
        }

    def _normalize_user(self, row: dict) -> dict:
        """Strip whitespace from string fields in a user row."""
        return {
            key: value.strip() if isinstance(value, str) else value
            for key, value in row.items()
        }

    def _hash_password(self, password: str) -> str:
        """Hash a password using SHA-256."""
        return self.db.hash_value(password)
