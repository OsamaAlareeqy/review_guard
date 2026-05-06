from celery import Celery
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import select
import asyncio
from datetime import datetime, timedelta
import logging

from app.services.scraper import GoogleMapsScraper
from app.services.review_analyzer import ReviewAnalyzer
from app.services.alert_service import AlertService
from app.models import Business, Review, ScraperLog, User, UserRole
from app.database import AsyncSessionLocal
from app.config import settings

logger = logging.getLogger(__name__)

# Initialize Celery
celery_app = Celery(
    'review_collector',
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,
)

class ReviewCollector:
    def __init__(self):
        self.scraper = GoogleMapsScraper()
        self.analyzer = ReviewAnalyzer()
        self.alert_service = AlertService()
    
    async def collect_reviews_for_business(self, business_id: int):
        """Collect reviews for a specific business"""
        async with AsyncSessionLocal() as db:
            # Get business
            result = await db.execute(select(Business).where(Business.id == business_id))
            business = result.scalar_one_or_none()
            
            if not business or not business.is_active:
                return
            
            # Create log entry
            log = ScraperLog(
                business_id=business_id,
                status='running',
                started_at=datetime.utcnow()
            )
            db.add(log)
            await db.commit()
            
            try:
                # Scrape reviews
                reviews_data = await self.scraper.scrape_reviews(
                    business.google_maps_url,
                    max_reviews=settings.MAX_REVIEWS_PER_BUSINESS
                )
                
                new_reviews = 0
                for review_data in reviews_data:
                    # Check if review exists
                    existing = await db.execute(
                        select(Review).where(Review.review_id == review_data['review_id'])
                    )
                    if existing.scalar_one_or_none():
                        continue
                    
                    # Analyze review
                    analysis = self.analyzer.analyze_review(
                        review_data['review_text'],
                        review_data['rating']
                    )
                    
                    # Create review record
                    review = Review(
                        business_id=business_id,
                        review_id=review_data['review_id'],
                        reviewer_name=review_data['reviewer_name'],
                        rating=review_data['rating'],
                        review_text=review_data['review_text'],
                        review_date=review_data['review_date'],
                        is_negative=analysis['is_negative'],
                        complaint_category=analysis['complaint_category'],
                        urgency_score=analysis['urgency_score'],
                        complaint_summary=analysis['complaint_summary']
                    )
                    
                    db.add(review)
                    
                    # Send instant alert if review is negative and user is pro
                    if analysis['is_negative']:
                        await self.alert_service.send_instant_alert(
                            db, review, business
                        )
                    
                    new_reviews += 1
                
                # Update business
                business.last_scraped_at = datetime.utcnow()
                
                # Update log
                log.status = 'success'
                log.reviews_found = len(reviews_data)
                log.reviews_new = new_reviews
                log.completed_at = datetime.utcnow()
                
                await db.commit()
                
                logger.info(f"Collected {new_reviews} new reviews for business {business.business_name}")
                
            except Exception as e:
                logger.error(f"Error collecting reviews for business {business_id}: {e}")
                log.status = 'failed'
                log.error_message = str(e)
                log.completed_at = datetime.utcnow()
                await db.commit()
    
    async def collect_all_reviews(self):
        """Collect reviews for all active businesses"""
        async with AsyncSessionLocal() as db:
            # Get all active businesses
            result = await db.execute(
                select(Business).where(Business.is_active == True)
            )
            businesses = result.scalars().all()
            
            logger.info(f"Starting review collection for {len(businesses)} businesses")
            
            for business in businesses:
                await self.collect_reviews_for_business(business.id)
                # Add delay between businesses
                await asyncio.sleep(5)

@celery_app.task
def scheduled_review_collection():
    """Celery task to run review collection on schedule"""
    collector = ReviewCollector()
    asyncio.run(collector.collect_all_reviews())

@celery_app.task
def daily_summary_emails():
    """Send daily summary emails to free users"""
    alert_service = AlertService()
    asyncio.run(alert_service.send_daily_summaries())