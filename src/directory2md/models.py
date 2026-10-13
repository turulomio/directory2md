"""Data models for document metadata and extraction results."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class EmailHeaders:
    """Structured headers extracted from RFC-822 or Outlook email messages."""

    sender: Optional[str] = None
    to: List[str] = field(default_factory=list)
    cc: List[str] = field(default_factory=list)
    bcc: List[str] = field(default_factory=list)
    subject: Optional[str] = None
    date: Optional[str] = None
    message_id: Optional[str] = None
    attachments: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert headers to serializable dictionary."""
        return {
            "sender": self.sender,
            "to": self.to,
            "cc": self.cc,
            "bcc": self.bcc,
            "subject": self.subject,
            "date": self.date,
            "message_id": self.message_id,
            "attachments": self.attachments,
        }


@dataclass
class DocumentMetadata:
    """Standard metadata extracted from any supported document format."""

    filepath: str
    relative_path: str = ""
    filename: str = ""
    extension: str = ""
    date_str: Optional[str] = None
    time_str: Optional[str] = None
    timestamp: Optional[datetime] = None
    title: str = ""
    file_size_bytes: int = 0
    sha256_hash: str = ""
    word_count: int = 0
    text_snippet: str = ""
    extracted_text: str = ""
    contained_files: List[str] = field(default_factory=list)
    parent_document: Optional[str] = None
    origin_type: str = "file"
    email_headers: Optional[EmailHeaders] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert document metadata to a serializable dictionary."""
        res: Dict[str, Any] = {
            "filepath": self.filepath,
            "relative_path": self.relative_path,
            "filename": self.filename,
            "extension": self.extension,
            "title": self.title,
            "file_size_bytes": self.file_size_bytes,
            "sha256_hash": self.sha256_hash,
            "word_count": self.word_count,
            "origin_type": self.origin_type,
        }
        if self.date_str:
            res["date"] = self.date_str
        if self.time_str:
            res["time"] = self.time_str
        if self.timestamp:
            res["timestamp"] = self.timestamp.isoformat()
        if self.parent_document:
            res["parent_document"] = self.parent_document
        if self.contained_files:
            res["contained_files"] = self.contained_files
        if self.email_headers:
            res["email_headers"] = self.email_headers.to_dict()
        return res
