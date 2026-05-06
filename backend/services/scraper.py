import asyncio
import aiohttp
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import time
import re
from typing import List, Dict, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class GoogleMapsScraper:
    def __init__(self):
        self.options = webdriver.ChromeOptions()
        self.options.add_argument('--headless')  # Run in background
        self.options.add_argument('--no-sandbox')
        self.options.add_argument('--disable-dev-shm-usage')
        self.options.add_argument('--disable-blink-features=AutomationControlled')
        self.options.add_experimental_option("excludeSwitches", ["enable-automation"])
        self.options.add_experimental_option('useAutomationExtension', False)
        
    async def extract_place_id(self, url: str) -> Optional[str]:
        """Extract Google Maps place ID from URL"""
        # Pattern: !1s0x...!8e2 or /place/.../data=...
        pattern = r'!1s(.*?)!8e2'
        match = re.search(pattern, url)
        if match:
            return match.group(1)
        
        # Alternative: extract from /place/ path
        place_pattern = r'/place/([^/]+)/'
        match = re.search(place_pattern, url)
        if match:
            return match.group(1)
        
        return None
    
    async def scrape_reviews(self, business_url: str, max_reviews: int = 50) -> List[Dict]:
        """Scrape reviews from Google Maps business page"""
        driver = webdriver.Chrome(options=self.options)
        reviews_data = []
        
        try:
            # Load the page
            driver.get(business_url)
            await asyncio.sleep(3)  # Initial load
            
            # Click on reviews tab
            try:
                reviews_tab = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(@aria-label, 'Reviews')]"))
                )
                reviews_tab.click()
                await asyncio.sleep(2)
            except:
                logger.warning("Could not find reviews tab")
            
            # Sort by newest
            try:
                sort_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(@aria-label, 'Sort')]"))
                )
                sort_button.click()
                await asyncio.sleep(1)
                
                newest_option = driver.find_element(By.XPATH, "//div[contains(text(), 'Newest')]")
                newest_option.click()
                await asyncio.sleep(2)
            except:
                logger.warning("Could not sort by newest")
            
            # Scroll and collect reviews
            scroll_attempts = 0
            collected_reviews = set()
            
            while len(reviews_data) < max_reviews and scroll_attempts < 10:
                # Find review elements
                review_elements = driver.find_elements(By.XPATH, "//div[@jsname='fk8dgd']")
                
                for element in review_elements:
                    try:
                        # Extract review data
                        reviewer_name = element.find_element(By.XPATH, ".//div[@class='d4r55']").text
                        rating = await self._extract_rating(element)
                        review_text = await self._extract_review_text(element)
                        review_date = await self._extract_date(element)
                        
                        # Create unique ID for review
                        review_id = f"{reviewer_name}_{review_date}"
                        
                        if review_id not in collected_reviews and review_text:
                            collected_reviews.add(review_id)
                            reviews_data.append({
                                'review_id': review_id,
                                'reviewer_name': reviewer_name,
                                'rating': rating,
                                'review_text': review_text,
                                'review_date': review_date,
                                'is_negative': rating <= 2.0
                            })
                            
                    except Exception as e:
                        logger.error(f"Error extracting review: {e}")
                        continue
                
                # Scroll down
                driver.execute_script("window.scrollBy(0, 1000);")
                await asyncio.sleep(2)
                scroll_attempts += 1
            
            logger.info(f"Scraped {len(reviews_data)} reviews from {business_url}")
            return reviews_data[:max_reviews]
            
        except Exception as e:
            logger.error(f"Error scraping reviews: {e}")
            return []
        finally:
            driver.quit()
    
    async def _extract_rating(self, element) -> float:
        """Extract star rating from review element"""
        try:
            rating_element = element.find_element(By.XPATH, ".//span[@aria-label]")
            aria_label = rating_element.get_attribute("aria-label")
            # Extract number from "Rated X out of 5 stars"
            match = re.search(r'(\d+)', aria_label)
            if match:
                return float(match.group(1))
        except:
            pass
        return 0
    
    async def _extract_review_text(self, element) -> str:
        """Extract review text"""
        try:
            text_element = element.find_element(By.XPATH, ".//span[@class='wiI7pd']")
            return text_element.text
        except:
            return ""
    
    async def _extract_date(self, element) -> Optional[datetime]:
        """Extract review date"""
        try:
            date_element = element.find_element(By.XPATH, ".//span[@class='rsqaWe']")
            date_text = date_element.text
            # Parse relative dates like "2 days ago", "last week", etc.
            return datetime.now()  # Simplified - implement proper parsing
        except:
            return datetime.now()

# Alternative: Use requests + BeautifulSoup for simpler scraping
class SimpleReviewScraper:
    """Lightweight scraper using requests (less reliable but faster)"""
    
    async def scrape_reviews(self, business_url: str) -> List[Dict]:
        # This would use Google Places API or a scraping service
        # For MVP, recommend using Selenium or a 3rd party API
        pass