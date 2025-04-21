from abc import ABC, abstractmethod
from typing import Optional, Tuple, Any
from panda3d.core import NodePath
from panda3d.bullet import BulletWorld

class IPhysicsService(ABC):
    """
    Interface para o serviço de física.
    Define métodos necessários para gerenciar a física do jogo.
    """
    
    @abstractmethod
    def initialize(self) -> None:
        """Inicializa o sistema de física."""
        pass
    
    @abstractmethod
    def get_bullet_world(self) -> BulletWorld:
        """
        Retorna o mundo de física do Bullet.
        
        Returns:
            Instância do BulletWorld
        """
        pass
    
    @abstractmethod
    def update(self, dt: float) -> None:
        """
        Atualiza a simulação de física.
        
        Args:
            dt: Delta time (tempo desde o último frame)
        """
        pass
    
    @abstractmethod
    def add_rigid_body(self, node: NodePath, mass: float, shape_type: str, 
                      dimensions: Tuple = None, compound: bool = False) -> Any:
        """
        Adiciona um corpo rígido à simulação de física.
        
        Args:
            node: NodePath ao qual o corpo rígido será vinculado
            mass: Massa do corpo rígido (0 para objetos estáticos)
            shape_type: Tipo de forma do collider ('box', 'sphere', 'capsule', etc.)
            dimensions: Dimensões da forma (depende do shape_type)
            compound: Se é um corpo composto (formado por múltiplas formas)
            
        Returns:
            Instância do corpo rígido adicionado
        """
        pass
    
    @abstractmethod
    def remove_rigid_body(self, rigid_body: Any) -> None:
        """
        Remove um corpo rígido da simulação de física.
        
        Args:
            rigid_body: O corpo rígido a remover
        """
        pass
    
    @abstractmethod
    def create_character_controller(self, node: NodePath, radius: float, height: float, 
                                  step_height: float) -> Any:
        """
        Cria um controlador de personagem para movimento com detecção de colisão.
        
        Args:
            node: NodePath do personagem
            radius: Raio do controlador
            height: Altura do controlador
            step_height: Altura máxima que o personagem pode subir sem pular
            
        Returns:
            Instância do controlador de personagem
        """
        pass
    
    @abstractmethod
    def create_ghost_object(self, node: NodePath, shape_type: str, 
                         dimensions: Tuple = None) -> Any:
        """
        Cria um objeto fantasma (ghost) para detecção de colisão sem resposta física.
        
        Args:
            node: NodePath ao qual o objeto fantasma será vinculado
            shape_type: Tipo de forma do collider ('box', 'sphere', 'capsule', etc.)
            dimensions: Dimensões da forma (depende do shape_type)
            
        Returns:
            Instância do objeto fantasma criado
        """
        pass
    
    @abstractmethod
    def perform_ray_test(self, from_pos: Tuple[float, float, float], 
                       to_pos: Tuple[float, float, float]) -> Optional[Any]:
        """
        Realiza um teste de raio (raycast) para detecção de colisão.
        
        Args:
            from_pos: Posição inicial do raio
            to_pos: Posição final do raio
            
        Returns:
            Resultado do teste de raio, ou None se não houver colisão
        """
        pass
    
    @abstractmethod
    def set_gravity(self, gravity: Tuple[float, float, float]) -> None:
        """
        Define a gravidade do mundo de física.
        
        Args:
            gravity: Vetor de gravidade (x, y, z)
        """
        pass
    
    @abstractmethod
    def toggle_debug_visualization(self, enabled: bool) -> None:
        """
        Ativa ou desativa a visualização de debug da física.
        
        Args:
            enabled: True para ativar, False para desativar
        """
        pass
    
    @abstractmethod
    def cleanup(self) -> None:
        """Limpa todos os recursos de física."""
        pass