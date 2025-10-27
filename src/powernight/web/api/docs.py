"""
PowerNight API Documentation

OpenAPI/Swagger documentation generator for the PowerNight enterprise API.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
import json
from datetime import datetime

from flask import Blueprint, jsonify, render_template_string
from ...core.config import get_config


docs_bp = Blueprint('docs', __name__, url_prefix='/docs')


@dataclass
class APIEndpoint:
    """Represents an API endpoint documentation."""
    path: str
    method: str
    summary: str
    description: str
    tags: List[str]
    parameters: List[Dict[str, Any]]
    request_body: Optional[Dict[str, Any]] = None
    responses: Dict[str, Dict[str, Any]] = None
    security: List[Dict[str, Any]] = None
    rate_limit: Optional[str] = None

    def to_openapi(self) -> Dict[str, Any]:
        """Convert to OpenAPI specification format."""
        spec = {
            'summary': self.summary,
            'description': self.description,
            'tags': self.tags,
        }

        if self.parameters:
            spec['parameters'] = self.parameters

        if self.request_body:
            spec['requestBody'] = self.request_body

        if self.responses:
            spec['responses'] = self.responses
        else:
            spec['responses'] = {
                '200': {
                    'description': 'Successful operation',
                    'content': {
                        'application/json': {
                            'schema': {'type': 'object'}
                        }
                    }
                }
            }

        if self.security:
            spec['security'] = self.security

        if self.rate_limit:
            spec['x-rate-limit'] = self.rate_limit

        return spec


class OpenAPIDocumentationGenerator:
    """Enterprise OpenAPI documentation generator."""

    def __init__(self):
        """Initialize the documentation generator."""
        self.endpoints = []
        self.schemas = {}
        self._load_schemas()
        self._define_endpoints()

    def _load_schemas(self) -> None:
        """Load JSON schemas for documentation."""
        from .schemas import BACKUP_RESERVE_SCHEMA

        # Convert JSON schemas to OpenAPI format
        self.schemas = {
            'BackupReserveRequest': self._convert_jsonschema_to_openapi(BACKUP_RESERVE_SCHEMA),
            'ValidationResult': {
                'type': 'object',
                'properties': {
                    'is_valid': {'type': 'boolean', 'description': 'Whether validation passed'},
                    'errors': {
                        'type': 'array',
                        'items': {'type': 'string'},
                        'description': 'List of validation errors'
                    },
                    'warnings': {
                        'type': 'array',
                        'items': {'type': 'string'},
                        'description': 'List of validation warnings'
                    },
                    'error_count': {'type': 'integer', 'description': 'Number of errors'},
                    'warning_count': {'type': 'integer', 'description': 'Number of warnings'}
                }
            },
            'StatusResponse': {
                'type': 'object',
                'properties': {
                    'status': {'type': 'string', 'description': 'Current system status'},
                    'timestamp': {'type': 'string', 'format': 'date-time'},
                    'version': {'type': 'string', 'description': 'Application version'},
                    'uptime': {'type': 'number', 'description': 'Uptime in seconds'},
                    'powerwall': {
                        'type': 'object',
                        'properties': {
                            'connected': {'type': 'boolean'},
                            'battery_level': {'type': 'number'},
                            'backup_reserve': {'type': 'number'}
                        }
                    },
                    'scheduler': {
                        'type': 'object',
                        'properties': {
                            'running': {'type': 'boolean'},
                            'job_count': {'type': 'integer'},
                            'next_run': {'type': 'string', 'format': 'date-time'}
                        }
                    }
                }
            },
            'ConfigurationHistory': {
                'type': 'object',
                'properties': {
                    'version': {'type': 'string'},
                    'timestamp': {'type': 'string', 'format': 'date-time'},
                    'user_id': {'type': 'string'},
                    'changes': {'type': 'object'},
                    'backup_path': {'type': 'string'}
                }
            },
            'ErrorResponse': {
                'type': 'object',
                'properties': {
                    'error': {'type': 'string', 'description': 'Error message'},
                    'code': {'type': 'string', 'description': 'Error code'},
                    'details': {'type': 'object', 'description': 'Additional error details'},
                    'timestamp': {'type': 'string', 'format': 'date-time'},
                    'request_id': {'type': 'string', 'description': 'Unique request identifier'}
                }
            },
            'SystemMetrics': {
                'type': 'object',
                'properties': {
                    'cpu_percent': {'type': 'number', 'description': 'CPU usage percentage'},
                    'memory_percent': {'type': 'number', 'description': 'Memory usage percentage'},
                    'memory_used_mb': {'type': 'number', 'description': 'Memory used in MB'},
                    'memory_available_mb': {'type': 'number', 'description': 'Memory available in MB'},
                    'disk_usage_percent': {'type': 'number', 'description': 'Disk usage percentage'},
                    'network_sent_mb': {'type': 'number', 'description': 'Network data sent in MB'},
                    'network_recv_mb': {'type': 'number', 'description': 'Network data received in MB'},
                    'process_count': {'type': 'integer', 'description': 'Number of running processes'},
                    'uptime_seconds': {'type': 'number', 'description': 'System uptime in seconds'},
                    'timestamp': {'type': 'string', 'format': 'date-time'}
                }
            },
            'Alert': {
                'type': 'object',
                'properties': {
                    'type': {'type': 'string', 'description': 'Alert type'},
                    'severity': {'type': 'string', 'enum': ['warning', 'critical'], 'description': 'Alert severity'},
                    'message': {'type': 'string', 'description': 'Alert message'},
                    'value': {'type': 'number', 'description': 'Current value that triggered alert'},
                    'threshold': {'type': 'number', 'description': 'Threshold value'},
                    'timestamp': {'type': 'string', 'format': 'date-time'}
                }
            }
        }

    def _convert_jsonschema_to_openapi(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Convert JSON Schema to OpenAPI schema format."""
        # This is a simplified conversion - in practice, you might want a more robust converter
        openapi_schema = {}

        for key, value in schema.items():
            if key == '$schema':
                continue
            elif key == 'additionalProperties':
                openapi_schema['additionalProperties'] = value
            else:
                openapi_schema[key] = value

        return openapi_schema

    def _define_endpoints(self) -> None:
        """Define all API endpoints for documentation."""

        # Status endpoints
        self.endpoints.append(APIEndpoint(
            path='/api/v1/status',
            method='get',
            summary='Get system status',
            description='Retrieve comprehensive system status including Powerwall connection, scheduler state, and application health.',
            tags=['System'],
            parameters=[],
            responses={
                '200': {
                    'description': 'System status retrieved successfully',
                    'content': {
                        'application/json': {
                            'schema': {'$ref': '#/components/schemas/StatusResponse'}
                        }
                    }
                }
            },
            rate_limit='60 requests per minute'
        ))

        # Configuration endpoints
        self.endpoints.append(APIEndpoint(
            path='/api/v1/config',
            method='get',
            summary='Get current configuration',
            description='Retrieve the current PowerNight configuration with sensitive fields masked.',
            tags=['Configuration'],
            parameters=[],
            security=[{'ApiKeyAuth': []}, {'BasicAuth': []}],
            responses={
                '200': {
                    'description': 'Configuration retrieved successfully',
                    'content': {
                        'application/json': {
                            'schema': {'$ref': '#/components/schemas/ConfigurationUpdate'}
                        }
                    }
                },
                '401': {'$ref': '#/components/responses/UnauthorizedError'}
            },
            rate_limit='30 requests per minute'
        ))

        self.endpoints.append(APIEndpoint(
            path='/api/v1/config',
            method='post',
            summary='Update configuration',
            description='Update PowerNight configuration with enterprise-grade validation and automatic backup.',
            tags=['Configuration'],
            parameters=[],
            request_body={
                'required': True,
                'content': {
                    'application/json': {
                        'schema': {'$ref': '#/components/schemas/ConfigurationUpdate'}
                    }
                }
            },
            security=[{'ApiKeyAuth': []}, {'BasicAuth': []}],
            responses={
                '200': {
                    'description': 'Configuration updated successfully',
                    'content': {
                        'application/json': {
                            'schema': {
                                'type': 'object',
                                'properties': {
                                    'success': {'type': 'boolean'},
                                    'message': {'type': 'string'},
                                    'validation_result': {'$ref': '#/components/schemas/ValidationResult'},
                                    'backup_version': {'type': 'string'}
                                }
                            }
                        }
                    }
                },
                '400': {'$ref': '#/components/responses/ValidationError'},
                '401': {'$ref': '#/components/responses/UnauthorizedError'},
                '429': {'$ref': '#/components/responses/RateLimitError'}
            },
            rate_limit='10 requests per minute'
        ))

        self.endpoints.append(APIEndpoint(
            path='/api/v1/config/validate',
            method='post',
            summary='Validate configuration',
            description='Validate configuration data without applying changes. Useful for form validation.',
            tags=['Configuration'],
            parameters=[],
            request_body={
                'required': True,
                'content': {
                    'application/json': {
                        'schema': {'$ref': '#/components/schemas/ConfigurationUpdate'}
                    }
                }
            },
            security=[{'ApiKeyAuth': []}, {'BasicAuth': []}],
            responses={
                '200': {
                    'description': 'Validation completed',
                    'content': {
                        'application/json': {
                            'schema': {'$ref': '#/components/schemas/ValidationResult'}
                        }
                    }
                }
            },
            rate_limit='60 requests per minute'
        ))

        self.endpoints.append(APIEndpoint(
            path='/api/v1/config/history',
            method='get',
            summary='Get configuration history',
            description='Retrieve configuration change history with pagination support.',
            tags=['Configuration'],
            parameters=[
                {
                    'name': 'limit',
                    'in': 'query',
                    'description': 'Maximum number of entries to return',
                    'schema': {'type': 'integer', 'default': 10, 'maximum': 100}
                },
                {
                    'name': 'offset',
                    'in': 'query',
                    'description': 'Number of entries to skip',
                    'schema': {'type': 'integer', 'default': 0}
                }
            ],
            security=[{'ApiKeyAuth': []}, {'BasicAuth': []}],
            responses={
                '200': {
                    'description': 'Configuration history retrieved',
                    'content': {
                        'application/json': {
                            'schema': {
                                'type': 'object',
                                'properties': {
                                    'history': {
                                        'type': 'array',
                                        'items': {'$ref': '#/components/schemas/ConfigurationHistory'}
                                    },
                                    'total': {'type': 'integer'},
                                    'limit': {'type': 'integer'},
                                    'offset': {'type': 'integer'}
                                }
                            }
                        }
                    }
                }
            },
            rate_limit='30 requests per minute'
        ))

        # Backup reserve endpoints
        self.endpoints.append(APIEndpoint(
            path='/api/v1/backup-reserve',
            method='post',
            summary='Set backup reserve percentage',
            description='Set the Powerwall backup reserve percentage with optional scheduling and validation.',
            tags=['Powerwall'],
            parameters=[],
            request_body={
                'required': True,
                'content': {
                    'application/json': {
                        'schema': {'$ref': '#/components/schemas/BackupReserveRequest'}
                    }
                }
            },
            security=[{'ApiKeyAuth': []}, {'BasicAuth': []}],
            responses={
                '200': {
                    'description': 'Backup reserve updated successfully',
                    'content': {
                        'application/json': {
                            'schema': {
                                'type': 'object',
                                'properties': {
                                    'success': {'type': 'boolean'},
                                    'message': {'type': 'string'},
                                    'previous_percentage': {'type': 'number'},
                                    'new_percentage': {'type': 'number'},
                                    'timestamp': {'type': 'string', 'format': 'date-time'}
                                }
                            }
                        }
                    }
                },
                '400': {'$ref': '#/components/responses/ValidationError'},
                '500': {'$ref': '#/components/responses/PowerwallError'}
            },
            rate_limit='30 requests per minute'
        ))

        # Monitoring endpoints
        self.endpoints.append(APIEndpoint(
            path='/api/v1/metrics',
            method='get',
            summary='Get performance metrics',
            description='Retrieve comprehensive performance metrics and analytics with time-series data.',
            tags=['Monitoring'],
            parameters=[
                {
                    'name': 'time_window',
                    'in': 'query',
                    'description': 'Time window in hours for metrics',
                    'schema': {'type': 'integer', 'default': 1, 'maximum': 24}
                },
                {
                    'name': 'format',
                    'in': 'query',
                    'description': 'Export format',
                    'schema': {'type': 'string', 'enum': ['json', 'prometheus'], 'default': 'json'}
                },
                {
                    'name': 'include_system',
                    'in': 'query',
                    'description': 'Include system metrics',
                    'schema': {'type': 'boolean', 'default': True}
                },
                {
                    'name': 'include_requests',
                    'in': 'query',
                    'description': 'Include request analytics',
                    'schema': {'type': 'boolean', 'default': True}
                }
            ],
            security=[{'ApiKeyAuth': []}, {'BasicAuth': []}],
            responses={
                '200': {
                    'description': 'Metrics retrieved successfully',
                    'content': {
                        'application/json': {
                            'schema': {
                                'type': 'object',
                                'properties': {
                                    'success': {'type': 'boolean'},
                                    'data': {
                                        'type': 'object',
                                        'properties': {
                                            'timestamp': {'type': 'string', 'format': 'date-time'},
                                            'time_window_hours': {'type': 'integer'},
                                            'current_system': {'$ref': '#/components/schemas/SystemMetrics'},
                                            'request_analytics': {'type': 'object'},
                                            'performance_summary': {'type': 'object'},
                                            'current_alerts': {'type': 'array', 'items': {'type': 'object'}}
                                        }
                                    }
                                }
                            }
                        },
                        'text/plain': {
                            'schema': {'type': 'string', 'description': 'Prometheus format metrics'}
                        }
                    }
                }
            },
            rate_limit='60 requests per minute'
        ))

        self.endpoints.append(APIEndpoint(
            path='/api/v1/metrics/alerts',
            method='get',
            summary='Get system alerts',
            description='Retrieve current system alerts and warnings with filtering capabilities.',
            tags=['Monitoring'],
            parameters=[
                {
                    'name': 'severity',
                    'in': 'query',
                    'description': 'Filter by severity level',
                    'schema': {'type': 'string', 'enum': ['warning', 'critical']}
                },
                {
                    'name': 'limit',
                    'in': 'query',
                    'description': 'Maximum number of alerts to return',
                    'schema': {'type': 'integer', 'default': 50, 'maximum': 100}
                }
            ],
            security=[{'ApiKeyAuth': []}, {'BasicAuth': []}],
            responses={
                '200': {
                    'description': 'Alerts retrieved successfully',
                    'content': {
                        'application/json': {
                            'schema': {
                                'type': 'object',
                                'properties': {
                                    'success': {'type': 'boolean'},
                                    'data': {
                                        'type': 'object',
                                        'properties': {
                                            'alerts': {'type': 'array', 'items': {'$ref': '#/components/schemas/Alert'}},
                                            'alert_count': {'type': 'integer'},
                                            'alert_summary': {'type': 'object'}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            rate_limit='60 requests per minute'
        ))

        self.endpoints.append(APIEndpoint(
            path='/api/v1/health',
            method='get',
            summary='Health check',
            description='Lightweight health check endpoint for monitoring systems and load balancers.',
            tags=['Monitoring'],
            parameters=[],
            responses={
                '200': {
                    'description': 'System is healthy',
                    'content': {
                        'application/json': {
                            'schema': {
                                'type': 'object',
                                'properties': {
                                    'status': {'type': 'string', 'enum': ['healthy', 'degraded', 'unhealthy']},
                                    'timestamp': {'type': 'string', 'format': 'date-time'},
                                    'version': {'type': 'string'},
                                    'uptime_seconds': {'type': 'number'},
                                    'checks': {
                                        'type': 'object',
                                        'properties': {
                                            'configuration': {'type': 'boolean'},
                                            'powerwall': {'type': 'boolean'},
                                            'scheduler': {'type': 'boolean'}
                                        }
                                    }
                                }
                            }
                        }
                    }
                },
                '503': {
                    'description': 'System is unhealthy or degraded',
                    'content': {
                        'application/json': {
                            'schema': {
                                'type': 'object',
                                'properties': {
                                    'status': {'type': 'string'},
                                    'error': {'type': 'string'},
                                    'timestamp': {'type': 'string', 'format': 'date-time'}
                                }
                            }
                        }
                    }
                }
            },
            rate_limit='120 requests per minute'
        ))

    def generate_openapi_spec(self) -> Dict[str, Any]:
        """Generate complete OpenAPI specification."""
        try:
            config = get_config()
        except Exception:
            # Use default config if none is loaded
            from ...core.config import (
                PowerNightConfig, WebInterfaceSettings, PowerwallSettings,
                AutomationSettings, LoggingSettings, MonitoringSettings
            )
            config = PowerNightConfig(
                powerwall=PowerwallSettings(tesla_email="demo@example.com"),
                web_interface=WebInterfaceSettings(host="127.0.0.1", port=5000)
            )

        spec = {
            'openapi': '3.0.3',
            'info': {
                'title': 'PowerNight API',
                'description': '''
Enterprise-grade API for Tesla Powerwall automation and scheduling.

PowerNight provides automated backup reserve percentage management for Tesla Powerwall systems,
with comprehensive scheduling, monitoring, and configuration capabilities.

## Features

- **Automated Scheduling**: Configure time-based backup reserve changes
- **Enterprise Security**: API key and basic authentication with rate limiting
- **Configuration Management**: Full configuration CRUD with backup/rollback
- **Real-time Monitoring**: System status and Powerwall state monitoring
- **Audit Logging**: Comprehensive audit trails for all changes
- **Data Validation**: Enterprise-grade input validation and sanitization

## Authentication

This API supports two authentication methods:

1. **API Key Authentication**: Include `X-API-Key` header with your API key
2. **HTTP Basic Authentication**: Use username/password configured in settings

## Rate Limiting

All endpoints have rate limits to ensure system stability:

- Configuration updates: 10 requests per minute
- Status checks: 60 requests per minute
- Validation: 60 requests per minute
- General endpoints: 30 requests per minute

Rate limit headers are included in all responses.
                ''',
                'version': '1.0.0',
                'contact': {
                    'name': 'PowerNight Support',
                    'url': 'https://github.com/your-org/powernight'
                },
                'license': {
                    'name': 'MIT',
                    'url': 'https://opensource.org/licenses/MIT'
                }
            },
            'servers': [
                {
                    'url': f'http://{config.web_interface.host}:{config.web_interface.port}',
                    'description': 'PowerNight API Server'
                }
            ],
            'paths': {},
            'components': {
                'schemas': self.schemas,
                'securitySchemes': {
                    'ApiKeyAuth': {
                        'type': 'apiKey',
                        'in': 'header',
                        'name': 'X-API-Key',
                        'description': 'API key for authentication'
                    },
                    'BasicAuth': {
                        'type': 'http',
                        'scheme': 'basic',
                        'description': 'HTTP Basic Authentication'
                    }
                },
                'responses': {
                    'UnauthorizedError': {
                        'description': 'Authentication required',
                        'content': {
                            'application/json': {
                                'schema': {'$ref': '#/components/schemas/ErrorResponse'}
                            }
                        }
                    },
                    'ValidationError': {
                        'description': 'Validation failed',
                        'content': {
                            'application/json': {
                                'schema': {
                                    'allOf': [
                                        {'$ref': '#/components/schemas/ErrorResponse'},
                                        {
                                            'type': 'object',
                                            'properties': {
                                                'validation_result': {'$ref': '#/components/schemas/ValidationResult'}
                                            }
                                        }
                                    ]
                                }
                            }
                        }
                    },
                    'RateLimitError': {
                        'description': 'Rate limit exceeded',
                        'content': {
                            'application/json': {
                                'schema': {'$ref': '#/components/schemas/ErrorResponse'}
                            }
                        },
                        'headers': {
                            'X-RateLimit-Limit': {
                                'description': 'Rate limit maximum requests',
                                'schema': {'type': 'integer'}
                            },
                            'X-RateLimit-Remaining': {
                                'description': 'Rate limit remaining requests',
                                'schema': {'type': 'integer'}
                            },
                            'X-RateLimit-Reset': {
                                'description': 'Rate limit reset time',
                                'schema': {'type': 'integer'}
                            }
                        }
                    },
                    'PowerwallError': {
                        'description': 'Powerwall communication error',
                        'content': {
                            'application/json': {
                                'schema': {'$ref': '#/components/schemas/ErrorResponse'}
                            }
                        }
                    }
                }
            },
            'security': [
                {'ApiKeyAuth': []},
                {'BasicAuth': []}
            ]
        }

        # Add endpoint definitions to paths
        for endpoint in self.endpoints:
            path = endpoint.path.replace('/api/v1', '')  # Remove /api/v1 prefix for cleaner docs
            if path not in spec['paths']:
                spec['paths'][path] = {}
            spec['paths'][path][endpoint.method] = endpoint.to_openapi()

        return spec


# Global documentation generator
_doc_generator = OpenAPIDocumentationGenerator()


@docs_bp.route('/openapi.json')
def openapi_spec():
    """Get OpenAPI specification as JSON."""
    return jsonify(_doc_generator.generate_openapi_spec())


@docs_bp.route('/swagger')
def swagger_ui():
    """Serve Swagger UI for interactive API documentation."""
    swagger_html = '''
<!DOCTYPE html>
<html>
<head>
    <title>PowerNight API Documentation</title>
    <link rel="stylesheet" type="text/css" href="https://unpkg.com/swagger-ui-dist@4.15.5/swagger-ui.css" />
    <style>
        body { margin: 0; }
        .swagger-ui .topbar { display: none; }
        .swagger-ui .info .title { color: #1f2937; }
    </style>
</head>
<body>
    <div id="swagger-ui"></div>
    <script src="https://unpkg.com/swagger-ui-dist@4.15.5/swagger-ui-bundle.js"></script>
    <script>
        SwaggerUIBundle({
            url: '/docs/openapi.json',
            dom_id: '#swagger-ui',
            presets: [
                SwaggerUIBundle.presets.apis,
                SwaggerUIBundle.presets.standalone
            ],
            plugins: [
                SwaggerUIBundle.plugins.DownloadUrl
            ],
            layout: "StandaloneLayout",
            deepLinking: true,
            showExtensions: true,
            showCommonExtensions: true,
            defaultModelRendering: 'example',
            defaultModelsExpandDepth: 2,
            defaultModelExpandDepth: 2,
            tryItOutEnabled: true,
            filter: true,
            syntaxHighlight: {
                activate: true,
                theme: "agate"
            }
        });
    </script>
</body>
</html>
    '''
    return swagger_html


@docs_bp.route('/redoc')
def redoc_ui():
    """Serve ReDoc UI for alternative API documentation."""
    redoc_html = '''
<!DOCTYPE html>
<html>
<head>
    <title>PowerNight API Documentation</title>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://fonts.googleapis.com/css?family=Montserrat:300,400,700|Roboto:300,400,700" rel="stylesheet">
    <style>
        body { margin: 0; padding: 0; }
    </style>
</head>
<body>
    <redoc spec-url='/docs/openapi.json'
           theme='light'
           hide-download-button='false'
           native-scrollbars='true'
           no-auto-auth='false'
           path-in-middle-panel='true'
           required-props-first='true'
           sort-props-alphabetically='true'>
    </redoc>
    <script src="https://cdn.jsdelivr.net/npm/redoc@2.0.0/bundles/redoc.standalone.js"></script>
</body>
</html>
    '''
    return redoc_html


@docs_bp.route('/')
def docs_index():
    """Documentation index page."""
    index_html = '''
<!DOCTYPE html>
<html>
<head>
    <title>PowerNight API Documentation</title>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            margin: 0;
            padding: 40px;
            background: #f8fafc;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
            background: white;
            padding: 40px;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        h1 { color: #1f2937; border-bottom: 2px solid #3b82f6; padding-bottom: 10px; }
        h2 { color: #374151; margin-top: 30px; }
        .docs-links {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin: 30px 0;
        }
        .docs-card {
            border: 1px solid #e5e7eb;
            border-radius: 6px;
            padding: 20px;
            text-decoration: none;
            color: inherit;
            transition: all 0.2s;
        }
        .docs-card:hover {
            border-color: #3b82f6;
            box-shadow: 0 4px 12px rgba(59, 130, 246, 0.1);
            transform: translateY(-1px);
        }
        .docs-card h3 {
            margin: 0 0 10px 0;
            color: #1f2937;
        }
        .docs-card p {
            margin: 0;
            color: #6b7280;
            font-size: 14px;
        }
        .feature-list {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }
        .feature {
            background: #f3f4f6;
            padding: 15px;
            border-radius: 6px;
            border-left: 4px solid #3b82f6;
        }
        .feature h4 {
            margin: 0 0 5px 0;
            color: #1f2937;
            font-size: 14px;
        }
        .feature p {
            margin: 0;
            color: #6b7280;
            font-size: 12px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>PowerNight API Documentation</h1>

        <p>
            Welcome to the PowerNight API documentation. PowerNight is an enterprise-grade
            automation system for Tesla Powerwall backup reserve management.
        </p>

        <h2>Documentation Formats</h2>

        <div class="docs-links">
            <a href="/docs/swagger" class="docs-card">
                <h3>Swagger UI</h3>
                <p>Interactive API explorer with request testing capabilities. Try out API endpoints directly from the browser.</p>
            </a>

            <a href="/docs/redoc" class="docs-card">
                <h3>ReDoc</h3>
                <p>Beautiful, responsive API documentation with detailed schemas and examples. Perfect for reference.</p>
            </a>

            <a href="/docs/openapi.json" class="docs-card">
                <h3>OpenAPI Spec</h3>
                <p>Machine-readable OpenAPI 3.0 specification in JSON format. Use for code generation and tooling.</p>
            </a>
        </div>

        <h2>API Features</h2>

        <div class="feature-list">
            <div class="feature">
                <h4>Enterprise Security</h4>
                <p>API key and basic authentication with comprehensive rate limiting</p>
            </div>

            <div class="feature">
                <h4>Configuration Management</h4>
                <p>Full CRUD operations with backup, rollback, and audit capabilities</p>
            </div>

            <div class="feature">
                <h4>Real-time Monitoring</h4>
                <p>System status, Powerwall state, and scheduler monitoring</p>
            </div>

            <div class="feature">
                <h4>Data Validation</h4>
                <p>Enterprise-grade input validation with detailed error reporting</p>
            </div>

            <div class="feature">
                <h4>Automated Scheduling</h4>
                <p>Time-based backup reserve changes with retry mechanisms</p>
            </div>

            <div class="feature">
                <h4>Audit Logging</h4>
                <p>Comprehensive audit trails for all configuration changes</p>
            </div>
        </div>

        <h2>Quick Start</h2>

        <p>
            To get started with the PowerNight API:
        </p>

        <ol>
            <li>Configure authentication in the PowerNight settings</li>
            <li>Obtain an API key or use basic authentication credentials</li>
            <li>Visit the <a href="/docs/swagger">Swagger UI</a> to explore endpoints interactively</li>
            <li>Check the <a href="/api/v1/status">system status</a> to verify connectivity</li>
        </ol>

        <h2>Support</h2>

        <p>
            For support and additional information, please visit the
            <a href="https://github.com/your-org/powernight">PowerNight GitHub repository</a>.
        </p>
    </div>
</body>
</html>
    '''
    return index_html


def get_docs_generator() -> OpenAPIDocumentationGenerator:
    """Get the global documentation generator instance."""
    return _doc_generator