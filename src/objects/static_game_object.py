from typing import Optional, Tuple, List
from panda3d.core import NodePath, Vec3, Point3, Texture, BitMask32, CollisionNode, CollisionBox
from src.entities.entity import Entity
from src.entities.static_object import StaticObject
from src.objects.game_object import GameObject

class StaticGameObject(GameObject):
    """
    Classe base para objetos estáticos do jogo.
    Implementa o padrão Factory Method para criar objetos estáticos.
    """
    
    def __init__(self, 
                name: str,
                model_path: str,
                texture: Texture,
                collision_dimensions: Optional[Tuple] = None):
        """
        Inicializa um objeto estático.
        
        Args:
            name: Nome base do objeto
            model_path: Caminho para o modelo 3D
            texture: Textura a ser aplicada
            collision_dimensions: Dimensões para colisão (se None, usa metade da escala)
        """
        self._name = name
        self._model_path = model_path
        self._texture = texture
        self._collision_dimensions = collision_dimensions
    
    def create(self, parent: NodePath, position: Vec3, scale: Vec3) -> Entity:
        """
        Cria uma instância do objeto estático.
        
        Args:
            parent: NodePath pai
            position: Posição (Vec3)
            scale: Escala (Vec3)
            
        Returns:
            A entidade criada
        """
        # Cria um objeto estático
        entity = StaticObject(f"{self._name}_{id(position)}")
        
        # Define as dimensões de colisão se não especificadas
        dims = self._collision_dimensions
        if dims is None:
            dims = (scale.x / 2, scale.y / 2, scale.z / 2)
        
        # Configura o objeto
        entity.setup(
            parent=parent,
            model_path=self._model_path,
            position=(position.x, position.y, position.z),
            scale=(scale.x, scale.y, scale.z),
            shape_type="box",
            dimensions=dims
        )
        
        # CORREÇÃO: Garante colisão sólida também no sistema Panda3D
        coll_node = CollisionNode(f'{entity.name}_collision')
        coll_node.addSolid(CollisionBox(Point3(0, 0, 0), dims[0], dims[1], dims[2]))
        coll_node.setIntoCollideMask(BitMask32.bit(0))  # Máscara padrão
        coll_np = entity.node_path.attachNewNode(coll_node)
        
        # Aplica a textura com configurações melhoradas
        self._apply_texture(entity.node_path, 
                           self._texture, 
                           repeat_x=2.0, 
                           repeat_y=2.0)
        
        return entity