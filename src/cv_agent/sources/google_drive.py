"""Google Drive implementation of the Source port (OAuth, read-only).

CVs live in date-named subfolders under one parent folder; ``list(since)`` keeps only
folders whose name is >= ``since`` (YYYYMMDD sorts chronologically). ``DocumentRef.id`` is
the opaque Drive file id (used to download); ``DocumentRef.name`` is the human filename
(used as the candidate hint and for interview selection).

The Drive ``service`` is injected, so listing/reading are unit-testable with a fake. Only
``from_env`` touches OAuth. The client-secret file is read by google-auth at runtime, never
by this code.
"""

from __future__ import annotations

import os

from cv_agent.sources.ports import DocumentRef

_FOLDER_MIME = "application/vnd.google-apps.folder"
_PDF_MIME = "application/pdf"
_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


class GoogleDriveSource:
    def __init__(self, service, folder_id: str) -> None:
        self._service = service
        self._folder_id = folder_id

    @classmethod
    def from_env(cls, env) -> "GoogleDriveSource":  # pragma: no cover - OAuth / real IO
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        client_secret = env["GOOGLE_OAUTH_CLIENT_SECRET"]
        token_path = env.get("GOOGLE_OAUTH_TOKEN", "./credentials/token.json")
        folder_id = env["GDRIVE_FOLDER_ID"]

        creds = None
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, _SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                creds = InstalledAppFlow.from_client_secrets_file(
                    client_secret, _SCOPES
                ).run_local_server(port=0)
            with open(token_path, "w", encoding="utf-8") as fh:
                fh.write(creds.to_json())

        return cls(build("drive", "v3", credentials=creds), folder_id)

    def list(self, since: str | None = None) -> tuple[DocumentRef, ...]:
        folders = self._children(self._folder_id, _FOLDER_MIME)
        if since:
            folders = [f for f in folders if f["name"] >= since]
        refs: list[DocumentRef] = []
        for folder in sorted(folders, key=lambda f: f["name"]):
            for pdf in self._children(folder["id"], _PDF_MIME):
                refs.append(DocumentRef(id=pdf["id"], name=pdf["name"]))
        return tuple(refs)

    def read_bytes(self, doc_id: str) -> bytes:
        return self._service.files().get_media(fileId=doc_id).execute()

    def read_text(self, doc_id: str) -> str:
        return self.read_bytes(doc_id).decode("utf-8")

    def _children(self, parent_id: str, mime: str) -> list[dict]:
        query = f"'{parent_id}' in parents and mimeType='{mime}' and trashed=false"
        out: list[dict] = []
        token: str | None = None
        while True:
            resp = (
                self._service.files()
                .list(
                    q=query,
                    fields="nextPageToken, files(id, name)",
                    pageSize=1000,
                    pageToken=token,
                )
                .execute()
            )
            out.extend(resp.get("files", []))
            token = resp.get("nextPageToken")
            if not token:
                break
        return out
