from app.services.feedback_registry_service import FeedbackRegistryService


def test_false_alarm_filter_suppresses_matching_finding_without_removing_others(tmp_path):
    service = FeedbackRegistryService()
    service._file_path = tmp_path / "review_feedback_registry.json"

    service.create_item(
        mode="french_review",
        feedback_type="false_alarm",
        issue_pattern=(
            "Finding showed \"Placeholder data '25%' is present on the slide, likely for a graph data label.\" "
            "But this is placed beyond the slide's extent. So do not consider it."
        ),
        reason="Ignore placeholder text outside the visible slide extent.",
        created_by="test",
    )

    findings = [
        {
            "page_number": 3,
            "language": "French",
            "category": "Formatting & Consistency",
            "issue_detected": "Placeholder data '25%' is present on the slide, likely for a graph data label.",
            "proposed_change": "Ignore placeholder content that appears outside the visible slide extent.",
            "source": "llm",
        },
        {
            "page_number": 4,
            "language": "French",
            "category": "Formatting & Consistency",
            "issue_detected": "Sentence starts with lowercase letter.",
            "proposed_change": "Commencer chaque nouvelle phrase par une majuscule.",
            "source": "deterministic",
        },
    ]

    filtered, suppressed_count = service.apply_false_alarm_filters(findings, "french_review")

    assert suppressed_count == 1
    assert len(filtered) == 1
    assert filtered[0]["issue_detected"] == "Sentence starts with lowercase letter."
