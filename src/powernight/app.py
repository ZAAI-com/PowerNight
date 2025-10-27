import logging
import signal
import sys
import time
import threading
from typing import Optional

from .core.database import db_migration
from .core.powerwall import initialize_powerwall_connector, PowerwallError
from .core.config import get_config_manager, get_config, load_config
from .core.planner import get_planner
from .web import create_app


class PowerNightApp:
    """
    Main PowerNight application controller.

    Manages the lifecycle of all PowerNight components including
    configuration, scheduling, and web interface.
    """

    def __init__(self):
        """Initialize the PowerNight application."""
        self.logger = logging.getLogger(__name__)
        self.planner = get_planner()
        self.config_manager = get_config_manager()
        self._shutdown_requested = False
        self.flask_app = None
        self.web_thread = None

        # --- Shared components ---
        self.powerwall_connector = None

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum: int, frame) -> None:
        """Handle shutdown signals."""
        signal_name = signal.Signals(signum).name
        self.logger.info(f"Received {signal_name} signal, initiating graceful shutdown")
        self._shutdown_requested = True

    def initialize(self, config_path: Optional[str] = None) -> bool:
        """
        Initialize the application with configuration.

        Args:
            config_path: Optional path to configuration file

        Returns:
            True if initialization was successful, False otherwise
        """
        try:
            self.logger.info("Initializing PowerNight application")

            # Load configuration
            if config_path:
                config = load_config(config_path)
            else:
                config = load_config()

            self.logger.info(f"Configuration loaded successfully")

            # Initialize database
            self.logger.info("Initializing and migrating database")
            db_migration.upgrade()
            self.logger.info("Database initialization complete")

            # Initialize Powerwall connector and store it
            self.logger.info("Initializing Powerwall connector")
            try:
                self.powerwall_connector = initialize_powerwall_connector(config)
                self.logger.info("Powerwall connector initialized")
                
                # Attempt to connect the PowerwallConnector
                self.logger.info("Connecting to Powerwall...")
                if self.powerwall_connector.connect():
                    self.logger.info("Powerwall connected successfully")
                else:
                    self.logger.warning("Failed to connect to Powerwall, but connector is available")
            except PowerwallError as e:
                self.logger.warning(f"Could not initialize Powerwall connector at startup: {e}")
                self.logger.warning("Application will continue, but Powerwall features will fail until configured.")

            self.logger.info(f"Automation enabled: {config.automation.enabled}")
            self.logger.info(f"Schedule entries: {len(config.automation.schedule)}")

            # Log scheduled entries
            for i, entry in enumerate(config.automation.schedule):
                status = "enabled" if entry.enabled else "disabled"
                self.logger.info(
                    f"  Schedule {i}: {entry.time} -> {entry.percentage}% "
                    f"({status}) - {entry.description or 'No description'}"
                )

            return True

        except Exception as e:
            self.logger.error(f"Failed to initialize application: {e}")
            return False

    def start_planner(self) -> bool:
        """
        Start the task planner.

        Returns:
            True if planner started successfully, False otherwise
        """
        try:
            self.logger.info("Starting task planner")
            self.planner.start(powerwall_connector=self.powerwall_connector)

            # Log planner status
            status = self.planner.get_status()
            self.logger.info(f"Task planner started with {status['task_count']} tasks")

            return True

        except Exception as e:
            self.logger.error(f"Failed to start planner: {e}")
            return False

    def stop_planner(self) -> None:
        """Stop the task planner."""
        try:
            self.logger.info("Stopping task planner")
            self.planner.stop()
            self.logger.info("Task planner stopped")
        except Exception as e:
            self.logger.error(f"Error stopping planner: {e}")

    def start_web_interface(self) -> bool:
        """
        Start the web interface in a separate thread.

        Returns:
            True if web interface started successfully, False otherwise
        """
        try:
            config = get_config()

            if not config.web_interface.enabled:
                self.logger.info("Web interface disabled in configuration")
                return True

            self.logger.info("Starting web interface")

            # Note: Planner already started in start_planner() method
            # No need to start it again here

            # Create Flask app and pass the connector
            self.flask_app = create_app(
                config=config,
                testing=False,
                powerwall_connector=self.powerwall_connector
            )

            # Store references for cross-component access
            self.flask_app.planner = self.planner
            self.flask_app.config_manager = self.config_manager

            # Start Flask in a separate thread
            def run_flask():
                try:
                    self.flask_app.run(
                        host=config.web_interface.host,
                        port=config.web_interface.port,
                        debug=config.web_interface.debug,
                        threaded=True,
                        use_reloader=False  # Disable reloader in threaded mode
                    )
                except Exception as e:
                    self.logger.error(f"Flask web server error: {e}")

            self.web_thread = threading.Thread(target=run_flask, daemon=True)
            self.web_thread.start()

            self.logger.info(f"Web interface started on {config.web_interface.host}:{config.web_interface.port}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to start web interface: {e}")
            return False

    def stop_web_interface(self) -> None:
        """Stop the web interface."""
        try:
            if self.web_thread and self.web_thread.is_alive():
                self.logger.info("Stopping web interface")
                # Flask doesn't have a clean shutdown method when running in a thread
                # The thread will be cleaned up when the main process exits
                self.logger.info("Web interface thread will stop with main process")
        except Exception as e:
            self.logger.error(f"Error stopping web interface: {e}")

    def add_custom_job(self, job_id: str, time_str: str, percentage: float,
                      description: str = "") -> bool:
        """
        Add a custom scheduled job.

        Args:
            job_id: Unique identifier for the job
            time_str: Time in HH:MM format
            percentage: Target percentage (0-100)
            description: Optional description

        Returns:
            True if job was added successfully, False otherwise
        """
        try:
            job = create_reserve_change_job(time_str, percentage, description)

            self.schedule_manager.add_job(
                job_id=job_id,
                name=job.name,
                schedule_time=time_str,
                job_func=job,
                description=job.description,
                enabled=True
            )

            self.logger.info(f"Added custom job: {job.name}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to add custom job: {e}")
            return False

    def run_job_manually(self, job_id: str) -> bool:
        """
        Manually execute a specific job.

        Args:
            job_id: ID of the job to execute

        Returns:
            True if job executed successfully, False otherwise
        """
        try:
            job_info = self.schedule_manager.get_job_info(job_id)
            self.logger.info(f"Manually executing job: {job_info.name}")

            # For manual execution, we need to find and execute the job function
            # This is a simplified approach - in practice, you might want to
            # store job instances separately
            matching_jobs = [job for job in self.schedule_manager._jobs.values()
                           if job.job_id == job_id]

            if not matching_jobs:
                self.logger.error(f"Job {job_id} not found")
                return False

            # Execute the job (this is simplified - actual implementation
            # would need to access the job function properly)
            self.logger.info(f"Job {job_id} would be executed manually")
            return True

        except Exception as e:
            self.logger.error(f"Failed to execute job manually: {e}")
            return False

    def get_status(self) -> dict:
        """
        Get comprehensive application status.

        Returns:
            Dictionary with application status information
        """
        try:
            config_status = self.config_manager.get_config_status()
            planner_status = self.planner.get_status()

            return {
                'application': {
                    'running': True,
                    'shutdown_requested': self._shutdown_requested
                },
                'configuration': config_status,
                'planner': planner_status
            }

        except Exception as e:
            self.logger.error(f"Failed to get application status: {e}")
            return {'error': str(e)}

    def run(self, config_path: Optional[str] = None) -> int:
        """
        Run the PowerNight application.

        Args:
            config_path: Optional path to configuration file

        Returns:
            Exit code (0 for success, non-zero for error)
        """
        try:
            # Initialize application
            if not self.initialize(config_path):
                self.logger.error("Application initialization failed")
                return 1

            # Start planner
            if not self.start_planner():
                self.logger.error("Failed to start planner")
                return 1

            # Start web interface
            if not self.start_web_interface():
                self.logger.error("Failed to start web interface")
                return 1

            self.logger.info("PowerNight application started successfully")
            self.logger.info("Press Ctrl+C to shutdown gracefully")

            # Main application loop
            while not self._shutdown_requested:
                try:
                    time.sleep(1)

                    # Periodic status logging (every 5 minutes)
                    if int(time.time()) % 300 == 0:
                        status = self.get_status()
                        planner_status = status.get('planner', {})
                        self.logger.info(
                            f"Status: Tasks={planner_status.get('task_count', 0)}, "
                            f"Running={planner_status.get('is_running', False)}, "
                            f"Next run={planner_status.get('next_run', 'None')}"
                        )

                except KeyboardInterrupt:
                    self.logger.info("Keyboard interrupt received")
                    break
                except Exception as e:
                    self.logger.error(f"Error in main loop: {e}")
                    time.sleep(1)

            # Graceful shutdown
            self.logger.info("Shutting down PowerNight application")
            self.stop_planner()
            self.stop_web_interface()
            self.logger.info("PowerNight application stopped")

            return 0

        except Exception as e:
            self.logger.critical(f"Critical error in application: {e}")
            return 1


def main() -> int:
    """
    Main entry point for the PowerNight application.

    Returns:
        Exit code
    """
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
        ]
    )

    # Create and run application
    app = PowerNightApp()
    return app.run()


if __name__ == "__main__":
    sys.exit(main())
