"""Pydantic schemas and structured response types for TinkyWiki MCP."""

from __future__ import annotations

import hashlib
import json
import re
from enum import Enum

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# URL patterns
# ---------------------------------------------------------------------------
REPO_URL_PATTERN = re.compile(
    r"^https?://(github\.com|gitlab\.com|bitbucket\.org)/[\w.\-]+/[\w.\-]+(/.*)?$"
)

OWNER_REPO_PATTERN = re.compile(r"^[\w.\-]+/[\w.\-]+$")


# ---------------------------------------------------------------------------
# Input schemas (like Zod in DeepWiki MCP)
# ---------------------------------------------------------------------------
class RepoInput(BaseModel):
    """Validated repository identifier — accepts full URL or owner/repo shorthand."""

    repo_url: str = Field(
        ...,
        description=(
            "Repository URL (e.g. https://github.com/microsoft/vscode) "
            "or shorthand owner/repo (e.g. microsoft/vscode)."
        ),
    )

    @field_validator("repo_url")
    @classmethod
    def normalize_repo_url(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("repo_url must not be empty")

        # Shorthand: owner/repo → full GitHub URL
        if OWNER_REPO_PATTERN.match(v):
            return f"https://github.com/{v}"

        # Full URL — accept as-is
        if REPO_URL_PATTERN.match(v):
            return v

        # --- Bare keyword resolution ---
        # If it's a single word (no slash, no URL scheme), try to resolve
        # it via TinkyWiki's search page (e.g., "vue" → "vuejs/vue")
        from .resolver import is_bare_keyword, resolve_keyword  # noqa: E402

        if is_bare_keyword(v):
            resolved, _results = resolve_keyword(v)
            if resolved:
                return f"https://github.com/{resolved}"
            # No results found — give a helpful error
            raise ValueError(
                f"Could not resolve keyword '{v}' to a repository. "
                "No matching repos found on TinkyWiki. "
                "Try using owner/repo format (e.g., 'vuejs/vue') or a full URL."
            )

        raise ValueError(
            f"Invalid repository URL: '{v}'. "
            "Expected https://github.com/owner/repo, owner/repo shorthand, "
            "or a product keyword (e.g., 'vue', 'react', 'fastapi')."
        )


class SearchInput(RepoInput):
    """Input for the tinkywiki_search_wiki tool."""

    query: str = Field(
        ...,
        min_length=1,
        description="The question to ask about the repository.",
    )

    @field_validator("query")
    @classmethod
    def query_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("query must not be blank")
        return v


class TopicsInput(RepoInput):
    """Input for the tinkywiki_list_topics tool."""

    # Only repo_url needed — no extra fields.


class SectionInput(RepoInput):
    """Input for the read_wiki_section tool."""

    section_title: str = Field(
        ...,
        min_length=1,
        description="Title (or partial title) of the section to retrieve.",
    )

    @field_validator("section_title")
    @classmethod
    def section_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("section_title must not be blank")
        return v


class ContentsInput(RepoInput):
    """Input for the tinkywiki_read_contents tool (with optional pagination)."""

    section_title: str = Field(
        default="",
        description="Title (or partial title) of a specific section to retrieve.",
    )
    offset: int = Field(
        default=0,
        ge=0,
        description="Section index to start from (0-based) when browsing the full page.",
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Maximum number of sections to return per call.",
    )


# ---------------------------------------------------------------------------
# Structured response types (like ErrorEnvelope in DeepWiki MCP)
# ---------------------------------------------------------------------------
class ResponseStatus(str, Enum):
    OK = "ok"
    ERROR = "error"
    PARTIAL = "partial"


class ErrorCode(str, Enum):
    VALIDATION = "VALIDATION"
    TIMEOUT = "TIMEOUT"
    DRIVER_ERROR = "DRIVER_ERROR"
    NO_CONTENT = "NO_CONTENT"
    NOT_INDEXED = "NOT_INDEXED"
    INPUT_NOT_FOUND = "INPUT_NOT_FOUND"
    INTERNAL = "INTERNAL"
    RETRY_EXHAUSTED = "RETRY_EXHAUSTED"
    RATE_LIMITED = "RATE_LIMITED"


class ResponseMeta(BaseModel):
    """Metadata about the response — timing, size, etc."""

    elapsed_ms: int = 0
    char_count: int = 0
    attempt: int = 1
    max_attempts: int = 1
    truncated: bool = False
    content_hash: str | None = None
    calls_remaining: int | None = None
    retry_after_seconds: float | None = None
    source: str | None = None  # "tinkywiki", "deepwiki", or "github_api"


def _compute_hash(data: str) -> str:
    """Compute a short SHA-256 hash of *data* for dedup / idempotency detection."""
    return hashlib.sha256(data.encode()).hexdigest()[:16]


class ToolResponse(BaseModel):
    """Structured response from any TinkyWiki tool."""

    status: ResponseStatus
    code: ErrorCode | None = None
    message: str | None = None
    data: str | None = None
    repo_url: str | None = None
    query: str | None = None
    idempotency_key: str | None = None
    meta: ResponseMeta = Field(default_factory=ResponseMeta)

    def to_text(self) -> str:
        """Serialize to JSON string for MCP transport."""
        return json.dumps(self.model_dump(exclude_none=True), indent=2)

    # -- Factory helpers --

    @classmethod
    def success(  # pylint: disable=too-many-arguments
        cls,
        data: str,
        *,
        repo_url: str | None = None,
        query: str | None = None,
        meta: ResponseMeta | None = None,
    ) -> ToolResponse:
        """Create a successful ToolResponse with content hash and idempotency key."""
        m = meta or ResponseMeta()
        m.char_count = len(data)
        m.content_hash = _compute_hash(data)

        # Build idempotency key from repo + content hash
        idem_parts = [p for p in [repo_url, m.content_hash] if p]
        idem_key = "::".join(idem_parts) if idem_parts else None

        return cls(
            status=ResponseStatus.OK,
            data=data,
            repo_url=repo_url,
            query=query,
            idempotency_key=idem_key,
            meta=m,
        )

    @classmethod
    def error(  # pylint: disable=too-many-arguments
        cls,
        code: ErrorCode,
        message: str,
        *,
        repo_url: str | None = None,
        query: str | None = None,
        meta: ResponseMeta | None = None,
    ) -> ToolResponse:
        """Create an error ToolResponse with given code and message."""
        return cls(
            status=ResponseStatus.ERROR,
            code=code,
            message=message,
            repo_url=repo_url,
            query=query,
            meta=meta or ResponseMeta(),
        )


def validate_search_input(repo_url: str, query: str) -> SearchInput | ToolResponse:
    """Validate and normalize search inputs. Returns SearchInput or ToolResponse error."""
    try:
        return SearchInput(repo_url=repo_url, query=query)
    except Exception as exc:  # pylint: disable=broad-except
        return ToolResponse.error(
            ErrorCode.VALIDATION,
            str(exc),
            repo_url=repo_url,
            query=query,
        )


def validate_topics_input(repo_url: str) -> TopicsInput | ToolResponse:
    """Validate and normalize topics inputs. Returns TopicsInput or ToolResponse error."""
    try:
        return TopicsInput(repo_url=repo_url)
    except Exception as exc:  # pylint: disable=broad-except
        return ToolResponse.error(
            ErrorCode.VALIDATION,
            str(exc),
            repo_url=repo_url,
        )


def validate_section_input(
    repo_url: str, section_title: str
) -> SectionInput | ToolResponse:
    """Validate and normalize section inputs. Returns SectionInput or ToolResponse error."""
    try:
        return SectionInput(repo_url=repo_url, section_title=section_title)
    except Exception as exc:  # pylint: disable=broad-except
        return ToolResponse.error(
            ErrorCode.VALIDATION,
            str(exc),
            repo_url=repo_url,
        )


def validate_contents_input(
    repo_url: str,
    section_title: str = "",
    offset: int = 0,
    limit: int = 5,
) -> ContentsInput | ToolResponse:
    """Validate and normalize contents inputs. Returns ContentsInput or ToolResponse error."""
    try:
        return ContentsInput(
            repo_url=repo_url,
            section_title=section_title,
            offset=offset,
            limit=limit,
        )
    except Exception as exc:  # pylint: disable=broad-except
        return ToolResponse.error(
            ErrorCode.VALIDATION,
            str(exc),
            repo_url=repo_url,
        )
