"""People profiles: a display name and the name variants the transcript might contain.

Deleting a profile deletes its name variants, voice samples and every attribution to it
(the database cascades), so its calls fall back to Unassigned unless someone else is on them.
"""

import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

from transcribr.attribution.names import normalize
from transcribr.store.db import transaction
from transcribr.timeutil import to_iso, utcnow

MAX_NAME_LENGTH = 80


class ProfileError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Profile:
    id: int
    display_name: str
    variants: tuple[str, ...]
    created_at: str


def _clean_name(display_name: str) -> str:
    name = display_name.strip()
    if not name:
        raise ProfileError("name_required", "Enter the person's name.")
    if len(name) > MAX_NAME_LENGTH:
        raise ProfileError("name_too_long", f"Keep the name under {MAX_NAME_LENGTH} characters.")
    return name


def _clean_variants(variants: Sequence[str]) -> list[tuple[str, str]]:
    """(variant, normalized) pairs, without duplicates that normalize the same."""
    cleaned: list[tuple[str, str]] = []
    for raw in variants:
        variant = raw.strip()
        if not variant:
            continue
        if len(variant) > MAX_NAME_LENGTH:
            raise ProfileError(
                "variant_too_long", f"Keep each name variant under {MAX_NAME_LENGTH} characters."
            )
        normalized = normalize(variant)
        if not normalized:
            raise ProfileError(
                "variant_without_letters", f"The name variant {variant!r} has no letters in it."
            )
        if all(normalized != n for _, n in cleaned):
            cleaned.append((variant, normalized))
    if not cleaned:
        raise ProfileError(
            "variant_required", "Add at least one way the name might appear in a transcript."
        )
    return cleaned


class Profiles:
    def __init__(self, conn: sqlite3.Connection, *, now: Callable[[], datetime] = utcnow) -> None:
        self._conn = conn
        self._now = now

    def everyone(self) -> list[Profile]:
        rows = self._conn.execute(
            "SELECT id FROM profiles ORDER BY display_name COLLATE NOCASE, id"
        ).fetchall()
        return [self._load(r["id"]) for r in rows]

    def get(self, profile_id: int) -> Profile:
        if not self.exists(profile_id):
            raise ProfileError("profile_not_found", "There is no such person.")
        return self._load(profile_id)

    def exists(self, profile_id: int) -> bool:
        row = self._conn.execute("SELECT 1 FROM profiles WHERE id = ?", (profile_id,)).fetchone()
        return row is not None

    def create(self, display_name: str, variants: Sequence[str]) -> Profile:
        name = _clean_name(display_name)
        cleaned = _clean_variants(variants)
        with transaction(self._conn):
            profile_id: int = self._conn.execute(
                "INSERT INTO profiles (display_name, created_at) VALUES (?, ?) RETURNING id",
                (name, to_iso(self._now())),
            ).fetchone()[0]
            self._set_variants(profile_id, cleaned)
        return self._load(profile_id)

    def update(self, profile_id: int, display_name: str, variants: Sequence[str]) -> Profile:
        """Rename the person and replace their name variants."""
        name = _clean_name(display_name)
        cleaned = _clean_variants(variants)
        with transaction(self._conn):
            if not self._conn.execute(
                "UPDATE profiles SET display_name = ? WHERE id = ?", (name, profile_id)
            ).rowcount:
                raise ProfileError("profile_not_found", "There is no such person.")
            self._conn.execute("DELETE FROM name_variants WHERE profile_id = ?", (profile_id,))
            self._set_variants(profile_id, cleaned)
        return self._load(profile_id)

    def delete(self, profile_id: int) -> None:
        with transaction(self._conn):
            if not self._conn.execute("DELETE FROM profiles WHERE id = ?", (profile_id,)).rowcount:
                raise ProfileError("profile_not_found", "There is no such person.")

    def _set_variants(self, profile_id: int, cleaned: Sequence[tuple[str, str]]) -> None:
        self._conn.executemany(
            "INSERT INTO name_variants (profile_id, variant, normalized) VALUES (?, ?, ?)",
            [(profile_id, variant, normalized) for variant, normalized in cleaned],
        )

    def _load(self, profile_id: int) -> Profile:
        row = self._conn.execute(
            "SELECT id, display_name, created_at FROM profiles WHERE id = ?", (profile_id,)
        ).fetchone()
        variants = tuple(
            r["variant"]
            for r in self._conn.execute(
                "SELECT variant FROM name_variants WHERE profile_id = ? ORDER BY id", (profile_id,)
            )
        )
        return Profile(row["id"], row["display_name"], variants, row["created_at"])
