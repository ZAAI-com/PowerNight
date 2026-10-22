"""Setup rate limits: status polling has its own bucket, separate from mutations."""

import pytest
from flask import Flask, jsonify

from powernight.web.middleware import configure_middleware


pytestmark = pytest.mark.unit


@pytest.fixture
def client():
    app = Flask(__name__)
    configure_middleware(app)

    @app.route('/api/auth/setup/start', methods=['POST'])
    def start():
        return jsonify({'success': True})

    @app.route('/api/auth/setup/status/<session_id>', methods=['GET'])
    def status(session_id):
        return jsonify({'success': True})

    @app.route('/api/auth/setup/helper/authorization', methods=['GET'])
    def helper():
        return jsonify({'success': True})

    return app.test_client()


def test_setup_mutations_are_limited_to_twenty_per_minute(client):
    codes = [client.post('/api/auth/setup/start').status_code for _ in range(21)]
    assert codes[:20] == [200] * 20
    assert codes[20] == 429
    limited = client.post('/api/auth/setup/start')
    assert limited.json['error_code'] == 'RATE_LIMITED'


def test_status_polling_has_its_own_bucket(client):
    for _ in range(20):
        client.post('/api/auth/setup/start')
    assert client.post('/api/auth/setup/start').status_code == 429

    codes = [client.get('/api/auth/setup/status/abc').status_code for _ in range(121)]
    assert codes[:120] == [200] * 120
    assert codes[120] == 429


def test_helper_bucket_is_separate(client):
    codes = [client.get('/api/auth/setup/helper/authorization').status_code for _ in range(31)]
    assert codes[:30] == [200] * 30
    assert codes[30] == 429
    assert client.post('/api/auth/setup/start').status_code == 200


def test_buckets_are_per_client(client):
    for _ in range(20):
        client.post('/api/auth/setup/start', environ_base={'REMOTE_ADDR': '192.168.1.10'})
    assert client.post('/api/auth/setup/start', environ_base={'REMOTE_ADDR': '192.168.1.10'}).status_code == 429
    assert client.post('/api/auth/setup/start', environ_base={'REMOTE_ADDR': '192.168.1.11'}).status_code == 200
