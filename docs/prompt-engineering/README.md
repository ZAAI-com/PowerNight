# AI Prompt Engineering Safety Review Framework

> **Comprehensive framework for analyzing, reviewing, and improving AI prompts for safety, bias, security, and effectiveness.**

## Quick Start

### Installation

The prompt safety framework is included with PowerNight:

```bash
# Install PowerNight
pip install -e .

# Verify installation
powernight-cli prompt-safety version
```

### Basic Usage

**Analyze a prompt:**
```bash
echo "Write a function to sort numbers" | powernight-cli prompt-safety analyze
```

**Improve a prompt:**
```bash
powernight-cli prompt-safety improve --file my_prompt.txt
```

**Get JSON output:**
```bash
powernight-cli prompt-safety analyze --file prompt.txt --format json
```

## Documentation

### Core Documents

| Document | Description |
|----------|-------------|
| **[FRAMEWORK.md](FRAMEWORK.md)** | Complete framework specification with analysis criteria, scoring system, and best practices |
| **[USAGE.md](USAGE.md)** | Detailed usage guide for CLI and Python API |
| **[EXAMPLES.md](EXAMPLES.md)** | Comprehensive examples of prompt analysis and improvement |

### Quick Links

- **Getting Started**: See [USAGE.md § Installation](USAGE.md#installation)
- **CLI Commands**: See [USAGE.md § CLI Usage](USAGE.md#cli-usage)
- **Python API**: See [USAGE.md § Python API Usage](USAGE.md#python-api-usage)
- **Analysis Framework**: See [FRAMEWORK.md § Analysis Framework](FRAMEWORK.md#analysis-framework)
- **Examples**: See [EXAMPLES.md](EXAMPLES.md)

## Features

### Analysis Dimensions

The framework evaluates prompts across **8 critical dimensions**:

1. **Safety Assessment** - Harmful content, violence, hate speech, misinformation
2. **Bias Detection** - Gender, racial, cultural, socioeconomic, ability biases
3. **Security & Privacy** - Data exposure, prompt injection, information leakage
4. **Effectiveness** - Clarity, context, constraints, format specification
5. **Best Practices** - Industry standards compliance (Microsoft, OpenAI, Google AI)
6. **Advanced Patterns** - Zero-shot, few-shot, chain-of-thought, role-based
7. **Technical Robustness** - Input validation, error handling, scalability
8. **Performance** - Token efficiency, response quality, consistency

### Scoring System

- **Overall Score**: Weighted average across all dimensions (0-100)
- **Component Scores**: Individual scores for each dimension
- **Risk Levels**: CRITICAL, HIGH, MEDIUM, LOW
- **Issue Severity**: Critical, High, Medium, Low, Info

### Output Formats

- **Text** - Human-readable report (default)
- **JSON** - Structured data for programmatic use
- **Markdown** - Formatted report for documentation

## CLI Commands

### `analyze`

Analyze a prompt for safety, bias, security, and effectiveness.

```bash
# From file
powernight-cli prompt-safety analyze --file prompt.txt

# From stdin
echo "Your prompt here" | powernight-cli prompt-safety analyze

# Interactive mode
powernight-cli prompt-safety analyze --interactive

# JSON output
powernight-cli prompt-safety analyze --file prompt.txt --format json

# Markdown output with verbose details
powernight-cli prompt-safety analyze --file prompt.txt --format markdown --verbose

# Save to file
powernight-cli prompt-safety analyze --file prompt.txt --output report.txt
```

### `improve`

Improve a prompt based on safety analysis.

```bash
# Improve from file
powernight-cli prompt-safety improve --file prompt.txt

# Save improved version
powernight-cli prompt-safety improve --file prompt.txt --output improved.txt

# Interactive mode
powernight-cli prompt-safety improve --interactive
```

### `version`

Show framework version.

```bash
powernight-cli prompt-safety version
```

## Python API

### Basic Analysis

```python
from powernight.utils.prompt_safety import PromptAnalyzer

analyzer = PromptAnalyzer()
result = analyzer.analyze("Write a Python function to sort numbers")

print(f"Score: {result.overall_score}/100")
print(f"Risk Level: {result.risk_level}")
print(f"Issues: {len(result.issues)}")
```

### Improve Prompts

```python
from powernight.utils.prompt_safety import PromptImprover

improver = PromptImprover()
result = improver.improve("Your prompt here")

print(f"Original: {result.original_score}/100")
print(f"Improved: {result.improved_score}/100")
print(f"New prompt: {result.improved_prompt}")
```

### Custom Configuration

```python
from powernight.utils.prompt_safety import PromptAnalyzer, AnalysisConfig

config = AnalysisConfig(
    min_score_threshold=80,
    strict_mode=True,
    verbose=True
)

analyzer = PromptAnalyzer(config=config)
result = analyzer.analyze(prompt)
```

## Example Analysis

**Input Prompt:**
```
Write code to sort numbers
```

**Analysis Output:**
```
Overall Score: 45/100
Risk Level: MEDIUM

Component Scores:
  Safety:        95/100
  Bias:          100/100
  Security:      100/100
  Effectiveness: 35/100
  Robustness:    40/100
  Performance:   90/100

Issues Found: 3

  1. [MEDIUM] effectiveness
     Prompt is very short and may lack clarity
     Location: Overall prompt length
     Suggestion: Provide more detail about the task, context, and expected output

  2. [MEDIUM] effectiveness
     No explicit output format specified
     Location: Overall structure
     Suggestion: Specify the expected output format (e.g., JSON, markdown, code, etc.)

  3. [MEDIUM] robustness
     No explicit constraints or requirements defined
     Location: Overall structure
     Suggestion: Define clear constraints and requirements for the output
```

## Use Cases

### For Developers

- **Code Generation Prompts**: Ensure clear, unambiguous specifications
- **Documentation Prompts**: Generate comprehensive, well-structured docs
- **Testing Prompts**: Create robust test cases and scenarios

### For Researchers

- **Academic Prompts**: Ensure evidence-based, unbiased analysis
- **Data Analysis Prompts**: Protect privacy, prevent data exposure
- **Literature Review Prompts**: Comprehensive, balanced perspectives

### For Content Creators

- **Creative Prompts**: Inclusive, culturally sensitive content
- **Educational Prompts**: Safe, appropriate for audience
- **Marketing Prompts**: Unbiased, compliant messaging

### For Security Professionals

- **Security Testing Prompts**: Authorized, ethical testing only
- **Incident Response Prompts**: Proper data handling, privacy protection
- **Compliance Prompts**: GDPR, CCPA, industry standards

## Best Practices

### ✅ Do's

- Always prioritize safety over functionality
- Use inclusive, neutral language
- Define clear constraints and boundaries
- Include relevant context and examples
- Test prompts with edge cases
- Document assumptions and limitations
- Version control prompts
- Monitor and iterate based on outputs

### ❌ Don'ts

- Don't assume demographic characteristics
- Don't include sensitive data in prompts
- Don't create prompts vulnerable to injection
- Don't use ambiguous or vague language
- Don't skip safety considerations
- Don't ignore potential biases
- Don't forget to test thoroughly
- Don't deploy without review

## Framework Principles

### Safety First

Every prompt is analyzed for potential harm:
- Harmful content generation
- Violence and hate speech
- Misinformation risks
- Illegal activities

### Bias Mitigation

Comprehensive bias detection across:
- Gender stereotypes
- Racial assumptions
- Cultural biases
- Socioeconomic assumptions
- Ability-based biases

### Security by Design

Protection against:
- Prompt injection attacks
- Data exposure and leakage
- Privacy violations
- Unauthorized access

### Effectiveness Focus

Ensuring prompts are:
- Clear and unambiguous
- Well-contextualized
- Properly constrained
- Format-specified
- Specific and complete

## Industry Standards

This framework incorporates best practices from:

- **Microsoft** - Responsible AI principles
- **OpenAI** - Safety best practices and GPT guidelines
- **Google AI** - AI Principles and ethics framework
- **Anthropic** - Constitutional AI and safety research
- **Partnership on AI** - Framework for responsible AI

## Integration

### With PowerNight

The prompt safety framework is fully integrated into PowerNight:

```bash
# Use alongside PowerNight commands
powernight-cli status
powernight-cli prompt-safety analyze --file prompt.txt
```

### Standalone Usage

Can be used independently for any prompt engineering work:

```python
from powernight.utils.prompt_safety import PromptAnalyzer

analyzer = PromptAnalyzer()
# Use in your own projects
```

## Contributing

We welcome contributions to improve the framework:

1. Add new analysis patterns
2. Improve detection accuracy
3. Enhance improvement suggestions
4. Add more examples
5. Improve documentation

See [CONTRIBUTING.md](../../CONTRIBUTING.md) for guidelines.

## Support

- **GitHub Issues**: [ZAAI-com/PowerNight/issues](https://github.com/ZAAI-com/PowerNight/issues)
- **Documentation**: [GitHub Repository](https://github.com/ZAAI-com/PowerNight)
- **Email**: powernight@zaai.com

## License

MIT License - See [LICENSE.md](../../LICENSE.md) for details.

## Version

**Current Version**: 1.0.0

See [USAGE.md](USAGE.md) for full documentation and [EXAMPLES.md](EXAMPLES.md) for comprehensive examples.

---

**Made with ❤️ by the PowerNight Team**
