"""
Configuration for prompt safety analysis.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional


class RuleSeverity(str, Enum):
    """Severity levels for custom rules."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class WeightConfig:
    """Component weights for overall score calculation."""

    safety: float = 0.30
    bias: float = 0.20
    security: float = 0.20
    effectiveness: float = 0.15
    robustness: float = 0.10
    performance: float = 0.05

    def __post_init__(self) -> None:
        """Validate weights sum to 1.0."""
        total = (
            self.safety
            + self.bias
            + self.security
            + self.effectiveness
            + self.robustness
            + self.performance
        )
        if not 0.99 <= total <= 1.01:  # Allow small floating point errors
            raise ValueError(f"Weights must sum to 1.0, got {total}")


@dataclass
class SafetyConfig:
    """Safety analysis configuration."""

    check_harmful_content: bool = True
    check_violence: bool = True
    check_hate_speech: bool = True
    check_misinformation: bool = True
    check_illegal_activities: bool = True


@dataclass
class BiasConfig:
    """Bias analysis configuration."""

    check_gender: bool = True
    check_racial: bool = True
    check_cultural: bool = True
    check_socioeconomic: bool = True
    check_ability: bool = True


@dataclass
class SecurityConfig:
    """Security analysis configuration."""

    check_data_exposure: bool = True
    check_injection: bool = True
    check_information_leakage: bool = True
    check_access_control: bool = True


@dataclass
class AnalysisConfig:
    """Main configuration for prompt safety analysis."""

    # General settings
    min_score_threshold: float = 75.0
    strict_mode: bool = False
    verbose: bool = False
    include_educational_insights: bool = True

    # Component configurations
    weights: WeightConfig = field(default_factory=WeightConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    bias: BiasConfig = field(default_factory=BiasConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)

    # Output settings
    output_format: str = "json"  # json, markdown, html, text
    include_examples: bool = True
    include_references: bool = True

    # Advanced settings
    min_confidence: float = 0.7
    max_issues_per_category: Optional[int] = None

    @classmethod
    def from_dict(cls, data: Dict) -> "AnalysisConfig":
        """Create config from dictionary."""
        weights_data = data.get("weights", {})
        safety_data = data.get("safety", {})
        bias_data = data.get("bias", {})
        security_data = data.get("security", {})

        return cls(
            min_score_threshold=data.get("min_score_threshold", 75.0),
            strict_mode=data.get("strict_mode", False),
            verbose=data.get("verbose", False),
            include_educational_insights=data.get(
                "include_educational_insights", True
            ),
            weights=WeightConfig(**weights_data) if weights_data else WeightConfig(),
            safety=SafetyConfig(**safety_data) if safety_data else SafetyConfig(),
            bias=BiasConfig(**bias_data) if bias_data else BiasConfig(),
            security=(
                SecurityConfig(**security_data)
                if security_data
                else SecurityConfig()
            ),
            output_format=data.get("output_format", "json"),
            include_examples=data.get("include_examples", True),
            include_references=data.get("include_references", True),
            min_confidence=data.get("min_confidence", 0.7),
            max_issues_per_category=data.get("max_issues_per_category"),
        )

    def to_dict(self) -> Dict:
        """Convert config to dictionary."""
        return {
            "min_score_threshold": self.min_score_threshold,
            "strict_mode": self.strict_mode,
            "verbose": self.verbose,
            "include_educational_insights": self.include_educational_insights,
            "weights": {
                "safety": self.weights.safety,
                "bias": self.weights.bias,
                "security": self.weights.security,
                "effectiveness": self.weights.effectiveness,
                "robustness": self.weights.robustness,
                "performance": self.weights.performance,
            },
            "safety": {
                "check_harmful_content": self.safety.check_harmful_content,
                "check_violence": self.safety.check_violence,
                "check_hate_speech": self.safety.check_hate_speech,
                "check_misinformation": self.safety.check_misinformation,
                "check_illegal_activities": self.safety.check_illegal_activities,
            },
            "bias": {
                "check_gender": self.bias.check_gender,
                "check_racial": self.bias.check_racial,
                "check_cultural": self.bias.check_cultural,
                "check_socioeconomic": self.bias.check_socioeconomic,
                "check_ability": self.bias.check_ability,
            },
            "security": {
                "check_data_exposure": self.security.check_data_exposure,
                "check_injection": self.security.check_injection,
                "check_information_leakage": self.security.check_information_leakage,
                "check_access_control": self.security.check_access_control,
            },
            "output_format": self.output_format,
            "include_examples": self.include_examples,
            "include_references": self.include_references,
            "min_confidence": self.min_confidence,
            "max_issues_per_category": self.max_issues_per_category,
        }
