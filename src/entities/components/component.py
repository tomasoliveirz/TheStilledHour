from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

# Evita referência circular
if TYPE_CHECKING:
    from src.entities.entity import Entity

class Component(ABC):
    """
    Classe base para todos os componentes.
    Implementa o padrão Component para um sistema ECS (Entity-Component-System) simplificado.
    """
    
    def __init__(self):
        """Inicializa o componente."""
        self._entity: Optional['Entity'] = None
        self._active = True
    
    def initialize(self, entity: 'Entity') -> None:
        """
        Inicializa o componente com uma entidade.
        
        Args:
            entity: A entidade à qual este componente pertence
        """
        self._entity = entity
        self.on_initialize()
    
    def on_initialize(self) -> None:
        """
        Chamado após a inicialização.
        Subclasses podem sobrescrever para lógica personalizada.
        """
        pass
    
    def update(self, dt: float) -> None:
        """
        Atualiza o componente.
        
        Args:
            dt: Delta time (tempo desde o último frame)
        """
        if self._active:
            self.on_update(dt)
    
    @abstractmethod
    def on_update(self, dt: float) -> None:
        """
        Lógica de atualização específica do componente.
        Deve ser implementada por subclasses.
        
        Args:
            dt: Delta time (tempo desde o último frame)
        """
        pass
    
    def set_active(self, active: bool) -> None:
        """
        Ativa ou desativa o componente.
        
        Args:
            active: True para ativar, False para desativar
        """
        if self._active != active:
            self._active = active
            
            if active:
                self.on_enable()
            else:
                self.on_disable()
    
    def on_enable(self) -> None:
        """
        Chamado quando o componente é ativado.
        Subclasses podem sobrescrever para lógica personalizada.
        """
        pass
    
    def on_disable(self) -> None:
        """
        Chamado quando o componente é desativado.
        Subclasses podem sobrescrever para lógica personalizada.
        """
        pass
    
    def cleanup(self) -> None:
        """
        Limpa todos os recursos associados a este componente.
        Chamado quando o componente é removido da entidade.
        """
        self.on_cleanup()
        self._entity = None
    
    def on_cleanup(self) -> None:
        """
        Chamado durante a limpeza.
        Subclasses devem sobrescrever para liberar recursos.
        """
        pass
    
    @property
    def entity(self) -> Optional['Entity']:
        """Retorna a entidade à qual este componente pertence."""
        return self._entity
    
    @property
    def active(self) -> bool:
        """Retorna se o componente está ativo."""
        return self._active