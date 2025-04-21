from typing import Optional, Tuple, Any, Dict, List
from direct.showbase.ShowBase import ShowBase
from panda3d.core import NodePath, TransformState, Point3, Vec3, BitMask32
from panda3d.bullet import (BulletWorld, BulletRigidBodyNode, BulletBoxShape,
                           BulletSphereShape, BulletCapsuleShape, BulletPlaneShape,
                           BulletGhostNode, BulletCharacterControllerNode,
                           BulletCylinderShape, BulletTriangleMeshShape,
                           BulletTriangleMesh, BulletDebugNode)

from src.services.interfaces.i_physics_service import IPhysicsService
from src.core.config import GRAVITY, PHYSICS_FRAME_RATE, MAX_SUBSTEPS, FIXED_TIMESTEP

class PhysicsService(IPhysicsService):
    """
    Implementação do serviço de física usando Panda3D Bullet, mas com configurações
    para minimizar problemas de colisão.
    """
    
    def __init__(self, show_base: ShowBase):
        """
        Inicializa o serviço de física.
        
        Args:
            show_base: Instância do ShowBase do Panda3D
        """
        self._show_base = show_base
        self._world: Optional[BulletWorld] = None
        self._debug_node: Optional[BulletDebugNode] = None
        self._debug_np: Optional[NodePath] = None
        self._rigid_bodies: Dict[str, BulletRigidBodyNode] = {}
        self._ghost_objects: Dict[str, BulletGhostNode] = {}
        self._character_controllers: Dict[str, BulletCharacterControllerNode] = {}
        self._time_accumulator: float = 0.0
        self._contact_added_callbacks: Dict[str, List[callable]] = {}
        self._contact_processed_callbacks: Dict[str, List[callable]] = {}
    
    def initialize(self) -> None:
        """Inicializa o sistema de física."""
        # Cria o mundo de física Bullet
        self._world = BulletWorld()
        self._world.setGravity(Vec3(0, 0, GRAVITY))
        
        # Aumenta a precisão da física
        if hasattr(self._world, 'setCcdSweptSphereRadius'):
            self._world.setCcdSweptSphereRadius(0.01)  # Raio de validação para CCD
        if hasattr(self._world, 'setCcdMotionThreshold'):
            self._world.setCcdMotionThreshold(0.001)  # Limiar para ativar CCD
        
        # Configura o nó de debug
        self._debug_node = BulletDebugNode('Debug')
        self._debug_node.showWireframe(True)
        self._debug_node.showConstraints(True)
        self._debug_node.showBoundingBoxes(False)
        self._debug_node.showNormals(True)  # Mostra normais para análise de colisão
        self._debug_np = self._show_base.render.attachNewNode(self._debug_node)
        self._debug_np.hide()
        
        # Registra o mundo com o nó de debug
        self._world.setDebugNode(self._debug_node)
        
        print("Serviço de física inicializado com configurações simplificadas")
    
    def update(self, dt: float) -> None:
        """
        Atualiza a simulação de física - VERSÃO MODIFICADA QUE NÃO FAZ NADA.
        Isso evita que o sistema de física mova objetos ou resolva colisões.
        
        Args:
            dt: Delta time (tempo desde o último frame)
        """
        # Não realizamos a simulação física para evitar teleportes
        # e deixamos o sistema de colisão do Panda3D lidar com isso
        pass
    
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
        if not self._world:
            self.initialize()
        
        try:
            # A cápsula no Bullet é definida por raio e comprimento do cilindro central
            capsule_height = height - 2 * radius
            if capsule_height < 0:
                capsule_height = 0.1  # Mínimo para evitar problemas
            
            # Cria a forma da cápsula para o personagem
            shape = BulletCapsuleShape(radius, capsule_height, 2)  # 2 = Z-up
            
            # Ajusta a margem de colisão para ser mais precisa
            shape.setMargin(0.01)  # Margem menor para detecção mais precisa
            
            # Cria o controlador de personagem
            node_name = node.getName() or "character"
            character = BulletCharacterControllerNode(shape, step_height, node_name)
            
            # Configurações importantes para o controlador
            character.setGravity(abs(GRAVITY) * 3.0)  # Gravidade mais forte para o personagem
            
            # Uso seguro de métodos que podem não existir em todas as versões
            try:
                # Configurar máscara de colisão para colidir com tudo
                character.setIntoCollideMask(BitMask32.allOn())
            except:
                print(f"Aviso: setIntoCollideMask não disponível para character controller")
                
            try:
                character.setFromCollideMask(BitMask32.allOn())
            except:
                print(f"Aviso: setFromCollideMask não disponível para character controller")
                # Tenta método alternativo se disponível
                try:
                    if hasattr(character, 'setCollideMask'):
                        character.setCollideMask(BitMask32.allOn())
                except:
                    print(f"Aviso: Não foi possível configurar máscara de colisão para character controller")
            
            # Define a velocidade de salto
            if hasattr(character, 'setJumpSpeed'):
                character.setJumpSpeed(10.0)  # Velocidade de salto mais forte
            
            # Define a velocidade de queda
            if hasattr(character, 'setFallSpeed'):
                character.setFallSpeed(55.0)  # Velocidade de queda rápida
            
            # Define o ângulo máximo de subida
            if hasattr(character, 'setMaxSlope'):
                character.setMaxSlope(0.7)  # Aproximadamente 40 graus
            
            # Ativa verificação de colisão contínua para evitar atravessar objetos
            if hasattr(character, 'setCcdMotionThreshold'):
                character.setCcdMotionThreshold(0.001)  # Limiar baixo ativa o CCD com mais frequência
            if hasattr(character, 'setCcdSweptSphereRadius'):
                character.setCcdSweptSphereRadius(radius * 0.9)  # Usa quase o raio completo
            
            # Cria o NodePath para o controlador
            np = node.attachNewNode(character)
            try:
                np.setCollideMask(BitMask32.allOn())  # Garante que colide com objetos visuais também
            except:
                print(f"Aviso: Não foi possível configurar máscara de colisão para NodePath do character controller")
            
            np.setPos(0, 0, 0)  # Posição relativa ao nó pai
            
            # Adiciona ao mundo
            self._world.attachCharacter(character)
            self._character_controllers[node_name] = character
            
            print(f"Character controller criado com sucesso: {node_name}")
            return character
                
        except Exception as e:
            print(f"Erro ao criar character controller: {e}")
            # Em caso de erro, cria um fallback com corpo rígido
            return self._create_character_fallback(node, radius, height, step_height)
    
    def _create_character_fallback(self, node: NodePath, radius: float, height: float, 
                                 step_height: float) -> Any:
        """Cria um corpo rígido como fallback para o controlador de personagem."""
        try:
            node_name = f"{node.getName() or 'character'}_fallback"
            body = BulletRigidBodyNode(node_name)
            body.setMass(80.0)  # Massa típica de uma pessoa
            
            # Cria cápsula para o jogador
            capsule_height = height - 2 * radius
            if capsule_height < 0:
                capsule_height = 0.1
            
            shape = BulletCapsuleShape(radius, capsule_height, 2)  # 2 = Z-up
            shape.setMargin(0.01)  # Margem menor para colisão mais precisa
            body.addShape(shape)
            
            # Configurações para prevenir tombamento
            body.setAngularFactor(Vec3(0, 0, 0))  # Bloqueia rotação
            body.setLinearDamping(0.2)
            body.setAngularDamping(0.999)  # Praticamente para qualquer rotação
            body.setFriction(0.8)  # Boa fricção para não escorregar
            body.setRestitution(0.0)  # Sem bounce
            
            # Ativa modo cinemático para poder controlar diretamente
            body.setKinematic(True)
            
            # Ativa detecção de colisão contínua (CCD)
            body.setCcdMotionThreshold(0.001)
            body.setCcdSweptSphereRadius(radius * 0.9)
            
            # Máscara de colisão para detectar tudo
            try:
                body.setIntoCollideMask(BitMask32.allOn())
                body.setFromCollideMask(BitMask32.allOn())
            except:
                print(f"Aviso: Não foi possível configurar máscara de colisão para fallback")
            
            # Adiciona ao mundo
            np = node.attachNewNode(body)
            try:
                np.setCollideMask(BitMask32.allOn())
            except:
                print(f"Aviso: Não foi possível configurar máscara de colisão para NodePath fallback")
            
            np.setPos(0, 0, 0)
            self._world.attachRigidBody(body)
            self._rigid_bodies[node_name] = body
            
            print(f"Corpo rígido fallback criado: {node_name}")
            return body
                
        except Exception as e:
            print(f"Erro ao criar fallback: {e}")
            return None
    
    def add_rigid_body(self, node: NodePath, mass: float, shape_type: str, 
                      dimensions: Tuple = None, compound: bool = False) -> BulletRigidBodyNode:
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
        if not self._world:
            self.initialize()
        
        # Cria o nó do corpo rígido
        node_name = node.getName() or "rigid_body"
        body = BulletRigidBodyNode(node_name)
        body.setMass(mass)
        
        # Verificar se é um objeto de cenário por nome
        is_wall = "wall" in node_name.lower() or "Wall" in node_name
        is_floor = "floor" in node_name.lower() or "Floor" in node_name
        is_ceiling = "ceiling" in node_name.lower() or "Ceiling" in node_name
        is_box = "box" in node_name.lower() or "Box" in node_name
        is_scenery = is_wall or is_floor or is_ceiling or is_box
        
        # Configurações otimizadas para objetos estáticos (paredes, chão)
        if mass == 0:
            body.setFriction(1.0)  # Alta fricção para superfícies estáticas
            body.setRestitution(0.0)  # Sem bounce para paredes/chão
            body.setKinematic(False)  # Garante que é realmente estático
            
            # Configuração específica para paredes
            if is_wall:
                body.setFriction(1.0)  # Paredes têm alta fricção
                body.setRestitution(0.0)  # Sem bounce para paredes
            
            # Configuração para o chão
            elif is_floor:
                body.setFriction(0.8)  # Chão tem boa fricção mas permite deslizamento
                body.setRestitution(0.0)  # Sem bounce para o chão
            
            # Configuração para teto
            elif is_ceiling:
                body.setFriction(1.0)  # Alta fricção para o teto
                body.setRestitution(0.0)  # Sem bounce para o teto
            
            # Configuração para caixas estáticas
            elif is_box:
                body.setFriction(0.9)  # Alta fricção para caixas
                body.setRestitution(0.1)  # Pequeno bounce para caixas
        else:
            # Objetos móveis
            body.setFriction(0.8)  # Boa fricção geral
            body.setRestitution(0.2)  # Leve bounce
            body.setLinearDamping(0.1)  # Amortecimento para desacelerar movimento
            body.setAngularDamping(0.9)  # Forte amortecimento para estabilizar rotação
            
            # Ativa detecção de colisão contínua para objetos móveis
            body.setCcdMotionThreshold(0.01)
            
            # Calcula um raio aproximado baseado nas dimensões
            ccd_radius = 0.1  # Valor padrão
            if dimensions:
                # Estima um raio baseado na média das dimensões
                ccd_radius = sum(dimensions) / len(dimensions) * 0.8
            
            body.setCcdSweptSphereRadius(ccd_radius)
        
        # Define máscaras de colisão otimizadas - CORREÇÃO
        # Verificações seguras para versões diferentes do Panda3D
        try:
            body.setIntoCollideMask(BitMask32.allOn())  # Tudo pode colidir com este objeto
        except:
            print(f"Aviso: setIntoCollideMask não disponível para {node_name}")
        
        # Uso de try/except para lidar com diferenças de API
        try:
            if is_scenery:
                # Objetos de cenário são só "into" - eles recebem colisões mas não detectam
                body.setFromCollideMask(BitMask32(0))
            else:
                # Outros objetos detectam colisões normalmente
                body.setFromCollideMask(BitMask32.allOn())
        except:
            # Se o método não existir, tentamos o método alternativo de colisão
            try:
                if hasattr(body, 'setCollideMask'):
                    body.setCollideMask(BitMask32.allOn())
            except:
                print(f"Aviso: Não foi possível configurar máscara de colisão para {node_name}")
        
        # Cria a forma de colisão apropriada
        shape = None
        
        if shape_type == 'box':
            # Dimensões esperadas: (half_x, half_y, half_z)
            if dimensions:
                shape = BulletBoxShape(Vec3(*dimensions))
            else:
                shape = BulletBoxShape(Vec3(0.5, 0.5, 0.5))
        
        elif shape_type == 'sphere':
            # Dimensões esperadas: (radius,)
            if dimensions and len(dimensions) >= 1:
                shape = BulletSphereShape(dimensions[0])
            else:
                shape = BulletSphereShape(0.5)
        
        elif shape_type == 'capsule':
            # Dimensões esperadas: (radius, height)
            if dimensions and len(dimensions) >= 2:
                shape = BulletCapsuleShape(dimensions[0], dimensions[1], 2)  # 2 = Z-up
            else:
                shape = BulletCapsuleShape(0.5, 1.0, 2)
        
        elif shape_type == 'plane':
            # Plano infinito (normal e constante)
            if dimensions and len(dimensions) >= 4:
                shape = BulletPlaneShape(Vec3(dimensions[0], dimensions[1], dimensions[2]), dimensions[3])
            else:
                shape = BulletPlaneShape(Vec3(0, 0, 1), 0)
        
        else:
            raise ValueError(f"Tipo de forma desconhecido: {shape_type}")
        
        # Adiciona a forma ao corpo
        if shape:
            # Ajusta margem de colisão para ser mais precisa
            # Valores bons: 0.01 a 0.04
            if is_scenery:
                # Objetos de cenário podem ter margem menor para precisão
                shape.setMargin(0.01)
            else:
                # Outros objetos têm margem padrão
                shape.setMargin(0.04)
            
            # Adiciona a forma ao corpo
            body.addShape(shape)
        
        # Cria o NodePath para o corpo
        np = node.attachNewNode(body)
        np.setPos(0, 0, 0)  # Posição relativa ao nó pai
        
        # Define máscara de colisão para renderização também
        try:
            np.setCollideMask(BitMask32.allOn())
        except:
            print(f"Aviso: Não foi possível configurar máscara de colisão no NodePath para {node_name}")
        
        # Adiciona ao mundo
        self._world.attachRigidBody(body)
        self._rigid_bodies[node_name] = body
        
        return body
    
    def get_bullet_world(self) -> BulletWorld:
        """Retorna o mundo de física do Bullet."""
        if not self._world:
            self.initialize()
        return self._world
    
    def perform_ray_test(self, from_pos: Tuple[float, float, float], 
                       to_pos: Tuple[float, float, float], 
                       filter_mask: Optional[BitMask32] = None) -> Optional[Any]:
        """
        Realiza um teste de raio (raycast) para detecção de colisão.
        
        Args:
            from_pos: Posição inicial do raio
            to_pos: Posição final do raio
            filter_mask: Máscara de bits opcional para filtrar colisões
            
        Returns:
            Resultado do teste de raio, ou None se não houver colisão
        """
        if not self._world:
            return None
        
        try:
            # Converte as posições para Point3
            from_point = Point3(*from_pos)
            to_point = Point3(*to_pos)
            
            # Realiza o teste de raio com ou sem filtro
            if filter_mask is not None:
                result = self._world.rayTestClosest(from_point, to_point, filter_mask)
            else:
                result = self._world.rayTestClosest(from_point, to_point)
            
            if result.hasHit():
                return result
            
            return None
        except Exception as e:
            print(f"Erro ao realizar raycast: {e}")
            return None
    
    def perform_sweep_test(self, shape: Any, from_trans: TransformState, 
                         to_trans: TransformState) -> Optional[Any]:
        """
        Realiza um teste de varrimento (sweep test) para detecção de colisão mais precisa.
        
        Args:
            shape: Forma para teste (BulletShape)
            from_trans: Transformação inicial
            to_trans: Transformação final
            
        Returns:
            Resultado do teste, ou None se não houver colisão
        """
        if not self._world:
            return None
        
        try:
            # Configura a forma para resposta de contato precisa
            if hasattr(shape, 'setMargin'):
                shape.setMargin(0.01)  # Margem pequena para precisão
                
            # Realiza o teste de sweeping
            result = self._world.sweepTestClosest(shape, from_trans, to_trans, BitMask32.allOn())
            
            if result.hasHit():
                return result
            
            return None
        except Exception as e:
            print(f"Erro ao realizar sweep test: {e}")
            return None
            
    def create_ghost_object(self, node: NodePath, shape_type: str, 
                         dimensions: Tuple = None) -> BulletGhostNode:
        """
        Cria um objeto fantasma (ghost) para detecção de colisão sem resposta física.
        
        Args:
            node: NodePath ao qual o objeto fantasma será vinculado
            shape_type: Tipo de forma do collider ('box', 'sphere', 'capsule', etc.)
            dimensions: Dimensões da forma (depende do shape_type)
            
        Returns:
            Instância do objeto fantasma criado
        """
        if not self._world:
            self.initialize()
        
        # Cria o nó fantasma
        node_name = node.getName() or "ghost"
        ghost = BulletGhostNode(node_name)
        
        # Configura máscaras de colisão para detectar tudo
        try:
            ghost.setIntoCollideMask(BitMask32(0))  # Ninguém colide com o ghost
            ghost.setFromCollideMask(BitMask32.allOn())  # Ghost detecta tudo
        except:
            print(f"Aviso: Não foi possível configurar máscara de colisão para ghost {node_name}")
        
        # Cria a forma de colisão apropriada (mesmo código do add_rigid_body)
        shape = None
        
        if shape_type == 'box':
            if dimensions:
                shape = BulletBoxShape(Vec3(*dimensions))
            else:
                shape = BulletBoxShape(Vec3(0.5, 0.5, 0.5))
        
        elif shape_type == 'sphere':
            if dimensions and len(dimensions) >= 1:
                shape = BulletSphereShape(dimensions[0])
            else:
                shape = BulletSphereShape(0.5)
        
        elif shape_type == 'capsule':
            if dimensions and len(dimensions) >= 2:
                shape = BulletCapsuleShape(dimensions[0], dimensions[1], 2)
            else:
                shape = BulletCapsuleShape(0.5, 1.0, 2)
        
        else:
            raise ValueError(f"Tipo de forma desconhecido para ghost: {shape_type}")
        
        # Adiciona a forma ao ghost
        if shape:
            ghost.addShape(shape)
            
            # Define margem de colisão para ser mais sensível
            if hasattr(shape, 'setMargin'):
                shape.setMargin(0.02)
        
        # Cria o NodePath para o ghost
        np = node.attachNewNode(ghost)
        np.setPos(0, 0, 0)  # Posição relativa ao nó pai
        
        # Adiciona ao mundo
        self._world.attachGhost(ghost)
        
        # Registra para rastreamento
        self._ghost_objects[node_name] = ghost
        
        return ghost
    
    def remove_rigid_body(self, rigid_body: BulletRigidBodyNode) -> None:
        """
        Remove um corpo rígido da simulação de física.
        
        Args:
            rigid_body: O corpo rígido a remover
        """
        if not self._world:
            return
        
        # Remove do mundo
        self._world.removeRigidBody(rigid_body)
        
        # Remove dos callbacks
        body_name = rigid_body.getName()
        if body_name in self._contact_added_callbacks:
            del self._contact_added_callbacks[body_name]
        
        if body_name in self._contact_processed_callbacks:
            del self._contact_processed_callbacks[body_name]
        
        # Remove do rastreamento
        for name, body in list(self._rigid_bodies.items()):
            if body == rigid_body:
                del self._rigid_bodies[name]
                break
    
    def set_gravity(self, gravity: Tuple[float, float, float]) -> None:
        """
        Define a gravidade do mundo de física.
        
        Args:
            gravity: Vetor de gravidade (x, y, z)
        """
        if not self._world:
            self.initialize()
        self._world.setGravity(Vec3(*gravity))
    
    def toggle_debug_visualization(self, enabled: bool) -> None:
        """
        Ativa ou desativa a visualização de debug da física.
        
        Args:
            enabled: True para ativar, False para desativar
        """
        if not self._debug_np:
            return
        
        if enabled:
            self._world.setDebugNode(self._debug_node)
            self._debug_np.show()
        else:
            self._debug_np.hide()
    
    def cleanup(self) -> None:
        """Limpa todos os recursos de física."""
        if self._world:
            # Remove todos os objetos do mundo
            for body in self._rigid_bodies.values():
                self._world.removeRigidBody(body)
            
            for character in self._character_controllers.values():
                self._world.removeCharacter(character)
            
            for ghost in self._ghost_objects.values():
                self._world.removeGhost(ghost)
        
        # Limpa os dicionários
        self._rigid_bodies.clear()
        self._character_controllers.clear()
        self._ghost_objects.clear()
        self._contact_added_callbacks.clear()
        self._contact_processed_callbacks.clear()
        
        # Remove o nó de debug
        if self._debug_np:
            self._debug_np.removeNode()
            self._debug_np = None
            self._debug_node = None
        
        self._time_accumulator = 0.0