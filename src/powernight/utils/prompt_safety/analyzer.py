"""
Main prompt safety analyzer.
"""

import re
from typing import Dict, List, Optional

from .config import AnalysisConfig
from .models import (
    AnalysisResult,
    Category,
    ComponentScore,
    Issue,
    Severity,
)


class PromptAnalyzer:
    """Analyzes prompts for safety, bias, security, and effectiveness."""

    def __init__(self, config: Optional[AnalysisConfig] = None):
        """
        Initialize analyzer.

        Args:
            config: Analysis configuration. Uses defaults if not provided.
        """
        self.config = config or AnalysisConfig()

    def analyze(self, prompt: str, context: Optional[Dict] = None) -> AnalysisResult:
        """
        Analyze a prompt comprehensively.

        Args:
            prompt: The prompt text to analyze
            context: Optional context information (domain, audience, etc.)

        Returns:
            AnalysisResult with scores and issues
        """
        context = context or {}

        # Run component analyses
        safety_issues = self._analyze_safety(prompt, context)
        bias_issues = self._analyze_bias(prompt, context)
        security_issues = self._analyze_security(prompt, context)
        effectiveness_issues = self._analyze_effectiveness(prompt, context)
        robustness_issues = self._analyze_robustness(prompt, context)
        performance_issues = self._analyze_performance(prompt, context)

        # Calculate component scores
        safety_score = self._calculate_score(safety_issues, Category.SAFETY)
        bias_score = self._calculate_score(bias_issues, Category.BIAS)
        security_score = self._calculate_score(security_issues, Category.SECURITY)
        effectiveness_score = self._calculate_score(
            effectiveness_issues, Category.EFFECTIVENESS
        )
        robustness_score = self._calculate_score(
            robustness_issues, Category.ROBUSTNESS
        )
        performance_score = self._calculate_score(
            performance_issues, Category.PERFORMANCE
        )

        # Set weights
        safety_score.weight = self.config.weights.safety
        bias_score.weight = self.config.weights.bias
        security_score.weight = self.config.weights.security
        effectiveness_score.weight = self.config.weights.effectiveness
        robustness_score.weight = self.config.weights.robustness
        performance_score.weight = self.config.weights.performance

        # Calculate overall score
        overall_score = (
            safety_score.weighted_score
            + bias_score.weighted_score
            + security_score.weighted_score
            + effectiveness_score.weighted_score
            + robustness_score.weighted_score
            + performance_score.weighted_score
        )

        # Collect all issues
        all_issues = (
            safety_issues
            + bias_issues
            + security_issues
            + effectiveness_issues
            + robustness_issues
            + performance_issues
        )

        # Filter by confidence if needed
        if self.config.min_confidence > 0:
            all_issues = [
                i for i in all_issues if i.confidence >= self.config.min_confidence
            ]

        # Sort issues by severity
        all_issues.sort(
            key=lambda x: {
                Severity.CRITICAL: 0,
                Severity.HIGH: 1,
                Severity.MEDIUM: 2,
                Severity.LOW: 3,
                Severity.INFO: 4,
            }[x.severity]
        )

        return AnalysisResult(
            prompt=prompt,
            overall_score=overall_score,
            safety_score=safety_score,
            bias_score=bias_score,
            security_score=security_score,
            effectiveness_score=effectiveness_score,
            robustness_score=robustness_score,
            performance_score=performance_score,
            issues=all_issues,
            metadata={"context": context, "config": self.config.to_dict()},
        )

    def _analyze_safety(self, prompt: str, context: Dict) -> List[Issue]:
        """Analyze prompt for safety issues."""
        issues = []

        if not self.config.safety.check_harmful_content:
            return issues

        # Check for harmful content indicators
        harmful_patterns = [
            (
                r"\b(harm|hurt|damage|injure|kill|attack)\s+(people|person|someone|others)",
                Severity.CRITICAL,
                "Prompt may generate content about harming people",
                "Reframe to focus on prevention, education, or fictional scenarios with clear context",
            ),
            (
                r"\b(how to|ways to|methods to)\s+(harm|hurt|damage|destroy)",
                Severity.HIGH,
                "Prompt requests potentially harmful instructions",
                "Add explicit safety constraints and educational framing",
            ),
            (
                r"\b(violence|violent|brutal|torture)\b",
                Severity.MEDIUM,
                "Prompt contains violence-related terms",
                "Add context for educational/awareness purposes if appropriate",
            ),
        ]

        for pattern, severity, message, suggestion in harmful_patterns:
            if re.search(pattern, prompt, re.IGNORECASE):
                issues.append(
                    Issue(
                        severity=severity,
                        category=Category.SAFETY,
                        message=message,
                        location=self._find_location(prompt, pattern),
                        suggestion=suggestion,
                        confidence=0.8,
                    )
                )

        # Check for hate speech patterns
        if self.config.safety.check_hate_speech:
            hate_patterns = [
                (
                    r"\b(hate|discriminate|racist|sexist|homophobic)\b",
                    Severity.HIGH,
                    "Prompt contains hate speech related terms",
                    "Use neutral, inclusive language",
                )
            ]

            for pattern, severity, message, suggestion in hate_patterns:
                if re.search(pattern, prompt, re.IGNORECASE):
                    issues.append(
                        Issue(
                            severity=severity,
                            category=Category.SAFETY,
                            message=message,
                            location=self._find_location(prompt, pattern),
                            suggestion=suggestion,
                            confidence=0.7,
                        )
                    )

        # Check for misinformation patterns
        if self.config.safety.check_misinformation:
            misinfo_patterns = [
                (
                    r"\b(prove|explain why)\s+.+\s+(is true|is false|is fact)",
                    Severity.MEDIUM,
                    "Prompt assumes conclusion, may promote misinformation",
                    "Request evidence-based analysis instead of proving predetermined conclusion",
                )
            ]

            for pattern, severity, message, suggestion in misinfo_patterns:
                if re.search(pattern, prompt, re.IGNORECASE):
                    issues.append(
                        Issue(
                            severity=severity,
                            category=Category.SAFETY,
                            message=message,
                            location=self._find_location(prompt, pattern),
                            suggestion=suggestion,
                            confidence=0.6,
                        )
                    )

        return issues

    def _analyze_bias(self, prompt: str, context: Dict) -> List[Issue]:
        """Analyze prompt for bias."""
        issues = []

        # Check for gender bias
        if self.config.bias.check_gender:
            gender_patterns = [
                (
                    r"\b(he|him|his)\b.*\b(engineer|developer|programmer|scientist|doctor|CEO)",
                    Severity.MEDIUM,
                    "Potential gender bias: assumes male for professional role",
                    "Use gender-neutral pronouns (they/them) or avoid pronouns",
                ),
                (
                    r"\b(she|her)\b.*\b(nurse|teacher|secretary|assistant)",
                    Severity.MEDIUM,
                    "Potential gender bias: assumes female for care/support role",
                    "Use gender-neutral pronouns (they/them) or avoid pronouns",
                ),
                (
                    r"\b(chairman|fireman|policeman|businessman)\b",
                    Severity.LOW,
                    "Gendered language detected",
                    "Use gender-neutral alternatives: chair, firefighter, police officer, businessperson",
                ),
            ]

            for pattern, severity, message, suggestion in gender_patterns:
                if re.search(pattern, prompt, re.IGNORECASE):
                    issues.append(
                        Issue(
                            severity=severity,
                            category=Category.BIAS,
                            message=message,
                            location=self._find_location(prompt, pattern),
                            suggestion=suggestion,
                            confidence=0.7,
                        )
                    )

        # Check for cultural bias
        if self.config.bias.check_cultural:
            cultural_patterns = [
                (
                    r"\b(holidays?)\b(?!.*\b(various|diverse|multiple|different)\b)",
                    Severity.LOW,
                    "May assume specific cultural context for holidays",
                    "Specify which cultural context or be explicit about diversity",
                ),
                (
                    r"\b(traditional|normal|standard)\s+(family|name|practice)\b",
                    Severity.MEDIUM,
                    "Cultural assumption detected",
                    "Avoid assuming what is 'traditional' or 'normal' - be specific or inclusive",
                ),
            ]

            for pattern, severity, message, suggestion in cultural_patterns:
                if re.search(pattern, prompt, re.IGNORECASE):
                    issues.append(
                        Issue(
                            severity=severity,
                            category=Category.BIAS,
                            message=message,
                            location=self._find_location(prompt, pattern),
                            suggestion=suggestion,
                            confidence=0.6,
                        )
                    )

        # Check for socioeconomic bias
        if self.config.bias.check_socioeconomic:
            socioeconomic_patterns = [
                (
                    r"\b(everyone has|assume.*have|users have)\b.*\b(smartphone|internet|computer|car|home)\b",
                    Severity.MEDIUM,
                    "Socioeconomic assumption: assumes universal access to resources",
                    "Acknowledge varying access levels and provide alternatives",
                )
            ]

            for pattern, severity, message, suggestion in socioeconomic_patterns:
                if re.search(pattern, prompt, re.IGNORECASE):
                    issues.append(
                        Issue(
                            severity=severity,
                            category=Category.BIAS,
                            message=message,
                            location=self._find_location(prompt, pattern),
                            suggestion=suggestion,
                            confidence=0.7,
                        )
                    )

        return issues

    def _analyze_security(self, prompt: str, context: Dict) -> List[Issue]:
        """Analyze prompt for security vulnerabilities."""
        issues = []

        # Check for injection vulnerabilities
        if self.config.security.check_injection:
            if "{user_input}" in prompt or "{input}" in prompt:
                # Check if there are protective measures
                if not any(
                    keyword in prompt.lower()
                    for keyword in [
                        "sanitize",
                        "validate",
                        "treat as data",
                        "not as instructions",
                    ]
                ):
                    issues.append(
                        Issue(
                            severity=Severity.HIGH,
                            category=Category.SECURITY,
                            message="User input included without validation/sanitization instructions",
                            location="User input placeholder detected",
                            suggestion="Add explicit instructions to treat user input as data, not commands. Include validation requirements.",
                            confidence=0.9,
                        )
                    )

        # Check for data exposure
        if self.config.security.check_data_exposure:
            sensitive_data_patterns = [
                (
                    r"\b(password|credential|api_key|secret|token)\b",
                    Severity.HIGH,
                    "Prompt may involve sensitive data",
                    "Ensure proper handling of sensitive information. Never include actual secrets.",
                ),
                (
                    r"\b(PII|personal.*information|email|phone|address|SSN)\b",
                    Severity.MEDIUM,
                    "Prompt may involve personally identifiable information",
                    "Ensure PII handling complies with privacy regulations (GDPR, CCPA)",
                ),
                (
                    r"\b(database|SQL|query)\b.*\b(dump|export|extract)\b",
                    Severity.HIGH,
                    "Prompt may expose database contents",
                    "Use aggregated, anonymized data only. Never expose raw database contents.",
                ),
            ]

            for pattern, severity, message, suggestion in sensitive_data_patterns:
                if re.search(pattern, prompt, re.IGNORECASE):
                    issues.append(
                        Issue(
                            severity=severity,
                            category=Category.SECURITY,
                            message=message,
                            location=self._find_location(prompt, pattern),
                            suggestion=suggestion,
                            confidence=0.7,
                        )
                    )

        return issues

    def _analyze_effectiveness(self, prompt: str, context: Dict) -> List[Issue]:
        """Analyze prompt effectiveness."""
        issues = []

        # Check clarity
        if len(prompt.strip()) < 20:
            issues.append(
                Issue(
                    severity=Severity.MEDIUM,
                    category=Category.EFFECTIVENESS,
                    message="Prompt is very short and may lack clarity",
                    location="Overall prompt length",
                    suggestion="Provide more detail about the task, context, and expected output",
                    confidence=0.8,
                )
            )

        # Check for vague language
        vague_patterns = [
            (
                r"\b(something|anything|stuff|things?|it|that|this)\b",
                Severity.LOW,
                "Vague language detected",
                "Be more specific about what you're referring to",
            ),
            (
                r"\b(maybe|perhaps|possibly|might|could)\b",
                Severity.LOW,
                "Uncertain language detected",
                "Be more definitive in requirements if possible",
            ),
        ]

        for pattern, severity, message, suggestion in vague_patterns:
            matches = re.findall(pattern, prompt, re.IGNORECASE)
            if len(matches) > 3:  # Only flag if used frequently
                issues.append(
                    Issue(
                        severity=severity,
                        category=Category.EFFECTIVENESS,
                        message=f"{message} (found {len(matches)} instances)",
                        location=self._find_location(prompt, pattern),
                        suggestion=suggestion,
                        confidence=0.6,
                    )
                )

        # Check for missing context indicators
        context_indicators = ["context:", "background:", "scenario:", "given:"]
        if not any(indicator in prompt.lower() for indicator in context_indicators):
            if len(prompt.split()) > 20:  # Only for longer prompts
                issues.append(
                    Issue(
                        severity=Severity.LOW,
                        category=Category.EFFECTIVENESS,
                        message="No explicit context section detected",
                        location="Overall structure",
                        suggestion="Consider adding a context section to provide background information",
                        confidence=0.5,
                    )
                )

        # Check for output format specification
        format_indicators = [
            "format:",
            "output:",
            "response format:",
            "return:",
            "provide:",
        ]
        if not any(indicator in prompt.lower() for indicator in format_indicators):
            issues.append(
                Issue(
                    severity=Severity.MEDIUM,
                    category=Category.EFFECTIVENESS,
                    message="No explicit output format specified",
                    location="Overall structure",
                    suggestion="Specify the expected output format (e.g., JSON, markdown, code, etc.)",
                    confidence=0.6,
                )
            )

        return issues

    def _analyze_robustness(self, prompt: str, context: Dict) -> List[Issue]:
        """Analyze prompt robustness."""
        issues = []

        # Check for error handling
        error_handling_keywords = [
            "if.*fail",
            "error",
            "exception",
            "edge case",
            "invalid input",
        ]
        has_error_handling = any(
            re.search(keyword, prompt, re.IGNORECASE)
            for keyword in error_handling_keywords
        )

        if not has_error_handling and len(prompt.split()) > 30:
            issues.append(
                Issue(
                    severity=Severity.LOW,
                    category=Category.ROBUSTNESS,
                    message="No error handling or edge case considerations mentioned",
                    location="Overall structure",
                    suggestion="Consider specifying how to handle errors or edge cases",
                    confidence=0.5,
                )
            )

        # Check for constraint definition
        constraint_keywords = [
            "must",
            "should",
            "required",
            "constraint",
            "limitation",
            "requirement",
        ]
        has_constraints = any(
            keyword in prompt.lower() for keyword in constraint_keywords
        )

        if not has_constraints and len(prompt.split()) > 20:
            issues.append(
                Issue(
                    severity=Severity.MEDIUM,
                    category=Category.ROBUSTNESS,
                    message="No explicit constraints or requirements defined",
                    location="Overall structure",
                    suggestion="Define clear constraints and requirements for the output",
                    confidence=0.6,
                )
            )

        return issues

    def _analyze_performance(self, prompt: str, context: Dict) -> List[Issue]:
        """Analyze prompt performance characteristics."""
        issues = []

        # Check token efficiency
        word_count = len(prompt.split())
        if word_count > 500:
            issues.append(
                Issue(
                    severity=Severity.LOW,
                    category=Category.PERFORMANCE,
                    message=f"Prompt is quite long ({word_count} words)",
                    location="Overall length",
                    suggestion="Consider if the prompt can be made more concise without losing clarity",
                    confidence=0.7,
                )
            )

        # Check for repetition
        words = prompt.lower().split()
        word_freq = {}
        for word in words:
            if len(word) > 4:  # Only check longer words
                word_freq[word] = word_freq.get(word, 0) + 1

        repeated_words = {w: c for w, c in word_freq.items() if c > 5}
        if repeated_words:
            issues.append(
                Issue(
                    severity=Severity.LOW,
                    category=Category.PERFORMANCE,
                    message=f"High repetition of certain words: {', '.join(list(repeated_words.keys())[:3])}",
                    location="Throughout prompt",
                    suggestion="Consider reducing repetition for better token efficiency",
                    confidence=0.6,
                )
            )

        return issues

    def _calculate_score(self, issues: List[Issue], category: Category) -> ComponentScore:
        """Calculate score based on issues."""
        # Start with perfect score
        score = 100.0

        # Deduct points based on severity
        severity_penalties = {
            Severity.CRITICAL: 30,
            Severity.HIGH: 20,
            Severity.MEDIUM: 10,
            Severity.LOW: 5,
            Severity.INFO: 2,
        }

        for issue in issues:
            penalty = severity_penalties.get(issue.severity, 5)
            # Weight by confidence
            weighted_penalty = penalty * issue.confidence
            score -= weighted_penalty

        # Ensure score is in valid range
        score = max(0.0, min(100.0, score))

        return ComponentScore(value=score, issues=issues)

    def _find_location(self, prompt: str, pattern: str) -> str:
        """Find approximate location of pattern in prompt."""
        match = re.search(pattern, prompt, re.IGNORECASE)
        if match:
            # Find line number
            lines_before = prompt[: match.start()].count("\n")
            return f"line {lines_before + 1}"
        return "unknown"
