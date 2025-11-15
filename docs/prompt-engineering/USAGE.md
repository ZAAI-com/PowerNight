# Prompt Safety Framework - Usage Guide

## Table of Contents

1. [Installation](#installation)
2. [CLI Usage](#cli-usage)
3. [Python API Usage](#python-api-usage)
4. [Configuration](#configuration)
5. [Output Formats](#output-formats)
6. [Advanced Features](#advanced-features)
7. [Troubleshooting](#troubleshooting)

## Installation

### As Part of PowerNight

The prompt safety framework is included with PowerNight:

```bash
# Install PowerNight with dev dependencies
pip install -e ".[dev]"

# Verify installation
powernight-cli prompt-safety --version
```

### Standalone Installation

If you want to use the prompt safety framework independently:

```bash
# Clone the repository
git clone https://github.com/ZAAI-com/PowerNight.git
cd PowerNight

# Install only prompt safety dependencies
pip install -e .
```

## CLI Usage

### Basic Analysis

Analyze a prompt from the command line:

```bash
# Analyze a prompt from stdin
echo "Write a function to calculate fibonacci numbers" | powernight-cli prompt-safety analyze

# Analyze a prompt from a file
powernight-cli prompt-safety analyze --file my_prompt.txt

# Analyze with interactive input
powernight-cli prompt-safety analyze --interactive
```

### Output Formats

Choose different output formats:

```bash
# JSON output (default)
powernight-cli prompt-safety analyze --file prompt.txt --format json

# Markdown report
powernight-cli prompt-safety analyze --file prompt.txt --format markdown

# HTML report
powernight-cli prompt-safety analyze --file prompt.txt --format html

# Plain text
powernight-cli prompt-safety analyze --file prompt.txt --format text
```

### Verbose Analysis

Get detailed analysis with explanations:

```bash
# Verbose mode
powernight-cli prompt-safety analyze --file prompt.txt --verbose

# Include educational insights
powernight-cli prompt-safety analyze --file prompt.txt --explain
```

### Batch Analysis

Analyze multiple prompts:

```bash
# Analyze all prompts in a directory
powernight-cli prompt-safety analyze --directory ./prompts/

# Analyze with glob pattern
powernight-cli prompt-safety analyze --pattern "prompts/**/*.txt"

# Output to directory
powernight-cli prompt-safety analyze --directory ./prompts/ --output ./reports/
```

### Configuration

Use custom configuration:

```bash
# Use custom config file
powernight-cli prompt-safety analyze --config my_config.yaml --file prompt.txt

# Override specific settings
powernight-cli prompt-safety analyze --file prompt.txt --min-score 80 --strict-mode
```

## Python API Usage

### Basic Analysis

```python
from powernight.utils.prompt_safety import PromptAnalyzer

# Create analyzer instance
analyzer = PromptAnalyzer()

# Analyze a prompt
prompt = "Write a Python function to sort a list"
result = analyzer.analyze(prompt)

# Access results
print(f"Overall Score: {result.overall_score}")
print(f"Safety Score: {result.safety_score}")
print(f"Bias Score: {result.bias_score}")
print(f"Issues Found: {len(result.issues)}")
```

### Detailed Analysis

```python
from powernight.utils.prompt_safety import PromptAnalyzer, AnalysisConfig

# Custom configuration
config = AnalysisConfig(
    min_score_threshold=80,
    strict_mode=True,
    check_bias=True,
    check_security=True,
    verbose=True
)

# Create analyzer with config
analyzer = PromptAnalyzer(config=config)

# Analyze prompt
result = analyzer.analyze(prompt, context={
    'domain': 'code_generation',
    'audience': 'developers',
    'sensitivity': 'low'
})

# Iterate through issues
for issue in result.issues:
    print(f"[{issue.severity}] {issue.category}: {issue.message}")
    print(f"  Suggestion: {issue.suggestion}")
    print(f"  Location: {issue.location}")
```

### Generate Improved Prompt

```python
from powernight.utils.prompt_safety import PromptImprover

# Create improver instance
improver = PromptImprover()

# Get improved version
original_prompt = "Create a user authentication system"
improved = improver.improve(original_prompt)

# Access improved prompt and explanation
print("Original:", original_prompt)
print("\nImproved:", improved.prompt)
print("\nImprovements Made:")
for improvement in improved.improvements:
    print(f"  - {improvement}")
```

### Custom Analyzers

```python
from powernight.utils.prompt_safety import (
    SafetyAnalyzer,
    BiasAnalyzer,
    SecurityAnalyzer,
    EffectivenessAnalyzer
)

# Use individual analyzers
safety_analyzer = SafetyAnalyzer()
bias_analyzer = BiasAnalyzer()

# Run specific checks
safety_result = safety_analyzer.analyze(prompt)
bias_result = bias_analyzer.analyze(prompt)

# Combine results
combined_issues = safety_result.issues + bias_result.issues
```

### Batch Processing

```python
from powernight.utils.prompt_safety import PromptBatchAnalyzer
from pathlib import Path

# Create batch analyzer
batch_analyzer = PromptBatchAnalyzer()

# Analyze directory
prompts_dir = Path("./prompts")
results = batch_analyzer.analyze_directory(prompts_dir)

# Generate summary report
summary = batch_analyzer.generate_summary(results)
print(f"Total Prompts: {summary.total_prompts}")
print(f"Average Score: {summary.average_score}")
print(f"Issues Found: {summary.total_issues}")

# Export results
batch_analyzer.export_results(results, output_dir="./reports", format="html")
```

## Configuration

### Configuration File

Create a `prompt_safety_config.yaml`:

```yaml
# Analysis Configuration
analysis:
  min_score_threshold: 75
  strict_mode: false
  include_educational_insights: true

# Component Weights
weights:
  safety: 0.30
  bias: 0.20
  security: 0.20
  effectiveness: 0.15
  robustness: 0.10
  performance: 0.05

# Safety Settings
safety:
  check_harmful_content: true
  check_violence: true
  check_hate_speech: true
  check_misinformation: true
  check_illegal_activities: true

# Bias Settings
bias:
  check_gender: true
  check_racial: true
  check_cultural: true
  check_socioeconomic: true
  check_ability: true

# Security Settings
security:
  check_data_exposure: true
  check_injection: true
  check_information_leakage: true
  check_access_control: true

# Output Settings
output:
  format: markdown
  verbose: true
  include_examples: true
  include_references: true
```

### Environment Variables

Override settings with environment variables:

```bash
export PROMPT_SAFETY_CONFIG=/path/to/config.yaml
export PROMPT_SAFETY_MIN_SCORE=80
export PROMPT_SAFETY_STRICT_MODE=true
export PROMPT_SAFETY_OUTPUT_FORMAT=json
```

## Output Formats

### JSON Output

```json
{
  "prompt": "Original prompt text",
  "analysis": {
    "overall_score": 85,
    "safety_score": 90,
    "bias_score": 85,
    "security_score": 80,
    "effectiveness_score": 85,
    "robustness_score": 85,
    "performance_score": 90
  },
  "issues": [
    {
      "severity": "medium",
      "category": "bias",
      "message": "Potential gender bias detected",
      "location": "line 2",
      "suggestion": "Use gender-neutral language"
    }
  ],
  "improved_prompt": "Enhanced version of the prompt",
  "improvements": [
    "Added safety constraints",
    "Replaced gendered language",
    "Clarified expected output format"
  ]
}
```

### Markdown Report

```markdown
# Prompt Safety Analysis Report

## Original Prompt
[Prompt text]

## Overall Score: 85/100

### Component Scores
- Safety: 90/100
- Bias: 85/100
- Security: 80/100
- Effectiveness: 85/100

### Issues Identified
1. [MEDIUM] Bias: Potential gender bias detected
   - Location: line 2
   - Suggestion: Use gender-neutral language

## Improved Prompt
[Enhanced prompt]

## Improvements Made
- Added safety constraints
- Replaced gendered language
```

### HTML Report

Interactive HTML report with:
- Syntax highlighting
- Expandable sections
- Issue filtering
- Side-by-side comparison
- Downloadable JSON data

## Advanced Features

### Custom Rules

Define custom analysis rules:

```python
from powernight.utils.prompt_safety import CustomRule, RuleSeverity

# Define custom rule
rule = CustomRule(
    name="no_hardcoded_credentials",
    pattern=r"(password|api_key|secret)\s*=\s*['\"]",
    category="security",
    severity=RuleSeverity.HIGH,
    message="Hardcoded credentials detected",
    suggestion="Use environment variables or secure configuration"
)

# Add to analyzer
analyzer.add_custom_rule(rule)
```

### Callbacks and Hooks

```python
from powernight.utils.prompt_safety import PromptAnalyzer

def on_issue_found(issue):
    print(f"Issue detected: {issue.message}")
    # Log to monitoring system
    # Send notification
    # etc.

analyzer = PromptAnalyzer()
analyzer.on_issue(on_issue_found)
analyzer.analyze(prompt)
```

### Plugin System

```python
from powernight.utils.prompt_safety import AnalyzerPlugin

class MyCustomAnalyzer(AnalyzerPlugin):
    def analyze(self, prompt, context):
        # Custom analysis logic
        issues = []
        # ... analysis code ...
        return issues

# Register plugin
analyzer.register_plugin(MyCustomAnalyzer())
```

## Troubleshooting

### Common Issues

**Issue: "Module not found: prompt_safety"**
```bash
# Solution: Reinstall PowerNight
pip install -e ".[dev]"
```

**Issue: "Low scores for all prompts"**
```bash
# Solution: Adjust threshold or disable strict mode
powernight-cli prompt-safety analyze --min-score 60 --no-strict
```

**Issue: "Too many false positives"**
```yaml
# Solution: Adjust sensitivity in config
analysis:
  strict_mode: false
  min_confidence: 0.7
```

### Debug Mode

Enable debug output:

```bash
# CLI debug mode
powernight-cli prompt-safety analyze --file prompt.txt --debug

# Python debug logging
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Performance Issues

For large batch analysis:

```python
# Use parallel processing
batch_analyzer = PromptBatchAnalyzer(workers=4)

# Enable caching
analyzer = PromptAnalyzer(cache=True)

# Reduce checks for faster analysis
config = AnalysisConfig(
    check_bias=True,
    check_security=False,  # Disable if not needed
    verbose=False  # Reduce output verbosity
)
```

## Best Practices

1. **Start with defaults**: Use default configuration first, then customize
2. **Iterate gradually**: Make incremental improvements based on analysis
3. **Test thoroughly**: Validate improved prompts with real use cases
4. **Document changes**: Track prompt versions and improvements
5. **Monitor production**: Continuously analyze prompts in production use
6. **Stay updated**: Keep framework updated for latest safety practices

## Examples

See [EXAMPLES.md](EXAMPLES.md) for comprehensive usage examples.

## Support

For questions or issues:
- GitHub Issues: https://github.com/ZAAI-com/PowerNight/issues
- Documentation: https://github.com/ZAAI-com/PowerNight/tree/main/docs/prompt-engineering
- Email: powernight@zaai.com
