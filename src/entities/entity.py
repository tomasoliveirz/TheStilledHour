from typing import Dict, List, Optional, Type, TypeVar, Generic, Any
from panda3d.core import NodePath
import uuid

from src.entities.components.component import Component

T = TypeVar('T', bound=Component)

class Entity:
    """
    Classe base para todas as entidades do jogo.
    Implementa o padrão Component para composição flexível de comportamentos.
    """
    
    def __init__(self, name: str = None):
        """
        Inicializa uma nova entidade.
        
        Args:
            name: Nome da entidade (opcional)
        """
        # Identificador único
        self._id = str(uuid.uuid4())
        
        # Nome amigável (ou baseado no ID se não fornecido)
        self._name = name or f"Entity_{self._id[:8]}"
        
        # NodePath raiz para esta entidade
        self._node_path: Optional[NodePath] = None
        
        # Dicionário para componentes por tipo
        self._components: Dict[Type[Component], Component] = {}
        
        # Flag para entidade ativa/inativa
        self._active = True
    
    def init_node_path(self, parent: NodePath) -> NodePath:
        """
        Inicializa o NodePath desta entidade como filho do nó especificado.
        
        Args:
            parent: O NodePath pai
            
        Returns:
            O NodePath criado
        """
        self._node_path = parent.attachNewNode(self._name)
        return self._node_path
    
    def add_component(self, component: Component) -> None:
        """
        Adiciona um componente à entidade.
        
        Args:
            component: O componente a ser adicionado
        """
        component_type = type(component)
        
        # Verifica se já existe um componente deste tipo
        if component_type in self._components:
            # Se quiser substituir, primeiro remova o antigo
            self.remove_component(component_type)
        
        # Armazena o componente
        self._components[component_type] = component
        
        # Inicializa o componente com esta entidade
        component.initialize(self)
    
    def remove_component(self, component_type: Type[Component]) -> None:
        """
        Remove um componente da entidade.
        
        Args:
            component_type: O tipo do componente a remover
        """
        if component_type in self._components:
            # Chama método de cleanup do componente
            self._components[component_type].cleanup()
            
            # Remove do dicionário
            del self._components[component_type]
    
    def get_component(self, component_type: Type[T]) -> Optional[T]:
        """
        Obtém um componente da entidade pelo tipo.
        
        Args:
            component_type: O tipo do componente a obter
            
        Returns:
            O componente, ou None se não encontrado
        """
        return self._components.get(component_type)
    
    def has_component(self, component_type: Type[Component]) -> bool:
        """
        Verifica se a entidade possui um componente de um tipo específico.
        
        Args:
            component_type: O tipo do componente a verificar
            
        Returns:
            True se a entidade possuir o componente, False caso contrário
        """
        return component_type in self._components
    
    def update(self, dt: float) -> None:
        """
        Atualiza a entidade e todos os seus componentes.
        
        Args:
            dt: Delta time (tempo desde o último frame)
        """
        if not self._active:
            return
        
        # Atualiza todos os componentes
        for component in self._components.values():
            component.update(dt)
    
    def set_active(self, active: bool) -> None:
        """
        Ativa ou desativa a entidade.
        
        Args:
            active: True para ativar, False para desativar
        """
        if self._active != active:
            self._active = active
            
            # Propaga para os componentes
            for component in self._components.values():
                component.set_active(active)
            
            # Oculta ou mostra o NodePath
            if self._node_path:
                if active:
                    self._node_path.show()
                else:
                    self._node_path.hide()
    
    def cleanup(self) -> None:
        """Limpa todos os recursos associados a esta entidade."""
        # Limpa todos os componentes
        for component in list(self._components.values()):
            component.cleanup()
        
        self._components.clear()
        
        # Remove o NodePath
        if self._node_path:
            self._node_path.removeNode()
            self._node_path = None
    
    @property
    def id(self) -> str:
        """Retorna o ID único da entidade."""
        return self._id
    
    @property
    def name(self) -> str:
        """Retorna o nome da entidade."""
        return self._name
    
    @name.setter
    def name(self, name: str) -> None:
        """Define o nome da entidade."""
        self._name = name
        
        # Atualiza o nome do NodePath se existir
        if self._node_path:
            self._node_path.setName(name)
    
    @property
    def node_path(self) -> Optional[NodePath]:
        """Retorna o NodePath da entidade."""
        return self._node_path
    
    @property
    def active(self) -> bool:
        """Retorna se a entidade está ativa."""
        return self._active