"""Shared fixtures for unslop tests."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


@pytest.fixture()
def tmp_repo(tmp_path: Path) -> Path:
    """Create a temporary git repository for testing.

    Returns:
        Path to the temporary repository root.
    """
    repo = tmp_path / "test_repo"
    repo.mkdir()

    # Initialize git repo
    import subprocess
    subprocess.run(["git", "init"], cwd=str(repo), capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(repo), capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(repo), capture_output=True, check=True)

    return repo


@pytest.fixture()
def tmp_file(tmp_path: Path) -> Path:
    """Create a temporary Python file for testing.

    Returns:
        Path to the temporary file.
    """
    return tmp_path / "test_file.py"


@pytest.fixture()
def tmp_ts_file(tmp_path: Path) -> Path:
    """Create a temporary TypeScript file for testing.

    Returns:
        Path to the temporary file.
    """
    return tmp_path / "test_file.ts"


@pytest.fixture()
def python_sloppy_file(tmp_path: Path) -> str:
    """Create a Python file with common AI slop patterns.

    Returns:
        Path to the temporary file.
    """
    content = '''"""User service module."""

import os
import sys
import json
import hashlib
import random
import uuid
from typing import List, Dict, Optional


class UserService:
    """Service for user operations."""

    def __init__(self, db):
        """Initialize the service."""
        self.db = db

    def get_user(self, user_id):
        """Get a user by ID."""
        # get the user from the database
        result = self.db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        # return the result
        return result

    def create_user(self, data):
        """Create a new user."""
        # create a new user object
        new_user = {"id": uuid.uuid4(), "data": data}
        # save to database
        self.db.execute("INSERT INTO users VALUES (?)", (new_user,))
        # return the created user
        return new_user

    def delete_user(self, user_id):
        """Delete a user."""
        try:
            self.db.execute("DELETE FROM users WHERE id = ?", (user_id,))
        except Exception:
            pass

    def process_batch(self, items):
        """Process a batch of items."""
        results = []
        for item in items:
            try:
                result = self.process_single(item)
                results.append(result)
            except Exception:
                pass
        return results

    def process_single(self, item):
        """Process a single item."""
        # validate the input
        if not item:
            return None
        # process the item
        processed = {"id": item.get("id"), "status": "done"}
        # return the processed item
        return processed

    def helper_function(self, data):
        """Helper function to process data."""
        # process the data
        result = {"processed": data}
        return result

    # TODO: add real authentication here
    # FIXME: this is broken
    def authenticate(self, user, password):
        """Authenticate a user."""
        # check if user exists
        user = self.get_user(user)
        if user:
            return True
        return None
'''
    path = tmp_path / "user_service.py"
    path.write_text(content, encoding="utf-8")
    return str(path)


@pytest.fixture()
def python_clean_file(tmp_path: Path) -> str:
    """Create a Python file with clean code patterns.

    Returns:
        Path to the temporary file.
    """
    content = '''"""User service module."""

from __future__ import annotations

from typing import Any


class UserNotFoundError(Exception):
    """Raised when a user is not found."""
    pass


class UserService:
    """Manage user operations."""

    def __init__(self, db: Any) -> None:
        self._db = db

    def get_user(self, user_id: int) -> dict | None:
        """Fetch a user by their ID."""
        return self._db.fetch_one("SELECT * FROM users WHERE id = ?", (user_id,))

    def create_user(self, data: dict) -> dict:
        """Persist a new user record."""
        user_id = self._db.insert("INSERT INTO users (data) VALUES (?)", (data,))
        return {"id": user_id, **data}

    def delete_user(self, user_id: int) -> None:
        """Remove a user record."""
        self._db.execute("DELETE FROM users WHERE id = ?", (user_id,))
'''
    path = tmp_path / "clean_service.py"
    path.write_text(content, encoding="utf-8")
    return str(path)


@pytest.fixture()
def ts_sloppy_file(tmp_path: Path) -> str:
    """Create a TypeScript file with common AI slop patterns.

    Returns:
        Path to the temporary file.
    """
    content = '''// User service module

import * as crypto from "crypto";
import * as fs from "fs";
import * as path from "path";
import { Logger } from "./logger";
import { Validator } from "./validator";

export class UserService {
    private logger: Logger;
    private validator: Validator;

    constructor(logger: Logger, validator: Validator) {
        // initialize the logger
        this.logger = logger;
        // initialize the validator
        this.validator = validator;
    }

    // get the user by ID
    getUser(userId: string): User | null {
        // find the user in the database
        const result = this.db.findUser(userId);
        // return the result
        return result;
    }

    // create a new user
    createUser(data: CreateUserInput): User {
        // validate the input
        const isValid = this.validator.validate(data);
        // create the user
        const newUser = { id: crypto.randomUUID(), ...data };
        // save to database
        this.db.saveUser(newUser);
        // return the created user
        return newUser;
    }

    deleteUser(userId: string): void {
        try {
            this.db.deleteUser(userId);
        } catch {
        }
    }

    // TODO: add rate limiting here
    // HACK: temporary workaround
    authenticate(user: string, password: string): boolean {
        // check if user exists
        const userObj = this.getUser(user);
        if (userObj) {
            return true;
        }
        return false;
    }
}
'''
    path = tmp_path / "user_service.ts"
    path.write_text(content, encoding="utf-8")
    return str(path)


@pytest.fixture()
def ts_clean_file(tmp_path: Path) -> str:
    """Create a TypeScript file with clean code patterns.

    Returns:
        Path to the temporary file.
    """
    content = '''/** User service module. */

import { Logger } from "./logger";
import { Validator } from "./validator";

export class UserService {
    private readonly logger: Logger;
    private readonly validator: Validator;

    constructor(logger: Logger, validator: Validator) {
        this.logger = logger;
        this.validator = validator;
    }

    getUser(userId: string): User | null {
        return this.db.findUser(userId);
    }

    createUser(data: CreateUserInput): User {
        this.validator.assertValid(data);
        const user: User = { id: crypto.randomUUID(), ...data };
        this.db.saveUser(user);
        return user;
    }

    deleteUser(userId: string): void {
        this.db.deleteUser(userId);
    }

    authenticate(username: string, password: string): boolean {
        const user = this.getUser(username);
        return user !== null && this.verifyPassword(user, password);
    }

    private verifyPassword(user: User, password: string): boolean {
        return user.passwordHash === hashPassword(password);
    }
}
'''
    path = tmp_path / "clean_service.ts"
    path.write_text(content, encoding="utf-8")
    return str(path)
