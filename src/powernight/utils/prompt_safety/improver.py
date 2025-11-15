"""
Prompt improvement engine.
"""

from typing import List, Optional

from .analyzer import PromptAnalyzer
from .config import AnalysisConfig
from .models import Improvement, ImprovementResult, Severity


class PromptImprover:
    """Improves prompts based on analysis results."""

    def __init__(self, config: Optional[AnalysisConfig] = None):
        """
        Initialize improver.

        Args:
            config: Analysis configuration
        """
        self.config = config or AnalysisConfig()
        self.analyzer = PromptAnalyzer(config=self.config)

    def improve(self, prompt: str) -> ImprovementResult:
        """
        Improve a prompt based on analysis.

        Args:
            prompt: Original prompt text

        Returns:
            ImprovementResult with improved prompt and list of improvements
        """
        # Analyze original prompt
        original_analysis = self.analyzer.analyze(prompt)

        # Generate improvements
        improvements = []
        improved_prompt = prompt

        # Apply improvements based on issues
        for issue in original_analysis.issues:
            if issue.severity in [Severity.CRITICAL, Severity.HIGH]:
                # Apply critical and high severity improvements
                improvement, improved_prompt = self._apply_improvement(
                    improved_prompt, issue
                )
                if improvement:
                    improvements.append(improvement)

        # If no critical improvements were made, add general enhancements
        if not improvements:
            improvements, improved_prompt = self._add_general_enhancements(
                improved_prompt, original_analysis
            )

        # Analyze improved prompt
        improved_analysis = self.analyzer.analyze(improved_prompt)

        return ImprovementResult(
            original_prompt=prompt,
            improved_prompt=improved_prompt,
            improvements=improvements,
            original_score=original_analysis.overall_score,
            improved_score=improved_analysis.overall_score,
            metadata={
                "original_issues": len(original_analysis.issues),
                "remaining_issues": len(improved_analysis.issues),
                "issues_resolved": len(original_analysis.issues)
                - len(improved_analysis.issues),
            },
        )

    def _apply_improvement(
        self, prompt: str, issue
    ) -> tuple[Optional[Improvement], str]:
        """
        Apply a specific improvement based on an issue.

        Args:
            prompt: Current prompt text
            issue: Issue to address

        Returns:
            Tuple of (Improvement object, improved prompt)
        """
        # This is a simplified implementation
        # In a full implementation, this would use more sophisticated NLP

        improvement = Improvement(
            category=issue.category.value,
            description=issue.suggestion,
        )

        # For now, we'll append the suggestion as a guideline
        # A more sophisticated version would actually modify the prompt text
        if "safety constraint" in issue.suggestion.lower():
            safety_note = "\n\nSafety Requirements:\n- " + issue.suggestion
            return improvement, prompt + safety_note

        if "gender-neutral" in issue.suggestion.lower():
            # Simple pronoun replacement
            improved = prompt
            improved = improved.replace(" he ", " they ")
            improved = improved.replace(" she ", " they ")
            improved = improved.replace(" him ", " them ")
            improved = improved.replace(" her ", " them ")
            improved = improved.replace(" his ", " their ")
            improvement.before = "gendered pronouns"
            improvement.after = "gender-neutral pronouns"
            return improvement, improved

        return None, prompt

    def _add_general_enhancements(
        self, prompt: str, analysis
    ) -> tuple[List[Improvement], str]:
        """
        Add general enhancements to improve prompt quality.

        Args:
            prompt: Current prompt text
            analysis: Analysis result

        Returns:
            Tuple of (list of improvements, improved prompt)
        """
        improvements = []
        enhanced = prompt

        # Add structure if missing
        if len(prompt.split()) > 20 and ":" not in prompt:
            structure_note = (
                "\n\nExpected Output Format:\n"
                "- Clear and structured response\n"
                "- Address all requirements\n"
                "- Include examples if appropriate"
            )
            enhanced += structure_note
            improvements.append(
                Improvement(
                    category="effectiveness",
                    description="Added output format specification",
                )
            )

        # Add safety note if none present
        if analysis.safety_score.value < 90:
            safety_note = (
                "\n\nSafety Guidelines:\n"
                "- Ensure output is appropriate and helpful\n"
                "- Avoid harmful, biased, or offensive content\n"
                "- Focus on constructive and educational value"
            )
            enhanced += safety_note
            improvements.append(
                Improvement(
                    category="safety",
                    description="Added safety guidelines",
                )
            )

        return improvements, enhanced
