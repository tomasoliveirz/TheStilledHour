from typing import Tuple, Optional
from panda3d.core import Vec3, Point3, Quat, LMatrix4f, NodePath

from src.entities.components.component import Component

class TransformComponent(Component):
    """
    Componente que gerencia a transformação (posição, rotação, escala) de uma entidade.
    """
    
    def __init__(self, position: Tuple[float, float, float] = (0, 0, 0),
                rotation: Tuple[float, float, float] = (0, 0, 0),
                scale: Tuple[float, float, float] = (1, 1, 1)):
        """
        Inicializa o componente de transformação.
        
        Args:
            position: Posição inicial (x, y, z)
            rotation: Rotação inicial em graus (h, p, r)
            scale: Escala inicial (sx, sy, sz)
        """
        super().__init__()
        
        # Armazena valores iniciais
        self._position = Vec3(*position)
        self._rotation = Vec3(*rotation)
        self._scale = Vec3(*scale)
        
        # Armazena forward, right e up
        self._forward = Vec3(0, 1, 0)  # Orientação padrão do Panda3D (y+)
        self._right = Vec3(1, 0, 0)    # x+
        self._up = Vec3(0, 0, 1)       # z+
        
        # Controle de dirty flag para otimização
        self._dirty = True
    
    def on_initialize(self) -> None:
        """Inicialização após ser adicionado à entidade."""
        # Aplica transformações iniciais ao NodePath
        self._apply_transform()
    
    def on_update(self, dt: float) -> None:
        """
        Atualiza o componente.
        
        Args:
            dt: Delta time (tempo desde o último frame)
        """
        # Se os valores mudaram, aplica as transformações
        if self._dirty:
            self._apply_transform()
            self._dirty = False
    
    def _apply_transform(self) -> None:
        """Aplica as transformações atuais ao NodePath da entidade."""
        node_path = self.entity.node_path if self.entity else None
        
        if node_path:
            # Aplica posição
            node_path.setPos(self._position)
            
            # Aplica rotação
            node_path.setHpr(self._rotation)
            
            # Aplica escala
            node_path.setScale(self._scale)
            
            # Atualiza vetores de direção
            rotation_quat = node_path.getQuat()
            
            # Atualiza forward, right e up com base na rotação atual
            self._forward = rotation_quat.xform(Vec3(0, 1, 0))
            self._right = rotation_quat.xform(Vec3(1, 0, 0))
            self._up = rotation_quat.xform(Vec3(0, 0, 1))
    
    def translate(self, delta: Tuple[float, float, float]) -> None:
        """
        Move a entidade relativamente à sua posição atual.
        
        Args:
            delta: Vetor de translação (dx, dy, dz)
        """
        self._position += Vec3(*delta)
        self._dirty = True
    
    def translate_local(self, forward: float = 0, right: float = 0, up: float = 0) -> None:
        """
        Move a entidade no espaço local (relativo à orientação atual).
        
        Args:
            forward: Distância a mover no eixo forward
            right: Distância a mover no eixo right
            up: Distância a mover no eixo up
        """
        delta = (self._forward * forward + 
                 self._right * right + 
                 self._up * up)
        
        self._position += delta
        self._dirty = True
    
    def rotate(self, delta: Tuple[float, float, float]) -> None:
        """
        Rotaciona a entidade relativamente à sua rotação atual.
        
        Args:
            delta: Vetor de rotação em graus (dh, dp, dr)
        """
        self._rotation += Vec3(*delta)
        self._dirty = True
    
    def look_at(self, point: Tuple[float, float, float]) -> None:
        """
        Faz a entidade olhar para um ponto no espaço.
        
        Args:
            point: Ponto para olhar (x, y, z)
        """
        node_path = self.entity.node_path if self.entity else None
        
        if node_path:
            # Usa a função lookAt do Panda3D
            node_path.lookAt(Point3(*point))
            
            # Atualiza o vetor de rotação
            self._rotation = node_path.getHpr()
            
            # Atualiza vetores de direção
            rotation_quat = node_path.getQuat()
            self._forward = rotation_quat.xform(Vec3(0, 1, 0))
            self._right = rotation_quat.xform(Vec3(1, 0, 0))
            self._up = rotation_quat.xform(Vec3(0, 0, 1))
    
    def set_position(self, position: Tuple[float, float, float]) -> None:
        """
        Define a posição absoluta da entidade.
        
        Args:
            position: Nova posição (x, y, z)
        """
        self._position = Vec3(*position)
        self._dirty = True
    
    def set_rotation(self, rotation: Tuple[float, float, float]) -> None:
        """
        Define a rotação absoluta da entidade em graus.
        
        Args:
            rotation: Nova rotação (h, p, r)
        """
        self._rotation = Vec3(*rotation)
        self._dirty = True
    
    def set_scale(self, scale: Tuple[float, float, float]) -> None:
        """
        Define a escala absoluta da entidade.
        
        Args:
            scale: Nova escala (sx, sy, sz)
        """
        self._scale = Vec3(*scale)
        self._dirty = True
    
    @property
    def position(self) -> Vec3:
        """Retorna a posição atual."""
        return self._position
    
    @property
    def rotation(self) -> Vec3:
        """Retorna a rotação atual em graus."""
        return self._rotation
    
    @property
    def scale(self) -> Vec3:
        """Retorna a escala atual."""
        return self._scale
    
    @property
    def forward(self) -> Vec3:
        """Retorna o vetor de direção forward."""
        return self._forward
    
    @property
    def right(self) -> Vec3:
        """Retorna o vetor de direção right."""
        return self._right
    
    @property
    def up(self) -> Vec3:
        """Retorna o vetor de direção up."""
        return self._up
    
    def get_world_matrix(self) -> LMatrix4f:
        """
        Retorna a matriz de transformação mundial da entidade.
        
        Returns:
            Matrix4 representando a transformação mundial
        """
        node_path = self.entity.node_path if self.entity else None
        
        if node_path:
            return node_path.getMat()
        
        # Retorna matriz identidade se não tiver NodePath
        return LMatrix4f.identMat()