import pytest

from transcribr.attribution.names import NameHit, find_name, opening


def said(start: float, text: str, gap: float = 0.4) -> list[tuple[float, str]]:
    """Words of `text`, one every `gap` seconds from `start`."""
    return [(start + n * gap, word) for n, word in enumerate(text.split())]


def hit(words: list[tuple[float, str]], *variants: str) -> NameHit | None:
    return find_name(opening(words), variants)


def test_name_in_greeting() -> None:
    words = said(0.5, "Thanks for calling Tire Pros, this is Nolan.")
    found = hit(words, "Nolan")
    assert found is not None and (found.variant, found.heard) == ("Nolan", "Nolan.")
    assert found.at_s == pytest.approx(0.5 + 7 * 0.4)


def test_name_only_late_in_the_call() -> None:
    words = said(0.0, "Tire Pros, how can I help?") + said(31.0, "ask Nolan about it")
    assert hit(words, "Nolan") is None


def test_the_opening_is_measured_from_the_first_word() -> None:
    words = said(20.0, "hello") + said(49.0, "this is Nolan")  # 29 s after the first word
    found = hit(words, "Nolan")
    assert found is not None and found.at_s == pytest.approx(49.8)


@pytest.mark.parametrize(
    ("transcript", "variant"),
    [
        ("this is Jose", "José"),
        ("this is José", "Jose"),
        ("this is Renée", "renee"),
    ],
)
def test_accents_and_case_dont_matter(transcript: str, variant: str) -> None:
    assert hit(said(0.0, transcript), variant) is not None


@pytest.mark.parametrize(
    ("transcript", "variant"),
    [
        ("this is Cristopher", "Christopher"),  # a dropped letter
        ("this is Christophe", "Christopher"),
        ("Nolan's desk, Tire Pros", "Nolan"),  # possessive
        ("this is Mary-Ann", "Mary Ann"),  # two words
    ],
)
def test_small_spelling_differences_still_match(transcript: str, variant: str) -> None:
    assert hit(said(0.0, transcript), variant) is not None


@pytest.mark.parametrize(
    ("transcript", "variant"),
    [
        ("this is Noah", "Nolan"),
        ("I need tires", "Nolan"),
        ("this is Nolen", "Nolan"),  # a different 5-letter name: list "Nolen" as a variant
    ],
)
def test_other_words_dont_match(transcript: str, variant: str) -> None:
    assert hit(said(0.0, transcript), variant) is None


def test_the_earliest_mention_wins_across_variants() -> None:
    words = said(0.0, "Nolen here, yes this is Nolan")
    found = hit(words, "Nolan", "Nolen")
    assert found is not None and (found.variant, found.at_s) == ("Nolen", 0.0)


def test_a_call_without_words_has_no_name() -> None:
    assert hit([], "Nolan") is None
    assert hit(said(0.0, "this is Nolan"), "   ", "--") is None
