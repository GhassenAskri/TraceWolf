import pytest

from app.slugs import MAX_SLUG_LENGTH, is_slug, next_free_slug, slugify


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        ("Support Desk", "support-desk"),
        ("  My   Project!! ", "my-project"),
        ("Café Bot", "cafe-bot"),
        ("ÀÉÎ", "aei"),
        ("a/b", "a-b"),
        ("Under_score", "under-score"),
        ("Version 2.0", "version-2-0"),
        ("already-a-slug", "already-a-slug"),
        ("UPPER", "upper"),
        ("--edges--", "edges"),
        ("a  -  b", "a-b"),
    ],
)
def test_slugify(name, slug):
    assert slugify(name) == slug


@pytest.mark.parametrize("name", ["日本語", "!!!", "   ", "---", "/", ""])
def test_a_name_without_letters_or_digits_gets_a_fallback(name):
    assert slugify(name) == "project"


def test_slugify_cuts_long_names_without_leaving_a_trailing_hyphen():
    slug = slugify("word " * 40)

    assert len(slug) <= MAX_SLUG_LENGTH
    assert not slug.endswith("-") and not slug.startswith("-")
    assert is_slug(slug)


def test_slugify_is_idempotent():
    for name in ["Support Desk", "Café Bot", "x" * 100, "日本語"]:
        assert slugify(slugify(name)) == slugify(name)


def test_every_generated_slug_is_valid():
    for name in ["Support Desk", "Café Bot", "x" * 100, "日本語", "a/b", "  "]:
        assert is_slug(slugify(name))


@pytest.mark.parametrize("value", ["a", "support-desk", "a1", "1-2-3", "x" * 64])
def test_valid_slugs(value):
    assert is_slug(value)


@pytest.mark.parametrize(
    "value", ["", "Support", "support desk", "-a", "a-", "a--b", "a_b", "a/b", "é", "x" * 65]
)
def test_invalid_slugs(value):
    assert not is_slug(value)


def test_the_base_is_used_when_it_is_free():
    assert next_free_slug("support-desk", set()) == "support-desk"
    assert next_free_slug("support-desk", {"other"}) == "support-desk"


def test_a_taken_slug_gets_the_next_number():
    assert next_free_slug("support-desk", {"support-desk"}) == "support-desk-2"
    assert next_free_slug("support-desk", {"support-desk", "support-desk-2"}) == "support-desk-3"


def test_the_smallest_free_number_is_used():
    assert next_free_slug("a", {"a", "a-3"}) == "a-2"


def test_a_suffix_never_pushes_a_long_slug_over_the_limit():
    base = "x" * MAX_SLUG_LENGTH

    slug = next_free_slug(base, {base})

    assert len(slug) <= MAX_SLUG_LENGTH and slug.endswith("-2") and is_slug(slug)
    assert next_free_slug(base, {base, slug}).endswith("-3")


def test_a_suffix_after_a_cut_does_not_leave_a_double_hyphen():
    base = slugify("word " * 40)

    slug = next_free_slug(base, {base})

    assert is_slug(slug) and "--" not in slug
