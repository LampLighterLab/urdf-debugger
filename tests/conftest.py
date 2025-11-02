from pathlib import Path

import pytest

from physcheck.urdf import load_urdf


ROBOT_PATH = Path("robots/cartpole/urdf/cartpole.urdf")


@pytest.fixture(scope="session")
def cartpole_model():
    return load_urdf(ROBOT_PATH)
