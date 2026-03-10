import json
from pathlib import Path


def test_dataset_has_3_to_5_reports():
    dataset_dir = Path(__file__).parent / "dataset"
    files = sorted(dataset_dir.glob("*.json"))
    assert 3 <= len(files) <= 5


def test_dataset_schema_is_valid():
    dataset_dir = Path(__file__).parent / "dataset"
    files = sorted(dataset_dir.glob("*.json"))

    for file_path in files:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        assert "name" in payload
        assert "language" in payload
        assert payload["language"] in {"French", "English"}
        assert isinstance(payload.get("pages"), list)

        for page in payload["pages"]:
            assert "page_number" in page
            assert "text" in page
            assert "expected_issues" in page
            assert isinstance(page["expected_issues"], list)
