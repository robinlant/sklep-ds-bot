from voice_tracker.botauth import is_allowlisted, parse_user_ids
from voice_tracker.discord_models import Interaction, InteractionCreate, Member, User


def test_parse_user_ids_dedupes_and_normalizes() -> None:
    ids = parse_user_ids("<@123>, 456\n<@!789> 456")
    assert ids == ["123", "456", "789"]


def test_is_allowlisted_matches_member_and_user_fallback() -> None:
    interaction = InteractionCreate(
        interaction=Interaction(member=Member(user=User(id="123")))
    )
    assert is_allowlisted(interaction, ["<@123>"]) is True

    fallback = InteractionCreate(interaction=Interaction(user=User(id="456")))
    assert is_allowlisted(fallback, ["456"]) is True
    assert is_allowlisted(interaction, ["999"]) is False
