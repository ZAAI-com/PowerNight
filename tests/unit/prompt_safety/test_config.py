"""
Tests for prompt safety configuration.
"""

import pytest

from powernight.utils.prompt_safety.config import (
    AnalysisConfig,
    BiasConfig,
    SafetyConfig,
    SecurityConfig,
    WeightConfig,
)


class TestWeightConfig:
    """Tests for WeightConfig."""

    def test_default_weights(self):
        """Test default weight configuration."""
        config = WeightConfig()

        assert config.safety == 0.30
        assert config.bias == 0.20
        assert config.security == 0.20
        assert config.effectiveness == 0.15
        assert config.robustness == 0.10
        assert config.performance == 0.05

    def test_weights_sum_to_one(self):
        """Test that default weights sum to 1.0."""
        config = WeightConfig()

        total = (
            config.safety
            + config.bias
            + config.security
            + config.effectiveness
            + config.robustness
            + config.performance
        )

        assert total == pytest.approx(1.0)

    def test_custom_weights(self):
        """Test custom weight configuration."""
        config = WeightConfig(
            safety=0.4,
            bias=0.2,
            security=0.2,
            effectiveness=0.1,
            robustness=0.05,
            performance=0.05,
        )

        assert config.safety == 0.4

    def test_invalid_weights(self):
        """Test that invalid weights raise error."""
        with pytest.raises(ValueError):
            WeightConfig(
                safety=0.5,
                bias=0.5,  # Total = 1.0 + other components = > 1.0
                security=0.2,
                effectiveness=0.1,
                robustness=0.1,
                performance=0.1,
            )


class TestSafetyConfig:
    """Tests for SafetyConfig."""

    def test_default_safety_config(self):
        """Test default safety configuration."""
        config = SafetyConfig()

        assert config.check_harmful_content is True
        assert config.check_violence is True
        assert config.check_hate_speech is True
        assert config.check_misinformation is True
        assert config.check_illegal_activities is True

    def test_custom_safety_config(self):
        """Test custom safety configuration."""
        config = SafetyConfig(
            check_harmful_content=True,
            check_violence=False,
            check_hate_speech=True,
            check_misinformation=False,
            check_illegal_activities=True,
        )

        assert config.check_violence is False
        assert config.check_misinformation is False


class TestBiasConfig:
    """Tests for BiasConfig."""

    def test_default_bias_config(self):
        """Test default bias configuration."""
        config = BiasConfig()

        assert config.check_gender is True
        assert config.check_racial is True
        assert config.check_cultural is True
        assert config.check_socioeconomic is True
        assert config.check_ability is True

    def test_custom_bias_config(self):
        """Test custom bias configuration."""
        config = BiasConfig(
            check_gender=True,
            check_racial=False,
            check_cultural=True,
            check_socioeconomic=False,
            check_ability=True,
        )

        assert config.check_racial is False
        assert config.check_socioeconomic is False


class TestSecurityConfig:
    """Tests for SecurityConfig."""

    def test_default_security_config(self):
        """Test default security configuration."""
        config = SecurityConfig()

        assert config.check_data_exposure is True
        assert config.check_injection is True
        assert config.check_information_leakage is True
        assert config.check_access_control is True

    def test_custom_security_config(self):
        """Test custom security configuration."""
        config = SecurityConfig(
            check_data_exposure=True,
            check_injection=False,
            check_information_leakage=True,
            check_access_control=False,
        )

        assert config.check_injection is False
        assert config.check_access_control is False


class TestAnalysisConfig:
    """Tests for AnalysisConfig."""

    def test_default_analysis_config(self):
        """Test default analysis configuration."""
        config = AnalysisConfig()

        assert config.min_score_threshold == 75.0
        assert config.strict_mode is False
        assert config.verbose is False
        assert config.include_educational_insights is True
        assert config.output_format == "json"
        assert config.include_examples is True
        assert config.include_references is True
        assert config.min_confidence == 0.7

    def test_custom_analysis_config(self):
        """Test custom analysis configuration."""
        config = AnalysisConfig(
            min_score_threshold=80.0,
            strict_mode=True,
            verbose=True,
            output_format="markdown",
        )

        assert config.min_score_threshold == 80.0
        assert config.strict_mode is True
        assert config.verbose is True
        assert config.output_format == "markdown"

    def test_from_dict(self):
        """Test creating config from dictionary."""
        data = {
            "min_score_threshold": 80.0,
            "strict_mode": True,
            "verbose": True,
            "weights": {
                "safety": 0.35,
                "bias": 0.25,
                "security": 0.20,
                "effectiveness": 0.10,
                "robustness": 0.05,
                "performance": 0.05,
            },
            "safety": {
                "check_harmful_content": True,
                "check_violence": False,
                "check_hate_speech": True,
                "check_misinformation": True,
                "check_illegal_activities": True,
            },
        }

        config = AnalysisConfig.from_dict(data)

        assert config.min_score_threshold == 80.0
        assert config.strict_mode is True
        assert config.weights.safety == 0.35
        assert config.safety.check_violence is False

    def test_to_dict(self):
        """Test converting config to dictionary."""
        config = AnalysisConfig(
            min_score_threshold=85.0,
            strict_mode=True,
        )

        data = config.to_dict()

        assert data["min_score_threshold"] == 85.0
        assert data["strict_mode"] is True
        assert "weights" in data
        assert "safety" in data
        assert "bias" in data
        assert "security" in data

    def test_nested_config_objects(self):
        """Test that nested config objects are properly initialized."""
        config = AnalysisConfig()

        assert isinstance(config.weights, WeightConfig)
        assert isinstance(config.safety, SafetyConfig)
        assert isinstance(config.bias, BiasConfig)
        assert isinstance(config.security, SecurityConfig)
