from typing import Optional, Tuple, List
from panda3d.core import NodePath, Vec3, Point3, Texture, BitMask32, CollisionNode, CollisionBox
from src.entities.entity import Entity
from src.entities.static_object import StaticObject
from src.objects.static_game_object import StaticGameObject
from src.entities.components.collider_component import ColliderComponent


class PhysicsGameObject(StaticGameObject):
    """
    Classe para objetos do jogo que respondem à física.
    Extensão da classe StaticGameObject que adiciona massa e propriedades físicas.
    """

    def __init__(self,
                 name: str,
                 model_path: str,
                 texture: Texture,
                 mass: float = 1.0,
                 friction: float = 0.5,
                 restitution: float = 0.2,
                 collision_dimensions: Optional[Tuple] = None):
        """
        Inicializa um objeto com física.

        Args:
            name: Nome base do objeto
            model_path: Caminho para o modelo 3D
            texture: Textura a ser aplicada
            mass: Massa do objeto (kg)
            friction: Coeficiente de fricção
            restitution: Coeficiente de restituição (bounce)
            collision_dimensions: Dimensões para colisão (se None, usa metade da escala)
        """
        super().__init__(name, model_path, texture, collision_dimensions)
        self._mass = mass
        self._friction = friction
        self._restitution = restitution

    def create(self, parent: NodePath, position: Vec3, scale: Vec3) -> Entity:
        """
        Cria uma instância do objeto físico.

        Args:
            parent: NodePath pai
            position: Posição (Vec3)
            scale: Escala (Vec3)

        Returns:
            A entidade criada
        """
        # Cria um objeto estático base
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

        # Aplica a textura (usando método seguro da classe pai)
        self._enhanced_apply_texture(entity.node_path,
                                     self._texture,
                                     repeat_x=2.0,
                                     repeat_y=2.0)

        # Adiciona propriedades físicas específicas
        collider = entity.get_component(ColliderComponent)
        if collider and collider.physics_node:
            if hasattr(collider.physics_node, 'setMass'):
                collider.physics_node.setMass(self._mass)
            if hasattr(collider.physics_node, 'setFriction'):
                collider.physics_node.setFriction(self._friction)
            if hasattr(collider.physics_node, 'setRestitution'):
                collider.physics_node.setRestitution(self._restitution)

            # CORREÇÃO: Configura explicitamente a máscara de colisão
            if hasattr(collider.physics_node, 'setIntoCollideMask'):
                collider.physics_node.setIntoCollideMask(BitMask32.allOn())
            if hasattr(collider.physics_node, 'setFromCollideMask'):
                collider.physics_node.setFromCollideMask(BitMask32.allOn())

        return entity