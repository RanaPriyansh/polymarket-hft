"""
Correlation Scanner Python Wrapper
Interfaces with Rust DAG-based scanner via PyO3 FFI
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import List, Dict, Optional
import json
import structlog

log = structlog.get_logger()


@dataclass
class MarketNode:
    """Python representation of a market in the DAG"""
    market_id: str
    token_id: str
    description: str
    current_price: Optional[Decimal] = None
    
    def to_json(self) -> str:
        return json.dumps({
            "market_id": self.market_id,
            "token_id": self.token_id,
            "description": self.description,
            "current_price": str(self.current_price) if self.current_price else None,
        })


@dataclass
class Violation:
    """A detected correlation violation"""
    violation_type: str
    parent_market: str
    child_market: str
    parent_price: Decimal
    child_price: Decimal
    expected_relation: str
    arbitrage_edge_bps: int


@dataclass
class DutchBookTrade:
    """Trade to exploit a violation"""
    long_market: str
    long_token_id: str
    short_market: str
    short_token_id: str
    expected_profit_bps: int


class CorrelationScannerPy:
    """
    Python wrapper for Rust Correlation Scanner
    Falls back to pure Python if Rust module not available
    """
    
    def __init__(self, min_edge_bps: int = 50, use_rust: bool = True):
        self.min_edge_bps = min_edge_bps
        self._rust_scanner = None
        
        if use_rust:
            try:
                from polymarket_muscle import PyCorrelationScanner
                self._rust_scanner = PyCorrelationScanner(min_edge_bps)
                log.info("rust_scanner_loaded")
            except ImportError:
                log.warning("rust_scanner_not_available", fallback="python")
                
        # Pure Python fallback storage
        self._markets: Dict[str, MarketNode] = {}
        self._relationships: List[tuple] = []

    def add_market(self, market: MarketNode):
        """Add a market node to the DAG"""
        if self._rust_scanner:
            self._rust_scanner.add_market(market.to_json())
        else:
            self._markets[market.market_id] = market

    def add_relationship(
        self, 
        parent_id: str, 
        child_id: str, 
        relation: str, 
        weight: float = 1.0
    ):
        """Add a relationship between markets"""
        if self._rust_scanner:
            self._rust_scanner.add_relationship(parent_id, child_id, relation, weight)
        else:
            self._relationships.append((parent_id, child_id, relation, weight))

    def update_price(self, market_id: str, price: Decimal):
        """Update a market's current price"""
        if self._rust_scanner:
            self._rust_scanner.update_price(market_id, str(price))
        elif market_id in self._markets:
            self._markets[market_id].current_price = price

    def scan(self) -> List[Violation]:
        """Scan for violations"""
        if self._rust_scanner:
            result = self._rust_scanner.scan()
            violations_data = json.loads(result)
            return [
                Violation(
                    violation_type=v["violation_type"],
                    parent_market=v["parent_market"],
                    child_market=v["child_market"],
                    parent_price=Decimal(str(v["parent_price"])),
                    child_price=Decimal(str(v["child_price"])),
                    expected_relation=v["expected_relation"],
                    arbitrage_edge_bps=v["arbitrage_edge_bps"],
                )
                for v in violations_data
            ]
        else:
            return self._scan_python()

    def _scan_python(self) -> List[Violation]:
        """Pure Python fallback scanner"""
        violations = []
        
        for parent_id, child_id, relation, _ in self._relationships:
            parent = self._markets.get(parent_id)
            child = self._markets.get(child_id)
            
            if not parent or not child:
                continue
            if parent.current_price is None or child.current_price is None:
                continue
                
            pp = parent.current_price
            cp = child.current_price
            
            if relation.lower() in ("implies", "contains") and cp > pp:
                edge_bps = int((cp - pp) / pp * 10000)
                if edge_bps >= self.min_edge_bps:
                    vtype = "MonotonicityViolation" if relation == "implies" else "SubsetViolation"
                    violations.append(Violation(
                        violation_type=vtype,
                        parent_market=parent_id,
                        child_market=child_id,
                        parent_price=pp,
                        child_price=cp,
                        expected_relation="P(Child) <= P(Parent)",
                        arbitrage_edge_bps=edge_bps,
                    ))
                    
        return violations

    def generate_dutch_book(self, violation: Violation) -> Optional[DutchBookTrade]:
        """Generate a Dutch Book trade for a violation"""
        parent = self._markets.get(violation.parent_market)
        child = self._markets.get(violation.child_market)
        
        if not parent or not child:
            return None
            
        return DutchBookTrade(
            long_market=violation.parent_market,
            long_token_id=parent.token_id,
            short_market=violation.child_market,
            short_token_id=child.token_id,
            expected_profit_bps=violation.arbitrage_edge_bps,
        )


# Example market relationships for Bitcoin price targets
def setup_bitcoin_dag(scanner: CorrelationScannerPy):
    """Set up a DAG for Bitcoin price target markets"""
    markets = [
        MarketNode("btc_50k", "token_50k", "Bitcoin > $50K"),
        MarketNode("btc_60k", "token_60k", "Bitcoin > $60K"),
        MarketNode("btc_70k", "token_70k", "Bitcoin > $70K"),
        MarketNode("btc_80k", "token_80k", "Bitcoin > $80K"),
        MarketNode("btc_90k", "token_90k", "Bitcoin > $90K"),
        MarketNode("btc_100k", "token_100k", "Bitcoin > $100K"),
    ]
    
    for m in markets:
        scanner.add_market(m)
        
    # Monotonicity: Higher targets imply lower targets
    # P(BTC>100k) <= P(BTC>90k) <= ... <= P(BTC>50k)
    scanner.add_relationship("btc_50k", "btc_60k", "implies")
    scanner.add_relationship("btc_60k", "btc_70k", "implies")
    scanner.add_relationship("btc_70k", "btc_80k", "implies")
    scanner.add_relationship("btc_80k", "btc_90k", "implies")
    scanner.add_relationship("btc_90k", "btc_100k", "implies")


def setup_election_dag(scanner: CorrelationScannerPy):
    """Set up a DAG for election markets"""
    markets = [
        MarketNode("dem_nominee", "token_dem_nom", "Democrat Nominee"),
        MarketNode("dem_president", "token_dem_pres", "Democrat Wins Presidency"),
        MarketNode("rep_nominee", "token_rep_nom", "Republican Nominee"),
        MarketNode("rep_president", "token_rep_pres", "Republican Wins Presidency"),
    ]
    
    for m in markets:
        scanner.add_market(m)
        
    # Winning presidency implies winning nomination
    scanner.add_relationship("dem_nominee", "dem_president", "contains")
    scanner.add_relationship("rep_nominee", "rep_president", "contains")
