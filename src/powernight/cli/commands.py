"""
PowerNight CLI - Command Line Interface

Provides CLI commands for manual operations and configuration.
"""

import click
import logging
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


def main() -> None:
    """CLI entry point."""
    cli()


if __name__ == "__main__":
    main()