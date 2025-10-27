from flask import Blueprint, jsonify, current_app, request
from ...core.config import get_config, get_config_manager
from typing import Any, Dict
import pytz

config_blueprint = Blueprint('config_api', __name__, url_prefix='/api/v1/config')

def get_app_config() -> Dict[str, Any]:
    """
    Get current application configuration.

    Returns:
        Dictionary with app configuration
    """
    try:
        config = get_config()
        return {
            'web': {
                'host': config.web_interface.host,
                'port': config.web_interface.port,
                'debug': config.web_interface.debug,
                'cors_origins': config.web_interface.cors_origins
            },
            'automation': {
                'enabled': config.automation.enabled,
                'schedule_count': len(config.automation.schedule)
            },
            'powerwall': {
                'configured': bool(config.powerwall.tesla_email),
                'timeout': config.powerwall.timeout,
                'retry_attempts': config.powerwall.retry_attempts
            }
        }
    except Exception as e:
        return {'error': f'Failed to load configuration: {e}'}


@config_blueprint.route('', methods=['GET'])
def get_config_api():
    """
    API endpoint to get the application configuration.
    """
    app_config = get_app_config()
    if 'error' in app_config:
        return jsonify({'success': False, 'error': app_config['error']}), 500
    return jsonify({'success': True, 'data': app_config})


@config_blueprint.route('/timezone', methods=['GET'])
def get_timezone_api():
    """
    API endpoint to get the current timezone configuration.
    """
    try:
        config = get_config()
        timezone = config.automation.timezone

        # Get timezone info
        try:
            tz = pytz.timezone(timezone)
            import datetime
            now = datetime.datetime.now(tz)
            tz_offset = now.strftime('%z')
            tz_name = now.strftime('%Z')
            current_time = now.isoformat()
        except Exception as e:
            tz_offset = 'Unknown'
            tz_name = 'Unknown'
            current_time = None

        return jsonify({
            'success': True,
            'data': {
                'timezone': timezone,
                'offset': tz_offset,
                'name': tz_name,
                'current_time': current_time
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@config_blueprint.route('/timezone', methods=['POST'])
def update_timezone_api():
    """
    API endpoint to update the timezone configuration.
    """
    try:
        data = request.get_json()
        new_timezone = data.get('timezone')

        if not new_timezone:
            return jsonify({'success': False, 'error': 'Timezone is required'}), 400

        # Validate timezone
        try:
            pytz.timezone(new_timezone)
        except Exception:
            return jsonify({'success': False, 'error': f'Invalid timezone: {new_timezone}'}), 400

        # Get config manager and update timezone
        config_manager = get_config_manager()
        config = config_manager.get_config()

        # Update the timezone
        config.automation.timezone = new_timezone

        # Save the configuration
        config_manager.save_config(config)

        return jsonify({
            'success': True,
            'message': 'Timezone updated successfully. Restart required for changes to take effect.',
            'data': {'timezone': new_timezone}
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@config_blueprint.route('/timezones', methods=['GET'])
def get_timezones_api():
    """
    API endpoint to get list of available timezones.
    """
    try:
        # Get all timezones
        all_timezones = pytz.common_timezones

        # Group by region
        timezones_by_region = {}
        for tz in all_timezones:
            if '/' in tz:
                region = tz.split('/')[0]
                if region not in timezones_by_region:
                    timezones_by_region[region] = []
                timezones_by_region[region].append(tz)

        # Create formatted list with current offset info
        import datetime
        now_utc = datetime.datetime.now(pytz.UTC)

        formatted_timezones = []
        for tz_name in all_timezones:
            try:
                tz = pytz.timezone(tz_name)
                now_local = now_utc.astimezone(tz)
                offset = now_local.strftime('%z')
                abbr = now_local.strftime('%Z')

                # Format: "Europe/Berlin (CEST, UTC+02:00)"
                formatted = f"{tz_name} ({abbr}, UTC{offset[:3]}:{offset[3:]})"

                region = tz_name.split('/')[0] if '/' in tz_name else 'Other'

                formatted_timezones.append({
                    'value': tz_name,
                    'label': formatted,
                    'region': region,
                    'offset': offset
                })
            except Exception:
                # Skip invalid timezones
                continue

        # Sort by region then by offset
        formatted_timezones.sort(key=lambda x: (x['region'], x['offset'], x['value']))

        return jsonify({
            'success': True,
            'data': {
                'timezones': formatted_timezones,
                'count': len(formatted_timezones)
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
