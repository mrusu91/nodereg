from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class AbstractModule(ABC):

    def __init__(
        self,
        node: Dict[str, Any],
        config: Dict[str, Any],
        chroot_path: Optional[str]=None,
    ) -> None:
        self.node = node
        self.config = config
        self.chroot_path = chroot_path

    @abstractmethod
    def run(self) -> None:
        pass
