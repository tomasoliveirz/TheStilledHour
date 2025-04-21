from typing import Tuple, Optional, Any
from panda3d.core import NodePath, Vec3, Point3, BitMask32, CollisionNode, CollisionBox
from panda3d.bullet import BulletRigidBodyNode, BulletGhostNode, BulletCharacterControllerNode

from src.entities.components.component import Component
from src.entities.components.transform_component import TransformComponent
from src.services.interfaces.i_physics_service import IPhysicsService
from src.utils.service_locator import ServiceLocator

class ColliderComponent(Component):
    """
    Componente que gerencia as colisões de uma entidade.
    Oferece interface única para diferentes tipos de colliders (RigidBody, Ghost, CharacterController).
    """
    
    def __init__(self, shape_type: str, dimensions: Tuple = None, mass: float = 0.0, 
                 is_trigger: bool = False, is_character: bool = False, step_height: float = 0.35):
        """
        Inicializa o componente de colisão.
        
        Args:
            shape_type: Tipo da forma de colisão ('box', 'sphere', 'capsule', etc.)
            dimensions: Dimensões da forma (depende do shape_type)
            mass: Massa do corpo (0 para objetos estáticos)
            is_trigger: Se é um trigger (detecta colisões mas não reage fisicamente)
            is_character: Se é um controlador de personagem
            step_height: Altura máxima que o personagem pode subir sem pular (apenas para is_character=True)
        """
        super().__init__()
        
        self._shape_type = shape_type
        self._dimensions = dimensions
        self._mass = mass
        self._is_trigger = is_trigger
        self._is_character = is_character
        self._step_height = step_height
        
        # Referência ao corpo físico/collider
        self._physics_node: Optional[Any] = None
        
        # Referência ao serviço de física
        self._physics_service: Optional[IPhysicsService] = None
        
        # Flag para evitar atualizações cíclicas
        self._is_updating = False
        
        # Nó de colisão adicional do Panda3D para garantir colisões sólidas
        self._collision_node: Optional[CollisionNode] = None
        self._collision_nodepath: Optional[NodePath] = None
    

    def on_initialize(self) -> None:
        """Inicialização após ser adicionado à entidade."""
        # Obtém o serviço de física
        self._physics_service = ServiceLocator().get(IPhysicsService)
        
        if not self._physics_service:
            print("Erro: Serviço de física não disponível")
            return
        
        # Obtém o transform component
        transform = self.entity.get_component(TransformComponent)
        
        if not transform:
            print(f"Erro: A entidade {self.entity.name} não possui um TransformComponent")
            return
        
        # Cria o corpo físico adequado
        if self._is_character:
            self._create_character_controller()
        elif self._is_trigger:
            self._create_ghost()
        else:
            self._create_rigid_body()
        
        # Adiciona também um nó de colisão do sistema nativo do Panda3D 
        # para melhorar a detecção de colisão
        self._add_panda3d_collision()
        
        # Sincroniza posição inicial
        self._sync_transform_to_physics()

    def _create_rigid_body(self) -> None:
        """Cria um corpo rígido para esta entidade."""
        if not self.entity.node_path:
            return
        
        try:
            # Cria o corpo rígido
            self._physics_node = self._physics_service.add_rigid_body(
                self.entity.node_path,
                self._mass,
                self._shape_type,
                self._dimensions
            )
            
            # Configurações para objetos estáticos (paredes, chão, etc.)
            if self._mass == 0 and self._physics_node:
                # Configuração de fricção
                if hasattr(self._physics_node, 'setFriction'):
                    self._physics_node.setFriction(1.0)
                
                # Garantir que o corpo é sólido
                try:
                    if hasattr(self._physics_node, 'setIntoCollideMask'):
                        self._physics_node.setIntoCollideMask(BitMask32.allOn())
                except:
                    print(f"Aviso: setIntoCollideMask não disponível para {self.entity.name}")
                
                # Configurar coeficiente de restituição (bouncing)
                if hasattr(self._physics_node, 'setRestitution'):
                    self._physics_node.setRestitution(0.0)
                
                # Configurar para ser realmente imóvel
                if hasattr(self._physics_node, 'setKinematic'):
                    self._physics_node.setKinematic(False)
            
            print(f"Corpo rígido criado com sucesso: {self.entity.name}")
            
        except Exception as e:
            print(f"Erro ao criar corpo rígido para {self.entity.name}: {e}")

    def _create_ghost(self) -> None:
        """Cria um objeto fantasma (trigger) para esta entidade."""
        if not self.entity.node_path:
            return
        
        try:
            self._physics_node = self._physics_service.create_ghost_object(
                self.entity.node_path,
                self._shape_type,
                self._dimensions
            )
            print(f"Objeto fantasma criado com sucesso: {self.entity.name}")
        except Exception as e:
            print(f"Erro ao criar ghost para {self.entity.name}: {e}")

    def _create_character_controller(self) -> None:
        """Cria um controlador de personagem para esta entidade."""
        if not self.entity.node_path:
            return
        
        try:
            # Normalmente, dimensions é (radius, height) para character controller
            radius = self._dimensions[0] if self._dimensions and len(self._dimensions) > 0 else 0.3
            height = self._dimensions[1] if self._dimensions and len(self._dimensions) > 1 else 1.8
            
            self._physics_node = self._physics_service.create_character_controller(
                self.entity.node_path,
                radius,
                height,
                self._step_height
            )
            
            # Configurações adicionais para o character controller
            if self._physics_node:
                # Configurar máscara de colisão para colidir com tudo
                try:
                    if hasattr(self._physics_node, 'setIntoCollideMask'):
                        self._physics_node.setIntoCollideMask(BitMask32.allOn())
                except:
                    print(f"Aviso: setIntoCollideMask não disponível para character controller")
                
                if hasattr(self._physics_node, 'getShape'):
                    shape = self._physics_node.getShape()
                    if shape and hasattr(shape, 'setMargin'):
                        shape.setMargin(0.04)  # Margem de colisão
            
            print(f"Character controller criado com sucesso: {self.entity.name}")
        except Exception as e:
            print(f"Erro ao criar character controller para {self.entity.name}: {e}")

    def _add_panda3d_collision(self) -> None:
        """
        Adiciona um nó de colisão do sistema nativo do Panda3D para garantir colisões sólidas.
        Implementação aprimorada com melhor detecção de colisão.
        """
        try:
            if not self.entity.node_path or not self._dimensions:
                return
                    
            # Cria um nó de colisão
            coll_node = CollisionNode(f"{self.entity.name}_p3d_collision")
            
            # Configura as máscaras de colisão
            # Para objetos estáticos como paredes e caixas, só recebem colisões
            is_static = self._mass == 0 or (self.entity.name and 
                                        ("wall" in self.entity.name.lower() or
                                        "floor" in self.entity.name.lower() or
                                        "ceiling" in self.entity.name.lower() or
                                        "box" in self.entity.name.lower()))
            
            if is_static:
                # Objetos estáticos só recebem colisões (não detectam)
                coll_node.setFromCollideMask(BitMask32(0))
                coll_node.setIntoCollideMask(BitMask32.allOn())
            else:
                # Objetos dinâmicos (como o jogador) detectam e podem receber colisões
                coll_node.setFromCollideMask(BitMask32.allOn())
                coll_node.setIntoCollideMask(BitMask32.bit(0))  # Inicialmente não recebe colisões
            
            # Adiciona a forma de colisão apropriada
            if self._shape_type == 'box':
                # Cria um box
                half_x, half_y, half_z = self._dimensions
                box = CollisionBox(Point3(0, 0, 0), half_x, half_y, half_z)
                coll_node.addSolid(box)
            
            elif self._shape_type == 'sphere':
                # Cria uma esfera
                from panda3d.core import CollisionSphere
                radius = self._dimensions[0] if len(self._dimensions) > 0 else 0.5
                sphere = CollisionSphere(0, 0, 0, radius)
                coll_node.addSolid(sphere)
            
            elif self._shape_type == 'capsule':
                # Cria uma cápsula
                from panda3d.core import CollisionCapsule
                radius = self._dimensions[0] if len(self._dimensions) > 0 else 0.3
                height = self._dimensions[1] if len(self._dimensions) > 1 else 1.0
                
                # Cria a cápsula entre dois pontos
                capsule = CollisionCapsule(
                    0, 0, -height/2,  # Ponto inferior
                    0, 0, height/2,   # Ponto superior
                    radius            # Raio
                )
                coll_node.addSolid(capsule)
            
            # Adiciona o nó à hierarquia
            self._collision_nodepath = self.entity.node_path.attachNewNode(coll_node)
            self._collision_node = coll_node
            
            # Adiciona um segundo nó de colisão especial para objetos estáticos
            # Este garante colisões ainda mais sólidas
            if is_static:
                # Cria um nó de colisão adicional com configuração diferente
                solid_node = CollisionNode(f"{self.entity.name}_p3d_solid")
                
                # Este nó é puramente "into" - só recebe colisões mas não detecta
                solid_node.setFromCollideMask(BitMask32(0))
                solid_node.setIntoCollideMask(BitMask32.allOn())
                
                # Adiciona a mesma forma mas com uma margem ligeiramente maior
                if self._shape_type == 'box':
                    # Ligeiramente maior para evitar "vazamentos" de colisão
                    half_x, half_y, half_z = self._dimensions
                    # Aumentar em 1% para garantir que cobre completamente
                    solid_box = CollisionBox(Point3(0, 0, 0), 
                                            half_x * 1.01, 
                                            half_y * 1.01, 
                                            half_z * 1.01)
                    solid_node.addSolid(solid_box)
                
                elif self._shape_type == 'sphere':
                    from panda3d.core import CollisionSphere
                    radius = self._dimensions[0] if len(self._dimensions) > 0 else 0.5
                    solid_sphere = CollisionSphere(0, 0, 0, radius * 1.01)
                    solid_node.addSolid(solid_sphere)
                
                elif self._shape_type == 'capsule':
                    from panda3d.core import CollisionCapsule
                    radius = self._dimensions[0] if len(self._dimensions) > 0 else 0.3
                    height = self._dimensions[1] if len(self._dimensions) > 1 else 1.0
                    
                    solid_capsule = CollisionCapsule(
                        0, 0, -height/2,  # Ponto inferior
                        0, 0, height/2,   # Ponto superior
                        radius * 1.01     # Raio ligeiramente maior
                    )
                    solid_node.addSolid(solid_capsule)
                
                # Adiciona o nó sólido à hierarquia
                solid_np = self.entity.node_path.attachNewNode(solid_node)
                solid_np.setPos(0, 0, 0)
                
                # Armazena referência adicional (opcional)
                self._solid_collision_np = solid_np
            
            # Para debugging visual (descomentar para ver colisões durante debug)
            debug_collisions = False
            if debug_collisions:
                if self._collision_nodepath:
                    self._collision_nodepath.show()
                if hasattr(self, '_solid_collision_np') and self._solid_collision_np:
                    self._solid_collision_np.show()
            
            print(f"Colisão Panda3D adicional criada para {self.entity.name}")
            
        except Exception as e:
            print(f"Erro ao criar colisão adicional: {e}")

    def _sync_position_with_physics(self) -> None:
        """
        Sincroniza a posição do TransformComponent com o corpo físico.
        Versão melhorada para evitar problemas de sincronização.
        """
        if not self._physics_node or not self.entity or self._is_updating:
            return
        
        transform = self.entity.get_component(TransformComponent)
        if not transform:
            return
        
        try:
            # Marca como atualizando para evitar loop infinito
            self._is_updating = True
            
            # Obtém o NodePath do corpo físico
            physics_np = None
            if isinstance(self._physics_node, (BulletRigidBodyNode, BulletGhostNode, BulletCharacterControllerNode)):
                physics_np = self.entity.node_path.find(f"**/{self._physics_node.getName()}")
            
            if physics_np:
                # Obtém posições atuais
                current_pos = physics_np.getPos()
                transform_pos = transform.position
                
                # Se houve mudança significativa, atualiza
                if (abs(transform_pos.x - current_pos.x) > 0.001 or 
                    abs(transform_pos.y - current_pos.y) > 0.001 or 
                    abs(transform_pos.z - current_pos.z) > 0.001):
                    
                    # Aplica posição
                    physics_np.setPos(transform.position)
                    
                    # Para o jogador, sempre manter estabilidade vertical
                    if self.entity.name == "Player":
                        physics_np.setHpr(physics_np.getH(), 0, 0)
                    else:
                        # Para outros objetos, aplica a rotação do transform
                        physics_np.setHpr(transform.rotation)
                    
                    # Para corpos rígidos, zeramos velocidades para evitar deslizamento
                    if isinstance(self._physics_node, BulletRigidBodyNode):
                        if hasattr(self._physics_node, 'setLinearVelocity'):
                            self._physics_node.setLinearVelocity(Vec3(0, 0, 0))
                        if hasattr(self._physics_node, 'setAngularVelocity'):
                            self._physics_node.setAngularVelocity(Vec3(0, 0, 0))
                            
                    # Para character controllers, podemos atualizar a posição diretamente
                    if isinstance(self._physics_node, BulletCharacterControllerNode):
                        if hasattr(self._physics_node, 'setTransform'):
                            from panda3d.core import TransformState
                            t = TransformState.makePosHpr(
                                transform.position,
                                Vec3(physics_np.getH(), 0, 0)  # Apenas rotação horizontal
                            )
                            self._physics_node.setTransform(t)
            
            # Também atualiza a colisão do Panda3D se existir
            if self._collision_nodepath:
                self._collision_nodepath.setPos(0, 0, 0)  # Relativo ao nó pai
                
            # Atualiza a colisão sólida adicional se existir
            if hasattr(self, '_solid_collision_np') and self._solid_collision_np:
                self._solid_collision_np.setPos(0, 0, 0)  # Relativo ao nó pai
        except Exception as e:
            print(f"Erro ao sincronizar transform para physics: {e}")
        finally:
            # Sempre reseta a flag de atualização
            self._is_updating = False


    def on_update(self, dt: float) -> None:
        """
        Atualiza o componente.
        
        Args:
            dt: Delta time (tempo desde o último frame)
        """
        if not self._physics_node or self._is_updating:
            return
        
        # Marca como atualizando para evitar loop infinito
        self._is_updating = True
        
        try:
            # Se for um corpo dinâmico ou character controller, sincroniza a física para o transform
            if (isinstance(self._physics_node, BulletRigidBodyNode) and self._mass > 0) or \
               isinstance(self._physics_node, BulletCharacterControllerNode):
                self._sync_physics_to_transform()
        finally:
            # Sempre reseta a flag de atualização
            self._is_updating = False
    
    def _sync_transform_to_physics(self) -> None:
        """Sincroniza a posição do TransformComponent com o corpo físico."""
        if not self._physics_node or not self.entity or self._is_updating:
            return
        
        transform = self.entity.get_component(TransformComponent)
        if not transform:
            return
        
        try:
            # Marca como atualizando para evitar loop infinito
            self._is_updating = True
            
            # Obtém o NodePath do corpo físico
            physics_np = None
            if isinstance(self._physics_node, (BulletRigidBodyNode, BulletGhostNode, BulletCharacterControllerNode)):
                physics_np = self.entity.node_path.find(f"**/{self._physics_node.getName()}")
            
            if physics_np:
                # Verifica se a posição realmente mudou
                current_pos = physics_np.getPos()
                transform_pos = transform.position
                
                if (abs(transform_pos.x - current_pos.x) > 0.001 or 
                    abs(transform_pos.y - current_pos.y) > 0.001 or 
                    abs(transform_pos.z - current_pos.z) > 0.001):
                    
                    # Aplica posição
                    physics_np.setPos(transform.position)
                    
                    # Importante: para o jogador, sempre resetar a rotação para evitar tombamento
                    if self.entity.name == "Player":
                        physics_np.setHpr(physics_np.getH(), 0, 0)
                    else:
                        # Para outros objetos, aplica a rotação do transform
                        physics_np.setHpr(transform.rotation)
                    
                    # Se for um corpo rígido com velocidade, zera para evitar deslizamento
                    if isinstance(self._physics_node, BulletRigidBodyNode):
                        if hasattr(self._physics_node, 'setLinearVelocity'):
                            self._physics_node.setLinearVelocity(Vec3(0, 0, 0))
                        if hasattr(self._physics_node, 'setAngularVelocity'):
                            self._physics_node.setAngularVelocity(Vec3(0, 0, 0))
            
            # Também atualiza a colisão do Panda3D
            if self._collision_nodepath:
                self._collision_nodepath.setPos(0, 0, 0)  # Relativo ao nó pai
        except Exception as e:
            print(f"Erro ao sincronizar transform para physics: {e}")
        finally:
            # Sempre reseta a flag de atualização
            self._is_updating = False
    
    def _sync_physics_to_transform(self) -> None:
        """Sincroniza a posição do corpo físico com o TransformComponent."""
        if not self._physics_node or not self.entity or self._is_updating:
            return
        
        transform = self.entity.get_component(TransformComponent)
        if not transform:
            return
        
        try:
            # Marca como atualizando para evitar loop infinito
            self._is_updating = True
            
            # Obtém o NodePath do corpo físico
            physics_np = None
            if isinstance(self._physics_node, (BulletRigidBodyNode, BulletGhostNode, BulletCharacterControllerNode)):
                physics_np = self.entity.node_path.find(f"**/{self._physics_node.getName()}")
            
            if physics_np:
                # Obtém a posição e rotação do corpo físico
                pos = physics_np.getPos()
                
                # Verifica se a posição realmente mudou
                current_pos = transform.position
                if (abs(pos.x - current_pos.x) > 0.001 or 
                    abs(pos.y - current_pos.y) > 0.001 or 
                    abs(pos.z - current_pos.z) > 0.001):
                    
                    # Atualiza a posição
                    transform.set_position((pos.x, pos.y, pos.z))
        except Exception as e:
            print(f"Erro ao sincronizar physics para transform: {e}")
        finally:
            # Sempre reseta a flag de atualização
            self._is_updating = False
    
    def apply_impulse(self, impulse: Tuple[float, float, float], 
                    point: Tuple[float, float, float] = None) -> None:
        """Aplica um impulso ao corpo rígido."""
        if not self._physics_node or not isinstance(self._physics_node, BulletRigidBodyNode):
            return
        
        try:
            # Converte para Vec3
            impulse_vec = Vec3(*impulse)
            
            if point:
                point_vec = Vec3(*point)
                self._physics_node.applyImpulse(impulse_vec, point_vec)
            else:
                self._physics_node.applyCentralImpulse(impulse_vec)
        except Exception as e:
            print(f"Erro ao aplicar impulso: {e}")
    
    def apply_force(self, force: Tuple[float, float, float], 
                   point: Tuple[float, float, float] = None) -> None:
        """Aplica uma força ao corpo rígido."""
        if not self._physics_node or not isinstance(self._physics_node, BulletRigidBodyNode):
            return
        
        try:
            # Converte para Vec3
            force_vec = Vec3(*force)
            
            if point:
                point_vec = Vec3(*point)
                self._physics_node.applyForce(force_vec, point_vec)
            else:
                self._physics_node.applyCentralForce(force_vec)
        except Exception as e:
            print(f"Erro ao aplicar força: {e}")
    
    def move_character(self, direction: Tuple[float, float, float]) -> None:
        """Move um controlador de personagem."""
        if not self._physics_node:
            return
        
        try:
            # Converte para Vec3
            direction_vec = Vec3(*direction)
            
            # Não processar movimento se for muito pequeno
            if direction_vec.length_squared() < 0.000001:
                return
            
            # Verificação para garantir que o jogador esteja "em pé"
            physics_np = None
            if self.entity and self.entity.node_path:
                physics_np = self.entity.node_path.find(f"**/{self._physics_node.getName()}")
                if physics_np:
                    # Certifica-se de que só tem rotação horizontal
                    h = physics_np.getH()
                    physics_np.setHpr(h, 0, 0)
            
            # Para BulletCharacterControllerNode
            if isinstance(self._physics_node, BulletCharacterControllerNode):
                if hasattr(self._physics_node, 'setWalkDirection'):
                    self._physics_node.setWalkDirection(direction_vec)
                    return
            
            # Para corpo rígido, aplicar velocidade diretamente
            if isinstance(self._physics_node, BulletRigidBodyNode):
                # Preserva a velocidade vertical (para salto/gravidade)
                current_vel = Vec3(0, 0, 0)
                if hasattr(self._physics_node, 'getLinearVelocity'):
                    current_vel = self._physics_node.getLinearVelocity()
                
                # Define nova velocidade horizontal, mantendo componente vertical
                new_vel = Vec3(direction_vec.x * 5.0, direction_vec.y * 5.0, current_vel.z)
                
                if hasattr(self._physics_node, 'setLinearVelocity'):
                    self._physics_node.setLinearVelocity(new_vel)
                    return
            
            # Se chegou aqui, move o NodePath diretamente
            if physics_np:
                current_pos = physics_np.getPos()
                new_pos = current_pos + direction_vec
                physics_np.setPos(new_pos)
                
                # Sincroniza com o transform
                transform = self.entity.get_component(TransformComponent)
                if transform:
                    transform.set_position((new_pos.x, new_pos.y, new_pos.z))
        except Exception as e:
            print(f"Erro ao mover personagem: {e}")
    
    def get_overlapping_bodies(self) -> list:
        """Retorna uma lista de corpos sobrepostos a este ghost object."""
        if not self._physics_node or not isinstance(self._physics_node, BulletGhostNode):
            return []
        
        result = []
        try:
            for i in range(self._physics_node.getNumOverlappingNodes()):
                node = self._physics_node.getOverlappingNode(i)
                result.append(node)
        except Exception as e:
            print(f"Erro ao obter corpos sobrepostos: {e}")
        
        return result
    
    def on_cleanup(self) -> None:
        """Limpa recursos ao remover o componente."""
        if not self._physics_service or not self._physics_node:
            return
        
        try:
            # Remove o corpo físico do mundo
            if isinstance(self._physics_node, BulletRigidBodyNode):
                self._physics_service.remove_rigid_body(self._physics_node)
            elif isinstance(self._physics_node, BulletGhostNode):
                self._physics_service.get_bullet_world().removeGhost(self._physics_node)
            elif isinstance(self._physics_node, BulletCharacterControllerNode):
                self._physics_service.get_bullet_world().removeCharacter(self._physics_node)
            
            # Remove o nó de colisão do Panda3D
            if self._collision_nodepath:
                self._collision_nodepath.removeNode()
        except Exception as e:
            print(f"Erro ao limpar componente de colisão: {e}")
        
        # Limpa referências
        self._physics_node = None
        self._collision_node = None
        self._collision_nodepath = None
    
    @property
    def physics_node(self) -> Any:
        """Retorna o nó de física associado."""
        return self._physics_node