import pytest

from asset_compass.db import initialize, make_engine


@pytest.fixture
def engine():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    initialize(engine)
    yield engine
    engine.dispose()

