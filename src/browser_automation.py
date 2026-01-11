"""
Browser Automation for Upwork Applications

Handles browser automation using Playwright to navigate Upwork pages,
fill application forms, and submit cover letters automatically.
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
import time
from playwright.async_api import async_playwright, Browser, Page, TimeoutError, Locator

from .config import get_config
from .utils import save_json_async, load_json_async, ensure_directories
from .cover_letter_gen import CoverLetterGenerator

logger = logging.getLogger(__name__)

class BrowserAutomation:
    """Handles browser automation for Upwork job applications"""
    
    def __init__(self):
        """Initialize the browser automation with configuration"""
        self.config = get_config()
        self.browser_config = self.config.get_browser_config()
        self.storage_config = self.config.get_storage_config()
        
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.cover_letter_generator = CoverLetterGenerator()
        
        logger.info("Browser automation initialized")
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.start_browser()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close_browser()
    
    async def start_browser(self) -> None:
        """Start the browser instance"""
        try:
            playwright = await async_playwright().start()
            
            # Launch browser
            browser_type = self.browser_config.get('browser_type', 'chromium')
            headless = self.browser_config.get('headless', False)
            
            launch_options = {
                'headless': headless,
                'args': [
                    '--no-sandbox',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-web-security',
                    '--disable-features=VizDisplayCompositor'
                ]
            }
            
            if browser_type == 'chromium':
                self.browser = await playwright.chromium.launch(**launch_options)
            elif browser_type == 'firefox':
                self.browser = await playwright.firefox.launch(**launch_options)
            elif browser_type == 'webkit':
                self.browser = await playwright.webkit.launch(**launch_options)
            else:
                raise ValueError(f"Unsupported browser type: {browser_type}")
            
            # Create new page with realistic user agent
            self.page = await self.browser.new_page()
            await self.page.set_extra_http_headers({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
            })
            
            # Set timeout
            timeout = self.browser_config.get('timeout', 30000)
            self.page.set_default_timeout(timeout)
            
            logger.info(f"Started {browser_type} browser (headless={headless})")
            
        except Exception as e:
            logger.error(f"Error starting browser: {e}")
            raise
    
    async def close_browser(self) -> None:
        """Close the browser instance"""
        try:
            if self.page:
                await self.page.close()
            if self.browser:
                await self.browser.close()
            logger.info("Browser closed")
        except Exception as e:
            logger.error(f"Error closing browser: {e}")
    
    async def navigate_to_job_application(self, job_url: str) -> bool:
        """
        Navigate to a job application page
        
        Args:
            job_url: URL of the Upwork job posting
        
        Returns:
            bool: True if navigation successful, False otherwise
        """
        try:
            logger.info(f"Navigating to job: {job_url}")
            
            # Add /apply to the URL if not already present
            if not job_url.endswith('/apply/') and not job_url.endswith('/apply'):
                if job_url.endswith('/'):
                    application_url = f"{job_url}apply/"
                else:
                    application_url = f"{job_url}/apply/"
            else:
                application_url = job_url
            
            await self.page.goto(application_url)
            
            # Wait for the page to load and check if we're on the application page
            try:
                # Look for common application page elements
                await self.page.wait_for_selector(
                    'textarea[aria-labelledby="cover_letter_label"], '
                    '.cover-letter-area textarea, '
                    '[data-test="cover-letter"] textarea, '
                    '.air3-textarea',
                    timeout=15000
                )
                
                logger.info("Successfully navigated to job application page")
                return True
                
            except TimeoutError:
                # Check if we need to click "Apply Now" button first
                apply_selectors = [
                    'button[data-qa="apply_now_button"]',
                    'a[data-qa="apply_now_button"]',
                    'button:has-text("Apply Now")',
                    'a:has-text("Apply Now")',
                    '.apply-button',
                    '[data-test="apply-button"]'
                ]
                
                for selector in apply_selectors:
                    try:
                        apply_button = await self.page.wait_for_selector(selector, timeout=3000)
                        if apply_button:
                            logger.info("Found Apply Now button, clicking...")
                            await apply_button.click()
                            
                            # Wait for application form to load
                            await self.page.wait_for_selector(
                                'textarea[aria-labelledby="cover_letter_label"], '
                                '.cover-letter-area textarea, '
                                '[data-test="cover-letter"] textarea',
                                timeout=10000
                            )
                            
                            logger.info("Successfully navigated to application form")
                            return True
                            
                    except TimeoutError:
                        continue
                
                logger.error("Could not find application form or Apply Now button")
                return False
                
        except Exception as e:
            logger.error(f"Error navigating to job application: {e}")
            return False
    
    async def fill_cover_letter(self, cover_letter_text: str) -> bool:
        """
        Fill the cover letter textarea with the provided text
        
        Args:
            cover_letter_text: The cover letter content to insert
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            logger.info("Looking for cover letter textarea...")
            
            # Multiple selectors to try for the cover letter field
            cover_letter_selectors = [
                'textarea[aria-labelledby="cover_letter_label"]',  # Primary selector from HTML
                'textarea.air3-textarea.inner-textarea',          # Class-based selector
                '.cover-letter-area textarea',                    # Container-based selector
                '[data-test="cover-letter"] textarea',            # Data attribute selector
                'textarea[placeholder*="cover"]',                 # Placeholder-based
                'textarea[rows="10"]',                            # Based on rows attribute
                '.air3-textarea textarea',                        # Nested textarea
                'form textarea:first-of-type'                     # Fallback to first textarea
            ]
            
            cover_letter_element = None
            for selector in cover_letter_selectors:
                try:
                    cover_letter_element = await self.page.wait_for_selector(selector, timeout=3000)
                    if cover_letter_element:
                        logger.info(f"Found cover letter field using selector: {selector}")
                        break
                except TimeoutError:
                    continue
            
            if not cover_letter_element:
                logger.error("Could not find cover letter textarea")
                return False
            
            # Clear existing content and fill with new cover letter
            await cover_letter_element.click()
            await self.page.keyboard.press('Control+A')  # Select all
            await self.page.keyboard.press('Delete')     # Delete existing content
            
            # Add a small delay to ensure the field is ready
            delay_ms = self.browser_config.get('delay_between_actions', 2000)
            await asyncio.sleep(delay_ms / 1000)
            
            # Type the cover letter with human-like timing
            await cover_letter_element.type(cover_letter_text, delay=50)
            
            logger.info("Successfully filled cover letter field")
            return True
            
        except Exception as e:
            logger.error(f"Error filling cover letter: {e}")
            return False
    
    async def submit_application(self, dry_run: bool = False) -> bool:
        """
        Submit the job application
        
        Args:
            dry_run: If True, don't actually submit (for testing)
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if dry_run:
                logger.info("Dry run mode - not actually submitting application")
                return True
            
            logger.info("Looking for submit button...")
            
            # Common submit button selectors
            submit_selectors = [
                'button[type="submit"]:has-text("Submit")',
                'button:has-text("Submit Proposal")',
                'button:has-text("Send Proposal")',
                'button[data-qa="submit_proposal"]',
                'input[type="submit"]',
                '.submit-button',
                '[data-test="submit-button"]',
                'form button:last-of-type'  # Often the last button in form
            ]
            
            submit_button = None
            for selector in submit_selectors:
                try:
                    submit_button = await self.page.wait_for_selector(selector, timeout=3000)
                    if submit_button:
                        # Check if button is enabled
                        is_disabled = await submit_button.get_attribute('disabled')
                        if not is_disabled:
                            logger.info(f"Found submit button using selector: {selector}")
                            break
                        else:
                            logger.debug(f"Submit button found but disabled: {selector}")
                except TimeoutError:
                    continue
            
            if not submit_button:
                logger.error("Could not find enabled submit button")
                return False
            
            # Take screenshot before submission (if enabled)
            if self.browser_config.get('screenshot_on_error', True):
                screenshot_path = f"screenshots/before_submit_{int(time.time())}.png"
                ensure_directories(Path(screenshot_path).parent)
                await self.page.screenshot(path=screenshot_path)
                logger.info(f"Screenshot saved: {screenshot_path}")
            
            # Click submit button
            await submit_button.click()
            
            # Wait for submission confirmation or next page
            try:
                # Look for success indicators
                success_selectors = [
                    ':has-text("Proposal sent")',
                    ':has-text("Application submitted")',
                    ':has-text("Thank you")',
                    '.success-message',
                    '[data-test="success"]'
                ]
                
                for selector in success_selectors:
                    try:
                        await self.page.wait_for_selector(selector, timeout=5000)
                        logger.info("Application submitted successfully!")
                        return True
                    except TimeoutError:
                        continue
                
                # If no explicit success message, check if URL changed
                current_url = self.page.url
                if 'apply' not in current_url or 'success' in current_url or 'thank' in current_url:
                    logger.info("Application appears to have been submitted (URL changed)")
                    return True
                
                logger.warning("Could not confirm application submission")
                return False
                
            except Exception as e:
                logger.error(f"Error confirming submission: {e}")
                return False
            
        except Exception as e:
            logger.error(f"Error submitting application: {e}")
            return False
    
    async def apply_to_job(self, job_data: Dict[str, Any], custom_prompt: Optional[str] = None) -> bool:
        """
        Complete application process for a single job
        
        Args:
            job_data: Job information dictionary
            custom_prompt: Optional custom prompt for cover letter generation
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            job_id = job_data.get('id')
            job_title = job_data.get('title', 'Unknown Job')
            job_url = job_data.get('upwork_url')
            
            if not job_url:
                logger.error(f"No URL provided for job {job_id}")
                return False
            
            logger.info(f"Starting application process for: {job_title}")
            
            # Step 1: Generate cover letter
            logger.info("Generating cover letter...")
            cover_letter_path = await self.cover_letter_generator.generate_and_save_cover_letter(
                job_data, custom_prompt
            )
            
            if not cover_letter_path:
                logger.error("Failed to generate cover letter")
                return False
            
            # Load the generated cover letter
            cover_letter_text = await self.cover_letter_generator.load_cover_letter(job_id)
            if not cover_letter_text:
                logger.error("Failed to load generated cover letter")
                return False
            
            # Step 2: Navigate to job application page
            logger.info("Navigating to application page...")
            if not await self.navigate_to_job_application(job_url):
                logger.error("Failed to navigate to application page")
                return False
            
            # Step 3: Fill cover letter
            logger.info("Filling cover letter...")
            if not await self.fill_cover_letter(cover_letter_text):
                logger.error("Failed to fill cover letter")
                return False
            
            # Step 4: Submit application (optional - can be disabled for safety)
            auto_submit = self.browser_config.get('auto_submit', True)
            if auto_submit:
                logger.info("Submitting application...")
                if not await self.submit_application():
                    logger.error("Failed to submit application")
                    return False
            else:
                logger.info("Auto-submit disabled - application ready for manual submission")
            
            # Step 5: Update application status
            await self._update_application_status(job_data, True, cover_letter_path)
            
            logger.info(f"Successfully completed application for: {job_title}")
            return True
            
        except Exception as e:
            logger.error(f"Error applying to job {job_data.get('id', 'unknown')}: {e}")
            await self._update_application_status(job_data, False, None, str(e))
            return False
    
    async def apply_to_multiple_jobs(self, job_list: List[Dict[str, Any]], 
                                   custom_prompt: Optional[str] = None) -> Dict[str, Any]:
        """
        Apply to multiple jobs in sequence
        
        Args:
            job_list: List of job data dictionaries
            custom_prompt: Optional custom prompt for cover letter generation
        
        Returns:
            Dictionary with application results and statistics
        """
        results = {
            'total_jobs': len(job_list),
            'successful_applications': 0,
            'failed_applications': 0,
            'job_results': [],
            'errors': []
        }
        
        logger.info(f"Starting batch application process for {len(job_list)} jobs")
        
        for i, job_data in enumerate(job_list, 1):
            job_id = job_data.get('id', f'job_{i}')
            job_title = job_data.get('title', 'Unknown Job')
            
            try:
                logger.info(f"Processing job {i}/{len(job_list)}: {job_title}")
                
                # Apply to the job
                success = await self.apply_to_job(job_data, custom_prompt)
                
                job_result = {
                    'job_id': job_id,
                    'job_title': job_title,
                    'success': success,
                    'timestamp': datetime.now().isoformat()
                }
                
                if success:
                    results['successful_applications'] += 1
                    logger.info(f"✓ Successfully applied to: {job_title}")
                else:
                    results['failed_applications'] += 1
                    logger.error(f"✗ Failed to apply to: {job_title}")
                
                results['job_results'].append(job_result)
                
                # Add delay between applications to avoid rate limiting
                if i < len(job_list):  # Don't wait after the last job
                    delay_seconds = self.browser_config.get('delay_between_jobs', 10)
                    logger.info(f"Waiting {delay_seconds} seconds before next application...")
                    await asyncio.sleep(delay_seconds)
                
            except Exception as e:
                error_msg = f"Unexpected error applying to job {job_id}: {e}"
                logger.error(error_msg)
                results['errors'].append(error_msg)
                results['failed_applications'] += 1
                
                job_result = {
                    'job_id': job_id,
                    'job_title': job_title,
                    'success': False,
                    'error': str(e),
                    'timestamp': datetime.now().isoformat()
                }
                results['job_results'].append(job_result)
        
        # Summary
        success_rate = (results['successful_applications'] / results['total_jobs']) * 100
        logger.info(
            f"Batch application complete: "
            f"{results['successful_applications']}/{results['total_jobs']} successful "
            f"({success_rate:.1f}% success rate)"
        )
        
        return results
    
    async def _update_application_status(self, job_data: Dict[str, Any], success: bool, 
                                       cover_letter_path: Optional[str], 
                                       error_message: Optional[str] = None) -> None:
        """
        Update the application status in the local storage
        
        Args:
            job_data: Job information
            success: Whether the application was successful
            cover_letter_path: Path to the cover letter file
            error_message: Optional error message if application failed
        """
        try:
            from datetime import datetime, timezone
            
            # Load existing applications data
            applications_file = self.storage_config.get('applications_file', 'data/applications.json')
            applications_data = await load_json_async(applications_file, default={'applications': []})
            
            # Create application record
            application_record = {
                'job_id': job_data.get('id'),
                'job_title': job_data.get('title'),
                'job_url': job_data.get('upwork_url'),
                'applied_date': datetime.now(timezone.utc).isoformat(),
                'success': success,
                'cover_letter_file': cover_letter_path,
                'error_message': error_message
            }
            
            # Add to applications list
            applications_data['applications'].append(application_record)
            
            # Save updated applications data
            await save_json_async(applications_data, applications_file)
            
            # Update job data to mark as applied
            job_data['applied'] = success
            job_data['application_date'] = application_record['applied_date']
            job_data['cover_letter_file'] = cover_letter_path
            
            logger.debug(f"Updated application status for job {job_data.get('id')}")
            
        except Exception as e:
            logger.error(f"Error updating application status: {e}")

# Convenience functions for external use
async def apply_to_jobs(job_data_list: List[Dict[str, Any]], 
                       custom_prompt: Optional[str] = None) -> Dict[str, Any]:
    """
    Apply to multiple jobs using browser automation (convenience function)
    
    Args:
        job_data_list: List of job data dictionaries
        custom_prompt: Optional custom prompt for cover letter generation
    
    Returns:
        Dictionary with application results
    """
    async with BrowserAutomation() as automation:
        return await automation.apply_to_multiple_jobs(job_data_list, custom_prompt)

async def apply_to_single_job(job_data: Dict[str, Any], 
                            custom_prompt: Optional[str] = None) -> bool:
    """
    Apply to a single job using browser automation (convenience function)
    
    Args:
        job_data: Job data dictionary
        custom_prompt: Optional custom prompt for cover letter generation
    
    Returns:
        bool: True if successful, False otherwise
    """
    async with BrowserAutomation() as automation:
        return await automation.apply_to_job(job_data, custom_prompt)

if __name__ == "__main__":
    # Test the browser automation
    async def test_automation():
        try:
            # Sample job data for testing
            job_data = {
                "id": "test_job_123",
                "title": "Python Developer Position",
                "description": "We are looking for a skilled Python developer...",
                "upwork_url": "https://www.upwork.com/jobs/~01234567890123456789"
            }
            
            success = await apply_to_single_job(job_data)
            print(f"Application {'successful' if success else 'failed'}")
            
        except Exception as e:
            print(f"Error: {e}")
    
    asyncio.run(test_automation())
