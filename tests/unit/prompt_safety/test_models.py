"""
Tests for prompt safety models.
"""

import pytest

from powernight.utils.prompt_safety.models import (
    AnalysisResult,
    Category,
    ComponentScore,
    Improvement,
    ImprovementResult,
    Issue,
    Severity,
)


class TestIssue:
    """Tests for Issue model."""

    def test_issue_creation(self):
        """Test creating an issue."""
        issue = Issue(
            severity=Severity.HIGH,
            category=Category.SAFETY,
            message="Test issue",
            location="line 1",
            suggestion="Fix it",
            confidence=0.9,
        )

        assert issue.severity == Severity.HIGH
        assert issue.category == Category.SAFETY
        assert issue.message == "Test issue"
        assert issue.location == "line 1"
        assert issue.suggestion == "Fix it"
        assert issue.confidence == 0.9

    def test_issue_to_dict(self):
        """Test converting issue to dictionary."""
        issue = Issue(
            severity=Severity.MEDIUM,
            category=Category.BIAS,
            message="Bias detected",
            location="line 2",
            suggestion="Use neutral language",
        )

        data = issue.to_dict()

        assert data["severity"] == "medium"
        assert data["category"] == "bias"
        assert data["message"] == "Bias detected"
        assert data["location"] == "line 2"
        assert data["suggestion"] == "Use neutral language"


class TestComponentScore:
    """Tests for ComponentScore model."""

    def test_component_score_creation(self):
        """Test creating a component score."""
        score = ComponentScore(value=85.5, weight=0.3)

        assert score.value == 85.5
        assert score.weight == 0.3
        assert score.weighted_score == pytest.approx(25.65)

    def test_component_score_with_issues(self):
        """Test component score with issues."""
        issues = [
            Issue(
                severity=Severity.LOW,
                category=Category.EFFECTIVENESS,
                message="Minor issue",
                location="line 1",
                suggestion="Improve",
            )
        ]

        score = ComponentScore(value=90.0, weight=0.2, issues=issues)

        assert len(score.issues) == 1
        assert score.to_dict()["issues_count"] == 1


class TestAnalysisResult:
    """Tests for AnalysisResult model."""

    def test_analysis_result_creation(self):
        """Test creating an analysis result."""
        result = AnalysisResult(
            prompt="Test prompt",
            overall_score=85.0,
            safety_score=ComponentScore(value=90.0, weight=0.3),
            bias_score=ComponentScore(value=85.0, weight=0.2),
            security_score=ComponentScore(value=80.0, weight=0.2),
            effectiveness_score=ComponentScore(value=85.0, weight=0.15),
            robustness_score=ComponentScore(value=80.0, weight=0.10),
            performance_score=ComponentScore(value=90.0, weight=0.05),
        )

        assert result.prompt == "Test prompt"
        assert result.overall_score == 85.0

    def test_risk_level_critical(self):
        """Test critical risk level determination."""
        result = AnalysisResult(
            prompt="Test",
            overall_score=50.0,
            safety_score=ComponentScore(value=30.0),  # Low safety = CRITICAL
            bias_score=ComponentScore(value=80.0),
            security_score=ComponentScore(value=80.0),
            effectiveness_score=ComponentScore(value=80.0),
            robustness_score=ComponentScore(value=80.0),
            performance_score=ComponentScore(value=80.0),
        )

        assert result.risk_level == "CRITICAL"

    def test_risk_level_high(self):
        """Test high risk level determination."""
        result = AnalysisResult(
            prompt="Test",
            overall_score=55.0,
            safety_score=ComponentScore(value=50.0),
            bias_score=ComponentScore(value=50.0),
            security_score=ComponentScore(value=50.0),
            effectiveness_score=ComponentScore(value=50.0),
            robustness_score=ComponentScore(value=50.0),
            performance_score=ComponentScore(value=50.0),
        )

        assert result.risk_level == "HIGH"

    def test_risk_level_medium(self):
        """Test medium risk level determination."""
        result = AnalysisResult(
            prompt="Test",
            overall_score=70.0,
            safety_score=ComponentScore(value=70.0),
            bias_score=ComponentScore(value=70.0),
            security_score=ComponentScore(value=70.0),
            effectiveness_score=ComponentScore(value=70.0),
            robustness_score=ComponentScore(value=70.0),
            performance_score=ComponentScore(value=70.0),
        )

        assert result.risk_level == "MEDIUM"

    def test_risk_level_low(self):
        """Test low risk level determination."""
        result = AnalysisResult(
            prompt="Test",
            overall_score=90.0,
            safety_score=ComponentScore(value=90.0),
            bias_score=ComponentScore(value=90.0),
            security_score=ComponentScore(value=90.0),
            effectiveness_score=ComponentScore(value=90.0),
            robustness_score=ComponentScore(value=90.0),
            performance_score=ComponentScore(value=90.0),
        )

        assert result.risk_level == "LOW"

    def test_critical_issues_filter(self):
        """Test filtering critical issues."""
        issues = [
            Issue(
                severity=Severity.CRITICAL,
                category=Category.SAFETY,
                message="Critical",
                location="line 1",
                suggestion="Fix",
            ),
            Issue(
                severity=Severity.HIGH,
                category=Category.SECURITY,
                message="High",
                location="line 2",
                suggestion="Fix",
            ),
            Issue(
                severity=Severity.CRITICAL,
                category=Category.BIAS,
                message="Critical bias",
                location="line 3",
                suggestion="Fix",
            ),
        ]

        result = AnalysisResult(
            prompt="Test",
            overall_score=50.0,
            safety_score=ComponentScore(value=50.0),
            bias_score=ComponentScore(value=50.0),
            security_score=ComponentScore(value=50.0),
            effectiveness_score=ComponentScore(value=50.0),
            robustness_score=ComponentScore(value=50.0),
            performance_score=ComponentScore(value=50.0),
            issues=issues,
        )

        critical = result.critical_issues
        assert len(critical) == 2
        assert all(i.severity == Severity.CRITICAL for i in critical)

    def test_to_dict(self):
        """Test converting analysis result to dictionary."""
        result = AnalysisResult(
            prompt="Test prompt",
            overall_score=85.0,
            safety_score=ComponentScore(value=90.0, weight=0.3),
            bias_score=ComponentScore(value=85.0, weight=0.2),
            security_score=ComponentScore(value=80.0, weight=0.2),
            effectiveness_score=ComponentScore(value=85.0, weight=0.15),
            robustness_score=ComponentScore(value=80.0, weight=0.10),
            performance_score=ComponentScore(value=90.0, weight=0.05),
        )

        data = result.to_dict()

        assert data["prompt"] == "Test prompt"
        assert data["overall_score"] == 85.0
        assert data["risk_level"] == "MEDIUM"
        assert "component_scores" in data
        assert "safety" in data["component_scores"]


class TestImprovementResult:
    """Tests for ImprovementResult model."""

    def test_improvement_result_creation(self):
        """Test creating an improvement result."""
        improvements = [
            Improvement(
                category="safety",
                description="Added safety constraints",
            )
        ]

        result = ImprovementResult(
            original_prompt="Original",
            improved_prompt="Improved",
            improvements=improvements,
            original_score=60.0,
            improved_score=85.0,
        )

        assert result.original_prompt == "Original"
        assert result.improved_prompt == "Improved"
        assert len(result.improvements) == 1
        assert result.original_score == 60.0
        assert result.improved_score == 85.0

    def test_score_improvement(self):
        """Test score improvement calculation."""
        result = ImprovementResult(
            original_prompt="Original",
            improved_prompt="Improved",
            improvements=[],
            original_score=60.0,
            improved_score=85.0,
        )

        assert result.score_improvement == 25.0

    def test_to_dict(self):
        """Test converting improvement result to dictionary."""
        improvements = [
            Improvement(
                category="safety",
                description="Added constraints",
                before="No constraints",
                after="With constraints",
            )
        ]

        result = ImprovementResult(
            original_prompt="Original",
            improved_prompt="Improved",
            improvements=improvements,
            original_score=60.0,
            improved_score=85.0,
        )

        data = result.to_dict()

        assert data["original_prompt"] == "Original"
        assert data["improved_prompt"] == "Improved"
        assert len(data["improvements"]) == 1
        assert data["score_improvement"] == 25.0
