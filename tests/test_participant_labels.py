from uuid import UUID

from splitnshare.presentation.labels import participant_html, participant_label

PERSON_ID = UUID("a1b2c3d4-0000-0000-0000-000000000001")


def test_label_uses_normalized_telegram_username() -> None:
    assert participant_label("Alex", PERSON_ID, "@alex") == "Alex (@alex)"


def test_label_uses_stable_short_code_without_username() -> None:
    assert participant_label("Alex", PERSON_ID) == "Alex (#a1b2c3)"


def test_html_label_escapes_names_and_usernames() -> None:
    assert participant_html("Alex <One>", PERSON_ID, "a&b") == (
        "Alex &lt;One&gt; (@a&amp;b)"
    )
