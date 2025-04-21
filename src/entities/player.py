from typing import Optional, Tuple, List
from direct.showbase.ShowBase import ShowBase
from panda3d.core import NodePath, Vec3, Point3, CollisionRay, CollisionNode, CollisionSphere
from panda3d.core import CollisionBox, CollisionCapsule, CollisionHandlerQueue, CollisionTraverser, BitMask32
from panda3d.core import CollisionHandlerPusher, TransformState
import math

from src.entities.entity import Entity
from src.entities.components.transform_component import TransformComponent
from src.entities.components.collider_component import ColliderComponent
from src.core.config import (PLAYER_HEIGHT, PLAYER_COLLISION_RADIUS, 
                           PLAYER_STEP_HEIGHT, PLAYER_CAMERA_FOV)
from src.utils.event_bus import EventBus

class Player(Entity):
    """
    Entidade do jogador que o usuário controla.
    Implementa o padrão Facade para encapsular os componentes relacionados ao jogador.
    """
    
    def __init__(self, show_base: ShowBase):
        """
        Inicializa o jogador.
        
        Args:
            show_base: Instância do ShowBase do Panda3D
        """
        super().__init__(name="Player")
        
        self._show_base = show_base
        self._camera = None
        self._velocity = Vec3(0, 0, 0)
        self._walking = False
        self._sprinting = False
        self._crouching = False
        self._grounded = True  # Assumir que começa no chão
        self._jump_requested = False
        self._jump_cooldown = 0.0
        self._last_position = Vec3(0, 0, 0)
        self._gravity_enabled = True
        self._vertical_velocity = 0.0
        self._jump_velocity = 10.0  # Velocidade inicial do salto
        self._gravity = 20.0  # Gravidade, valor maior = queda mais rápida
        
        # EventBus para publicação de eventos
        self._event_bus = EventBus()
        
        # Sistema de colisão do Panda3D para detecção precisa
        self._cTrav = CollisionTraverser("PlayerTraverser")
        self._collision_queue = CollisionHandlerQueue()
        
        # Hitbox e raios
        self._hitbox_node = None
        self._hitbox_np = None
        self._hitbox_dimensions = None
        self._ground_ray_node = None
        self._ground_ray_np = None
        
        # Estado de salto
        self._is_jumping = False
        self._jump_grace_period = 0.0
        
        # Para uso em vários métodos
        self._ground_debounce_timer = 0.0
        
        # Debug
        self._debug_shape = None
        self._debug_enabled = False  # Desativado por padrão
    
    def setup(self, parent: NodePath, position: Tuple[float, float, float] = (0, 0, 0)) -> None:
        """
        Configura o jogador, iniciando seu NodePath e adicionando componentes.
        Versão corrigida que mantém o movimento funcionando.
        
        Args:
            parent: NodePath pai para o jogador
            position: Posição inicial do jogador
        """
        # Inicializa o NodePath
        self.init_node_path(parent)
        
        # Posição inicial garantindo que o jogador está acima do chão
        floor_offset = PLAYER_HEIGHT / 2.0
        starting_pos = (position[0], position[1], position[2] + floor_offset)
        
        # Adiciona o componente de transformação
        self._transform = TransformComponent(position=starting_pos)
        self.add_component(self._transform)
        
        # Adiciona o componente de colisão padrão
        self._collider = ColliderComponent(
            shape_type='box',
            dimensions=(PLAYER_COLLISION_RADIUS, PLAYER_COLLISION_RADIUS, PLAYER_HEIGHT/2),
            mass=80.0,
            is_character=False,
        )
        self.add_component(self._collider)
        
        # Configura a câmera
        self._setup_camera()
        
        # Armazena a posição inicial
        self._last_position = Vec3(*starting_pos)
        
        # Inicializa estado de chão
        self._grounded = True
        
        print(f"Jogador inicializado na posição: {starting_pos}")

    def _setup_camera(self) -> None:
        """
        Configura a câmera em primeira pessoa.
        Versão final com acoplamento correto entre rotação do jogador e câmera.
        """
        if not self._show_base or not self.node_path:
            return
        
        # Configura a câmera diretamente ligada ao jogador
        camera_height = PLAYER_HEIGHT * 0.7  # 70% da altura do jogador
        camera_offset = Vec3(0, 0, camera_height - PLAYER_HEIGHT/2.0)
        
        # Cria um nó para a câmera como filho direto do jogador
        self._camera = self.node_path.attachNewNode("player_camera")
        self._camera.setPos(camera_offset)
        
        # A câmera do Panda3D fica como filha deste nó
        self._show_base.camera.reparentTo(self._camera)
        self._show_base.camera.setPos(0, 0, 0)
        self._show_base.camera.setHpr(0, 0, 0)
        
        # Configura o FOV
        self._show_base.camLens.setFov(PLAYER_CAMERA_FOV)
        
        # Guarda valor de altura para referência
        self._fixed_camera_height = camera_offset.z
        
        print(f"Câmera configurada com altura fixa em relação ao jogador: {camera_height}")
        
    def update(self, dt: float) -> None:
        """
        Atualiza o jogador com física vertical simplificada.
        """
        # Chama a implementação do pai para atualizar componentes
        super().update(dt)
        
        # Atualiza o estado de chão
        was_grounded = self._grounded
        self._check_ground_collision(dt)
        
        # Aplica física vertical
        self._apply_vertical_physics(dt)
        
        # Atualiza a posição anterior para o próximo frame
        self._last_position = Vec3(self._transform.position)

    def move(self, direction: Vec3, speed: float) -> None:
        """
        Move o jogador na direção especificada.
        Versão final com movimento relativo à câmera e detectção de colisão.
        
        Args:
            direction: Vetor de direção normalizado no espaço local
            speed: Velocidade do movimento
        """
        if not self._transform:
            return
        
        # Se não há movimento, não faz nada
        if direction.length_squared() < 0.0001:
            self._walking = False
            return
        
        # Calcula o delta time
        dt = self._show_base.taskMgr.globalClock.getDt()
        dt = min(dt, 0.1)  # Evita saltos com framerate baixo
        
        # Calcula a movimentação
        move_amount = speed * dt
        
        # Normaliza a direção se necessário
        move_dir = Vec3(direction)
        if move_dir.length_squared() > 1.001:
            move_dir.normalize()
        
        # IMPORTANTE: Converte a direção para o espaço global baseado na rotação do jogador
        # Isso garante que o movimento seja relativo à direção do olhar
        heading_rad = math.radians(self.node_path.getH())
        sin_h = math.sin(heading_rad)
        cos_h = math.cos(heading_rad)
        
        global_dir_x = move_dir.x * cos_h - move_dir.y * sin_h
        global_dir_y = move_dir.x * sin_h + move_dir.y * cos_h
        
        # Direção global do movimento
        global_move_dir = Vec3(global_dir_x, global_dir_y, 0)
        global_move_dir.normalize()
        
        # Calcula a posição de destino
        current_pos = self._transform.position
        desired_pos = current_pos + (global_move_dir * move_amount)
        
        # Obtém o sistema de colisão
        collision_system = self._get_collision_system()
        
        # Verificação de colisão e correção
        final_pos = desired_pos
        if collision_system:
            try:
                # Tenta usar o método de deslizamento
                if hasattr(collision_system, 'check_move_with_sliding'):
                    final_pos = collision_system.check_move_with_sliding(self, desired_pos)
                else:
                    # Fallback para verificação simples
                    has_collision, corrected_pos = collision_system.check_collision(self, desired_pos)
                    if has_collision:
                        final_pos = corrected_pos
            except Exception as e:
                print(f"Erro na verificação de colisão: {e}")
                # Em caso de erro, permite o movimento
                final_pos = desired_pos
        
        # Aplica a nova posição, mantendo Z atual
        self._transform.set_position((final_pos.x, final_pos.y, current_pos.z))
        self.node_path.setPos(final_pos.x, final_pos.y, current_pos.z)
        
        # Atualiza estado de caminhada
        self._walking = True
        
    def rotate_head(self, h_degrees: float, p_degrees: float) -> None:
        """
        Rotaciona a cabeça (câmera) do jogador.
        Versão final que mantém o alinhamento entre jogador e câmera.
        
        Args:
            h_degrees: Alteração de rotação horizontal (heading)
            p_degrees: Alteração de rotação vertical (pitch)
        """
        if not self._camera:
            return
        
        # Rotação apenas da câmera no eixo vertical (pitch)
        current_p = self._camera.getP()
        new_p = max(-80, min(80, current_p + p_degrees))
        self._camera.setP(new_p)
        
        # Rotação do JOGADOR E CÂMERA no eixo horizontal (heading)
        # Isso garante que a direção do olhar e do movimento estejam alinhadas
        if self.node_path:
            current_h = self.node_path.getH()
            new_h = current_h + h_degrees
            self.node_path.setH(new_h)
            
            # Importante: a câmera deve ter H=0 para que sua rotação 
            # seja completamente herdada do jogador
            self._camera.setH(0)

    def _check_ground_collision(self, dt: float) -> None:
        """
        Verifica se o jogador está no chão.
        Versão simplificada e corrigida.
        """
        # Se estamos em período de graça após o salto, ignoramos
        if self._jump_grace_period > 0:
            self._jump_grace_period -= dt
            return
        
        # Estado anterior
        was_grounded = self._grounded
        is_on_ground_now = False
        ground_height = -1000.0
        
        # Posição atual
        current_pos = self._transform.position
        player_half_height = PLAYER_HEIGHT / 2.0
        
        # Cria um raio simples para verificação de chão
        from panda3d.core import CollisionRay, CollisionNode, CollisionHandlerQueue
        from panda3d.core import CollisionTraverser, BitMask32
        
        # Cria um traverser temporário
        traverser = CollisionTraverser('ground_traverser')
        queue = CollisionHandlerQueue()
        
        # Cria um raio único no centro
        ray = CollisionRay(current_pos.x, current_pos.y, current_pos.z, 0, 0, -1)
        ray_node = CollisionNode('ground_ray')
        ray_node.setFromCollideMask(BitMask32.bit(0))  # Bit 0 para objetos estáticos
        ray_node.setIntoCollideMask(BitMask32(0))  # Não recebe colisões
        ray_node.addSolid(ray)
        
        ray_np = self._show_base.render.attachNewNode(ray_node)
        traverser.addCollider(ray_np, queue)
        
        # Executa o teste
        traverser.traverse(self._show_base.render)
        
        # Processa resultados
        if queue.getNumEntries() > 0:
            queue.sortEntries()
            entry = queue.getEntry(0)
            
            hit_pos = entry.getSurfacePoint(self._show_base.render)
            hit_normal = entry.getSurfaceNormal(self._show_base.render)
            
            # Verifica se a normal aponta para cima
            if hit_normal.z > 0.7:
                # Distância do jogador ao chão
                distance = current_pos.z - hit_pos.z
                
                # Tolerância para estar no chão
                if distance < player_half_height + 0.2:
                    is_on_ground_now = True
                    ground_height = hit_pos.z
        
        # Limpa recursos
        traverser.removeCollider(ray_np)
        ray_np.removeNode()
        
        # Estabilidade: debounce para saída do chão
        if was_grounded and not is_on_ground_now:
            self._ground_debounce_timer += dt
            
            if self._ground_debounce_timer < 0.1:  # 100ms
                is_on_ground_now = True
            else:
                self._ground_debounce_timer = 0.0
        else:
            self._ground_debounce_timer = 0.0
        
        # Atualiza o estado
        self._grounded = is_on_ground_now
        
        # Ajusta altura se acabou de tocar o chão
        if is_on_ground_now and not was_grounded and ground_height > -999:
            current_pos = self._transform.position
            desired_z = ground_height + player_half_height + 0.01
            
            if abs(desired_z - current_pos.z) > 0.1:
                self._transform.set_position((current_pos.x, current_pos.y, desired_z))
                self.node_path.setPos(current_pos.x, current_pos.y, desired_z)

    def _apply_vertical_physics(self, dt: float) -> None:
        """
        Aplica física vertical com detecção de chão.
        Versão simplificada e corrigida.
        """
        if not self._transform:
            return
        
        # Se está no chão e não está pulando, não faz nada
        if self._grounded and not self._is_jumping:
            self._vertical_velocity = 0.0
            return
        
        # Aplica gravidade se no ar
        if not self._grounded or self._is_jumping:
            self._vertical_velocity -= self._gravity * dt
            if self._vertical_velocity < -20.0:
                self._vertical_velocity = -20.0
            
            # Aplica movimento vertical
            current_pos = self._transform.position
            new_z = current_pos.z + self._vertical_velocity * dt
            
            # Verifica colisão com o chão durante queda
            if self._vertical_velocity < 0:
                # Verifica se há chão próximo
                from panda3d.core import CollisionRay, CollisionNode, CollisionHandlerQueue
                from panda3d.core import CollisionTraverser, BitMask32
                
                player_half_height = PLAYER_HEIGHT / 2.0
                
                # Cria raio para detecção de chão
                ray = CollisionRay(current_pos.x, current_pos.y, current_pos.z, 0, 0, -1)
                ray_node = CollisionNode('fall_check_ray')
                ray_node.setFromCollideMask(BitMask32.bit(0))
                ray_node.setIntoCollideMask(BitMask32(0))
                ray_node.addSolid(ray)
                
                ray_np = self._show_base.render.attachNewNode(ray_node)
                
                traverser = CollisionTraverser('fall_traverser')
                queue = CollisionHandlerQueue()
                traverser.addCollider(ray_np, queue)
                
                traverser.traverse(self._show_base.render)
                
                # Verifica se há chão próximo
                floor_detected = False
                floor_height = -1000.0
                
                if queue.getNumEntries() > 0:
                    queue.sortEntries()
                    entry = queue.getEntry(0)
                    
                    hit_pos = entry.getSurfacePoint(self._show_base.render)
                    hit_normal = entry.getSurfaceNormal(self._show_base.render)
                    
                    if hit_normal.z > 0.7:
                        # Distância ao chão
                        distance_to_floor = current_pos.z - hit_pos.z
                        fall_distance = -self._vertical_velocity * dt
                        
                        if distance_to_floor <= fall_distance + player_half_height + 0.05:
                            floor_detected = True
                            floor_height = hit_pos.z
                
                # Limpa recursos
                traverser.removeCollider(ray_np)
                ray_np.removeNode()
                
                # Se detectou chão e irá atravessá-lo, ajusta posição
                if floor_detected:
                    player_half_height = PLAYER_HEIGHT / 2.0
                    new_z = max(new_z, floor_height + player_half_height + 0.01)
                    self._vertical_velocity = 0.0
                    self._grounded = True
            
            # Verifica colisão com o teto
            ceiling_hit = False
            if self._vertical_velocity > 0:
                from panda3d.core import CollisionRay, CollisionNode, CollisionHandlerQueue
                from panda3d.core import CollisionTraverser, BitMask32
                
                player_half_height = PLAYER_HEIGHT / 2.0
                
                # Raio para cima
                ray = CollisionRay(current_pos.x, current_pos.y, current_pos.z, 0, 0, 1)
                ray_node = CollisionNode('ceiling_ray')
                ray_node.setFromCollideMask(BitMask32.bit(0))
                ray_node.setIntoCollideMask(BitMask32(0))
                ray_node.addSolid(ray)
                
                ray_np = self._show_base.render.attachNewNode(ray_node)
                
                traverser = CollisionTraverser('ceiling_traverser')
                queue = CollisionHandlerQueue()
                traverser.addCollider(ray_np, queue)
                
                traverser.traverse(self._show_base.render)
                
                if queue.getNumEntries() > 0:
                    entry = queue.getEntry(0)
                    hit_pos = entry.getSurfacePoint(self._show_base.render)
                    
                    # Distância até o teto
                    head_pos = Vec3(current_pos.x, current_pos.y, current_pos.z + player_half_height - 0.1)
                    distance = hit_pos.z - head_pos.z
                    
                    if distance < 0.3:
                        ceiling_hit = True
                        self._vertical_velocity = 0.0
                        new_z = current_pos.z
                
                # Limpa recursos
                traverser.removeCollider(ray_np)
                ray_np.removeNode()
            
            # Aplica a nova posição Z
            if not ceiling_hit:
                self._transform.set_position((current_pos.x, current_pos.y, new_z))
                self.node_path.setPos(current_pos.x, current_pos.y, new_z)
        
        # Verifica se o jogador caiu fora do mapa
        if self._transform.position.z < -5.0:
            self.teleport_to_ground()
            print(f"Jogador caiu do mapa e foi reposicionado")

    def _get_collision_system(self):
        """
        Obtém o sistema de colisão da cena.
        Método auxiliar para evitar repetição de código.
        
        Returns:
            Sistema de colisão ou None se não encontrado
        """
        # Tenta obter via SceneManager
        collision_system = None
        try:
            from src.managers.scene_manager import SceneManager
            scene_manager = SceneManager()
            if scene_manager and hasattr(scene_manager, 'get_collision_system'):
                collision_system = scene_manager.get_collision_system()
        except:
            pass
        
        # Tenta via game_app
        if not collision_system:
            try:
                if hasattr(self._show_base, 'gameApp'):
                    if hasattr(self._show_base.gameApp, '_collision_system'):
                        collision_system = self._show_base.gameApp._collision_system
            except:
                pass
        
        return collision_system

    def teleport_to_ground(self) -> None:
        """
        Teleporta o jogador para o chão abaixo dele.
        Versão melhorada que garante uma posição válida no mapa.
        """
        if not self._transform:
            return
            
        # Obtém a posição atual, ignorando Z
        current_pos = self._transform.position
        
        # Define uma posição de fallback caso não encontre chão válido
        fallback_pos = Vec3(0, 0, PLAYER_HEIGHT / 2.0)
        
        # Tenta encontrar o chão sob a posição atual
        from panda3d.core import CollisionRay, CollisionNode, CollisionHandlerQueue
        from panda3d.core import CollisionTraverser, BitMask32
        
        # Emite raio da altura máxima possível
        ray = CollisionRay(current_pos.x, current_pos.y, 10.0, 0, 0, -1)
        ray_node = CollisionNode('teleport_ray')
        ray_node.setFromCollideMask(BitMask32.bit(0))  # Objetos estáticos
        ray_node.setIntoCollideMask(BitMask32(0))  # Não recebe colisões
        ray_node.addSolid(ray)
        
        ray_np = self._show_base.render.attachNewNode(ray_node)
        
        traverser = CollisionTraverser('teleport_traverser')
        queue = CollisionHandlerQueue()
        traverser.addCollider(ray_np, queue)
        
        # Executa o teste
        traverser.traverse(self._show_base.render)
        
        # Processa resultados
        found_ground = False
        ground_pos = Vec3(current_pos.x, current_pos.y, PLAYER_HEIGHT / 2.0)
        
        if queue.getNumEntries() > 0:
            queue.sortEntries()
            for i in range(queue.getNumEntries()):
                entry = queue.getEntry(i)
                hit_pos = entry.getSurfacePoint(self._show_base.render)
                hit_normal = entry.getSurfaceNormal(self._show_base.render)
                
                # Verifica se é um chão válido
                if hit_normal.z > 0.7:
                    found_ground = True
                    ground_pos = Vec3(current_pos.x, current_pos.y, hit_pos.z + PLAYER_HEIGHT / 2.0)
                    break
        
        # Limpa recursos
        traverser.removeCollider(ray_np)
        ray_np.removeNode()
        
        # Se não encontrou chão, usa a posição de fallback
        final_pos = ground_pos if found_ground else fallback_pos
        
        # Atualiza a posição
        self._transform.set_position((final_pos.x, final_pos.y, final_pos.z))
        self.node_path.setPos(final_pos)
        
        # Reseta a física
        self._grounded = True
        self._vertical_velocity = 0.0
        self._is_jumping = False
        
        # Atualiza a posição anterior
        self._last_position = Vec3(final_pos)
        
        print(f"Jogador teleportado para o chão em: ({final_pos.x}, {final_pos.y}, {final_pos.z})")

    def jump(self) -> None:
        """
        Faz o jogador pular.
        Versão final com bom feedback.
        """
        # Verifica se está apto a pular
        if not self._grounded or self._jump_cooldown > 0 or self._is_jumping:
            print("Tecla de pulo pressionada - ignorando (não está no chão)")
            return
        
        # Define estado de pulo
        print("Tecla de pulo pressionada - executando salto")
        self._jump_requested = True
        self._jump_cooldown = 0.3  # 300ms entre pulos
        self._jump_grace_period = 0.1  # 100ms onde ignoramos detecção de chão
        self._is_jumping = True
        self._grounded = False
        
        # Aplicação direta de impulso vertical
        self._vertical_velocity = 10.0  # Velocidade fixa para simplicidade
    
    def sprint(self, enabled: bool) -> None:
        """
        Alterna o estado de corrida.
        
        Args:
            enabled: True para correr, False para velocidade normal
        """
        self._sprinting = enabled
    
    def crouch(self, enabled: bool) -> None:
        """
        Alterna o estado de agachamento.
        
        Args:
            enabled: True para agachar, False para levantar
        """
        if self._crouching == enabled:
            return
        
        self._crouching = enabled
        
        # Ajusta a altura da câmera para agachamento
        if self._camera:
            if enabled:
                # Agachado - mais baixo
                player_half_height = PLAYER_HEIGHT / 2.0
                offset = PLAYER_HEIGHT * 0.4 - player_half_height
                self._camera.setZ(offset)
            else:
                # Em pé - altura normal
                player_half_height = PLAYER_HEIGHT / 2.0
                offset = PLAYER_HEIGHT * 0.7 - player_half_height
                self._camera.setZ(offset)
    
    def stand_up(self) -> None:
        """Força o jogador a ficar em pé se estiver caído."""
        if not self._transform or not self.node_path:
            return
        
        # Corrige a rotação do jogador
        self.node_path.setR(0)
        self.node_path.setP(0)
        
        # Volta para estado não agachado
        self._crouching = False
        
        # Ajusta a câmera
        if self._camera:
            player_half_height = PLAYER_HEIGHT / 2.0
            offset = PLAYER_HEIGHT * 0.7 - player_half_height
            self._camera.setZ(offset)
    
    @property
    def camera_node(self) -> Optional[NodePath]:
        """Retorna o NodePath da câmera do jogador."""
        return self._camera
    
    @property
    def is_walking(self) -> bool:
        """Retorna se o jogador está caminhando."""
        return self._walking
    
    @property
    def is_sprinting(self) -> bool:
        """Retorna se o jogador está correndo."""
        return self._sprinting
    
    @property
    def is_crouching(self) -> bool:
        """Retorna se o jogador está agachado."""
        return self._crouching
    
    @property
    def is_grounded(self) -> bool:
        """Retorna se o jogador está no chão."""
        return self._grounded
    
    @is_grounded.setter
    def is_grounded(self, value: bool) -> None:
        """Define se o jogador está no chão."""
        if self._grounded != value:
            self._grounded = value
            if value:
                self._is_jumping = False
                self._vertical_velocity = 0.0