from typing import List, Tuple, Optional
from panda3d.core import NodePath, Vec3, Point3, BitMask32, CollisionSolid, CollisionBox, CollisionNode
from direct.showbase.ShowBase import ShowBase

from src.objects.factory.game_object_factory import GameObjectFactory
from src.entities.entity import Entity
from src.core.config import ROOM_SIZE, WALL_THICKNESS
from src.entities.components.collider_component import ColliderComponent

class RoomBuilder:
    """
    Constrói salas completas com paredes, teto e piso.
    Implementa o padrão Builder para construção complexa de salas.
    """
    
    def __init__(self, factory: GameObjectFactory):
        """
        Inicializa o construtor de salas.
        
        Args:
            factory: Fábrica de objetos de jogo
        """
        self._factory = factory
        self._created_entities: List[Entity] = []
    
    def build_rectangular_room(self, 
                              parent: NodePath,
                              width: float, 
                              length: float, 
                              height: float,
                              wall_thickness: float = WALL_THICKNESS,
                              position: Tuple[float, float, float] = (0, 0, 0)) -> List[Entity]:
        """
        Constrói uma sala retangular completa.
        
        Args:
            parent: NodePath pai
            width: Largura da sala
            length: Comprimento da sala
            height: Altura da sala
            wall_thickness: Espessura das paredes
            position: Posição central da sala
            
        Returns:
            Lista de entidades criadas
        """
        self._created_entities = []
        
        # Calcular half sizes e posição
        hw, hl = width/2, length/2
        pos_x, pos_y, pos_z = position
        
        # Criar o piso
        floor = self._factory.create_floor(
            parent=parent,
            position=(pos_x, pos_y, pos_z - wall_thickness/2),  # Base em z=0
            scale=(width, length, wall_thickness)
        )
        self._created_entities.append(floor)
        self._ensure_solid_collisions(floor, (hw, hl, wall_thickness/2))
        
        # Criar as paredes
        wall_front = self._factory.create_wall(
            parent=parent,
            position=(pos_x, pos_y + hl + wall_thickness/2, pos_z + height/2),
            scale=(width + wall_thickness*2, wall_thickness, height)
        )
        self._created_entities.append(wall_front)
        self._ensure_solid_collisions(wall_front, (hw + wall_thickness, wall_thickness/2, height/2))
        
        wall_back = self._factory.create_wall(
            parent=parent,
            position=(pos_x, pos_y - hl - wall_thickness/2, pos_z + height/2),
            scale=(width + wall_thickness*2, wall_thickness, height)
        )
        self._created_entities.append(wall_back)
        self._ensure_solid_collisions(wall_back, (hw + wall_thickness, wall_thickness/2, height/2))
        
        wall_left = self._factory.create_wall(
            parent=parent,
            position=(pos_x - hw - wall_thickness/2, pos_y, pos_z + height/2),
            scale=(wall_thickness, length + wall_thickness*2, height)
        )
        self._created_entities.append(wall_left)
        self._ensure_solid_collisions(wall_left, (wall_thickness/2, hl + wall_thickness, height/2))
        
        wall_right = self._factory.create_wall(
            parent=parent,
            position=(pos_x + hw + wall_thickness/2, pos_y, pos_z + height/2),
            scale=(wall_thickness, length + wall_thickness*2, height)
        )
        self._created_entities.append(wall_right)
        self._ensure_solid_collisions(wall_right, (wall_thickness/2, hl + wall_thickness, height/2))
        
        # Criar o teto
        ceiling = self._factory.create_ceiling(
            parent=parent,
            position=(pos_x, pos_y, pos_z + height + wall_thickness/2),
            scale=(width, length, wall_thickness)
        )
        self._created_entities.append(ceiling)
        self._ensure_solid_collisions(ceiling, (hw, hl, wall_thickness/2))
        
        print(f"Sala construída com {len(self._created_entities)} elementos - todas as colisões verificadas")
        return self._created_entities
    
    def _ensure_solid_collisions(self, entity: Entity, dimensions: Tuple[float, float, float]) -> None:
        """
        Garante que a entidade tenha colisões sólidas.
        
        Args:
            entity: A entidade a verificar
            dimensions: Dimensões para colisão (x, y, z)
        """
        # Certifica-se que o ColliderComponent existe e está configurado corretamente
        collider = entity.get_component(ColliderComponent)
        if collider and collider.physics_node:
            # Garante que o corpo físico tem as máscara de colisão corretas
            if hasattr(collider.physics_node, 'setIntoCollideMask'):
                collider.physics_node.setIntoCollideMask(BitMask32.allOn())
        
        # Adiciona um CollisionNode redundante para garantir que há colisão
        coll_node = CollisionNode(f'{entity.name}_solid_collision')
        coll_node.addSolid(CollisionBox(Point3(0, 0, 0), dimensions[0], dimensions[1], dimensions[2]))
        coll_node.setIntoCollideMask(BitMask32.bit(0))  # Máscara padrão
        
        # Garante que o no CollisionNode é filho do NodePath da entidade
        if entity.node_path:
            coll_np = entity.node_path.attachNewNode(coll_node)
            coll_np.setPos(0, 0, 0)
    
    def add_boxes(self, 
                 parent: NodePath, 
                 count: int, 
                 min_size: float = 0.3,
                 max_size: float = 0.8,
                 movable: bool = False,
                 room_bounds: Optional[Tuple[float, float, float, float]] = None,
                 min_distance_from_player: float = 2.0) -> List[Entity]:
        """
        Adiciona caixas aleatórias à sala.
        
        Args:
            parent: NodePath pai
            count: Número de caixas a adicionar
            min_size: Tamanho mínimo das caixas
            max_size: Tamanho máximo das caixas
            movable: Se as caixas podem ser movidas pela física
            room_bounds: (min_x, min_y, max_x, max_y) ou None para usar ROOM_SIZE
            min_distance_from_player: Distância mínima do jogador
            
        Returns:
            Lista de entidades de caixas criadas
        """
        import random
        
        boxes: List[Entity] = []
        
        # Usar ROOM_SIZE se room_bounds não for especificado
        if room_bounds is None:
            width, length, _ = ROOM_SIZE
            min_x, min_y = -width/2 + 1.0, -length/2 + 1.0
            max_x, max_y = width/2 - 1.0, length/2 - 1.0
        else:
            min_x, min_y, max_x, max_y = room_bounds
        
        for i in range(count):
            # Posição aleatória dentro dos limites da sala
            while True:
                pos_x = random.uniform(min_x, max_x)
                pos_y = random.uniform(min_y, max_y)
                
                # Verifica distância do jogador (0,0,0)
                distance_from_player = ((pos_x)**2 + (pos_y)**2)**0.5
                if distance_from_player > min_distance_from_player:
                    break
            
            # Tamanho aleatório
            size = random.uniform(min_size, max_size)
            
            # Cria a caixa
            box = self._factory.create_box(
                parent=parent,
                position=(pos_x, pos_y, size/2),  # Base no chão
                scale=(size, size, size),
                movable=movable
            )
            
            # Garante colisões sólidas para a caixa
            self._ensure_solid_collisions(box, (size/2, size/2, size/2))
            
            boxes.append(box)
            self._created_entities.append(box)
        
        print(f"Criadas {len(boxes)} caixas - todas com colisões verificadas")
        
        return boxes