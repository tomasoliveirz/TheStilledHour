from typing import Optional, List, Dict, Tuple, Set
from direct.showbase.ShowBase import ShowBase
from panda3d.core import Vec3, Point3, NodePath, BitMask32
from panda3d.core import CollisionTraverser, CollisionHandlerQueue, CollisionNode
from panda3d.core import CollisionBox, CollisionRay, CollisionSegment

from src.utils.event_bus import EventBus
from src.entities.entity import Entity
from src.entities.player import Player
from src.core.config import PLAYER_HEIGHT, PLAYER_COLLISION_RADIUS

class CollisionSystem:
    """
    Sistema de colisão com hitbox paralelepípedo para o jogador.
    Versão final corrigida.
    """
    
    def __init__(self, show_base: ShowBase):
        """
        Inicializa o sistema de colisão.
        
        Args:
            show_base: Instância do ShowBase do Panda3D
        """
        self._show_base = show_base
        self._event_bus = EventBus()
        
        # Entidades com colisão
        self._entities: List[Entity] = []
        self._static_entities: List[Entity] = []  # Objetos que não se movem
        self._player: Optional[Player] = None
        
        # Sistema de colisão do Panda3D
        self._traverser = CollisionTraverser("CollisionSystem")
        self._collision_queue = CollisionHandlerQueue()
    
    def initialize(self) -> None:
        """Inicializa o sistema de colisão."""
        # Registra para eventos
        self._event_bus.subscribe("on_entity_added", self._on_entity_added)
        self._event_bus.subscribe("on_entity_removed", self._on_entity_removed)
        
        print("Sistema de colisão por hitbox paralelepípedo inicializado")
   
    def register_player(self, player: Player) -> None:
        """
        Registra o jogador para processamento especial de colisão.
        
        Args:
            player: A entidade do jogador
        """
        self._player = player
        self.add_entity(player)
        
        # Configura a hitbox para o jogador
        self._setup_player_hitbox()
        
        print(f"Jogador registrado no sistema de colisão: {player.name}")

    def _setup_player_hitbox(self) -> None:
        """
        Configura uma hitbox paralelepípeda para o jogador.
        Versão corrigida.
        """
        if not self._player or not self._player.node_path:
            return
        
        # Define as dimensões da hitbox
        half_width = PLAYER_COLLISION_RADIUS * 0.8
        half_depth = PLAYER_COLLISION_RADIUS * 0.8
        half_height = PLAYER_HEIGHT / 2.0
        
        # Cria um nó de colisão para a hitbox
        hitbox_node = CollisionNode('player_hitbox')
        hitbox_node.setFromCollideMask(BitMask32.bit(1))  # Bit 1 para o jogador
        hitbox_node.setIntoCollideMask(BitMask32(0))  # Jogador não recebe colisões
        
        # Cria o paralelepípedo
        hitbox = CollisionBox(Point3(0, 0, 0), half_width, half_depth, half_height)
        hitbox_node.addSolid(hitbox)
        
        # Adiciona a hitbox ao jogador
        hitbox_np = self._player.node_path.attachNewNode(hitbox_node)
        
        # Armazena referências no jogador
        self._player._hitbox_node = hitbox_node
        self._player._hitbox_np = hitbox_np
        self._player._hitbox_dimensions = (half_width, half_depth, half_height)
        
        # Configura o traverser com a hitbox
        self._traverser.addCollider(hitbox_np, self._collision_queue)
        
        print("Hitbox paralelepípeda configurada para o jogador")

    def add_entity(self, entity: Entity) -> None:
        """
        Adiciona uma entidade para monitoramento de colisão.
        
        Args:
            entity: A entidade a adicionar
        """
        if entity not in self._entities:
            self._entities.append(entity)
            
            # Se é um objeto estático, adiciona colisão
            is_static = entity.name and ("Wall" in entity.name or "Floor" in entity.name or 
                                        "Ceiling" in entity.name or "Box" in entity.name)
            
            if is_static:
                self._static_entities.append(entity)
                self._ensure_entity_has_collision(entity)

    def _ensure_entity_has_collision(self, entity: Entity) -> None:
        """
        Garante que a entidade tem colisão adequada.
        
        Args:
            entity: A entidade a verificar
        """
        # Verifique se a entidade já tem um nó de colisão
        if entity.node_path:
            coll_np = entity.node_path.find("**/+CollisionNode")
            if not coll_np.isEmpty():
                # Já tem colisão, mas vamos corrigir as máscaras
                coll_node = coll_np.node()
                if isinstance(coll_node, CollisionNode):
                    coll_node.setFromCollideMask(BitMask32(0))  # Não detecta colisões
                    coll_node.setIntoCollideMask(BitMask32.bit(1))  # Recebe do jogador
                return
        
        # Se não tem colisão, adiciona
        from src.entities.components.transform_component import TransformComponent
        transform = entity.get_component(TransformComponent)
        
        if transform and entity.node_path:
            # Obtém dimensões aproximadas
            scale = transform.scale
            half_x = scale.x / 2.0
            half_y = scale.y / 2.0
            half_z = scale.z / 2.0
            
            # Cria nó de colisão
            coll_node = CollisionNode(f"{entity.name}_collision")
            coll_node.setFromCollideMask(BitMask32(0))  # Não detecta
            coll_node.setIntoCollideMask(BitMask32.bit(1))  # Recebe do jogador
            
            # Cria paralelepípedo
            box = CollisionBox(Point3(0, 0, 0), half_x, half_y, half_z)
            coll_node.addSolid(box)
            
            # Adiciona à entidade
            coll_np = entity.node_path.attachNewNode(coll_node)
            
            print(f"Colisão adicionada para {entity.name}")

    def _on_entity_added(self, entity: Entity) -> None:
        """Callback quando uma entidade é adicionada à cena."""
        self.add_entity(entity)
    
    def _on_entity_removed(self, entity: Entity) -> None:
        """Callback quando uma entidade é removida da cena."""
        if entity in self._entities:
            self._entities.remove(entity)
        if entity in self._static_entities:
            self._static_entities.remove(entity)
    
    def update(self, dt: float) -> None:
        """
        Atualiza o sistema de colisão.
        
        Args:
            dt: Delta time (tempo desde o último frame)
        """
        # Sistema passivo - colisões verificadas quando necessário
        pass
    
    def check_collision(self, entity: Entity, position: Vec3) -> Tuple[bool, Vec3]:
        """
        Verifica colisão na posição especificada.
        
        Args:
            entity: A entidade a verificar
            position: A posição de destino
            
        Returns:
            Tupla (tem_colisao, posicao_corrigida)
        """
        if entity != self._player or not hasattr(entity, '_hitbox_np'):
            return False, position
        
        # Guarda posição original
        original_pos = entity.node_path.getPos()
        
        # Move temporariamente
        entity.node_path.setPos(position)
        
        # Verifica colisões
        self._collision_queue.clearEntries()
        self._traverser.traverse(self._show_base.render)
        
        # Processa resultados
        has_collision = False
        corrected_pos = Vec3(position)
        
        num_entries = self._collision_queue.getNumEntries()
        if num_entries > 0:
            self._collision_queue.sortEntries()
            
            for i in range(num_entries):
                entry = self._collision_queue.getEntry(i)
                
                # Verificação simplificada
                from_node = entry.getFromNodePath().node()
                if from_node == entity._hitbox_node:
                    has_collision = True
                    
                    # Corrije posição
                    contact_pos = entry.getSurfacePoint(self._show_base.render)
                    contact_normal = entry.getSurfaceNormal(self._show_base.render)
                    
                    # Normaliza a normal
                    if contact_normal.length_squared() > 0:
                        contact_normal.normalize()
                    else:
                        contact_normal = Vec3(0, 0, 1)
                    
                    # Correção mínima
                    correction_vector = contact_normal * 0.05
                    corrected_pos = Vec3(position + correction_vector)
                    break
        
        # Restaura posição
        entity.node_path.setPos(original_pos)
        
        return has_collision, corrected_pos
    
    def check_move_with_sliding(self, entity: Entity, desired_pos: Vec3) -> Vec3:
        """
        Verifica movimento com deslizamento.
        
        Args:
            entity: A entidade a mover
            desired_pos: Posição desejada
            
        Returns:
            Posição final
        """
        # Posição atual
        current_pos = entity.node_path.getPos()
        
        # Teste completo
        has_collision, corrected_pos = self.check_collision(entity, desired_pos)
        
        if not has_collision:
            # Se não há colisão, permite o movimento completo
            return desired_pos
        
        # Se há colisão, tenta movimento separado em X e Y
        x_pos = Vec3(desired_pos.x, current_pos.y, current_pos.z)
        x_collision, x_corrected = self.check_collision(entity, x_pos)
        
        y_pos = Vec3(current_pos.x, desired_pos.y, current_pos.z)
        y_collision, y_corrected = self.check_collision(entity, y_pos)
        
        # Constrói posição final
        final_pos = Vec3(
            x_corrected.x if not x_collision else current_pos.x,
            y_corrected.y if not y_collision else current_pos.y,
            current_pos.z  # Mantém Z atual
        )
        
        # Tenta subir degrau
        if (x_collision or y_collision):
            step_height = 0.35  # Altura máxima para subir
            step_pos = Vec3(desired_pos.x, desired_pos.y, current_pos.z + step_height)
            
            step_collision, step_corrected = self.check_collision(entity, step_pos)
            if not step_collision:
                # Pode subir
                final_pos = Vec3(desired_pos.x, desired_pos.y, current_pos.z + step_height)
        
        return final_pos
    
    def cleanup(self) -> None:
        """Limpa recursos do sistema de colisão."""
        self._event_bus.unsubscribe("on_entity_added", self._on_entity_added)
        self._event_bus.unsubscribe("on_entity_removed", self._on_entity_removed)
        
        if self._player and hasattr(self._player, '_hitbox_np'):
            self._traverser.removeCollider(self._player._hitbox_np)
        
        self._entities.clear()
        self._static_entities.clear()
        self._player = None