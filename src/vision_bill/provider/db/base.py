from abc import ABC, abstractmethod
from typing import List, Any
from src.vision_bill.model.receipt import Receipt  # Placeholder until model is confirmed or found

class DatabaseProvider(ABC):
    @abstractmethod
    async def connect(self) -> None:
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        pass

    @abstractmethod
    async def save_receipt(self, receipt: Receipt) -> None:
        pass

    @abstractmethod
    async def get_tmpimage_since(self, seconds: int) -> List[Any]:
        pass
