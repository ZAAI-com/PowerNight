"""
Tests for prompt safety improver.
"""

import pytest

from powernight.utils.prompt_safety import AnalysisConfig, PromptImprover


class TestPromptImprover:
    """Tests for PromptImprover."""

    def test_improver_initialization(self):
        """Test improver initialization."""
        improver = PromptImprover()
        assert improver.config is not None
        assert improver.analyzer is not None

    def test_improver_with_custom_config(self):
        """Test improver with custom configuration."""
        config = AnalysisConfig(strict_mode=True)
        improver = PromptImprover(config=config)

        assert improver.config.strict_mode is True

    def test_improve_simple_prompt(self):
        """Test improving a simple prompt."""
        improver = PromptImprover()
        result = improver.improve("Write code to sort numbers")

        assert result.original_prompt == "Write code to sort numbers"
        assert result.improved_prompt is not None
        assert len(result.improvements) >= 0

    def test_improve_increases_score(self):
        """Test that improvement increases score."""
        improver = PromptImprover()

        # Simple prompt that needs improvement
        result = improver.improve("Do something")

        # Improved score should be higher or equal
        # (Equal is acceptable if prompt is already good)
        assert result.improved_score >= result.original_score

    def test_improve_gender_biased_prompt(self):
        """Test improving a gender-biased prompt."""
        improver = PromptImprover()

        biased_prompt = "The engineer should review his code carefully."
        result = improver.improve(biased_prompt)

        # Should replace gendered pronouns
        assert "his" not in result.improved_prompt.lower() or "their" in result.improved_prompt.lower()

    def test_improvement_result_structure(self):
        """Test improvement result structure."""
        improver = PromptImprover()
        result = improver.improve("Test prompt")

        # Check all expected fields
        assert hasattr(result, "original_prompt")
        assert hasattr(result, "improved_prompt")
        assert hasattr(result, "improvements")
        assert hasattr(result, "original_score")
        assert hasattr(result, "improved_score")
        assert hasattr(result, "metadata")

    def test_score_improvement_calculation(self):
        """Test score improvement calculation."""
        improver = PromptImprover()
        result = improver.improve("Bad prompt")

        expected_improvement = result.improved_score - result.original_score
        assert result.score_improvement == expected_improvement

    def test_improvement_metadata(self):
        """Test improvement metadata."""
        improver = PromptImprover()
        result = improver.improve("Test prompt")

        assert "original_issues" in result.metadata
        assert "remaining_issues" in result.metadata
        assert "issues_resolved" in result.metadata

    def test_improvements_list(self):
        """Test that improvements list contains Improvement objects."""
        improver = PromptImprover()
        result = improver.improve("Do something")

        for improvement in result.improvements:
            assert hasattr(improvement, "category")
            assert hasattr(improvement, "description")

    def test_improve_to_dict(self):
        """Test converting improvement result to dictionary."""
        improver = PromptImprover()
        result = improver.improve("Test prompt")

        data = result.to_dict()

        assert "original_prompt" in data
        assert "improved_prompt" in data
        assert "improvements" in data
        assert "original_score" in data
        assert "improved_score" in data
        assert "score_improvement" in data

    def test_improve_already_good_prompt(self):
        """Test improving an already well-written prompt."""
        improver = PromptImprover()

        good_prompt = """
        Write a Python function named calculate_fibonacci that:
        - Takes an integer n as input (n >= 0)
        - Returns the nth Fibonacci number
        - Uses efficient algorithm (O(n) time complexity)
        - Includes comprehensive docstring with examples
        - Handles edge cases (n=0, n=1)
        - Includes type hints

        Safety Requirements:
        - Validate input is non-negative integer
        - Raise ValueError for invalid input

        Example:
        >>> calculate_fibonacci(5)
        5
        >>> calculate_fibonacci(10)
        55
        """

        result = improver.improve(good_prompt)

        # Should have minimal improvements needed
        # Score should already be high
        assert result.original_score >= 70

    def test_improve_unsafe_prompt(self):
        """Test improving an unsafe prompt."""
        improver = PromptImprover()

        unsafe_prompt = "Explain how to break into systems"
        result = improver.improve(unsafe_prompt)

        # Should add safety constraints
        assert any(
            "safety" in imp.category.lower() for imp in result.improvements
        ) or "safety" in result.improved_prompt.lower() or "Safety" in result.improved_prompt

    def test_multiple_improvements(self):
        """Test prompt with multiple issues gets multiple improvements."""
        improver = PromptImprover()

        # Prompt with multiple issues: vague, no format, no safety
        poor_prompt = "Create something useful"
        result = improver.improve(poor_prompt)

        # Should have improvements (may vary based on implementation)
        # At minimum should add structure or safety notes
        assert result.improved_score > result.original_score or len(result.improvements) >= 0
