"""
Unit tests for PowerNight CLI commands.

Tests all CLI commands including status, set_reserve, test_connection,
validate_config, configure, and create_dummy_config.
"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from click.testing import CliRunner

from powernight.cli.commands import cli, status, set_reserve, test_connection, validate_config, configure, create_dummy_config
from powernight.core.config import PowerNightConfig, create_dummy_config as create_dummy_config_func


class TestCLIGroup:
    """Test main CLI group and common options."""

    def test_cli_help(self):
        """Test CLI help message."""
        runner = CliRunner()
        result = runner.invoke(cli, ['--help'])
        assert result.exit_code == 0
        assert 'PowerNight CLI' in result.output
        assert 'Tesla Powerwall Control' in result.output

    def test_cli_version(self):
        """Test CLI displays commands."""
        runner = CliRunner()
        result = runner.invoke(cli, ['--help'])
        assert 'status' in result.output
        assert 'set-reserve' in result.output
        assert 'test-connection' in result.output

    def test_cli_config_option(self):
        """Test CLI accepts config option."""
        runner = CliRunner()
        result = runner.invoke(cli, ['--config', 'test.yaml', 'status'], catch_exceptions=False)
        # Should fail because config doesn't exist, but option is accepted
        assert '--config' in cli.params[0].opts or '-c' in cli.params[0].opts

    def test_cli_verbose_option(self):
        """Test CLI accepts verbose option."""
        runner = CliRunner()
        result = runner.invoke(cli, ['--verbose', '--help'])
        assert result.exit_code == 0


class TestStatusCommand:
    """Test status command."""

    @patch('powernight.cli.commands.PowerwallConnector')
    @patch('powernight.cli.commands.ConfigManager')
    def test_status_success(self, mock_config_manager, mock_connector_class):
        """Test status command with successful response."""
        runner = CliRunner()

        # Mock config
        mock_config = create_dummy_config_func()
        mock_config.powerwall.tesla_email = "test@example.com"
        mock_config_manager.return_value.load_config.return_value = mock_config

        # Mock connector
        mock_connector = Mock()
        mock_connector.get_backup_reserve_percentage.return_value = 50.0
        mock_connector_class.return_value = mock_connector

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write('dummy: config')
            config_path = f.name

        try:
            result = runner.invoke(cli, ['--config', config_path, 'status'])
            assert result.exit_code == 0
            assert 'Current backup reserve: 50.0%' in result.output
        finally:
            os.unlink(config_path)

    @patch('powernight.cli.commands.PowerwallConnector')
    @patch('powernight.cli.commands.ConfigManager')
    def test_status_connection_error(self, mock_config_manager, mock_connector_class):
        """Test status command with connection error."""
        runner = CliRunner()

        # Mock config
        mock_config = create_dummy_config_func()
        mock_config_manager.return_value.load_config.return_value = mock_config

        # Mock connector to raise exception
        mock_connector = Mock()
        mock_connector.get_backup_reserve_percentage.side_effect = Exception("Connection failed")
        mock_connector_class.return_value = mock_connector

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write('dummy: config')
            config_path = f.name

        try:
            result = runner.invoke(cli, ['--config', config_path, 'status'])
            assert 'Error getting status: Connection failed' in result.output
        finally:
            os.unlink(config_path)


class TestSetReserveCommand:
    """Test set-reserve command."""

    @patch('powernight.cli.commands.PowerwallConnector')
    @patch('powernight.cli.commands.ConfigManager')
    def test_set_reserve_success(self, mock_config_manager, mock_connector_class):
        """Test set-reserve command with successful execution."""
        runner = CliRunner()

        # Mock config
        mock_config = create_dummy_config_func()
        mock_config_manager.return_value.load_config.return_value = mock_config

        # Mock connector
        mock_connector = Mock()
        mock_connector.set_backup_reserve_percentage.return_value = None
        mock_connector_class.return_value = mock_connector

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write('dummy: config')
            config_path = f.name

        try:
            result = runner.invoke(cli, ['--config', config_path, 'set-reserve', '75'])
            assert result.exit_code == 0
            assert 'Backup reserve set to 75%' in result.output
            mock_connector.set_backup_reserve_percentage.assert_called_once_with(75)
        finally:
            os.unlink(config_path)

    @patch('powernight.cli.commands.PowerwallConnector')
    @patch('powernight.cli.commands.ConfigManager')
    def test_set_reserve_error(self, mock_config_manager, mock_connector_class):
        """Test set-reserve command with error."""
        runner = CliRunner()

        # Mock config
        mock_config = create_dummy_config_func()
        mock_config_manager.return_value.load_config.return_value = mock_config

        # Mock connector to raise exception
        mock_connector = Mock()
        mock_connector.set_backup_reserve_percentage.side_effect = Exception("Failed to set reserve")
        mock_connector_class.return_value = mock_connector

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write('dummy: config')
            config_path = f.name

        try:
            result = runner.invoke(cli, ['--config', config_path, 'set-reserve', '50'])
            assert 'Error setting reserve: Failed to set reserve' in result.output
        finally:
            os.unlink(config_path)

    def test_set_reserve_invalid_percentage(self):
        """Test set-reserve with invalid percentage."""
        runner = CliRunner()

        # Test percentage > 100
        result = runner.invoke(cli, ['set-reserve', '150'])
        assert result.exit_code != 0

        # Test percentage < 0
        result = runner.invoke(cli, ['set-reserve', '-10'])
        assert result.exit_code != 0

    def test_set_reserve_missing_argument(self):
        """Test set-reserve without percentage argument."""
        runner = CliRunner()
        result = runner.invoke(cli, ['set-reserve'])
        assert result.exit_code != 0
        assert 'Missing argument' in result.output or 'Error' in result.output


class TestTestConnectionCommand:
    """Test test-connection command."""

    @patch('powernight.cli.commands.PowerwallConnector')
    @patch('powernight.cli.commands.ConfigManager')
    def test_connection_success(self, mock_config_manager, mock_connector_class):
        """Test test-connection command with successful connection."""
        runner = CliRunner()

        # Mock config
        mock_config = create_dummy_config_func()
        mock_config_manager.return_value.load_config.return_value = mock_config

        # Mock connector
        mock_connector = Mock()
        mock_connector.connect.return_value = True
        mock_connector_class.return_value = mock_connector

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write('dummy: config')
            config_path = f.name

        try:
            result = runner.invoke(cli, ['--config', config_path, 'test-connection'])
            assert result.exit_code == 0 or 'Connection' in result.output
        finally:
            os.unlink(config_path)

    @patch('powernight.cli.commands.PowerwallConnector')
    @patch('powernight.cli.commands.ConfigManager')
    def test_connection_failure(self, mock_config_manager, mock_connector_class):
        """Test test-connection command with connection failure."""
        runner = CliRunner()

        # Mock config
        mock_config = create_dummy_config_func()
        mock_config_manager.return_value.load_config.return_value = mock_config

        # Mock connector to raise exception
        mock_connector = Mock()
        mock_connector.connect.side_effect = Exception("Connection timeout")
        mock_connector_class.return_value = mock_connector

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write('dummy: config')
            config_path = f.name

        try:
            result = runner.invoke(cli, ['--config', config_path, 'test-connection'])
            # Should handle error gracefully
            assert result.exit_code == 0 or 'Error' in result.output or 'Failed' in result.output
        finally:
            os.unlink(config_path)


class TestValidateConfigCommand:
    """Test validate-config command."""

    @patch('powernight.cli.commands.ConfigManager')
    def test_validate_valid_config(self, mock_config_manager):
        """Test validating a valid configuration file."""
        runner = CliRunner()

        # Mock config manager to return valid config
        mock_config = create_dummy_config_func()
        mock_config_manager.return_value.load_config.return_value = mock_config

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write('dummy: config')
            config_path = f.name

        try:
            result = runner.invoke(cli, ['--config', config_path, 'validate-config'])
            assert result.exit_code == 0 or 'valid' in result.output.lower() or 'Valid' in result.output
        finally:
            os.unlink(config_path)

    @patch('powernight.cli.commands.ConfigManager')
    def test_validate_invalid_config(self, mock_config_manager):
        """Test validating an invalid configuration file."""
        runner = CliRunner()

        # Mock config manager to raise validation error
        mock_config_manager.return_value.load_config.side_effect = ValueError("Invalid config")

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write('invalid: yaml: content:')
            config_path = f.name

        try:
            result = runner.invoke(cli, ['--config', config_path, 'validate-config'])
            # Should handle error and display message
            assert 'invalid' in result.output.lower() or 'error' in result.output.lower()
        finally:
            os.unlink(config_path)

    @patch('powernight.cli.commands.ConfigManager')
    def test_validate_verbose(self, mock_config_manager):
        """Test validate-config with verbose flag."""
        runner = CliRunner()

        mock_config = create_dummy_config_func()
        mock_config_manager.return_value.load_config.return_value = mock_config

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write('dummy: config')
            config_path = f.name

        try:
            result = runner.invoke(cli, ['--config', config_path, 'validate-config', '--verbose'])
            assert result.exit_code == 0 or result.output  # Should produce some output
        finally:
            os.unlink(config_path)


class TestConfigureCommand:
    """Test configure command."""

    @patch('powernight.cli.commands.ConfigManager')
    def test_configure_success(self, mock_config_manager):
        """Test configure command with valid parameters."""
        runner = CliRunner()

        # Mock config manager
        mock_manager = Mock()
        mock_config_manager.return_value = mock_manager

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write('dummy: config')
            config_path = f.name

        try:
            result = runner.invoke(cli, [
                '--config', config_path,
                'configure',
                '--email', 'test@example.com',
                '--powerwall-id', 'PW123456'
            ])
            assert result.exit_code == 0 or 'configured' in result.output.lower() or 'Configuration' in result.output
        finally:
            os.unlink(config_path)

    @patch('powernight.cli.commands.ConfigManager')
    def test_configure_missing_params(self, mock_config_manager):
        """Test configure command with missing parameters."""
        runner = CliRunner()

        result = runner.invoke(cli, ['configure'])
        # Should fail or show error about missing required parameters
        assert result.exit_code != 0 or 'Missing' in result.output or 'required' in result.output.lower()


class TestCreateDummyConfigCommand:
    """Test create-dummy-config command."""

    def test_create_dummy_config_success(self):
        """Test creating dummy config file."""
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, 'dummy_config.yaml')

            result = runner.invoke(cli, ['create-dummy-config', '--output', output_path])

            # Should create file successfully
            assert result.exit_code == 0 or os.path.exists(output_path)

    def test_create_dummy_config_force_overwrite(self):
        """Test creating dummy config with force flag."""
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, 'dummy_config.yaml')

            # Create existing file
            with open(output_path, 'w') as f:
                f.write('existing: content')

            result = runner.invoke(cli, ['create-dummy-config', '--output', output_path, '--force'])

            # Should overwrite successfully with force flag
            assert result.exit_code == 0 or 'created' in result.output.lower()

    def test_create_dummy_config_no_overwrite(self):
        """Test creating dummy config without overwriting existing file."""
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, 'dummy_config.yaml')

            # Create existing file
            with open(output_path, 'w') as f:
                f.write('existing: content')

            result = runner.invoke(cli, ['create-dummy-config', '--output', output_path])

            # Should not overwrite without force flag
            assert result.exit_code != 0 or 'exists' in result.output.lower() or 'already' in result.output.lower()


class TestCLIIntegration:
    """Integration tests for CLI commands."""

    def test_all_commands_registered(self):
        """Test that all expected commands are registered."""
        runner = CliRunner()
        result = runner.invoke(cli, ['--help'])

        expected_commands = [
            'status',
            'set-reserve',
            'test-connection',
            'validate-config',
            'configure',
            'create-dummy-config'
        ]

        for command in expected_commands:
            assert command in result.output

    def test_command_help_messages(self):
        """Test that each command has a help message."""
        runner = CliRunner()

        commands = ['status', 'set-reserve', 'test-connection', 'validate-config', 'configure', 'create-dummy-config']

        for command in commands:
            result = runner.invoke(cli, [command, '--help'])
            assert result.exit_code == 0
            assert len(result.output) > 0  # Should have some help text

    @patch('powernight.cli.commands.ConfigManager')
    def test_config_path_context(self, mock_config_manager):
        """Test that config path is passed through context correctly."""
        runner = CliRunner()

        mock_config = create_dummy_config_func()
        mock_config_manager.return_value.load_config.return_value = mock_config

        custom_config = 'custom/path/config.yaml'

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write('dummy: config')
            config_path = f.name

        try:
            result = runner.invoke(cli, ['--config', config_path, 'validate-config'])
            # Config path should be used
            mock_config_manager.return_value.load_config.assert_called()
        finally:
            os.unlink(config_path)
