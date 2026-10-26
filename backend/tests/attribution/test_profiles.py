import sqlite3

import pytest

from tests.attribution.conftest import add_call
from tests.clock import FakeClock
from transcribr.attribution.names import normalize
from transcribr.attribution.profiles import ProfileError, Profiles


@pytest.fixture
def profiles(conn: sqlite3.Connection) -> Profiles:
    return Profiles(conn, now=FakeClock().utcnow)


def attribute(conn: sqlite3.Connection, call_id: int, profile_id: int, source: str) -> None:
    conn.execute(
        "INSERT INTO attributions (call_id, profile_id, status, source, method, updated_at)"
        " VALUES (?, ?, 'confident', ?, ?, 't')",
        (call_id, profile_id, source, "manual" if source == "manual" else "name"),
    )


@pytest.mark.parametrize(
    ("raw", "normalized"),
    [
        ("Nolan", "nolan"),
        ("  NOLEN. ", "nolen"),
        ("José", "jose"),
        ("Mary-Ann", "mary ann"),
        ("O'Brien", "o brien"),
        ("!!!", ""),
    ],
)
def test_names_are_compared_without_case_accents_or_punctuation(raw: str, normalized: str) -> None:
    assert normalize(raw) == normalized


def test_create_a_profile(profiles: Profiles) -> None:
    nolan = profiles.create("Nolan", ["Nolan", "Nolen"])
    assert (nolan.display_name, nolan.variants) == ("Nolan", ("Nolan", "Nolen"))
    assert nolan.created_at == "2026-10-22T14:00:00Z"
    profiles.create("dana", ["Dana"])
    assert [p.display_name for p in profiles.everyone()] == ["dana", "Nolan"]
    assert profiles.get(nolan.id) == nolan


def test_variants_that_read_the_same_are_kept_once(profiles: Profiles) -> None:
    nolan = profiles.create(" Nolan ", ["Nolan", "nolan", "NOLAN!", " ", "Nolen"])
    assert (nolan.display_name, nolan.variants) == ("Nolan", ("Nolan", "Nolen"))


@pytest.mark.parametrize(
    ("name", "variants", "code"),
    [
        ("  ", ["Nolan"], "name_required"),
        ("x" * 81, ["Nolan"], "name_too_long"),
        ("Nolan", [], "variant_required"),
        ("Nolan", ["  "], "variant_required"),
        ("Nolan", ["--"], "variant_without_letters"),
        ("Nolan", ["n" * 81], "variant_too_long"),
    ],
)
def test_bad_profiles_are_refused(
    profiles: Profiles, name: str, variants: list[str], code: str
) -> None:
    with pytest.raises(ProfileError) as refused:
        profiles.create(name, variants)
    assert refused.value.code == code
    assert profiles.everyone() == []


def test_edit_renames_and_replaces_the_variants(profiles: Profiles) -> None:
    nolan = profiles.create("Nolan", ["Nolan"])
    edited = profiles.update(nolan.id, "Nolan B.", ["Nolan", "Nolen", "Nole"])
    assert (edited.display_name, edited.variants) == ("Nolan B.", ("Nolan", "Nolen", "Nole"))
    with pytest.raises(ProfileError):
        profiles.update(nolan.id, "Nolan", [])
    assert profiles.get(nolan.id) == edited  # a refused edit changes nothing


def test_unknown_profiles(profiles: Profiles) -> None:
    for action in (
        lambda: profiles.get(999),
        lambda: profiles.update(999, "X", ["X"]),
        lambda: profiles.delete(999),
    ):
        with pytest.raises(ProfileError) as refused:
            action()
        assert refused.value.code == "profile_not_found"


def test_delete_a_profile(conn: sqlite3.Connection, profiles: Profiles) -> None:
    nolan = profiles.create("Nolan", ["Nolan"])
    dana = profiles.create("Dana", ["Dana"])
    add_call(conn, 1, [(0.0, 5.0, None)])
    add_call(conn, 2, [(0.0, 5.0, None)])
    attribute(conn, 1, nolan.id, "auto")  # only Nolan: becomes Unassigned
    attribute(conn, 2, nolan.id, "manual")
    attribute(conn, 2, dana.id, "auto")  # Dana stays on call 2

    profiles.delete(nolan.id)

    assert [p.display_name for p in profiles.everyone()] == ["Dana"]
    rows = conn.execute("SELECT call_id, profile_id FROM attributions").fetchall()
    assert [tuple(r) for r in rows] == [(2, dana.id)]
    assert conn.execute("SELECT count(*) FROM name_variants").fetchone()[0] == 1
