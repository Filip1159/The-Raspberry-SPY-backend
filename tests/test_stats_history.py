from app.stats_history import StatsHistory, stats_history


def test_keeps_only_the_latest_samples_oldest_first():
    history = StatsHistory(length=3)
    for i in range(5):
        history.add({'cpuUsage': i})

    assert [sample['cpuUsage'] for sample in history.samples()] == [2, 3, 4]


def test_returns_a_copy():
    history = StatsHistory()
    history.add({'cpuUsage': 1})

    history.samples().clear()

    assert len(history.samples()) == 1


def test_history_endpoint_requires_a_token(client):
    response = client.get('/stats/history')

    assert response.status_code == 401
    assert 'msg' in response.json()


def test_history_endpoint_returns_the_samples(client, auth_headers):
    stats_history.add({'cpuUsage': 42, 'cpuTemperature': 50, 'ramUsage': 30, 'humidity': None, 'temperature': None, 'timestamp': 1})

    response = client.get('/stats/history', headers=auth_headers)

    assert response.status_code == 200
    assert response.json()[-1]['cpuUsage'] == 42
