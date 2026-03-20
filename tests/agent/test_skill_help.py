from src.agent.hub.skill_help import maybe_get_skill_help_reply


def test_product_help_query_returns_assistant_guide_without_enable_instructions() -> None:
    reply = maybe_get_skill_help_reply(
        "How do I use this assistant?",
        source="telegram",
        enabled_skills={"email", "calendar"},
    )

    assert reply is not None
    assert "Using OctaMind" in reply
    assert "/enable" not in reply


def test_scheduler_help_still_returns_skill_specific_help() -> None:
    reply = maybe_get_skill_help_reply("Help with scheduler", source="telegram", enabled_skills=set())

    assert reply is not None
    assert "Scheduler Skill" in reply
    assert "/enable scheduler" in reply