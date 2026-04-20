# Google Sheets export client — writes review findings to a Sheets spreadsheet
# (moved from app/services/sheets_service.py).

from typing import Any, Dict, List

from google.oauth2 import service_account
from googleapiclient.discovery import build

from app.core.config import get_settings


class SheetsClient:
    """Writes review findings to Google Sheets."""

    SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

    def __init__(self) -> None:
        settings = get_settings()
        self.spreadsheet_id = settings.google_sheets_template_id
        self.credentials_path = settings.google_application_credentials
        self.worksheet_name = settings.google_sheets_worksheet_name

        if not self.spreadsheet_id:
            raise ValueError("GOOGLE_SHEETS_TEMPLATE_ID is required")
        if not self.credentials_path:
            raise ValueError("GOOGLE_APPLICATION_CREDENTIALS is required")

        credentials = service_account.Credentials.from_service_account_file(
            self.credentials_path, scopes=self.SCOPES
        )
        self.service = build("sheets", "v4", credentials=credentials)

    def export_findings(self, findings: List[Dict[str, Any]], sheet_id: str = "") -> str:
        """
        Append findings into the configured worksheet and return the spreadsheet URL.
        *sheet_id* is accepted for forward-compatibility but the configured ID is used.
        """
        result = self.write_findings(findings)
        return result.get("spreadsheet_url", "")

    def write_findings(self, findings: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Append findings into the configured worksheet."""
        self._ensure_worksheet_exists()
        self._ensure_header_row()

        rows: List[List[str]] = []

        normalized = self._normalize_findings(findings)
        if not normalized:
            rows.append(["-", "-", "No issues detected", "No change required"])
        else:
            rows.extend(normalized)

        self.service.spreadsheets().values().append(
            spreadsheetId=self.spreadsheet_id,
            range=f"{self.worksheet_name}!A:D",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": rows},
        ).execute()

        return {
            "spreadsheet_id": self.spreadsheet_id,
            "spreadsheet_url": f"https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}",
            "rows_written": len(rows),
            "worksheet_name": self.worksheet_name,
        }

    def _ensure_worksheet_exists(self) -> None:
        metadata = self.service.spreadsheets().get(spreadsheetId=self.spreadsheet_id).execute()
        sheet_titles = {
            s.get("properties", {}).get("title")
            for s in metadata.get("sheets", [])
        }
        if self.worksheet_name in sheet_titles:
            return

        self.service.spreadsheets().batchUpdate(
            spreadsheetId=self.spreadsheet_id,
            body={
                "requests": [
                    {
                        "addSheet": {
                            "properties": {
                                "title": self.worksheet_name,
                            }
                        }
                    }
                ]
            },
        ).execute()

    def _ensure_header_row(self) -> None:
        response = self.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=f"{self.worksheet_name}!A1:D1",
        ).execute()
        values = response.get("values", [])
        if values and values[0]:
            return

        self.service.spreadsheets().values().update(
            spreadsheetId=self.spreadsheet_id,
            range=f"{self.worksheet_name}!A1:D1",
            valueInputOption="RAW",
            body={
                "values": [[
                    "Page Number",
                    "Language of the report",
                    "Category",
                    "Issue Detected",
                    "Proposed Change",
                ]]
            },
        ).execute()

    def _normalize_findings(self, findings: List[Dict[str, Any]]) -> List[List[str]]:
        rows: List[List[str]] = []
        if not findings:
            return rows

        det = [f for f in findings if f.get("source") == "deterministic"]
        other = [f for f in findings if f.get("source") != "deterministic"]

        def to_rows(items: List[Dict[str, Any]]) -> List[List[str]]:
            items_sorted = sorted(items or [], key=lambda x: (x.get("page_number") or 0))
            out: List[List[str]] = []
            for finding in items_sorted:
                page_number = finding.get("page_number", "-")
                language = finding.get("language", "-")
                category = finding.get("category", "")
                issue = finding.get("issue_detected", "")
                proposed_change = finding.get("proposed_change", "")
                out.append([
                    str(page_number),
                    str(language),
                    str(category),
                    str(issue),
                    str(proposed_change),
                ])
            return out

        if det:
            rows.append(["", "", "--- Deterministic Findings ---", "", ""])
            rows.extend(to_rows(det))
            rows.append(["", "", "", "", ""])

        if other:
            rows.append(["", "", "--- LLM Findings ---", "", ""])
            rows.extend(to_rows(other))

        return rows


# Backward-compatible alias so existing imports of GoogleSheetsWriterService work
GoogleSheetsWriterService = SheetsClient
