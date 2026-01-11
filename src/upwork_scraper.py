"""
Upwork Job Scraper

Extracts saved jobs from Upwork using Playwright browser automation.
Handles authentication, pagination, and job data extraction.
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from playwright.async_api import async_playwright, Browser, Page, TimeoutError
from bs4 import BeautifulSoup

from .config import get_config
from .utils import (
    save_json_async, load_json_async, validate_job_data, 
    extract_upwork_job_id, retry_async, ensure_directories
)

logger = logging.getLogger(__name__)

class UpworkScraper:
    """Handles extraction of saved jobs from Upwork"""
    
    def __init__(self):
        """Initialize the scraper with configuration"""
        self.config = get_config()
        self.upwork_config = self.config.get_upwork_config()
        self.browser_config = self.config.get_browser_config()
        self.storage_config = self.config.get_storage_config()
        
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        
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
            
            if browser_type == 'chromium':
                self.browser = await playwright.chromium.launch(headless=headless)
            elif browser_type == 'firefox':
                self.browser = await playwright.firefox.launch(headless=headless)
            elif browser_type == 'webkit':
                self.browser = await playwright.webkit.launch(headless=headless)
            else:
                raise ValueError(f"Unsupported browser type: {browser_type}")
            
            # Create new page
            self.page = await self.browser.new_page()
            
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
    
    async def login_to_upwork(self, email: Optional[str] = None) -> bool:
        """
        Handle Upwork login process (manual for now)
        
        Args:
            email: Optional email for auto-fill
        
        Returns:
            bool: True if login successful, False otherwise
        """
        try:
            base_url = self.upwork_config.get('base_url', 'https://www.upwork.com')
            login_url = self.upwork_config.get('login_url', '/ab/account-security/login')
            full_login_url = f"{base_url}{login_url}"
            
            logger.info(f"Navigating to login page: {full_login_url}")
            await self.page.goto(full_login_url)
            
            # Wait for login form to load
            await self.page.wait_for_selector('form', timeout=10000)
            
            # Fill email if provided
            if email:
                try:
                    email_input = await self.page.wait_for_selector('input[type="email"], input[name="login"]', timeout=5000)
                    if email_input:
                        await email_input.fill(email)
                        logger.info(f"Auto-filled email: {email}")
                except Exception as e:
                    logger.warning(f"Could not auto-fill email: {e}")
            
            # Wait for user to complete login manually
            print("\n" + "="*60)
            print("MANUAL LOGIN REQUIRED")
            print("="*60)
            print("Please complete the login process in the browser window.")
            print("After successful login, you should be redirected to the dashboard.")
            print("Press Enter here when login is complete...")
            print("="*60)
            
            input("Press Enter after completing login: ")
            
            # Check if login was successful by looking for user profile or dashboard
            try:
                await self.page.wait_for_selector(
                    '[data-test="logged-in-user"], .navbar-logged-in, .nav-user',
                    timeout=5000
                )
                logger.info("Login appears successful")
                return True
            except TimeoutError:
                logger.warning("Could not confirm successful login")
                # Continue anyway, might still work
                return True
                
        except Exception as e:
            logger.error(f"Error during login process: {e}")
            return False
    
    async def navigate_to_saved_jobs(self) -> bool:
        """
        Navigate to the saved jobs page
        
        Returns:
            bool: True if navigation successful, False otherwise
        """
        try:
            base_url = self.upwork_config.get('base_url', 'https://www.upwork.com')
            saved_jobs_url = self.upwork_config.get('saved_jobs_url', '/nx/search/jobs/saved')
            full_url = f"{base_url}{saved_jobs_url}"
            
            logger.info(f"Navigating to saved jobs: {full_url}")
            await self.page.goto(full_url)
            
            # Wait for jobs to load
            await self.page.wait_for_selector('[data-test="job-tile"], .job-tile, article', timeout=15000)
            
            logger.info("Successfully navigated to saved jobs page")
            return True
            
        except TimeoutError:
            logger.error("Timeout waiting for saved jobs page to load")
            return False
        except Exception as e:
            logger.error(f"Error navigating to saved jobs: {e}")
            return False
    
    async def extract_jobs_from_page(self) -> List[Dict[str, Any]]:
        """
        Extract job data from the current page
        
        Returns:
            List of job dictionaries
        """
        jobs = []
        
        try:
            # Get page content
            content = await self.page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            # Find job tiles/cards (try multiple selectors)
            job_selectors = [
                '[data-test="job-tile"]',
                '.job-tile',
                'article[data-test*="job"]',
                '.saved-job',
                '[data-cy="job-tile"]'
            ]
            
            job_elements = []
            for selector in job_selectors:
                elements = await self.page.query_selector_all(selector)
                if elements:
                    job_elements = elements
                    logger.info(f"Found {len(elements)} job elements using selector: {selector}")
                    break
            
            if not job_elements:
                logger.warning("No job elements found on page")
                return jobs
            
            # Extract data from each job element
            for i, job_element in enumerate(job_elements):
                try:
                    job_data = await self._extract_job_data(job_element)
                    if job_data and validate_job_data(job_data):
                        jobs.append(job_data)
                        logger.debug(f"Extracted job {i+1}: {job_data.get('title', 'Unknown')}")
                    else:
                        logger.warning(f"Invalid job data for element {i+1}")
                        
                except Exception as e:
                    logger.error(f"Error extracting job {i+1}: {e}")
                    continue
            
            logger.info(f"Successfully extracted {len(jobs)} jobs from page")
            
        except Exception as e:
            logger.error(f"Error extracting jobs from page: {e}")
        
        return jobs
    
    async def _extract_job_data(self, job_element) -> Optional[Dict[str, Any]]:
        """
        Extract data from a single job element
        
        Args:
            job_element: Playwright element handle
        
        Returns:
            Job data dictionary or None
        """
        try:
            # Get job element HTML for parsing
            html = await job_element.inner_html()
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract job URL
            url_link = soup.find('a', href=True)
            if not url_link:
                # Try to find link in parent element
                parent_html = await job_element.evaluate('el => el.parentElement.innerHTML')
                parent_soup = BeautifulSoup(parent_html, 'html.parser')
                url_link = parent_soup.find('a', href=True)
            
            if not url_link:
                logger.warning("Could not find job URL")
                return None
            
            upwork_url = url_link['href']
            if not upwork_url.startswith('http'):
                base_url = self.upwork_config.get('base_url', 'https://www.upwork.com')
                upwork_url = f"{base_url}{upwork_url}"
            
            # Extract job ID from URL
            job_id = extract_upwork_job_id(upwork_url)
            if not job_id:
                job_id = f"job_{hash(upwork_url) % 1000000}"
            
            # Extract title
            title_selectors = [
                'h4 a', 'h3 a', 'h2 a', 'h5 a',
                '[data-test="job-title"] a', '.job-title a',
                'a[data-test*="title"]', '.title a'
            ]
            
            title = "Unknown Title"
            for selector in title_selectors:
                title_elem = soup.select_one(selector)
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    break
            
            # Extract description/excerpt
            description_selectors = [
                '[data-test="job-description"]', '.job-description',
                'p', '.excerpt', '.summary'
            ]
            
            description = ""
            for selector in description_selectors:
                desc_elem = soup.select_one(selector)
                if desc_elem:
                    description = desc_elem.get_text(strip=True)
                    if len(description) > 50:  # Only use if substantial
                        break
            
            # Extract budget/rate
            budget_selectors = [
                '[data-test*="budget"]', '.budget', '[data-test*="rate"]',
                '.hourly-rate', '.fixed-price', '.job-amount'
            ]
            
            budget = "Not specified"
            for selector in budget_selectors:
                budget_elem = soup.select_one(selector)
                if budget_elem:
                    budget = budget_elem.get_text(strip=True)
                    break
            
            # Extract client rating (if available)
            rating_selectors = [
                '[data-test*="rating"]', '.rating', '.client-rating',
                '.star-rating', '[data-test*="star"]'
            ]
            
            client_rating = None
            for selector in rating_selectors:
                rating_elem = soup.select_one(selector)
                if rating_elem:
                    rating_text = rating_elem.get_text(strip=True)
                    # Try to extract numeric rating
                    import re
                    rating_match = re.search(r'(\d+\.?\d*)', rating_text)
                    if rating_match:
                        try:
                            client_rating = float(rating_match.group(1))
                            break
                        except ValueError:
                            pass
            
            # Extract client location (if available)
            location_selectors = [
                '[data-test*="location"]', '.location', '.client-location',
                '.country', '[data-test*="country"]'
            ]
            
            client_location = "Unknown"
            for selector in location_selectors:
                location_elem = soup.select_one(selector)
                if location_elem:
                    client_location = location_elem.get_text(strip=True)
                    break
            
            # Create job data object
            job_data = {
                'id': job_id,
                'title': title,
                'description': description,
                'budget': budget,
                'client_rating': client_rating,
                'client_location': client_location,
                'upwork_url': upwork_url,
                'saved_date': datetime.now(timezone.utc).isoformat(),
                'applied': False,
                'application_date': None,
                'cover_letter_file': None
            }
            
            return job_data
            
        except Exception as e:
            logger.error(f"Error extracting job data from element: {e}")
            return None
    
    async def handle_pagination(self) -> bool:
        """
        Check if there are more pages and navigate to next page
        
        Returns:
            bool: True if there's a next page, False otherwise
        """
        try:
            # Look for next page button
            next_selectors = [
                '[data-test="pagination"] [aria-label="Next"]',
                '.pagination .next:not(.disabled)',
                '[data-test*="next"]:not([disabled])',
                'button[aria-label*="Next"]:not([disabled])'
            ]
            
            for selector in next_selectors:
                next_button = await self.page.query_selector(selector)
                if next_button:
                    # Check if button is enabled
                    is_disabled = await next_button.get_attribute('disabled')
                    if not is_disabled:
                        logger.info("Found next page button, clicking...")
                        await next_button.click()
                        
                        # Wait for new page to load
                        await asyncio.sleep(2)
                        await self.page.wait_for_selector('[data-test="job-tile"], .job-tile, article', timeout=10000)
                        
                        return True
            
            logger.info("No more pages found")
            return False
            
        except Exception as e:
            logger.error(f"Error handling pagination: {e}")
            return False
    
    async def extract_all_saved_jobs(self, email: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Extract all saved jobs from Upwork
        
        Args:
            email: Optional email for auto-login
        
        Returns:
            List of all job data
        """
        all_jobs = []
        
        try:
            logger.info("Starting job extraction process")
            
            # Login to Upwork
            if not await self.login_to_upwork(email):
                raise Exception("Failed to login to Upwork")
            
            # Navigate to saved jobs
            if not await self.navigate_to_saved_jobs():
                raise Exception("Failed to navigate to saved jobs page")
            
            # Extract jobs from all pages
            page_count = 0
            while True:
                page_count += 1
                logger.info(f"Extracting jobs from page {page_count}")
                
                # Extract jobs from current page
                page_jobs = await self.extract_jobs_from_page()
                all_jobs.extend(page_jobs)
                
                logger.info(f"Found {len(page_jobs)} jobs on page {page_count}")
                
                # Check for next page
                if not await self.handle_pagination():
                    break
                
                # Add delay between pages
                delay = self.browser_config.get('delay_between_actions', 2000) / 1000
                await asyncio.sleep(delay)
            
            logger.info(f"Extraction complete. Found {len(all_jobs)} total jobs across {page_count} pages")
            
            # Remove duplicates based on job ID
            unique_jobs = {}
            for job in all_jobs:
                job_id = job.get('id')
                if job_id and job_id not in unique_jobs:
                    unique_jobs[job_id] = job
            
            all_jobs = list(unique_jobs.values())
            logger.info(f"After removing duplicates: {len(all_jobs)} unique jobs")
            
        except Exception as e:
            logger.error(f"Error extracting saved jobs: {e}")
            raise
        
        return all_jobs
    
    async def save_jobs_to_file(self, jobs: List[Dict[str, Any]]) -> bool:
        """
        Save jobs to JSON file
        
        Args:
            jobs: List of job data
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            jobs_file = self.storage_config.get('jobs_file', 'data/jobs.json')
            
            # Ensure directory exists
            ensure_directories(Path(jobs_file).parent)
            
            # Load existing jobs to merge
            existing_jobs = await load_json_async(jobs_file, default=[])
            existing_job_ids = {job.get('id') for job in existing_jobs if job.get('id')}
            
            # Merge new jobs with existing ones
            merged_jobs = list(existing_jobs)
            new_job_count = 0
            
            for job in jobs:
                job_id = job.get('id')
                if job_id and job_id not in existing_job_ids:
                    merged_jobs.append(job)
                    new_job_count += 1
            
            # Save merged jobs
            success = await save_json_async(merged_jobs, jobs_file)
            
            if success:
                logger.info(f"Saved {len(merged_jobs)} total jobs ({new_job_count} new) to {jobs_file}")
            else:
                logger.error("Failed to save jobs to file")
            
            return success
            
        except Exception as e:
            logger.error(f"Error saving jobs to file: {e}")
            return False
    
    async def load_jobs_from_file(self) -> List[Dict[str, Any]]:
        """
        Load jobs from JSON file
        
        Returns:
            List of job data
        """
        try:
            jobs_file = self.storage_config.get('jobs_file', 'data/jobs.json')
            jobs = await load_json_async(jobs_file, default=[])
            logger.info(f"Loaded {len(jobs)} jobs from {jobs_file}")
            return jobs
            
        except Exception as e:
            logger.error(f"Error loading jobs from file: {e}")
            return []

# Convenience functions for external use
async def extract_saved_jobs(email: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Extract saved jobs from Upwork (convenience function)
    
    Args:
        email: Optional email for auto-login
    
    Returns:
        List of job data
    """
    async with UpworkScraper() as scraper:
        jobs = await scraper.extract_all_saved_jobs(email)
        await scraper.save_jobs_to_file(jobs)
        return jobs

async def load_saved_jobs() -> List[Dict[str, Any]]:
    """
    Load saved jobs from file (convenience function)
    
    Returns:
        List of job data
    """
    scraper = UpworkScraper()
    return await scraper.load_jobs_from_file()

if __name__ == "__main__":
    # Test the scraper
    async def test_scraper():
        try:
            jobs = await extract_saved_jobs()
            print(f"Extracted {len(jobs)} jobs")
            for job in jobs[:3]:  # Show first 3 jobs
                print(f"- {job.get('title', 'Unknown')}: {job.get('budget', 'N/A')}")
        except Exception as e:
            print(f"Error: {e}")
    
    asyncio.run(test_scraper())
