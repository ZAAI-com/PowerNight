"""
PowerNight CLI - Command Line Interface

Provides CLI commands for manual operations and configuration.
"""

import click
import json
import logging
import sys
from pathlib import Path
from typing import Optional

from powernight.core.config import ConfigManager, create_dummy_config
from powernight.core.powerwall import PowerwallConnector


@click.group()
@click.option("--config", "-c", default="config/config.yaml", help="Configuration file path")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.pass_context
def cli(ctx: click.Context, config: str, verbose: bool) -> None:
    """PowerNight CLI - Tesla Powerwall Control."""

    # Setup logging
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

    # Store config path in context
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config


@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Get current Powerwall status."""
    config_manager = ConfigManager()
    config = config_manager.load_config(ctx.obj["config_path"])

    connector = PowerwallConnector(
        email=config.powerwall.tesla_email,
        powerwall_id=config.powerwall.powerwall_id
    )

    try:
        current_reserve = connector.get_backup_reserve_percentage()
        click.echo(f"Current backup reserve: {current_reserve}%")
    except Exception as e:
        click.echo(f"Error getting status: {e}", err=True)


@cli.command()
@click.argument("percentage", type=click.IntRange(0, 100))
@click.pass_context
def set_reserve(ctx: click.Context, percentage: int) -> None:
    """Set backup reserve percentage (0-100)."""
    config_manager = ConfigManager()
    config = config_manager.load_config(ctx.obj["config_path"])

    connector = PowerwallConnector(
        email=config.powerwall.tesla_email,
        powerwall_id=config.powerwall.powerwall_id
    )

    try:
        connector.set_backup_reserve_percentage(percentage)
        click.echo(f"Backup reserve set to {percentage}%")
    except Exception as e:
        click.echo(f"Error setting reserve: {e}", err=True)


@cli.command()
@click.pass_context
def test_connection(ctx: click.Context) -> None:
    """Test connection to Powerwall."""
    config_manager = ConfigManager()
    config = config_manager.load_config(ctx.obj["config_path"])

    connector = PowerwallConnector(
        email=config.powerwall.tesla_email,
        powerwall_id=config.powerwall.powerwall_id
    )

    try:
        connector.test_connection()
        click.echo("✓ Connection to Powerwall successful")
    except Exception as e:
        click.echo(f"✗ Connection failed: {e}", err=True)


@cli.command()
@click.option("--verbose", "-v", is_flag=True, help="Show detailed validation information")
@click.pass_context
def validate_config(ctx: click.Context, verbose: bool) -> None:
    """Validate configuration file for errors."""
    config_path = ctx.obj["config_path"]

    try:
        config_manager = ConfigManager()
        config = config_manager.load_config(config_path)

        # Run validation
        errors = config.validate()

        # Display results
        click.echo("=" * 60)
        click.echo("PowerNight Configuration Validation")
        click.echo("=" * 60)
        click.echo(f"\nConfig file: {config_path}")

        if len(errors) == 0:
            click.echo(click.style("\n✓ Configuration is VALID", fg="green", bold=True))

            if verbose:
                click.echo("\nConfiguration Summary:")
                click.echo(f"  • Tesla Email: {config.powerwall.tesla_email}")
                click.echo(f"  • Powerwall ID: {config.powerwall.powerwall_id or '(auto-detect)'}")
                click.echo(f"  • Automation: {'Enabled' if config.automation.enabled else 'Disabled'}")
                click.echo(f"  • Scheduled Tasks: {len(config.automation.schedule)}")
                click.echo(f"  • Timezone: {config.automation.timezone}")
                click.echo(f"  • Web Interface: {'Enabled' if config.web_interface.enabled else 'Disabled'} on {config.web_interface.host}:{config.web_interface.port}")
                click.echo(f"  • Authentication: {'Enabled' if config.web_interface.auth_required else 'Disabled'}")
                click.echo(f"  • Log Level: {config.logging.level}")
                click.echo(f"  • Monitoring: {'Enabled' if config.monitoring.enabled else 'Disabled'}")
                click.echo(f"  • Circuit Breaker: {'Enabled' if config.monitoring.circuit_breaker_enabled else 'Disabled'}")
        else:
            click.echo(click.style(f"\n✗ Configuration is INVALID", fg="red", bold=True))
            click.echo(f"\nFound {len(errors)} validation error(s):\n")
            for i, error in enumerate(errors, 1):
                click.echo(click.style(f"  {i}. {error}", fg="red"))

        click.echo("\n" + "=" * 60)

        # Exit with error code if validation failed
        if errors:
            ctx.exit(1)

    except FileNotFoundError:
        click.echo(click.style(f"✗ Configuration file not found: {config_path}", fg="red"), err=True)
        ctx.exit(1)
    except Exception as e:
        click.echo(click.style(f"✗ Failed to load configuration: {e}", fg="red"), err=True)
        ctx.exit(1)


@cli.command()
@click.option("--email", prompt="Tesla account email", help="Tesla account email")
@click.option("--powerwall-id", help="Specific Powerwall ID (optional)")
@click.pass_context
def configure(ctx: click.Context, email: str, powerwall_id: str) -> None:
    """Configure Powerwall connection settings."""
    config_manager = ConfigManager()

    try:
        config = config_manager.load_config(ctx.obj["config_path"])
        config.powerwall.host = host
        config.powerwall.password = password
        config_manager.save_config(config)
        click.echo("✓ Configuration saved successfully")
    except Exception as e:
        click.echo(f"✗ Configuration failed: {e}", err=True)


@cli.command()
@click.option("--output", "-o", default="config/dummy-config.yaml", help="Output path for dummy config")
@click.option("--force", "-f", is_flag=True, help="Overwrite existing file")
def create_dummy_config(output: str, force: bool) -> None:
    """Create a dummy configuration for testing/development when Powerwall is not available."""
    import os
    from pathlib import Path
    import yaml

    output_path_obj = Path(output)

    # Check if file exists
    if output_path_obj.exists() and not force:
        if not click.confirm(f"File '{output}' already exists. Overwrite?"):
            return

    try:
        # Create dummy config directly
        dummy_config = create_dummy_config()

        # Ensure parent directory exists
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)

        # Save to file using yaml directly
        config_dict = dummy_config.to_dict()
        with open(output_path_obj, 'w') as f:
            yaml.dump(config_dict, f, default_flow_style=False, indent=2, sort_keys=False)

        click.echo(f"✓ Dummy configuration created at '{output}'")
        click.echo("  This configuration enables dry-run mode and disables automation")
        click.echo("  The web interface will be available for testing purposes")

    except Exception as e:
        click.echo(f"✗ Failed to create dummy configuration: {e}", err=True)


@cli.group()
def prompt_safety() -> None:
    """Prompt Safety Framework - Analyze and improve AI prompts."""
    pass


@prompt_safety.command()
@click.option(
    "--file", "-f", type=click.Path(exists=True), help="File containing the prompt"
)
@click.option("--interactive", "-i", is_flag=True, help="Enter prompt interactively")
@click.option(
    "--format",
    type=click.Choice(["json", "markdown", "text"], case_sensitive=False),
    default="text",
    help="Output format",
)
@click.option("--verbose", "-v", is_flag=True, help="Show detailed analysis")
@click.option(
    "--output", "-o", type=click.Path(), help="Output file (default: stdout)"
)
def analyze(
    file: Optional[str],
    interactive: bool,
    format: str,
    verbose: bool,
    output: Optional[str],
) -> None:
    """Analyze a prompt for safety, bias, security, and effectiveness."""
    from powernight.utils.prompt_safety import PromptAnalyzer, AnalysisConfig

    # Get prompt text
    if interactive:
        click.echo("Enter your prompt (press Ctrl+D when done):")
        prompt = sys.stdin.read()
    elif file:
        with open(file, "r") as f:
            prompt = f.read()
    else:
        # Read from stdin
        prompt = sys.stdin.read()

    if not prompt.strip():
        click.echo("Error: No prompt provided", err=True)
        sys.exit(1)

    # Create analyzer
    config = AnalysisConfig(verbose=verbose, output_format=format)
    analyzer = PromptAnalyzer(config=config)

    # Analyze prompt
    result = analyzer.analyze(prompt)

    # Format output
    if format == "json":
        output_text = json.dumps(result.to_dict(), indent=2)
    elif format == "markdown":
        output_text = _format_markdown(result, verbose)
    else:  # text
        output_text = _format_text(result, verbose)

    # Write output
    if output:
        with open(output, "w") as f:
            f.write(output_text)
        click.echo(f"Analysis written to {output}")
    else:
        click.echo(output_text)


@prompt_safety.command()
@click.option(
    "--file", "-f", type=click.Path(exists=True), help="File containing the prompt"
)
@click.option("--interactive", "-i", is_flag=True, help="Enter prompt interactively")
@click.option(
    "--output", "-o", type=click.Path(), help="Output file for improved prompt"
)
def improve(file: Optional[str], interactive: bool, output: Optional[str]) -> None:
    """Improve a prompt based on safety analysis."""
    from powernight.utils.prompt_safety import PromptImprover

    # Get prompt text
    if interactive:
        click.echo("Enter your prompt (press Ctrl+D when done):")
        prompt = sys.stdin.read()
    elif file:
        with open(file, "r") as f:
            prompt = f.read()
    else:
        # Read from stdin
        prompt = sys.stdin.read()

    if not prompt.strip():
        click.echo("Error: No prompt provided", err=True)
        sys.exit(1)

    # Create improver
    improver = PromptImprover()

    # Improve prompt
    click.echo("Analyzing and improving prompt...")
    result = improver.improve(prompt)

    # Display results
    click.echo("\n" + "=" * 80)
    click.echo("PROMPT IMPROVEMENT REPORT")
    click.echo("=" * 80)

    click.echo(f"\nOriginal Score: {result.original_score:.1f}/100")
    click.echo(f"Improved Score: {result.improved_score:.1f}/100")
    click.echo(
        f"Improvement: {result.score_improvement:+.1f} points"
    )

    click.echo("\nImprovements Made:")
    for i, improvement in enumerate(result.improvements, 1):
        click.echo(f"  {i}. [{improvement.category}] {improvement.description}")

    click.echo("\n" + "-" * 80)
    click.echo("IMPROVED PROMPT:")
    click.echo("-" * 80)
    click.echo(result.improved_prompt)
    click.echo("-" * 80)

    # Write to file if requested
    if output:
        with open(output, "w") as f:
            f.write(result.improved_prompt)
        click.echo(f"\nImproved prompt written to {output}")


@prompt_safety.command()
def version() -> None:
    """Show prompt safety framework version."""
    from powernight.utils.prompt_safety import __version__

    click.echo(f"Prompt Safety Framework v{__version__}")


def _format_text(result, verbose: bool) -> str:
    """Format analysis result as plain text."""
    lines = []
    lines.append("=" * 80)
    lines.append("PROMPT SAFETY ANALYSIS REPORT")
    lines.append("=" * 80)

    # Overall score
    lines.append(f"\nOverall Score: {result.overall_score:.1f}/100")
    lines.append(f"Risk Level: {result.risk_level}")

    # Component scores
    lines.append("\nComponent Scores:")
    lines.append(f"  Safety:        {result.safety_score.value:.1f}/100")
    lines.append(f"  Bias:          {result.bias_score.value:.1f}/100")
    lines.append(f"  Security:      {result.security_score.value:.1f}/100")
    lines.append(f"  Effectiveness: {result.effectiveness_score.value:.1f}/100")
    lines.append(f"  Robustness:    {result.robustness_score.value:.1f}/100")
    lines.append(f"  Performance:   {result.performance_score.value:.1f}/100")

    # Issues
    if result.issues:
        lines.append(f"\nIssues Found: {len(result.issues)}")
        lines.append(
            f"  Critical: {len(result.critical_issues)}, High: {len(result.high_issues)}"
        )

        lines.append("\nDetailed Issues:")
        for i, issue in enumerate(result.issues, 1):
            lines.append(f"\n  {i}. [{issue.severity.value.upper()}] {issue.category.value}")
            lines.append(f"     {issue.message}")
            lines.append(f"     Location: {issue.location}")
            lines.append(f"     Suggestion: {issue.suggestion}")
            if verbose:
                lines.append(f"     Confidence: {issue.confidence:.1%}")
    else:
        lines.append("\n✓ No issues found!")

    lines.append("\n" + "=" * 80)
    return "\n".join(lines)


def _format_markdown(result, verbose: bool) -> str:
    """Format analysis result as markdown."""
    lines = []
    lines.append("# Prompt Safety Analysis Report\n")

    # Overall score
    lines.append(f"**Overall Score:** {result.overall_score:.1f}/100")
    lines.append(f"**Risk Level:** {result.risk_level}\n")

    # Component scores
    lines.append("## Component Scores\n")
    lines.append("| Component | Score |")
    lines.append("|-----------|-------|")
    lines.append(f"| Safety | {result.safety_score.value:.1f}/100 |")
    lines.append(f"| Bias | {result.bias_score.value:.1f}/100 |")
    lines.append(f"| Security | {result.security_score.value:.1f}/100 |")
    lines.append(f"| Effectiveness | {result.effectiveness_score.value:.1f}/100 |")
    lines.append(f"| Robustness | {result.robustness_score.value:.1f}/100 |")
    lines.append(f"| Performance | {result.performance_score.value:.1f}/100 |")

    # Issues
    if result.issues:
        lines.append(f"\n## Issues Found: {len(result.issues)}\n")
        lines.append(
            f"- **Critical:** {len(result.critical_issues)}"
        )
        lines.append(f"- **High:** {len(result.high_issues)}\n")

        lines.append("### Detailed Issues\n")
        for i, issue in enumerate(result.issues, 1):
            lines.append(
                f"#### {i}. [{issue.severity.value.upper()}] {issue.category.value}\n"
            )
            lines.append(f"**Message:** {issue.message}")
            lines.append(f"**Location:** {issue.location}")
            lines.append(f"**Suggestion:** {issue.suggestion}")
            if verbose:
                lines.append(f"**Confidence:** {issue.confidence:.1%}")
            lines.append("")
    else:
        lines.append("\n## ✓ No issues found!\n")

    return "\n".join(lines)


def main() -> None:
    """CLI entry point."""
    cli()


if __name__ == "__main__":
    main()