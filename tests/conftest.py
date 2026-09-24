import pytest

from best_deal.storage import Store


@pytest.fixture
def store():
    return Store(":memory:")
