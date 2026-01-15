"""
Bot 3: The Resolution Sniper

Target: UMA Optimistic Oracle Liveness Period

Logic:
1. Listen for QuestionInitialized events on the CTF Adapter
2. Compare the "Proposed Answer" to an external API (oracle/news)
3. If market trades at <0.99 but answer is confirmed "Yes", BUY
4. If market trades at >0.01 but answer is confirmed "No", SELL
"""

import asyncio
import json
import os
from dataclasses import dataclass
from enum import Enum
from typing import Optional
import httpx


class ResolutionOutcome(Enum):
    YES = "yes"
    NO = "no"
    UNKNOWN = "unknown"


@dataclass
class PendingResolution:
    """A market pending resolution"""
    condition_id: str
    question_id: str
    proposed_answer: str
    liveness_ends_at: int
    current_price: float
    external_answer: Optional[str] = None
    confidence: float = 0.0
    action: Optional[str] = None


@dataclass
class SniperOpportunity:
    """An opportunity detected by the Resolution Sniper"""
    condition_id: str
    token_id: str
    side: str  # "BUY" or "SELL"
    current_price: float
    expected_resolution: str
    confidence: float
    expected_profit_bps: float


class ResolutionSniper:
    """
    Bot 3: The Resolution Sniper
    
    Monitors UMA Optimistic Oracle liveness periods and snipes
    markets where the proposed answer is highly likely to be correct
    but the market hasn't fully priced it in.
    """
    
    def __init__(
        self,
        ctf_adapter_address: str = "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296",
        min_confidence: float = 0.90,
        min_profit_bps: float = 100.0,
    ):
        self.ctf_adapter = ctf_adapter_address
        self.min_confidence = min_confidence
        self.min_profit_bps = min_profit_bps
        self.pending: dict[str, PendingResolution] = {}
        self.name = "ResolutionSniper"
        
    def add_pending(
        self,
        condition_id: str,
        question_id: str,
        proposed_answer: str,
        liveness_ends_at: int,
        current_price: float,
    ) -> None:
        """Add a market with pending resolution to watch list."""
        self.pending[condition_id] = PendingResolution(
            condition_id=condition_id,
            question_id=question_id,
            proposed_answer=proposed_answer,
            liveness_ends_at=liveness_ends_at,
            current_price=current_price,
        )
    
    def remove_pending(self, condition_id: str) -> None:
        """Remove a resolved market from watch list."""
        self.pending.pop(condition_id, None)
    
    async def check_external_oracle(
        self, 
        question_id: str,
        proposed_answer: str,
    ) -> tuple[str, float]:
        """
        Check external sources to verify the proposed answer.
        
        Returns: (confirmed_answer, confidence)
        
        In production, this would call:
        - News APIs (AP, Reuters)
        - Official government sources
        - Sports APIs (ESPN, etc.)
        - Crypto price feeds (CoinGecko, etc.)
        
        For now, we mock this with a simple heuristic.
        """
        # MOCK: In production, replace with actual API calls
        # This simulates checking if the oracle answer matches reality
        
        # Simulate high confidence for most resolutions
        # In reality, you'd call actual oracle/news APIs
        return proposed_answer, 0.95
    
    async def scan(self) -> list[SniperOpportunity]:
        """
        Scan all pending resolutions for sniper opportunities.
        
        An opportunity exists when:
        1. External oracle confirms the proposed answer
        2. Market price hasn't fully reflected this
        3. Liveness period is still active (not disputed)
        """
        opportunities = []
        
        for condition_id, pending in self.pending.items():
            # Check external oracle
            confirmed_answer, confidence = await self.check_external_oracle(
                pending.question_id,
                pending.proposed_answer,
            )
            
            pending.external_answer = confirmed_answer
            pending.confidence = confidence
            
            if confidence < self.min_confidence:
                continue
            
            # Determine if there's a pricing discrepancy
            current = pending.current_price
            
            if confirmed_answer.lower() == "yes":
                # Market should be at ~1.0, if it's lower, BUY
                if current < 0.99:
                    expected_profit_bps = (1.0 - current) / current * 10_000
                    if expected_profit_bps >= self.min_profit_bps:
                        opportunities.append(SniperOpportunity(
                            condition_id=condition_id,
                            token_id=f"{condition_id}_YES",
                            side="BUY",
                            current_price=current,
                            expected_resolution="YES",
                            confidence=confidence,
                            expected_profit_bps=expected_profit_bps,
                        ))
                        pending.action = "BUY_YES"
                        
            elif confirmed_answer.lower() == "no":
                # YES token should go to 0, if it's higher, SELL
                if current > 0.01:
                    expected_profit_bps = current / (1.0 - current) * 10_000
                    if expected_profit_bps >= self.min_profit_bps:
                        opportunities.append(SniperOpportunity(
                            condition_id=condition_id,
                            token_id=f"{condition_id}_YES",
                            side="SELL",
                            current_price=current,
                            expected_resolution="NO",
                            confidence=confidence,
                            expected_profit_bps=expected_profit_bps,
                        ))
                        pending.action = "SELL_YES"
        
        return opportunities
    
    def get_pending_count(self) -> int:
        """Get number of markets being monitored."""
        return len(self.pending)
    
    def get_pending_list(self) -> list[dict]:
        """Get list of pending resolutions."""
        return [
            {
                "condition_id": p.condition_id,
                "proposed_answer": p.proposed_answer,
                "current_price": p.current_price,
                "action": p.action,
            }
            for p in self.pending.values()
        ]

    def __repr__(self) -> str:
        return f"ResolutionSniper(pending={len(self.pending)}, min_confidence={self.min_confidence})"


# Convenience function for importing
def create_bot() -> ResolutionSniper:
    """Factory function to create a Resolution Sniper bot."""
    return ResolutionSniper(
        ctf_adapter_address=os.getenv("NEGRISK_ADAPTER", "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296"),
        min_confidence=0.90,
        min_profit_bps=100.0,
    )
