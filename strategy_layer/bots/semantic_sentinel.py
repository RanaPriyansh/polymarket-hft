"""
Bot 5: The Semantic Sentinel (Gemini Edition)

Target: News Latency Arbitrage

Logic:
1. Use Google Gemini LLM to parse news headlines
2. Detect keywords: "Resign", "Strike", "Invade", "Acquire"
3. If sentiment/event probability > threshold, trigger a trade
4. Beat the market by processing news faster than manual traders
"""

import asyncio
import os
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

# Google Gemini integration (new API)
try:
    from google import genai
    from google.genai import types
    HAS_GEMINI = True
except ImportError:
    # Fallback to old API
    try:
        import google.generativeai as genai
        HAS_GEMINI = True
    except ImportError:
        HAS_GEMINI = False
        genai = None


class SentimentSignal(Enum):
    STRONGLY_BULLISH = "strongly_bullish"
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"
    STRONGLY_BEARISH = "strongly_bearish"


@dataclass
class NewsEvent:
    """A news event detected by the Sentinel"""
    headline: str
    source: str
    timestamp: datetime
    keywords_found: list[str]
    relevant_markets: list[str]
    sentiment: SentimentSignal
    confidence: float
    raw_analysis: Optional[str] = None


@dataclass
class TradeSignal:
    """A trade signal generated from news analysis"""
    market_slug: str
    side: str  # "BUY" or "SELL"
    urgency: str  # "HIGH", "MEDIUM", "LOW"
    headline: str
    reasoning: str
    confidence: float


# Keywords that indicate market-moving events
TRIGGER_KEYWORDS = {
    # Political
    "resign": ["resignation", "resigns", "resigned", "stepping down"],
    "impeach": ["impeachment", "impeached"],
    "indicted": ["indictment", "charges filed", "arrested"],
    
    # Military/Geopolitical
    "invade": ["invasion", "invaded", "military action", "declares war"],
    "strike": ["airstrike", "missile strike", "bombing"],
    "ceasefire": ["peace deal", "truce", "armistice"],
    
    # Corporate
    "acquire": ["acquisition", "merger", "takeover", "buys"],
    "bankrupt": ["bankruptcy", "chapter 11", "insolvent"],
    "ipo": ["goes public", "listing", "direct listing"],
    
    # Regulatory
    "ban": ["banned", "prohibition", "outlawed"],
    "approve": ["approved", "authorization", "greenlight"],
    
    # Natural Events
    "earthquake": ["quake", "tremor"],
    "hurricane": ["typhoon", "cyclone", "storm"],
}


class SemanticSentinel:
    """
    Bot 5: The Semantic Sentinel (Gemini Edition)
    
    Monitors news feeds and uses Google Gemini LLM to detect
    market-moving events before they're fully priced in.
    """
    
    def __init__(
        self,
        gemini_api_key: Optional[str] = None,
        min_confidence: float = 0.75,
        model_name: str = "gemini-2.0-flash",
    ):
        self.api_key = gemini_api_key or os.getenv("GEMINI_API_KEY")
        self.min_confidence = min_confidence
        self.model_name = model_name
        self.name = "SemanticSentinel"
        
        # Market keyword mappings
        self.market_keywords: dict[str, list[str]] = {}
        
        # Initialize Gemini client
        self.client = None
        self._use_new_api = False
        
        if HAS_GEMINI and self.api_key:
            try:
                # Try new google-genai API first
                self.client = genai.Client(api_key=self.api_key)
                self._use_new_api = True
            except (TypeError, AttributeError):
                # Fall back to old API
                try:
                    genai.configure(api_key=self.api_key)
                    self.client = genai.GenerativeModel(self.model_name)
                    self._use_new_api = False
                except Exception as e:
                    print(f"Warning: Failed to initialize Gemini: {e}")
                    self.client = None
    
    def register_market(self, market_slug: str, keywords: list[str]) -> None:
        """Register a market with associated keywords to monitor."""
        self.market_keywords[market_slug] = [kw.lower() for kw in keywords]
    
    def unregister_market(self, market_slug: str) -> None:
        """Stop monitoring a market."""
        self.market_keywords.pop(market_slug, None)
    
    def _find_keywords(self, text: str) -> list[str]:
        """Find trigger keywords in text."""
        text_lower = text.lower()
        found = []
        
        for primary, variants in TRIGGER_KEYWORDS.items():
            if primary in text_lower:
                found.append(primary)
            else:
                for variant in variants:
                    if variant in text_lower:
                        found.append(primary)
                        break
        
        return list(set(found))
    
    def _find_relevant_markets(self, text: str) -> list[str]:
        """Find markets relevant to the news text."""
        text_lower = text.lower()
        relevant = []
        
        for market, keywords in self.market_keywords.items():
            for kw in keywords:
                if kw in text_lower:
                    relevant.append(market)
                    break
        
        return relevant
    
    def _quick_sentiment(self, headline: str, keywords: list[str]) -> tuple[SentimentSignal, float]:
        """Quick rule-based sentiment analysis (fallback when no LLM)."""
        # Negative keywords
        negative = ["resign", "invade", "strike", "bankrupt", "ban", "indicted"]
        # Positive keywords
        positive = ["approve", "ceasefire", "acquire"]
        
        neg_count = sum(1 for kw in keywords if kw in negative)
        pos_count = sum(1 for kw in keywords if kw in positive)
        
        if neg_count > pos_count:
            if neg_count >= 2:
                return SentimentSignal.STRONGLY_BEARISH, 0.80
            return SentimentSignal.BEARISH, 0.70
        elif pos_count > neg_count:
            if pos_count >= 2:
                return SentimentSignal.STRONGLY_BULLISH, 0.80
            return SentimentSignal.BULLISH, 0.70
        
        return SentimentSignal.NEUTRAL, 0.50
    
    async def analyze_with_llm(self, headline: str, context: str = "") -> dict:
        """
        Analyze headline using Google Gemini LLM.
        
        Returns structured analysis:
        - sentiment: bullish/bearish/neutral
        - confidence: 0-1
        - affected_markets: list of market slugs
        - reasoning: explanation
        """
        if not self.client:
            # Fallback to rule-based
            keywords = self._find_keywords(headline)
            sentiment, confidence = self._quick_sentiment(headline, keywords)
            return {
                "sentiment": sentiment.value,
                "confidence": confidence,
                "affected_markets": self._find_relevant_markets(headline),
                "reasoning": f"Rule-based analysis. Keywords: {keywords}",
            }
        
        prompt = f"""Analyze this news headline for prediction market trading:

HEADLINE: {headline}

{f'CONTEXT: {context}' if context else ''}

Registered markets we're monitoring: {list(self.market_keywords.keys())}

Provide a JSON response with:
1. "sentiment": one of "strongly_bullish", "bullish", "neutral", "bearish", "strongly_bearish"
2. "confidence": 0.0 to 1.0
3. "affected_markets": list of market slugs that would be affected
4. "reasoning": brief explanation

Respond ONLY with valid JSON, no markdown formatting."""

        try:
            # Use appropriate API based on what's available
            if self._use_new_api:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                )
                response_text = response.text.strip()
            else:
                response = self.client.generate_content(prompt)
                response_text = response.text.strip()
            
            # Parse JSON from response
            import json
            # Remove markdown code blocks if present
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            result = json.loads(response_text)
            return result
            
        except Exception as e:
            # Fallback to rule-based
            keywords = self._find_keywords(headline)
            sentiment, confidence = self._quick_sentiment(headline, keywords)
            return {
                "sentiment": sentiment.value,
                "confidence": confidence,
                "affected_markets": self._find_relevant_markets(headline),
                "reasoning": f"LLM failed ({e}), used rule-based. Keywords: {keywords}",
            }
    
    async def process_headline(self, headline: str, source: str = "unknown") -> Optional[NewsEvent]:
        """
        Process a news headline and return event if significant.
        """
        keywords = self._find_keywords(headline)
        
        if not keywords:
            return None  # No trigger keywords found
        
        relevant_markets = self._find_relevant_markets(headline)
        
        # Analyze with LLM or rules
        analysis = await self.analyze_with_llm(headline)
        
        sentiment_map = {
            "strongly_bullish": SentimentSignal.STRONGLY_BULLISH,
            "bullish": SentimentSignal.BULLISH,
            "neutral": SentimentSignal.NEUTRAL,
            "bearish": SentimentSignal.BEARISH,
            "strongly_bearish": SentimentSignal.STRONGLY_BEARISH,
        }
        
        sentiment = sentiment_map.get(analysis.get("sentiment", "neutral"), SentimentSignal.NEUTRAL)
        confidence = analysis.get("confidence", 0.5)
        
        return NewsEvent(
            headline=headline,
            source=source,
            timestamp=datetime.now(),
            keywords_found=keywords,
            relevant_markets=relevant_markets or analysis.get("affected_markets", []),
            sentiment=sentiment,
            confidence=confidence,
            raw_analysis=analysis.get("reasoning"),
        )
    
    async def generate_signals(self, event: NewsEvent) -> list[TradeSignal]:
        """
        Generate trade signals from a news event.
        """
        if event.confidence < self.min_confidence:
            return []
        
        signals = []
        
        for market in event.relevant_markets:
            # Determine trade direction based on sentiment
            if event.sentiment in [SentimentSignal.STRONGLY_BULLISH, SentimentSignal.BULLISH]:
                side = "BUY"
            elif event.sentiment in [SentimentSignal.STRONGLY_BEARISH, SentimentSignal.BEARISH]:
                side = "SELL"
            else:
                continue  # Skip neutral
            
            # Determine urgency
            if event.sentiment in [SentimentSignal.STRONGLY_BULLISH, SentimentSignal.STRONGLY_BEARISH]:
                urgency = "HIGH"
            else:
                urgency = "MEDIUM"
            
            signals.append(TradeSignal(
                market_slug=market,
                side=side,
                urgency=urgency,
                headline=event.headline,
                reasoning=event.raw_analysis or f"Keywords: {event.keywords_found}",
                confidence=event.confidence,
            ))
        
        return signals
    
    def get_monitored_markets(self) -> list[str]:
        """Get list of monitored market slugs."""
        return list(self.market_keywords.keys())
    
    def __repr__(self) -> str:
        if self.client:
            api_type = "genai" if self._use_new_api else "generativeai"
            llm_status = f"Gemini ({api_type})"
        else:
            llm_status = "rules"
        return f"SemanticSentinel(markets={len(self.market_keywords)}, mode={llm_status})"


# Convenience function for importing
def create_bot() -> SemanticSentinel:
    """Factory function to create a Semantic Sentinel bot."""
    return SemanticSentinel(
        gemini_api_key=os.getenv("GEMINI_API_KEY"),
        min_confidence=0.75,
        model_name="gemini-2.0-flash",
    )
