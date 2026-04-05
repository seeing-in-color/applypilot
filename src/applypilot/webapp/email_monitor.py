"""Gmail API integration for monitoring job application responses."""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from applypilot.config import APP_DIR
from applypilot.database import get_connection

logger = logging.getLogger(__name__)

# Gmail API scopes needed
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Path to store OAuth tokens
TOKEN_PATH = APP_DIR / "gmail_token.json"
CREDENTIALS_PATH = APP_DIR / "gmail_credentials.json"

# Email classification patterns
EMAIL_PATTERNS = {
    "rejection": [
        r"unfortunately",
        r"not moving forward",
        r"decided (not )?to (pursue|move forward with) other candidates",
        r"position has been filled",
        r"not a (good )?fit",
        r"we('ve| have) decided to move forward with (another|other) candidate",
        r"application (was )?not (been )?selected",
        r"regret to inform",
        r"won'?t be (moving|proceeding)",
        r"not selected for (the|this|an) interview",
        r"after careful (review|consideration)",
    ],
    "interview": [
        r"schedule (an |a )?interview",
        r"like to (meet|speak|chat) with you",
        r"invitation to interview",
        r"interview (request|invitation|invite)",
        r"next (step|round)",
        r"phone (screen|call)",
        r"video (interview|call)",
        r"meet the team",
        r"technical (interview|screen|assessment)",
        r"on-?site (visit|interview)",
    ],
    "assessment": [
        r"(coding |technical |skills? )?assessment",
        r"(take-?home |coding )?test",
        r"hackerrank",
        r"codility",
        r"leetcode",
        r"codesignal",
        r"complete (the|this|a) (challenge|exercise|assignment)",
        r"skills? (evaluation|test)",
    ],
    "confirmation": [
        r"application (received|submitted|confirmed)",
        r"thank(s| you) for (applying|your (application|interest))",
        r"we('ve| have) received your application",
        r"successfully (applied|submitted)",
        r"confirmation of (your )?application",
    ],
    "info_request": [
        r"(additional |more )?information (needed|required|requested)",
        r"please (provide|send|submit)",
        r"could you (send|provide)",
        r"we need (more|additional)",
        r"missing (information|documents)",
        r"update (your|the) (resume|cv|profile)",
    ],
    "recruiter_reply": [
        r"thanks for reaching out",
        r"thank(s| you) for (connecting|your message)",
        r"I('d|'m| would| am) (like|happy|interested) to",
        r"let('s| us) (connect|chat|talk|schedule)",
        r"I (saw|noticed|reviewed) your (profile|resume|application)",
    ],
    "offer": [
        r"(pleased|excited|happy) to (offer|extend)",
        r"job offer",
        r"offer (letter|of employment)",
        r"we('d| would) like to (offer|hire) you",
        r"welcome (to|aboard)",
        r"start date",
        r"compensation (package|details)",
    ],
}


def get_gmail_service():
    """Get authenticated Gmail API service."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        logger.error(
            "Gmail API dependencies not installed. "
            "Run: pip install google-api-python-client google-auth-oauthlib"
        )
        return None
    
    creds = None
    
    # Load existing token
    if TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        except Exception:
            pass
    
    # Refresh or create new credentials
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None
        
        if not creds:
            if not CREDENTIALS_PATH.exists():
                logger.error(
                    f"Gmail credentials not found. "
                    f"Download OAuth2 credentials from Google Cloud Console "
                    f"and save to {CREDENTIALS_PATH}"
                )
                return None
            
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_PATH), SCOPES
            )
            creds = flow.run_local_server(port=8090)
        
        # Save credentials for next run
        TOKEN_PATH.write_text(creds.to_json())
    
    return build("gmail", "v1", credentials=creds)


def classify_email(subject: str, body: str) -> tuple[str, float]:
    """Classify email content and return (status, confidence).
    
    Returns:
        Tuple of (status, confidence) where status is one of:
        - rejection, interview, assessment, confirmation, info_request, recruiter_reply, offer
        And confidence is 0.0 to 1.0
    """
    text = f"{subject}\n{body}".lower()
    
    matches: dict[str, int] = {}
    
    for category, patterns in EMAIL_PATTERNS.items():
        count = 0
        for pattern in patterns:
            if re.search(pattern, text, re.I):
                count += 1
        if count > 0:
            matches[category] = count
    
    if not matches:
        return ("unknown", 0.0)
    
    # Return category with most matches
    best = max(matches.items(), key=lambda x: x[1])
    total_patterns = len(EMAIL_PATTERNS[best[0]])
    confidence = min(best[1] / max(total_patterns / 2, 1), 1.0)
    
    return (best[0], confidence)


def extract_company_from_email(sender: str, subject: str, body: str) -> Optional[str]:
    """Try to extract company name from email."""
    # Common patterns in sender email
    # e.g., noreply@greenhouse.io on behalf of Company
    # careers@company.com
    # recruiting@company.com
    
    sender_lower = sender.lower()
    
    # Extract from common recruiting platforms
    ats_patterns = [
        r"on behalf of ([^<]+)",
        r"from ([^<]+) via",
    ]
    
    for pattern in ats_patterns:
        match = re.search(pattern, sender, re.I)
        if match:
            return match.group(1).strip()
    
    # Extract from email domain
    domain_match = re.search(r"@([a-zA-Z0-9-]+)\.", sender)
    if domain_match:
        domain = domain_match.group(1)
        # Skip common non-company domains
        if domain.lower() not in ["gmail", "yahoo", "outlook", "hotmail", "greenhouse", "lever", "workday"]:
            return domain.replace("-", " ").title()
    
    # Try to find company name in subject
    company_patterns = [
        r"application (at|to|for|with) ([^-–]+)",
        r"your ([^-–]+) application",
        r"opportunity at ([^-–]+)",
        r"from ([^-–]+) recruiting",
    ]
    
    for pattern in company_patterns:
        match = re.search(pattern, subject, re.I)
        if match:
            return match.group(match.lastindex or 1).strip()
    
    return None


def match_email_to_job(company: str, subject: str, body: str) -> Optional[str]:
    """Try to match email to a job in the database.
    
    Returns job URL if found, None otherwise.
    """
    if not company:
        return None
    
    conn = get_connection()
    
    # Search by company name in URL/title/site
    rows = conn.execute("""
        SELECT url, title, site FROM jobs 
        WHERE applied_at IS NOT NULL
        ORDER BY applied_at DESC
        LIMIT 100
    """).fetchall()
    
    company_lower = company.lower()
    
    for row in rows:
        url = row["url"] or ""
        title = row["title"] or ""
        site = row["site"] or ""
        
        # Check if company name appears in job data
        if (
            company_lower in url.lower() or
            company_lower in title.lower() or
            company_lower in site.lower()
        ):
            return url
        
        # Check for partial matches (e.g., "Acme Inc" vs "Acme")
        for word in company_lower.split():
            if len(word) > 3 and word in url.lower():
                return url
    
    return None


def update_job_from_email(job_url: str, status: str, email_data: dict):
    """Update job status based on email classification."""
    conn = get_connection()
    
    # Map email classification to job status
    status_map = {
        "rejection": "rejected",
        "interview": "interview",
        "assessment": "interview",  # Treat assessments as interview stage
        "offer": "offer",
        "info_request": "needs_input",
        "confirmation": None,  # Don't change status for confirmations
        "recruiter_reply": None,
        "unknown": None,
    }
    
    new_status = status_map.get(status)
    if not new_status:
        return False
    
    # Update job status
    conn.execute(
        "UPDATE jobs SET apply_status = ? WHERE url = ?",
        (new_status, job_url)
    )
    conn.commit()
    
    logger.info(f"Updated job {job_url} status to {new_status} based on email")
    return True


def sync_emails(days_back: int = 7) -> dict[str, Any]:
    """Sync emails from Gmail and update job statuses.
    
    Args:
        days_back: Number of days to look back
        
    Returns:
        Summary of processed emails
    """
    service = get_gmail_service()
    if not service:
        return {"error": "Gmail not authenticated", "processed": 0}
    
    # Build search query for job-related emails
    after_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y/%m/%d")
    
    # Search for emails that look job-related
    query_parts = [
        f"after:{after_date}",
        "(application OR interview OR opportunity OR position OR hiring OR recruiting OR career)",
    ]
    query = " ".join(query_parts)
    
    try:
        results = service.users().messages().list(
            userId="me",
            q=query,
            maxResults=50
        ).execute()
    except Exception as e:
        logger.error(f"Gmail API error: {e}")
        return {"error": str(e), "processed": 0}
    
    messages = results.get("messages", [])
    
    processed = 0
    updated = 0
    classifications: dict[str, int] = {}
    
    for msg in messages:
        try:
            # Get full message
            message = service.users().messages().get(
                userId="me",
                id=msg["id"],
                format="full"
            ).execute()
            
            # Extract headers
            headers = {h["name"].lower(): h["value"] for h in message["payload"]["headers"]}
            subject = headers.get("subject", "")
            sender = headers.get("from", "")
            
            # Extract body
            body = _extract_email_body(message["payload"])
            
            # Classify email
            status, confidence = classify_email(subject, body)
            classifications[status] = classifications.get(status, 0) + 1
            
            if status == "unknown" or confidence < 0.3:
                continue
            
            # Try to match to a job
            company = extract_company_from_email(sender, subject, body)
            job_url = match_email_to_job(company, subject, body)
            
            if job_url:
                if update_job_from_email(job_url, status, {
                    "subject": subject,
                    "sender": sender,
                    "date": headers.get("date"),
                }):
                    updated += 1
            
            processed += 1
            
        except Exception as e:
            logger.warning(f"Error processing email {msg['id']}: {e}")
            continue
    
    return {
        "processed": processed,
        "updated": updated,
        "classifications": classifications,
        "total_emails": len(messages),
    }


def _extract_email_body(payload: dict) -> str:
    """Extract text body from email payload."""
    body = ""
    
    if "body" in payload and payload["body"].get("data"):
        body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="ignore")
    
    if "parts" in payload:
        for part in payload["parts"]:
            if part["mimeType"] == "text/plain":
                if part["body"].get("data"):
                    body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="ignore")
                    break
            elif part["mimeType"] == "text/html":
                if part["body"].get("data") and not body:
                    html = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="ignore")
                    # Basic HTML stripping
                    body = re.sub(r"<[^>]+>", " ", html)
            elif "parts" in part:
                # Nested parts
                body = _extract_email_body(part) or body
    
    return body[:5000]  # Limit body size


def is_gmail_authenticated() -> bool:
    """Check if Gmail is authenticated."""
    if not TOKEN_PATH.exists():
        return False
    try:
        from google.oauth2.credentials import Credentials
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        return creds.valid or (creds.expired and creds.refresh_token)
    except Exception:
        return False


def get_auth_url() -> str:
    """Get the OAuth2 authorization URL for Gmail."""
    try:
        from google_auth_oauthlib.flow import Flow
    except ImportError:
        return ""
    
    if not CREDENTIALS_PATH.exists():
        return ""
    
    flow = Flow.from_client_secrets_file(
        str(CREDENTIALS_PATH),
        scopes=SCOPES,
        redirect_uri="http://localhost:8090/oauth2callback"
    )
    
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true"
    )
    
    return auth_url
