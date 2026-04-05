"""ATS-specific deterministic form handlers.

This module contains hardcoded selectors and logic for major Applicant 
Tracking Systems to minimize AI API calls during form filling.

Supported ATS platforms:
- Ashby (jobs.ashbyhq.com)
- Greenhouse (job-boards.greenhouse.io, boards.greenhouse.io)
- Workday (*.myworkdayjobs.com)
- Lever (jobs.lever.co)
- SmartRecruiters (jobs.smartrecruiters.com)
- Generic fallbacks
"""

from __future__ import annotations

import logging
import re
import time
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from playwright.sync_api import Page, Locator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ATS Detection
# ---------------------------------------------------------------------------

def detect_ats(url: str) -> str:
    """Detect which ATS platform a URL belongs to.
    
    Returns:
        ATS name: 'ashby', 'greenhouse', 'workday', 'lever', 'smartrecruiters', 
        'icims', 'taleo', 'brassring', 'jobvite', 'applytojob', or 'unknown'
    """
    url_lower = url.lower()
    
    if "ashbyhq.com" in url_lower:
        return "ashby"
    if "greenhouse.io" in url_lower:
        return "greenhouse"
    if "myworkdayjobs.com" in url_lower or "workday.com" in url_lower:
        return "workday"
    if "lever.co" in url_lower:
        return "lever"
    if "smartrecruiters.com" in url_lower:
        return "smartrecruiters"
    if "icims.com" in url_lower:
        return "icims"
    if "taleo" in url_lower:
        return "taleo"
    if "brassring.com" in url_lower:
        return "brassring"
    if "jobvite.com" in url_lower:
        return "jobvite"
    if "applytojob.com" in url_lower:
        return "applytojob"
    
    return "unknown"


# ---------------------------------------------------------------------------
# Ashby Handler (jobs.ashbyhq.com)
# ---------------------------------------------------------------------------

class AshbyHandler:
    """Handle Ashby ATS forms (jobs.ashbyhq.com)."""
    
    # Selectors for Ashby forms
    SELECTORS = {
        "apply_button": 'button:has-text("Apply"), a:has-text("Apply")',
        "first_name": 'input[name*="firstName"], input[placeholder*="First name"]',
        "last_name": 'input[name*="lastName"], input[placeholder*="Last name"]',
        "email": 'input[type="email"], input[name*="email"]',
        "phone": 'input[type="tel"], input[name*="phone"]',
        "resume_upload": 'input[type="file"][accept*="pdf"], input[type="file"]',
        "linkedin": 'input[name*="linkedin"], input[placeholder*="LinkedIn"]',
        "submit_button": 'button[type="submit"], button:has-text("Submit"), button:has-text("Apply")',
    }
    
    # Common question patterns and their field mappings
    QUESTION_PATTERNS = {
        r"authorized.*work": "work_authorization.legally_authorized_to_work",
        r"require.*sponsor": "work_authorization.require_sponsorship",
        r"willing.*relocate": "availability.willing_to_relocate",
        r"start.*date|when.*start|available.*start": "availability.start_date",
        r"salary|compensation|expected.*pay": "compensation.desired_salary",
        r"how.*hear|source|referral": "personal.application_source",
    }
    
    @staticmethod
    def is_ashby_page(page: "Page") -> bool:
        """Check if current page is an Ashby application."""
        return "ashbyhq.com" in page.url.lower()
    
    @staticmethod
    def fill_form(page: "Page", profile: dict) -> dict[str, Any]:
        """Fill Ashby application form.
        
        Args:
            page: Playwright page object
            profile: User profile dictionary
            
        Returns:
            Dict with 'success', 'fields_filled', 'errors'
        """
        result = {"success": False, "fields_filled": [], "errors": []}
        personal = profile.get("personal", {})
        
        try:
            # Wait for form to load
            page.wait_for_selector("form", timeout=5000)
            
            # Fill basic fields
            field_mappings = [
                (AshbyHandler.SELECTORS["first_name"], personal.get("first_name", "")),
                (AshbyHandler.SELECTORS["last_name"], personal.get("last_name", "")),
                (AshbyHandler.SELECTORS["email"], personal.get("email", "")),
                (AshbyHandler.SELECTORS["phone"], personal.get("phone", "")),
                (AshbyHandler.SELECTORS["linkedin"], personal.get("linkedin_url", "")),
            ]
            
            for selector, value in field_mappings:
                if value:
                    try:
                        loc = page.locator(selector).first
                        if loc.is_visible():
                            current = loc.input_value()
                            if not current or current != value:
                                loc.fill(value)
                                result["fields_filled"].append(selector)
                    except Exception as e:
                        logger.debug(f"Field {selector} not found or error: {e}")
            
            # Handle file upload
            resume_path = profile.get("resume_path")
            if resume_path:
                try:
                    upload = page.locator(AshbyHandler.SELECTORS["resume_upload"]).first
                    if upload.is_visible():
                        upload.set_input_files(resume_path)
                        result["fields_filled"].append("resume")
                except Exception as e:
                    result["errors"].append(f"Resume upload failed: {e}")
            
            # Handle common screening questions
            AshbyHandler._fill_screening_questions(page, profile, result)
            
            result["success"] = len(result["errors"]) == 0
            
        except Exception as e:
            result["errors"].append(f"Ashby form fill failed: {e}")
        
        return result
    
    @staticmethod
    def _fill_screening_questions(page: "Page", profile: dict, result: dict):
        """Fill common screening questions on Ashby forms."""
        # Find all question labels
        labels = page.locator("label, .question-label, [data-qa='question-label']").all()
        
        for label in labels:
            try:
                label_text = label.text_content() or ""
                label_text_lower = label_text.lower()
                
                # Match against known patterns
                for pattern, profile_path in AshbyHandler.QUESTION_PATTERNS.items():
                    if re.search(pattern, label_text_lower):
                        value = _get_profile_value(profile, profile_path)
                        if value:
                            # Find associated input
                            input_loc = _find_input_for_label(page, label)
                            if input_loc:
                                _fill_input(input_loc, value)
                                result["fields_filled"].append(label_text[:30])
                        break
            except Exception as e:
                logger.debug(f"Error processing label: {e}")


# ---------------------------------------------------------------------------
# Greenhouse Handler (greenhouse.io)
# ---------------------------------------------------------------------------

class GreenhouseHandler:
    """Handle Greenhouse ATS forms."""
    
    SELECTORS = {
        "apply_button": '#apply-now, button:has-text("Apply"), a:has-text("Apply now")',
        "form_frame": 'iframe[src*="greenhouse"]',
        "first_name": '#first_name, input[name="job_application[first_name]"]',
        "last_name": '#last_name, input[name="job_application[last_name]"]',
        "email": '#email, input[name="job_application[email]"]',
        "phone": '#phone, input[name="job_application[phone]"]',
        "resume_upload": '#resume, input[type="file"][name*="resume"]',
        "cover_letter_upload": '#cover_letter, input[type="file"][name*="cover"]',
        "linkedin": 'input[name*="linkedin"], #job_application_answers_attributes_0_text_value',
        "submit_button": '#submit_app, button[type="submit"]',
    }
    
    @staticmethod
    def is_greenhouse_page(page: "Page") -> bool:
        """Check if current page is a Greenhouse application."""
        return "greenhouse.io" in page.url.lower()
    
    @staticmethod
    def fill_form(page: "Page", profile: dict) -> dict[str, Any]:
        """Fill Greenhouse application form."""
        result = {"success": False, "fields_filled": [], "errors": []}
        personal = profile.get("personal", {})
        
        try:
            # Greenhouse forms are often in iframes
            frame = page
            iframe = page.locator(GreenhouseHandler.SELECTORS["form_frame"]).first
            if iframe.count() > 0:
                frame = iframe.content_frame()
            
            # Wait for form
            frame.wait_for_selector("form, #application-form", timeout=5000)
            
            # Fill basic fields
            field_mappings = [
                (GreenhouseHandler.SELECTORS["first_name"], personal.get("first_name", "")),
                (GreenhouseHandler.SELECTORS["last_name"], personal.get("last_name", "")),
                (GreenhouseHandler.SELECTORS["email"], personal.get("email", "")),
                (GreenhouseHandler.SELECTORS["phone"], personal.get("phone", "")),
            ]
            
            for selector, value in field_mappings:
                if value:
                    _safe_fill(frame, selector, value, result)
            
            # Handle resume upload
            resume_path = profile.get("resume_path")
            if resume_path:
                _safe_upload(frame, GreenhouseHandler.SELECTORS["resume_upload"], resume_path, result)
            
            # Handle cover letter if exists
            cover_path = profile.get("cover_letter_path")
            if cover_path:
                _safe_upload(frame, GreenhouseHandler.SELECTORS["cover_letter_upload"], cover_path, result)
            
            # Fill LinkedIn if field exists
            linkedin = personal.get("linkedin_url", "")
            if linkedin:
                _safe_fill(frame, GreenhouseHandler.SELECTORS["linkedin"], linkedin, result)
            
            # Handle custom questions
            GreenhouseHandler._fill_custom_questions(frame, profile, result)
            
            result["success"] = len(result["errors"]) == 0
            
        except Exception as e:
            result["errors"].append(f"Greenhouse form fill failed: {e}")
        
        return result
    
    @staticmethod
    def _fill_custom_questions(frame, profile: dict, result: dict):
        """Fill custom questions in Greenhouse forms."""
        # Find question containers
        questions = frame.locator(".field, .application-form-field, [data-qa='job-application-question']").all()
        
        for q in questions:
            try:
                label_text = q.locator("label, .field-label").first.text_content() or ""
                answer = _match_question_to_answer(label_text.lower(), profile)
                
                if answer:
                    input_elem = q.locator("input:not([type='hidden']), select, textarea").first
                    if input_elem.count() > 0:
                        _fill_input(input_elem, answer)
                        result["fields_filled"].append(label_text[:30])
            except Exception:
                continue


# ---------------------------------------------------------------------------
# Workday Handler (*.myworkdayjobs.com)
# ---------------------------------------------------------------------------

class WorkdayHandler:
    """Handle Workday ATS forms."""
    
    SELECTORS = {
        "apply_button": 'button[data-automation-id="applyButton"], a[data-automation-id="applyButton"]',
        "first_name": 'input[data-automation-id="legalNameSection_firstName"]',
        "last_name": 'input[data-automation-id="legalNameSection_lastName"]',
        "email": 'input[data-automation-id="email"]',
        "phone": 'input[data-automation-id="phone"]',
        "address": 'input[data-automation-id="addressSection_addressLine1"]',
        "city": 'input[data-automation-id="addressSection_city"]',
        "state": 'input[data-automation-id="addressSection_countryRegion"]',
        "postal_code": 'input[data-automation-id="addressSection_postalCode"]',
        "resume_upload": 'input[data-automation-id="resumeFileInput"], input[type="file"]',
        "submit_button": 'button[data-automation-id="bottom-navigation-next-button"]',
        "next_button": 'button[data-automation-id="bottom-navigation-next-button"]',
    }
    
    @staticmethod
    def is_workday_page(page: "Page") -> bool:
        """Check if current page is a Workday application."""
        return "workday" in page.url.lower() or "myworkdayjobs" in page.url.lower()
    
    @staticmethod
    def fill_form(page: "Page", profile: dict) -> dict[str, Any]:
        """Fill Workday application form (multi-page)."""
        result = {"success": False, "fields_filled": [], "errors": [], "pages_completed": 0}
        personal = profile.get("personal", {})
        
        try:
            # Workday has multi-page forms
            max_pages = 10
            
            for page_num in range(max_pages):
                page.wait_for_load_state("networkidle", timeout=10000)
                time.sleep(1)  # Workday is slow
                
                # Fill visible fields on current page
                WorkdayHandler._fill_current_page(page, profile, result)
                
                # Try to proceed to next page
                next_btn = page.locator(WorkdayHandler.SELECTORS["next_button"]).first
                if next_btn.is_visible() and next_btn.is_enabled():
                    next_btn.click()
                    result["pages_completed"] += 1
                    time.sleep(2)
                else:
                    # Check if we're on the review/submit page
                    if page.locator('button:has-text("Submit")').count() > 0:
                        result["success"] = True
                    break
            
        except Exception as e:
            result["errors"].append(f"Workday form fill failed: {e}")
        
        return result
    
    @staticmethod
    def _fill_current_page(page: "Page", profile: dict, result: dict):
        """Fill fields on current Workday page."""
        personal = profile.get("personal", {})
        address = personal.get("address", {})
        
        # Basic field mappings
        field_mappings = [
            (WorkdayHandler.SELECTORS["first_name"], personal.get("first_name", "")),
            (WorkdayHandler.SELECTORS["last_name"], personal.get("last_name", "")),
            (WorkdayHandler.SELECTORS["email"], personal.get("email", "")),
            (WorkdayHandler.SELECTORS["phone"], personal.get("phone", "")),
            (WorkdayHandler.SELECTORS["address"], address.get("street", "")),
            (WorkdayHandler.SELECTORS["city"], address.get("city", "")),
            (WorkdayHandler.SELECTORS["postal_code"], address.get("postal_code", "")),
        ]
        
        for selector, value in field_mappings:
            if value:
                _safe_fill(page, selector, value, result)
        
        # Handle file upload
        resume_path = profile.get("resume_path")
        if resume_path:
            _safe_upload(page, WorkdayHandler.SELECTORS["resume_upload"], resume_path, result)
        
        # Handle dropdowns (Workday uses custom dropdowns)
        WorkdayHandler._fill_workday_dropdowns(page, profile, result)
    
    @staticmethod
    def _fill_workday_dropdowns(page: "Page", profile: dict, result: dict):
        """Handle Workday's custom dropdown components."""
        # Workday dropdowns need click to open, then select
        dropdowns = page.locator('[data-automation-id*="dropdown"], [data-automation-id*="select"]').all()
        
        for dropdown in dropdowns:
            try:
                label = dropdown.locator("label").text_content() or ""
                answer = _match_question_to_answer(label.lower(), profile)
                
                if answer:
                    # Click to open dropdown
                    dropdown.click()
                    time.sleep(0.5)
                    
                    # Find and click matching option
                    options = page.locator('[data-automation-id="promptOption"]').all()
                    for opt in options:
                        if answer.lower() in (opt.text_content() or "").lower():
                            opt.click()
                            result["fields_filled"].append(label[:30])
                            break
            except Exception:
                continue


# ---------------------------------------------------------------------------
# Lever Handler (jobs.lever.co)
# ---------------------------------------------------------------------------

class LeverHandler:
    """Handle Lever ATS forms."""
    
    SELECTORS = {
        "apply_button": '.postings-btn-wrapper a, button:has-text("Apply")',
        "first_name": 'input[name="name"]',  # Lever uses combined name field
        "email": 'input[name="email"]',
        "phone": 'input[name="phone"]',
        "resume_upload": 'input[name="resume"]',
        "cover_letter_upload": 'input[name="coverLetter"]',
        "linkedin": 'input[name="urls[LinkedIn]"]',
        "github": 'input[name="urls[GitHub]"]',
        "portfolio": 'input[name="urls[Portfolio]"]',
        "submit_button": 'button[type="submit"]',
    }
    
    @staticmethod
    def is_lever_page(page: "Page") -> bool:
        return "lever.co" in page.url.lower()
    
    @staticmethod
    def fill_form(page: "Page", profile: dict) -> dict[str, Any]:
        """Fill Lever application form."""
        result = {"success": False, "fields_filled": [], "errors": []}
        personal = profile.get("personal", {})
        
        try:
            page.wait_for_selector("form", timeout=5000)
            
            # Lever often uses a single name field
            full_name = f"{personal.get('first_name', '')} {personal.get('last_name', '')}".strip()
            
            field_mappings = [
                (LeverHandler.SELECTORS["first_name"], full_name),
                (LeverHandler.SELECTORS["email"], personal.get("email", "")),
                (LeverHandler.SELECTORS["phone"], personal.get("phone", "")),
                (LeverHandler.SELECTORS["linkedin"], personal.get("linkedin_url", "")),
                (LeverHandler.SELECTORS["github"], personal.get("github_url", "")),
                (LeverHandler.SELECTORS["portfolio"], personal.get("portfolio_url", "")),
            ]
            
            for selector, value in field_mappings:
                if value:
                    _safe_fill(page, selector, value, result)
            
            # Handle file uploads
            if profile.get("resume_path"):
                _safe_upload(page, LeverHandler.SELECTORS["resume_upload"], profile["resume_path"], result)
            
            if profile.get("cover_letter_path"):
                _safe_upload(page, LeverHandler.SELECTORS["cover_letter_upload"], profile["cover_letter_path"], result)
            
            # Handle custom questions
            LeverHandler._fill_custom_questions(page, profile, result)
            
            result["success"] = len(result["errors"]) == 0
            
        except Exception as e:
            result["errors"].append(f"Lever form fill failed: {e}")
        
        return result
    
    @staticmethod
    def _fill_custom_questions(page: "Page", profile: dict, result: dict):
        """Fill Lever custom questions."""
        questions = page.locator('.application-question, [data-qa="application-question"]').all()
        
        for q in questions:
            try:
                label_text = q.locator("label, .question-label").first.text_content() or ""
                answer = _match_question_to_answer(label_text.lower(), profile)
                
                if answer:
                    input_elem = q.locator("input, select, textarea").first
                    if input_elem.count() > 0:
                        _fill_input(input_elem, answer)
                        result["fields_filled"].append(label_text[:30])
            except Exception:
                continue


# ---------------------------------------------------------------------------
# SmartRecruiters Handler
# ---------------------------------------------------------------------------

class SmartRecruitersHandler:
    """Handle SmartRecruiters ATS forms."""
    
    SELECTORS = {
        "apply_button": 'button.js-apply-button, a:has-text("Apply")',
        "first_name": 'input#first_name, input[name="firstName"]',
        "last_name": 'input#last_name, input[name="lastName"]',  
        "email": 'input#email, input[name="email"]',
        "phone": 'input#phone, input[name="phoneNumber"]',
        "resume_upload": 'input[type="file"]',
        "location": 'input[name="city"]',
        "submit_button": 'button[type="submit"]',
    }
    
    @staticmethod
    def is_smartrecruiters_page(page: "Page") -> bool:
        return "smartrecruiters.com" in page.url.lower()
    
    @staticmethod
    def fill_form(page: "Page", profile: dict) -> dict[str, Any]:
        """Fill SmartRecruiters application form."""
        result = {"success": False, "fields_filled": [], "errors": []}
        personal = profile.get("personal", {})
        
        try:
            page.wait_for_selector("form", timeout=5000)
            
            field_mappings = [
                (SmartRecruitersHandler.SELECTORS["first_name"], personal.get("first_name", "")),
                (SmartRecruitersHandler.SELECTORS["last_name"], personal.get("last_name", "")),
                (SmartRecruitersHandler.SELECTORS["email"], personal.get("email", "")),
                (SmartRecruitersHandler.SELECTORS["phone"], personal.get("phone", "")),
                (SmartRecruitersHandler.SELECTORS["location"], personal.get("city", "")),
            ]
            
            for selector, value in field_mappings:
                if value:
                    _safe_fill(page, selector, value, result)
            
            if profile.get("resume_path"):
                _safe_upload(page, SmartRecruitersHandler.SELECTORS["resume_upload"], profile["resume_path"], result)
            
            result["success"] = len(result["errors"]) == 0
            
        except Exception as e:
            result["errors"].append(f"SmartRecruiters form fill failed: {e}")
        
        return result


# ---------------------------------------------------------------------------
# Generic Handler (for unknown/custom sites)
# ---------------------------------------------------------------------------

class GenericFormHandler:
    """Handle generic job application forms."""
    
    # Common selectors across various sites
    SELECTORS = {
        "first_name": [
            'input[name*="first" i]',
            'input[id*="first" i]',
            'input[placeholder*="First" i]',
            'input[autocomplete="given-name"]',
        ],
        "last_name": [
            'input[name*="last" i]',
            'input[id*="last" i]',
            'input[placeholder*="Last" i]',
            'input[autocomplete="family-name"]',
        ],
        "email": [
            'input[type="email"]',
            'input[name*="email" i]',
            'input[id*="email" i]',
            'input[autocomplete="email"]',
        ],
        "phone": [
            'input[type="tel"]',
            'input[name*="phone" i]',
            'input[id*="phone" i]',
            'input[autocomplete="tel"]',
        ],
        "resume": [
            'input[type="file"][accept*="pdf"]',
            'input[type="file"][name*="resume" i]',
            'input[type="file"][id*="resume" i]',
            'input[type="file"]',
        ],
    }
    
    @staticmethod
    def fill_form(page: "Page", profile: dict) -> dict[str, Any]:
        """Fill generic application form using multiple selector strategies."""
        result = {"success": False, "fields_filled": [], "errors": []}
        personal = profile.get("personal", {})
        
        try:
            # Wait for any form
            page.wait_for_selector("form, [role='form']", timeout=5000)
            
            # Try each field with multiple selectors
            field_values = {
                "first_name": personal.get("first_name", ""),
                "last_name": personal.get("last_name", ""),
                "email": personal.get("email", ""),
                "phone": personal.get("phone", ""),
            }
            
            for field, value in field_values.items():
                if not value:
                    continue
                
                selectors = GenericFormHandler.SELECTORS.get(field, [])
                filled = False
                
                for selector in selectors:
                    try:
                        loc = page.locator(selector).first
                        if loc.is_visible():
                            loc.fill(value)
                            result["fields_filled"].append(field)
                            filled = True
                            break
                    except Exception:
                        continue
                
                if not filled:
                    logger.debug(f"Could not fill {field}")
            
            # Handle resume upload
            resume_path = profile.get("resume_path")
            if resume_path:
                for selector in GenericFormHandler.SELECTORS["resume"]:
                    try:
                        upload = page.locator(selector).first
                        if upload.count() > 0:
                            upload.set_input_files(resume_path)
                            result["fields_filled"].append("resume")
                            break
                    except Exception:
                        continue
            
            # Fill other visible inputs based on label matching
            GenericFormHandler._fill_labeled_inputs(page, profile, result)
            
            result["success"] = len(result["fields_filled"]) >= 2  # At least name + email
            
        except Exception as e:
            result["errors"].append(f"Generic form fill failed: {e}")
        
        return result
    
    @staticmethod
    def _fill_labeled_inputs(page: "Page", profile: dict, result: dict):
        """Fill inputs by matching their labels to profile data."""
        labels = page.locator("label").all()
        
        for label in labels:
            try:
                label_text = (label.text_content() or "").strip().lower()
                if not label_text:
                    continue
                
                # Get associated input
                for_id = label.get_attribute("for")
                if for_id:
                    input_elem = page.locator(f"#{for_id}").first
                else:
                    # Try to find input inside label
                    input_elem = label.locator("input, select, textarea").first
                
                if not input_elem or input_elem.count() == 0:
                    continue
                
                # Match label to profile value
                answer = _match_question_to_answer(label_text, profile)
                if answer:
                    _fill_input(input_elem, answer)
                    result["fields_filled"].append(label_text[:30])
                    
            except Exception:
                continue


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _safe_fill(page_or_frame, selector: str, value: str, result: dict):
    """Safely fill a field, catching errors."""
    try:
        loc = page_or_frame.locator(selector).first
        if loc.is_visible():
            current = loc.input_value() if hasattr(loc, 'input_value') else ""
            if not current or current != value:
                loc.fill(value)
                result["fields_filled"].append(selector.split('[')[0])
    except Exception as e:
        logger.debug(f"Could not fill {selector}: {e}")


def _safe_upload(page_or_frame, selector: str, file_path: str, result: dict):
    """Safely upload a file, catching errors."""
    try:
        upload = page_or_frame.locator(selector).first
        if upload.count() > 0:
            upload.set_input_files(file_path)
            result["fields_filled"].append("file_upload")
    except Exception as e:
        result["errors"].append(f"File upload failed: {e}")


def _fill_input(locator: "Locator", value: str):
    """Fill an input based on its type."""
    try:
        tag = locator.evaluate("el => el.tagName.toLowerCase()")
        input_type = locator.get_attribute("type") or "text"
        
        if tag == "select":
            # Try to select by label text
            options = locator.locator("option").all()
            for opt in options:
                if value.lower() in (opt.text_content() or "").lower():
                    locator.select_option(label=opt.text_content())
                    return
            # Fallback to first non-placeholder option
            if len(options) > 1:
                locator.select_option(index=1)
                
        elif input_type == "checkbox":
            if value.lower() in ("yes", "true", "1"):
                locator.check()
            else:
                locator.uncheck()
                
        elif input_type == "radio":
            if value.lower() in ("yes", "true", "1"):
                locator.check()
                
        else:
            locator.fill(value)
            
    except Exception as e:
        logger.debug(f"Error filling input: {e}")


def _find_input_for_label(page: "Page", label: "Locator") -> Optional["Locator"]:
    """Find the input associated with a label."""
    try:
        for_id = label.get_attribute("for")
        if for_id:
            return page.locator(f"#{for_id}").first
        
        # Check for input inside label
        inner = label.locator("input, select, textarea").first
        if inner.count() > 0:
            return inner
        
        # Check sibling
        parent = label.locator("..").first
        sibling = parent.locator("input, select, textarea").first
        if sibling.count() > 0:
            return sibling
            
    except Exception:
        pass
    
    return None


def _get_profile_value(profile: dict, path: str) -> Optional[str]:
    """Get nested value from profile by dot-separated path."""
    parts = path.split(".")
    current = profile
    
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    
    if current is None:
        return None
    
    return str(current)


def _match_question_to_answer(question: str, profile: dict) -> Optional[str]:
    """Match a question to a profile answer using keyword patterns."""
    question_lower = question.lower()
    
    # Common patterns mapped to profile paths
    patterns = {
        # Work authorization
        r"authorized.*work|legally.*work|eligib.*work": ("work_authorization.legally_authorized_to_work", "Yes"),
        r"require.*sponsor|need.*sponsor|visa.*sponsor|h1.?b": ("work_authorization.require_sponsorship", "No"),
        
        # Availability
        r"willing.*relocate|relocation": ("availability.willing_to_relocate", "Yes"),
        r"start.*date|when.*start|available.*start": ("availability.start_date", None),
        r"remote|work.*from.*home": ("availability.remote_preference", "Yes"),
        
        # Personal
        r"linkedin": ("personal.linkedin_url", None),
        r"github": ("personal.github_url", None),
        r"portfolio|website": ("personal.portfolio_url", None),
        r"location|city": ("personal.city", None),
        r"country": ("personal.country", "United States"),
        
        # Experience
        r"years.*experience|how.*long|experience.*years": ("experience.years", None),
        r"current.*title|job.*title": ("experience.current_title", None),
        r"current.*company|employer": ("experience.current_company", None),
        
        # Compensation
        r"salary|compensation|expected.*pay": ("compensation.desired_salary", None),
        
        # Source
        r"how.*hear|source|where.*find|referral": ("personal.application_source", "LinkedIn"),
        
        # Common yes/no questions
        r"18.*years|over.*18|age": (None, "Yes"),
        r"background.*check": (None, "Yes"),
        r"drug.*test": (None, "Yes"),
        r"previously.*work|worked.*before|prior.*employee": (None, "No"),
        r"felony|convicted": (None, "No"),
        r"disability|veteran|eeoc": (None, "Prefer not to disclose"),
    }
    
    for pattern, (profile_path, default) in patterns.items():
        if re.search(pattern, question_lower):
            if profile_path:
                value = _get_profile_value(profile, profile_path)
                return value or default
            return default
    
    return None


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def fill_application_form(page: "Page", profile: dict, url: str = None) -> dict[str, Any]:
    """Fill application form using appropriate ATS handler.
    
    Args:
        page: Playwright page object
        profile: User profile dictionary
        url: URL to help detect ATS (optional, uses page.url if not provided)
        
    Returns:
        Dict with 'success', 'fields_filled', 'errors', 'ats_detected'
    """
    target_url = url or page.url
    ats = detect_ats(target_url)
    
    handlers = {
        "ashby": AshbyHandler,
        "greenhouse": GreenhouseHandler,
        "workday": WorkdayHandler,
        "lever": LeverHandler,
        "smartrecruiters": SmartRecruitersHandler,
    }
    
    handler_class = handlers.get(ats, GenericFormHandler)
    logger.info(f"Using {handler_class.__name__} for {target_url}")
    
    result = handler_class.fill_form(page, profile)
    result["ats_detected"] = ats
    
    return result
