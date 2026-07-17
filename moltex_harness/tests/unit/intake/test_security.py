from moltex_harness.intake.security import redact, redact_text


def test_secret_values_are_redacted_recursively() -> None:
    secret = "sk-proj_SUPERSECRETVALUE123456"
    value = {
        "message": f"failed with {secret}",
        "api_key": secret,
        "nested": ["password=hunter2"],
    }
    result = redact(value)
    assert secret not in str(result)
    assert result["api_key"] == "[REDACTED]"
    assert "password=[REDACTED]" in result["nested"][0]
    assert "[REDACTED]" in redact_text(f"Bearer {secret}")
