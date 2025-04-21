from typing import Dict, Type, TypeVar, Generic, Optional, Any
from src.utils.singleton import Singleton

T = TypeVar('T')

class ServiceLocator(metaclass=Singleton):
    """
    Implementação do padrão Service Locator para facilitar a injeção de dependências.
    Permite que serviços sejam registrados e recuperados por interface, 
    promovendo baixo acoplamento.
    """
    
    def __init__(self):
        self._services: Dict[Type, Any] = {}
    
    def register(self, interface_type: Type[T], implementation: T) -> None:
        """
        Registra uma implementação para uma interface específica.
        
        Args:
            interface_type: O tipo da interface (ou classe base)
            implementation: A implementação concreta da interface
        """
        self._services[interface_type] = implementation
    
    def get(self, interface_type: Type[T]) -> Optional[T]:
        """
        Recupera a implementação registrada para uma interface.
        
        Args:
            interface_type: O tipo da interface (ou classe base)
            
        Returns:
            A implementação registrada ou None se não encontrada
        """
        return self._services.get(interface_type)
    
    def clear(self) -> None:
        """Limpa todos os serviços registrados."""
        self._services.clear()