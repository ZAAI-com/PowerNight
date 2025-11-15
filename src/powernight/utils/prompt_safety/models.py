"""
Data models for prompt safety analysis.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class Severity(str, Enum):
    """Issue severity levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class Category(str, Enum):
    """Issue categories."""

    SAFETY = "safety"
    BIAS = "bias"
    SECURITY = "security"
    EFFECTIVENESS = "effectiveness"
    ROBUSTNESS = "robustness"
    PERFORMANCE = "performance"


@dataclass
class Issue:
    """Represents an issue found during analysis."""

    severity: Severity
    category: Category
    message: str
    location: str
    suggestion: str
    confidence: float = 1.0
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert issue to dictionary."""
        return {
            "severity": self.severity.value,
            "category": self.category.value,
            "message": self.message,
            "location": self.location,
            "suggestion": self.suggestion,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }


@dataclass
class ComponentScore:
    """Score for a specific analysis component."""

    value: float  # 0-100
    max_value: float = 100.0
    weight: float = 1.0
    issues: List[Issue] = field(default_factory=list)

    @property
    def weighted_score(self) -> float:
        """Calculate weighted score."""
        return self.value * self.weight

    def to_dict(self) -> Dict:
        """Convert score to dictionary."""
        return {
            "value": round(self.value, 2),
            "max_value": self.max_value,
            "weight": self.weight,
            "weighted_score": round(self.weighted_score, 2),
            "issues_count": len(self.issues),
        }


@dataclass
class AnalysisResult:
    """Complete analysis result."""

    prompt: str
    overall_score: float
    safety_score: ComponentScore
    bias_score: ComponentScore
    security_score: ComponentScore
    effectiveness_score: ComponentScore
    robustness_score: ComponentScore
    performance_score: ComponentScore
    issues: List[Issue] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)

    @property
    def risk_level(self) -> str:
        """Determine overall risk level."""
        if self.safety_score.value < 40 or self.security_score.value < 40:
            return "CRITICAL"
        elif self.overall_score < 60:
            return "HIGH"
        elif self.overall_score < 75:
            return "MEDIUM"
        else:
            return "LOW"

    @property
    def critical_issues(self) -> List[Issue]:
        """Get critical severity issues."""
        return [i for i in self.issues if i.severity == Severity.CRITICAL]

    @property
    def high_issues(self) -> List[Issue]:
        """Get high severity issues."""
        return [i for i in self.issues if i.severity == Severity.HIGH]

    def to_dict(self) -> Dict:
        """Convert result to dictionary."""
        return {
            "prompt": self.prompt,
            "overall_score": round(self.overall_score, 2),
            "risk_level": self.risk_level,
            "component_scores": {
                "safety": self.safety_score.to_dict(),
                "bias": self.bias_score.to_dict(),
                "security": self.security_score.to_dict(),
                "effectiveness": self.effectiveness_score.to_dict(),
                "robustness": self.robustness_score.to_dict(),
                "performance": self.performance_score.to_dict(),
            },
            "issues": [issue.to_dict() for issue in self.issues],
            "critical_issues_count": len(self.critical_issues),
            "high_issues_count": len(self.high_issues),
            "total_issues": len(self.issues),
            "metadata": self.metadata,
        }


@dataclass
class Improvement:
    """Represents an improvement made to a prompt."""

    category: str
    description: str
    before: Optional[str] = None
    after: Optional[str] = None


@dataclass
class ImprovementResult:
    """Result of prompt improvement."""

    original_prompt: str
    improved_prompt: str
    improvements: List[Improvement]
    original_score: float
    improved_score: float
    metadata: Dict = field(default_factory=dict)

    @property
    def score_improvement(self) -> float:
        """Calculate score improvement."""
        return self.improved_score - self.original_score

    def to_dict(self) -> Dict:
        """Convert result to dictionary."""
        return {
            "original_prompt": self.original_prompt,
            "improved_prompt": self.improved_prompt,
            "improvements": [
                {
                    "category": imp.category,
                    "description": imp.description,
                    "before": imp.before,
                    "after": imp.after,
                }
                for imp in self.improvements
            ],
            "original_score": round(self.original_score, 2),
            "improved_score": round(self.improved_score, 2),
            "score_improvement": round(self.score_improvement, 2),
            "metadata": self.metadata,
        }
