import enum
from typing import Optional

from architectures.base import BaseModel
from architectures.constant_velocity import ConstantVelocityModel
from architectures.vectornet.target_driven_forecaster import TargetDrivenForecaster


class ModelType(enum.Enum):
    """
    Model type
    """
    CONSTANT_VELOCITY = 0
    VECTORNET = 1

    @staticmethod
    def from_str(name: str):
        name = name.lower()
        if name == 'constant_velocity':
            return ModelType.CONSTANT_VELOCITY
        elif name == 'vectornet':
            return ModelType.VECTORNET
        else:
            assert False, 'Invalid Program State!'


def model_factory(model_name: str, params: Optional[dict] = None) -> BaseModel:
    """
    Factory method for model creation

    Args:
        model_name: Model type to create
        params: Model parameters

    Returns: Model
    """
    if params is None:
        params = {}

    catalog = {
        ModelType.CONSTANT_VELOCITY: ConstantVelocityModel,
        ModelType.VECTORNET: TargetDrivenForecaster
    }

    return catalog[ModelType.from_str(model_name)](**params)
