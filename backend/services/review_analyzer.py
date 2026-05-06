import re
from typing import Dict, List, Tuple
from collections import Counter

class ReviewAnalyzer:
    # Negative keywords mapping to categories
    NEGATIVE_KEYWORDS = {
        'rude staff': ['rude', 'unfriendly', 'arrogant', 'disrespectful', 'ignorant'],
        'slow service': ['slow', 'waiting', 'delay', 'late', 'took too long'],
        'cleanliness': ['dirty', 'filthy', 'disgusting', 'messy', 'unclean', 'mold'],
        'pricing': ['expensive', 'overpriced', 'pricey', 'costly', 'rip off', 'waste of money'],
        'waiting time': ['queue', 'line', 'wait', 'delayed', 'backlog'],
        'product quality': ['bad quality', 'terrible', 'awful', 'horrible', 'poor quality', 'defective'],
        'food quality': ['tasteless', 'cold', 'raw', 'burnt', 'stale', 'bland'],
        'service': ['bad service', 'poor service', 'terrible experience', 'disappointing'],
        'scam': ['scam', 'fraud', 'fake', 'liar', 'dishonest']
    }
    
    # Urgency indicators
    URGENCY_INDICATORS = {
        10: ['health hazard', 'dangerous', 'emergency', 'lawsuit'],
        8: ['scam', 'fraud', 'stolen', 'illegal'],
        6: ['rude', 'insult', 'yelled', 'shouted'],
        4: ['dirty', 'broken', 'disappointed'],
        2: ['slow', 'expensive', 'wait']
    }
    
    @classmethod
    def analyze_review(cls, review_text: str, rating: float) -> Dict:
        """Analyze review and extract insights"""
        review_text_lower = review_text.lower()
        
        # Determine if negative
        is_negative = rating <= 2.0 or cls._has_negative_keywords(review_text_lower)
        
        if not is_negative:
            return {
                'is_negative': False,
                'complaint_category': None,
                'urgency_score': 0,
                'complaint_summary': None
            }
        
        # Categorize complaint
        category = cls._categorize_complaint(review_text_lower)
        
        # Calculate urgency score
        urgency_score = cls._calculate_urgency(review_text_lower)
        
        # Generate summary
        summary = cls._generate_summary(review_text, category, urgency_score)
        
        return {
            'is_negative': True,
            'complaint_category': category,
            'urgency_score': urgency_score,
            'complaint_summary': summary
        }
    
    @classmethod
    def _has_negative_keywords(cls, text: str) -> bool:
        """Check if text contains negative keywords"""
        all_keywords = []
        for keywords in cls.NEGATIVE_KEYWORDS.values():
            all_keywords.extend(keywords)
        
        for keyword in all_keywords:
            if keyword in text:
                return True
        return False
    
    @classmethod
    def _categorize_complaint(cls, text: str) -> str:
        """Categorize the complaint based on keywords"""
        scores = Counter()
        
        for category, keywords in cls.NEGATIVE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text:
                    scores[category] += 1
        
        if scores:
            return scores.most_common(1)[0][0]
        return 'other'
    
    @classmethod
    def _calculate_urgency(cls, text: str) -> int:
        """Calculate urgency score from 1-10"""
        max_urgency = 0
        
        for urgency, indicators in cls.URGENCY_INDICATORS.items():
            for indicator in indicators:
                if indicator in text:
                    max_urgency = max(max_urgency, urgency)
        
        return max_urgency if max_urgency > 0 else 3
    
    @classmethod
    def _generate_summary(cls, full_text: str, category: str, urgency: int) -> str:
        """Generate a brief summary of the complaint"""
        # Extract key sentence (first 100 chars or first sentence)
        sentences = full_text.split('.')
        if sentences:
            first_sentence = sentences[0][:100]
        else:
            first_sentence = full_text[:100]
        
        urgency_level = "Critical" if urgency >= 8 else "High" if urgency >= 6 else "Medium" if urgency >= 4 else "Low"
        
        return f"{urgency_level} urgency: {first_sentence}..."