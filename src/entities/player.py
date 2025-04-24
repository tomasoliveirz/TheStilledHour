import random
from typing import Optional, Tuple, List

from direct.showbase.Audio3DManager import Audio3DManager
from direct.showbase.ShowBase import ShowBase
from panda3d.core import NodePath, Vec3, Point3, CollisionRay, CollisionNode, CollisionSphere, AudioSound
from panda3d.core import CollisionBox, CollisionCapsule, CollisionHandlerQueue, CollisionTraverser, BitMask32
from panda3d.core import CollisionHandlerPusher, TransformState, CollisionSegment, LineSegs
from panda3d.core import LVector3f
import math
from panda3d.core import BitMask32
from src.managers.input_manager import InputManager

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
        # Audio3DManager permite posicionar os sons no espaço 3D
        self._audio3d = Audio3DManager(self._show_base.sfxManagerList[0], self._show_base.camera)
        # Lista de AudioSound
        self._step_sounds: List[AudioSound] = []
        self._jump_sound: Optional[AudioSound] = None
        # Quantidade de distância acumulada desde o último passo
        self._step_distance_accum = 0.0
        self._step_interval = 0.2
        self._step_interval_sprint = 0.1   # a correr (mais passos)
        input_manager = InputManager()
        input_manager.register_action_callback("toggle_crouch", self._on_crouch_toggle)
        input_manager.register_action_callback("toggle_sprint", self._on_sprint_toggle)
        # Tempo do último passo
        self._last_step_time = 0.0
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

        # Tempo mínimo de pulo para garantir que o jogador fica no ar
        self._min_jump_time = 0.0
        self._jump_time_counter = 0.0

        # Altura do passo para subir em caixas (aumentada para melhor navegação)
        self._step_height = PLAYER_STEP_HEIGHT * 1.5  # Aumentado para facilitar a subida em caixas médias

        # Anti-clipping para câmera
        self._camera_ideal_offset = Vec3(0, 0, 0)  # Offset ideal da câmera
        self._camera_current_offset = Vec3(0, 0, 0)  # Offset atual da câmera
        self._camera_wall_check_distance = 0.3  # Distância para verificar paredes
        self._camera_min_distance = 0.1  # Distância mínima da câmera até o jogador

        # Estado de "stepping up" (subindo em caixas)
        self._is_stepping_up = False
        self._step_up_progress = 0.0
        self._step_up_target_height = 0.0
        self._step_up_start_height = 0.0

        # Debug
        self._debug_shape = None
        self._debug_enabled = False  # Ativado para diagnóstico de colisão
        self._debug_rays = []

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
            dimensions=(PLAYER_COLLISION_RADIUS, PLAYER_COLLISION_RADIUS, PLAYER_HEIGHT / 2),
            mass=80.0,
            is_character=False,
        )
        self.add_component(self._collider)
        self._load_step_sounds()
        self._load_jump_sound()  # Nova linha para carregar som de pulo

        # Configura a câmera
        self._setup_camera()

        # Configura raios de colisão para detecção melhorada
        self._setup_collision_rays()

        # Armazena a posição inicial
        self._last_position = Vec3(*starting_pos)

        # Inicializa estado de chão
        self._grounded = True

        print(f"Jogador inicializado na posição: {starting_pos}")

    def _on_crouch_toggle(self, pressed: bool) -> None:
        """
        Callback quando a tecla de agachar é pressionada/liberada.

        Args:
            pressed: True se pressionada, False se liberada
        """
        # Não permite sprint enquanto agachado
        if pressed and self._sprinting:
            self._sprinting = False

        # Define o estado de agachamento
        self.crouch(pressed)

        if self._debug_enabled:
            print(f"[DEBUG:toggle] Agachamento {'ativado' if pressed else 'desativado'}")

    def _on_sprint_toggle(self, pressed: bool) -> None:
        """
        Callback quando a tecla de correr é pressionada/liberada.

        Args:
            pressed: True se pressionada, False se liberada
        """
        # Não permite sprint enquanto agachado
        if pressed and self._crouching:
            return

        # Define o estado de sprint
        self.sprint(pressed)

        if self._debug_enabled:
            print(f"[DEBUG:toggle] Corrida {'ativada' if pressed else 'desativada'}")
    def _setup_collision_rays(self) -> None:
        """
        Configura raios de colisão adicionais para melhorar a detecção.
        """
        # Raio principal para detecção de chão
        ray = CollisionRay(0, 0, 0, 0, 0, -1)
        ray_node = CollisionNode('player_ground_ray')
        ray_node.addSolid(ray)
        ray_node.setFromCollideMask(BitMask32.bit(0))
        ray_node.setIntoCollideMask(BitMask32(0))

        # Cria um NodePath para o raio
        self._ground_ray_np = self.node_path.attachNewNode(ray_node)
        self._ground_ray_np.setZ(0)  # Começa no centro do jogador

        # Cria raios adicionais para detecção de caixas pequenas
        self._setup_additional_rays()

    def _setup_additional_rays(self) -> None:
        """
        Configura raios de colisão adicionais para melhorar a detecção de caixas pequenas.
        """
        # Limpa raios existentes
        for ray in self._debug_rays:
            if ray is not None:
                ray.removeNode()
        self._debug_rays = []

        # Configuração mais densa de raios - melhor para caixas pequenas
        radius = PLAYER_COLLISION_RADIUS * 0.8
        points = [
            (0, 0),  # Centro
            (radius, 0),  # Frente
            (-radius, 0),  # Trás
            (0, radius),  # Direita
            (0, -radius),  # Esquerda
            (radius / 2, radius / 2),  # Diagonal frente-direita
            (radius / 2, -radius / 2),  # Diagonal frente-esquerda
            (-radius / 2, radius / 2),  # Diagonal trás-direita
            (-radius / 2, -radius / 2)  # Diagonal trás-esquerda
        ]

        for i, (x, y) in enumerate(points):
            ray = CollisionRay(x, y, 0, 0, 0, -1)
            node = CollisionNode(f'player_ray_{i}')
            node.addSolid(ray)
            node.setFromCollideMask(BitMask32.bit(0))
            node.setIntoCollideMask(BitMask32(0))

            ray_np = self.node_path.attachNewNode(node)
            self._debug_rays.append(ray_np)

            # Visual debug (comentado em produção)
            if self._debug_enabled:
                self._create_debug_line(x, y)

    def _create_debug_line(self, x: float, y: float) -> None:
        """
        Cria uma linha de debug para visualizar os raios de colisão.
        """
        ls = LineSegs()
        ls.setThickness(2)
        ls.setColor(1, 0, 0, 1)  # Vermelho

        # Linha do raio
        ls.moveTo(x, y, 0)
        ls.drawTo(x, y, -self._step_height - 0.2)

        node = ls.create()
        np = self.node_path.attachNewNode(node)
        np.setRenderModeWireframe()
        np.setZ(-PLAYER_HEIGHT / 2)  # Posiciona na base do jogador

    def _setup_camera(self) -> None:
        """
        Configura a câmera em primeira pessoa com anti-clipping.
        """
        if not self._show_base or not self.node_path:
            return

        # Configura a câmera diretamente ligada ao jogador
        camera_height = PLAYER_HEIGHT * 0.7  # 70% da altura do jogador
        camera_offset = Vec3(0, 0, camera_height - PLAYER_HEIGHT / 2.0)

        # Armazena o offset ideal da câmera
        self._camera_ideal_offset = camera_offset
        self._camera_current_offset = Vec3(camera_offset)

        # Cria um nó para a câmera como filho direto do jogador
        self._camera = self.node_path.attachNewNode("player_camera")
        self._camera.setPos(camera_offset)

        # A câmera do Panda3D fica como filha deste nó
        self._show_base.camera.reparentTo(self._camera)
        self._show_base.camera.setPos(0, 0, 0)
        self._show_base.camera.setHpr(0, 0, 0)

        # Configura o FOV
        self._show_base.camLens.setFov(PLAYER_CAMERA_FOV)

        # Ajusta o near clipping plane para evitar ver através de objetos próximos
        # Valor padrão é 0.1, vamos aumentar para 0.2
        self._show_base.camLens.setNear(0.05)

        # Guarda valor de altura para referência
        self._fixed_camera_height = camera_offset.z

        print(f"Câmera configurada com altura fixa em relação ao jogador: {camera_height}")

    def update(self, dt: float) -> None:
        """
        Atualiza o jogador com física vertical simplificada e debug.
        """
        super().update(dt)

        # Atualiza o temporizador de salto mínimo
        if self._min_jump_time > 0:
            self._min_jump_time -= dt

        # Atualiza cooldown de salto
        if self._jump_cooldown > 0:
            self._jump_cooldown -= dt

        # Guarda estado anterior
        was_grounded = self._grounded

        # Se estamos em um salto forçado, não verificamos colisão com o chão ainda
        if self._min_jump_time <= 0:
            self._check_ground_collision(dt)
        else:
            # Durante o tempo mínimo de salto, o jogador está sempre no ar
            self._grounded = False


        # Update step up animation if active
        if self._is_stepping_up:
            self._update_step_up(dt)

        # Física vertical (gravidade, salto)
        self._apply_vertical_physics(dt)

        if self._debug_enabled:
            print(
                f"[DEBUG:update] after _apply_vertical_physics z={self._transform.position.z:.3f} vert_vel={self._vertical_velocity:.3f}")

        # Atualiza a animação de câmera durante o salto
        if self._is_jumping:
            self._update_jump_camera_animation(dt)

        # Ajuste anti-clipping da câmera
        self._update_camera_anti_clipping(dt)

        # Guarda a posição atual para o próximo frame
        self._last_position = Vec3(self._transform.position)
        self._audio3d.update()

    def _update_step_up(self, dt: float) -> None:
        """
        Atualiza a animação de subida em degrau/caixa.
        """
        if not self._is_stepping_up:
            return

        # Velocidade da animação de subida
        step_speed = 5.0  # Velocidade em unidades por segundo

        # Incrementa o progresso
        self._step_up_progress += dt * step_speed

        if self._step_up_progress >= 1.0:
            # Animação completa, termina na altura alvo
            current_pos = self._transform.position
            final_pos = Vec3(current_pos.x, current_pos.y, self._step_up_target_height)

            self._transform.set_position((final_pos.x, final_pos.y, final_pos.z))
            self.node_path.setPos(final_pos)

            # Reseta estado
            self._is_stepping_up = False
            self._step_up_progress = 0.0
            self._grounded = True
        else:
            # Animação em progresso, interpola a altura
            current_pos = self._transform.position
            progress = self._step_up_progress  # 0.0 a 1.0

            # Interpola com uma curva suave para parecer mais natural
            smoothed_progress = 0.5 - 0.5 * math.cos(progress * math.pi)

            # Calcula a nova altura
            new_height = self._step_up_start_height + (
                        self._step_up_target_height - self._step_up_start_height) * smoothed_progress

            # Aplica a nova posição
            self._transform.set_position((current_pos.x, current_pos.y, new_height))
            self.node_path.setPos(current_pos.x, current_pos.y, new_height)

    def _update_jump_camera_animation(self, dt: float) -> None:
        """
        Atualiza a animação da câmera durante o salto para dar sensação de movimento vertical.

        Args:
            dt: Delta time (tempo desde o último frame)
        """
        if not self._camera:
            return

        # Adiciona um pequeno bob de câmera para aumentar sensação de movimento
        if self._vertical_velocity > 0:
            # Subindo - câmera move ligeiramente para baixo (sensação de aceleração)
            self._camera.setZ(self._fixed_camera_height - 0.05 * (self._vertical_velocity / self._jump_velocity))
        elif self._vertical_velocity < -5.0:
            # Caindo rapidamente - câmera move ligeiramente para cima (preparando para impacto)
            fall_intensity = min(1.0, abs(self._vertical_velocity) / 20.0)
            self._camera.setZ(self._fixed_camera_height + 0.08 * fall_intensity)
        else:
            # Volta gradualmente à posição normal
            current_z = self._camera.getZ()
            if abs(current_z - self._fixed_camera_height) > 0.01:
                self._camera.setZ(current_z + (self._fixed_camera_height - current_z) * dt * 5.0)

    def _update_camera_anti_clipping(self, dt: float) -> None:
        """
        Atualiza a posição da câmera para evitar clipping através de paredes.
        """
        if not self._camera:
            return

        # Obtém a posição do jogador
        player_pos = self._transform.position

        # Direção da câmera (para onde o jogador está olhando)
        head_h = self.node_path.getH()
        head_p = self._camera.getP()

        # Converte rotação para direção
        rad_h = math.radians(head_h)
        rad_p = math.radians(head_p)

        # Cria os raios de verificação
        # O principal é na direção do olhar
        from panda3d.core import CollisionSegment, CollisionNode, CollisionHandlerQueue, CollisionTraverser

        # Distância máxima a verificar
        max_distance = 0.5  # 50cm atrás do jogador

        # Posição dos olhos (de onde sai o raio)
        eye_pos = player_pos + Vec3(0, 0, self._fixed_camera_height * 0.7)

        # Cria o raio para trás (oposto à direção do olhar)
        dir_x = -math.sin(rad_h) * math.cos(rad_p)
        dir_y = -math.cos(rad_h) * math.cos(rad_p)
        dir_z = math.sin(rad_p)

        # Usamos um segmento do olho para trás (detectar paredes atrás da câmera)
        segment = CollisionSegment(
            eye_pos.x, eye_pos.y, eye_pos.z,
            eye_pos.x + dir_x * max_distance,
            eye_pos.y + dir_y * max_distance,
            eye_pos.z + dir_z * max_distance
        )

        # Configura o nó de colisão
        node = CollisionNode('camera_anti_clip')
        node.addSolid(segment)
        node.setFromCollideMask(BitMask32.bit(0))  # Objetos estáticos
        node.setIntoCollideMask(BitMask32(0))

        # Cria o NodePath e adiciona ao traverser
        traverser = CollisionTraverser('camera_clip_trav')
        queue = CollisionHandlerQueue()

        # Adiciona o nó ao render root para garantir que não colide com o jogador
        np = self._show_base.render.attachNewNode(node)
        traverser.addCollider(np, queue)

        # Executa a verificação
        traverser.traverse(self._show_base.render)

        # Distância atual até a parede
        wall_distance = max_distance

        # Verifica se houve colisão
        if queue.getNumEntries() > 0:
            queue.sortEntries()
            entry = queue.getEntry(0)
            hit_pos = entry.getSurfacePoint(self._show_base.render)

            # Calcula a distância da colisão
            distance = (Vec3(hit_pos) - eye_pos).length()

            # Atualiza a distância até a parede
            wall_distance = max(distance - 0.05, 0.01)  # Margem de 5cm

            # Debug
            if self._debug_enabled:
                print(f"[DEBUG:camera] wall detected at distance {distance:.2f}m, adjusted to {wall_distance:.2f}m")

        # Limpa recursos
        traverser.removeCollider(np)
        np.removeNode()

        # Ajusta a posição da câmera para evitar clipping
        if wall_distance < max_distance:
            # Calcula o offset da câmera baseado na distância da parede
            camera_factor = wall_distance / max_distance

            # Interpola entre a posição atual e a posição ideal
            interp_factor = min(dt * 10.0, 1.0)  # Velocidade de ajuste

            # Aplica o novo offset
            self._camera.setPos(0, 0, self._fixed_camera_height)

            # Aplica uma pequena translação para frente (ajuda a evitar clipping)
            self._camera.setY(-wall_distance * 0.5)
        else:
            # Não há parede, move a câmera gradualmente para a posição ideal
            current_pos = self._camera.getPos()
            ideal_pos = Vec3(0, 0, self._fixed_camera_height)

            # Interpola suavemente
            interp_factor = min(dt * 5.0, 1.0)
            new_pos = current_pos * (1.0 - interp_factor) + ideal_pos * interp_factor

            # Aplica a nova posição
            self._camera.setPos(new_pos)

    def move(self, direction: Vec3, speed: float) -> None:
        """
        Move o jogador na direção especificada, respeitando estados de movimento.

        Args:
            direction: Vetor de direção normalizado no espaço local
            speed: Velocidade base do movimento
        """
        if not self._transform:
            return

        # Se está no meio de uma animação de step up, não processa movimento horizontal
        if self._is_stepping_up:
            return

        # Aplica modificadores de velocidade baseado no estado atual
        actual_speed = speed
        if self._sprinting:
            actual_speed *= 1.8  # 80% mais rápido
        elif self._crouching:
            actual_speed *= 0.5  # 50% mais lento

        # Se não há movimento, atualiza apenas o estado de caminhada
        if direction.length_squared() < 0.0001:
            self._walking = False
            return

        # Calcula o delta time
        dt = self._show_base.taskMgr.globalClock.getDt()
        dt = min(dt, 0.1)  # Evita saltos com framerate baixo

        # Calcula a movimentação
        move_amount = actual_speed * dt
        
        interval = self._step_interval_sprint if self._sprinting else random.choice([self._step_interval, self._step_interval * 1.5])
        print(f"[DEBUG] Intervalo de passo: {interval:.2f}m")
        # acumula distância e dispara passo
        if self._grounded and self._walking:
            self._step_distance_accum += move_amount
            if self._step_distance_accum >= interval:
                self._step_distance_accum -= interval
                self._play_step_sound()
                
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
        has_collision = False

        if collision_system:
            try:
                # Tenta usar o método de deslizamento
                if hasattr(collision_system, 'check_move_with_sliding'):
                    final_pos = collision_system.check_move_with_sliding(self, desired_pos)

                    # Verifica se a posição foi corrigida (indica colisão)
                    has_collision = (final_pos != desired_pos)
                else:
                    # Fallback para verificação simples
                    has_collision, corrected_pos = collision_system.check_collision(self, desired_pos)
                    if has_collision:
                        final_pos = corrected_pos
            except Exception as e:
                print(f"Erro na verificação de colisão: {e}")
                # Em caso de erro, permite o movimento
                final_pos = desired_pos

        # NOVA FUNCIONALIDADE: Verifica se podemos subir em uma caixa
        if has_collision and self._grounded:
            # Tenta detectar uma caixa/degrau que podemos subir
            step_detected, step_height = self._check_step_up(desired_pos, global_move_dir)

            if step_detected:
                # Inicia a animação de subida
                self._start_step_up(step_height)
                return

        # Aplica a nova posição, mantendo Z atual
        self._transform.set_position((final_pos.x, final_pos.y, current_pos.z))
        self.node_path.setPos(final_pos.x, final_pos.y, current_pos.z)

        # Atualiza estado de caminhada
        self._walking = True




    def _check_step_up(self, desired_pos: Vec3, move_dir: Vec3) -> Tuple[bool, float]:
        """
        Verifica se há um degrau ou caixa na frente que podemos subir.

        Args:
            desired_pos: A posição desejada que foi bloqueada por colisão
            move_dir: A direção do movimento

        Returns:
            (pode_subir, altura_do_degrau)
        """
        # Parâmetros para detecção de degrau
        ray_height = self._step_height + 0.1  # Altura máxima que podemos subir

        # Posição atual e dos pés
        curr_pos = self._transform.position
        foot_pos = Vec3(curr_pos.x, curr_pos.y, curr_pos.z - PLAYER_HEIGHT / 2)

        # Cria um raio a partir dos pés para cima e depois para frente
        # Primeiro, um raio vertical para cima para detectar obstáculos na altura do passo
        from panda3d.core import CollisionSegment, CollisionNode, CollisionTraverser, CollisionHandlerQueue

        # Cria um segmento que sobe do pé até a altura do passo
        segment_up = CollisionSegment(
            foot_pos.x, foot_pos.y, foot_pos.z,  # Início nos pés
            foot_pos.x, foot_pos.y, foot_pos.z + ray_height  # Fim acima
        )

        # Configura o nó de colisão
        node_up = CollisionNode('step_check_up')
        node_up.addSolid(segment_up)
        node_up.setFromCollideMask(BitMask32.bit(0))  # Objetos estáticos
        node_up.setIntoCollideMask(BitMask32(0))

        # Cria o traverser e queue
        traverser = CollisionTraverser('step_check_trav')
        queue = CollisionHandlerQueue()

        # Adiciona o nó ao render
        np_up = self._show_base.render.attachNewNode(node_up)
        traverser.addCollider(np_up, queue)

        # Executa a verificação vertical
        traverser.traverse(self._show_base.render)

        # Se houver colisão vertical, não podemos subir
        if queue.getNumEntries() > 0:
            # Limpa recursos
            traverser.removeCollider(np_up)
            np_up.removeNode()
            return False, 0.0

        # Limpa a queue
        queue.clearEntries()

        # Posição onde o raio vertical termina (ponto alto)
        high_pos = Vec3(foot_pos.x, foot_pos.y, foot_pos.z + ray_height)

        # A partir do ponto alto, lança um raio para frente na direção do movimento
        forward_distance = PLAYER_COLLISION_RADIUS * 1.5  # Distância na frente

        # Cria um segmento que vai para frente na direção do movimento
        segment_fwd = CollisionSegment(
            high_pos.x, high_pos.y, high_pos.z,  # Início no ponto alto
            high_pos.x + move_dir.x * forward_distance,
            high_pos.y + move_dir.y * forward_distance,
            high_pos.z  # Mesma altura
        )

        # Configura o nó de colisão
        node_fwd = CollisionNode('step_check_fwd')
        node_fwd.addSolid(segment_fwd)
        node_fwd.setFromCollideMask(BitMask32.bit(0))
        node_fwd.setIntoCollideMask(BitMask32(0))

        # Adiciona o nó ao render
        np_fwd = self._show_base.render.attachNewNode(node_fwd)
        traverser.addCollider(np_fwd, queue)

        # Executa a verificação horizontal
        traverser.traverse(self._show_base.render)

        # Se houver colisão horizontal, não podemos avançar
        if queue.getNumEntries() > 0:
            # Limpa recursos
            traverser.removeCollider(np_up)
            traverser.removeCollider(np_fwd)
            np_up.removeNode()
            np_fwd.removeNode()
            return False, 0.0

        # Limpa a queue
        queue.clearEntries()

        # Posição onde o raio horizontal termina (ponto à frente)
        forward_pos = Vec3(
            high_pos.x + move_dir.x * forward_distance,
            high_pos.y + move_dir.y * forward_distance,
            high_pos.z
        )

        # A partir do ponto à frente, lança um raio para baixo para detectar a superfície
        segment_down = CollisionSegment(
            forward_pos.x, forward_pos.y, forward_pos.z,  # Início no ponto à frente
            forward_pos.x, forward_pos.y, foot_pos.z - 0.1  # Fim abaixo do nível do pé
        )

        # Configura o nó de colisão
        node_down = CollisionNode('step_check_down')
        node_down.addSolid(segment_down)
        node_down.setFromCollideMask(BitMask32.bit(0))
        node_down.setIntoCollideMask(BitMask32(0))

        # Adiciona o nó ao render
        np_down = self._show_base.render.attachNewNode(node_down)
        traverser.addCollider(np_down, queue)

        # Executa a verificação para baixo
        traverser.traverse(self._show_base.render)

        # Variáveis para o resultado
        step_detected = False
        step_height = 0.0

        # Processa resultados
        if queue.getNumEntries() > 0:
            queue.sortEntries()
            entry = queue.getEntry(0)
            hit_pos = entry.getSurfacePoint(self._show_base.render)
            hit_normal = entry.getSurfaceNormal(self._show_base.render)

            # Se a superfície é um "chão" (normal apontando para cima)
            if hit_normal.z > 0.7:
                # Altura da superfície em relação ao nível do pé
                surface_height = hit_pos.z - foot_pos.z

                # Se a superfície está entre 0.1 e a altura máxima do passo
                if 0.1 <= surface_height <= ray_height:
                    step_detected = True
                    step_height = curr_pos.z + surface_height

                    # Debug
                    if self._debug_enabled:
                        print(f"[DEBUG:step] Degrau detectado com altura {surface_height:.2f}m")

        # Limpa recursos
        traverser.removeCollider(np_up)
        traverser.removeCollider(np_fwd)
        traverser.removeCollider(np_down)
        np_up.removeNode()
        np_fwd.removeNode()
        np_down.removeNode()

        return step_detected, step_height

    def _start_step_up(self, target_height: float) -> None:
        """
        Inicia a animação de subida em um degrau ou caixa.

        Args:
            target_height: A altura alvo final do jogador
        """
        if self._is_stepping_up:
            return

        # Configura a animação de subida
        self._is_stepping_up = True
        self._step_up_progress = 0.0
        self._step_up_start_height = self._transform.position.z
        self._step_up_target_height = target_height

        # Desativa a gravidade temporariamente
        self._vertical_velocity = 0.0

        # Debug
        if self._debug_enabled:
            print(
                f"[DEBUG:step] Iniciando subida de {self._step_up_start_height:.2f}m para {self._step_up_target_height:.2f}m")



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

    def _load_jump_sound(self) -> None:
        """Carrega o som de pulo e anexa ao jogador."""
        try:
            jump_file = "assets/sounds/jump.wav"
            self._jump_sound = self._audio3d.loadSfx(jump_file)
            self._jump_sound.setLoop(False)
            self._audio3d.attachSoundToObject(self._jump_sound, self.node_path)
            print(f"Som de pulo carregado: {jump_file}")
        except Exception as e:
            print(f"Erro ao carregar som de pulo: {e}")
            self._jump_sound = None

    def _load_step_sounds(self) -> None:
        """Carrega step_0…step_4.wav e anexa cada som ao node_path."""
        self._step_sounds.clear()

        for i in range(4):                           # eram 4, mas existem 5 arquivos (0–4)
            fn = f"assets/sounds/step_{i}.wav"
            snd = self._audio3d.loadSfx(fn)         # carrega já preparado para 3D
            snd.setLoop(False)
            self._audio3d.attachSoundToObject(snd, self.node_path)
            self._step_sounds.append(snd)




        print(f"Sons 3D anexados ao player na posição {self.node_path.getPos()}")

    def _play_step_sound(self) -> None:
        """
        Escolhe aleatoriamente um dos sons carregados e reproduz com
        volume e frequência adaptados para caminhada normal, sprint e agachamento.
        """
        if not self._step_sounds:
            return

        # Tempo mínimo entre passos - mais rápido durante sprint, mais lento agachado
        if self._sprinting:
            min_time_between_steps = 0.2  # Rápido (sprint)
        elif self._crouching:
            min_time_between_steps = 0.7  # Mais lento (agachado)
        else:
            min_time_between_steps = 0.5  # Normal (caminhando)

        # Verifica se passou tempo suficiente desde o último passo
        current_time = self._show_base.taskMgr.globalClock.getFrameTime()
        if current_time - self._last_step_time < min_time_between_steps:
            return

        # Escolhe som aleatório
        sound = random.choice(self._step_sounds)

        # Define o volume e velocidade de reprodução baseado no estado do jogador
        if self._sprinting:
            sound.setPlayRate(1.2)  # 20% mais rápido
            sound.setVolume(1.0)  # Volume normal
        elif self._crouching:
            sound.setPlayRate(0.8)  # 20% mais lento
            sound.setVolume(0.4)  # 40% do volume normal (passos mais silenciosos)
        else:
            sound.setPlayRate(1.0)  # Velocidade normal
            sound.setVolume(1.0)  # Volume normal

        sound.play()

        # Atualiza o tempo do último passo
        self._last_step_time = current_time

    def _check_ground_collision(self, dt: float) -> None:
        """
        Verifica se o jogador está no chão com melhor detecção para caixas pequenas.
        """
        # Atualiza grace period
        if self._jump_grace_period > 0:
            self._jump_grace_period -= dt

        if self._debug_enabled:
            print(f"[DEBUG:_check_ground] grace_period={self._jump_grace_period:.3f}")

        # Guarda estado anterior
        was_grounded = self._grounded

        # Reset da detecção
        ground_detected = False
        highest_ground_z = -1e6

        # Parâmetros do jogador
        pos = self._transform.position
        half_height = PLAYER_HEIGHT / 2.0

        # Configuração do raio de detecção
        max_step_height = self._step_height + 0.05  # Altura máxima de degrau + margem
        ray_start_z = pos.z - half_height + 0.05  # Ligeiramente dentro do jogador
        ray_length = max_step_height + 0.2  # Comprimento do raio

        # Configuração do ângulo máximo de inclinação
        max_slope_angle = 50  # Ângulo máximo que considera como "chão"
        slope_threshold = math.cos(math.radians(max_slope_angle))

        # MELHORADO: Pontos para verificação bem distribuídos pela base do jogador
        radius = PLAYER_COLLISION_RADIUS * 0.8
        check_points = [
            (0, 0),  # Centro
            (radius, 0),  # Frente
            (-radius, 0),  # Trás
            (0, radius),  # Direita
            (0, -radius),  # Esquerda
            (radius / 2, radius / 2),  # Diagonal frente-direita
            (radius / 2, -radius / 2),  # Diagonal frente-esquerda
            (-radius / 2, radius / 2),  # Diagonal trás-direita
            (-radius / 2, -radius / 2)  # Diagonal trás-esquerda
        ]

        # Usar mais pontos melhora a detecção de caixas menores

        # Criar traverser e queue para detecção
        trav = CollisionTraverser('ground_check_trav')
        queue = CollisionHandlerQueue()

        # Verifica cada ponto da base
        for idx, (offset_x, offset_y) in enumerate(check_points):
            # Cria um segmento de colisão que vai da base do jogador para baixo
            from panda3d.core import CollisionSegment, CollisionNode

            # Posição de início do raio
            start_x = pos.x + offset_x
            start_y = pos.y + offset_y

            # Cria o segmento DE CIMA PARA BAIXO (importante a direção!)
            seg = CollisionSegment(
                start_x, start_y, ray_start_z,  # Início: dentro do jogador
                start_x, start_y, ray_start_z - ray_length  # Fim: abaixo do jogador
            )

            # Configura o nó de colisão
            node = CollisionNode(f'ground_check_{idx}')
            node.addSolid(seg)
            node.setFromCollideMask(BitMask32.bit(0))  # Colide com objetos estáticos
            node.setIntoCollideMask(BitMask32.allOff())  # Não recebe colisões

            # Cria o NodePath e adiciona ao traverser
            np_seg = self._show_base.render.attachNewNode(node)
            trav.addCollider(np_seg, queue)

            # Executa a verificação de colisão
            trav.traverse(self._show_base.render)

            # Processa resultados
            if queue.getNumEntries() > 0:
                # Ordena por distância
                queue.sortEntries()

                # Verifica cada colisão
                for i in range(queue.getNumEntries()):
                    entry = queue.getEntry(i)

                    # Obtém a normal da superfície (NO ESPAÇO GLOBAL)
                    normal = entry.getSurfaceNormal(self._show_base.render)

                    # Obtém a altura (coord Z) do ponto de colisão
                    hit_z = entry.getSurfacePoint(self._show_base.render).z

                    if self._debug_enabled:
                        print(f"  [hit {i}] normal={normal} z={hit_z:.3f}")

                    # Verifica se a normal aponta para cima (é chão válido)
                    # Para ser um chão, a normal deve apontar para CIMA
                    # Ou seja, o componente Z da normal deve ser POSITIVO
                    if normal.z >= slope_threshold:
                        ground_detected = True

                        # Registra o ponto mais alto para posicionar o jogador
                        if hit_z > highest_ground_z:
                            highest_ground_z = hit_z

            # Limpa a queue para o próximo teste
            queue.clearEntries()

            # Remove o NodePath
            np_seg.removeNode()

            # Se já detectamos chão, podemos sair do loop para economizar processamento
            if ground_detected:
                break

        # Número total de colisões detectadas
        if self._debug_enabled:
            print(f"[DEBUG:_check_ground] colisões detectadas: {queue.getNumEntries()}")

        # Coyote time - permite saltar um pouco depois de deixar uma plataforma
        # Mas APENAS se não estamos em um salto ativo!
        if not ground_detected and self._jump_grace_period > 0 and not self._is_jumping:
            ground_detected = True
            if self._debug_enabled:
                print("[DEBUG:_check_ground] coyote time active")

        # Debounce - evita oscilações rápidas no estado de chão
        if was_grounded and not ground_detected:
            self._ground_debounce_timer += dt
            if self._ground_debounce_timer < 0.1 and not self._is_jumping:
                ground_detected = True
            else:
                self._ground_debounce_timer = 0.0
        else:
            self._ground_debounce_timer = 0.0

        # Atualiza o estado de chão
        self._grounded = ground_detected

        if self._debug_enabled:
            print(f"[DEBUG:_check_ground] was={was_grounded} now={self._grounded} highest_z={highest_ground_z:.3f}")

        # Ajuste de posição ao aterrissar
        if self._grounded and not was_grounded and highest_ground_z > -1e5:
            # O jogador acabou de aterrissar, ajusta a altura
            desired_z = highest_ground_z + half_height + 0.01

            if self._debug_enabled:
                print(f"[DEBUG:_check_ground] aterrissou ajustando z de {pos.z:.3f} para {desired_z:.3f}")

            # Aplica a nova posição
            self._transform.set_position((pos.x, pos.y, desired_z))
            self.node_path.setZ(desired_z)

            # Zera a velocidade vertical e termina o salto
            self._vertical_velocity = 0.0
            self._is_jumping = False

            # Reproduz som ou efeito de pouso aqui
            self._event_bus.publish("on_player_landed")

        # Se estava no chão e agora não está, inicia queda suave
        elif was_grounded and not self._grounded and self._vertical_velocity >= 0 and not self._is_jumping:
            self._vertical_velocity = -0.1
            if self._debug_enabled:
                print("[DEBUG:_check_ground] iniciou queda suave")

    def _apply_vertical_physics(self, dt: float) -> None:
        """
        Aplica física vertical com detecção de chão melhorada.
        Versão corrigida para dar prioridade ao movimento de salto.
        """
        if not self._transform or self._is_stepping_up:
            return

        # Se está no salto forçado ou saltando, nunca cancela o movimento
        if self._min_jump_time > 0 or self._is_jumping:
            # Aplica gravidade gradualmente mesmo durante o salto
            self._vertical_velocity -= self._gravity * dt

            # Limita a velocidade máxima de queda
            if self._vertical_velocity < -20.0:
                self._vertical_velocity = -20.0

            # Continua o movimento vertical
            current_pos = self._transform.position
            new_z = current_pos.z + self._vertical_velocity * dt

            # Aplica a nova posição Z
            self._transform.set_position((current_pos.x, current_pos.y, new_z))
            self.node_path.setPos(current_pos.x, current_pos.y, new_z)
            return

        # Se está no chão e não está pulando, zera a velocidade vertical
        if self._grounded and not self._is_jumping:
            self._vertical_velocity = 0.0
            return

        # Aplica gravidade se no ar
        if not self._grounded:
            # Gravidade mais forte para queda mais rápida
            self._vertical_velocity -= self._gravity * dt

            # Limita a velocidade máxima de queda
            if self._vertical_velocity < -20.0:
                self._vertical_velocity = -20.0

            # Aplica movimento vertical
            current_pos = self._transform.position
            new_z = current_pos.z + self._vertical_velocity * dt

            # Verifica colisão com o chão durante queda
            if self._vertical_velocity < 0:
                from panda3d.core import CollisionRay, CollisionNode, CollisionHandlerQueue
                from panda3d.core import CollisionTraverser, BitMask32, CollisionSegment

                player_half_height = PLAYER_HEIGHT / 2.0
                player_radius = PLAYER_COLLISION_RADIUS

                # Distância prevista de queda neste frame
                fall_distance = -self._vertical_velocity * dt

                # Configuração dos pontos de verificação (centro e 4 pontos na base)
                check_points = [
                    (0, 0),  # Centro
                    (player_radius * 0.7, 0),  # Frente
                    (-player_radius * 0.7, 0),  # Trás
                    (0, player_radius * 0.7),  # Direita
                    (0, -player_radius * 0.7)  # Esquerda
                ]

                # Verifica colisão vertical a partir de múltiplos pontos
                traverser = CollisionTraverser('fall_traverser')
                queue = CollisionHandlerQueue()

                # Altura máxima que podemos colidir
                ray_length = fall_distance + player_half_height + 0.1

                floor_detected = False
                highest_floor = -1000.0

                for offset_x, offset_y in check_points:
                    # Configuração do raio/segmento
                    start_x = current_pos.x + offset_x
                    start_y = current_pos.y + offset_y
                    start_z = current_pos.z - player_half_height + 0.1  # Ligeiramente acima da base

                    # Usa um segmento em vez de um raio para precisão
                    segment = CollisionSegment(start_x, start_y, start_z,
                                               start_x, start_y, start_z - ray_length)

                    ray_node = CollisionNode('fall_check_segment')
                    ray_node.addSolid(segment)
                    ray_node.setFromCollideMask(BitMask32.bit(0))
                    ray_node.setIntoCollideMask(BitMask32(0))
                    ray_node.addSolid(segment)

                    ray_np = self._show_base.render.attachNewNode(ray_node)
                    traverser.addCollider(ray_np, queue)
                    traverser.traverse(self._show_base.render)

                    # Verifica resultados
                    if queue.getNumEntries() > 0:
                        queue.sortEntries()
                        entry = queue.getEntry(0)

                        hit_pos = entry.getSurfacePoint(self._show_base.render)
                        hit_normal = entry.getSurfaceNormal(self._show_base.render)

                        # Verifica se é uma superfície "chão" (normal apontando para cima)
                        if hit_normal.z > 0.7:
                            floor_detected = True
                            if hit_pos.z > highest_floor:
                                highest_floor = hit_pos.z

                    # Limpa para o próximo teste
                    traverser.removeCollider(ray_np)
                    ray_np.removeNode()
                    queue.clearEntries()

                if self._debug_enabled:
                    print(f"[DEBUG:_apply_vertical_physics] colisões detectadas: {queue.getNumEntries()}")

                # Se encontrou chão e vai colidir com ele neste frame
                if floor_detected and highest_floor > -999:
                    if self._debug_enabled:
                        print(f"[DEBUG:_apply_vertical_physics] chão detectado a {highest_floor:.3f} m")

                    # Coloca o jogador exatamente sobre o chão detectado
                    new_z = highest_floor + player_half_height + 0.01

                    # Zera velocidade vertical e marca como no chão
                    self._vertical_velocity = 0.0
                    self._grounded = True
                    self._is_jumping = False

            # Verifica colisão com teto
            if self._vertical_velocity > 0:
                from panda3d.core import CollisionRay, CollisionNode, CollisionHandlerQueue
                from panda3d.core import CollisionTraverser, BitMask32, CollisionSegment

                player_half_height = PLAYER_HEIGHT / 2.0
                ceiling_ray_length = self._vertical_velocity * dt + 0.1

                # Posição da cabeça do jogador
                head_pos_z = current_pos.z + player_half_height - 0.1

                # Configura segmento para detecção de teto
                segment = CollisionSegment(
                    current_pos.x, current_pos.y, head_pos_z,
                    current_pos.x, current_pos.y, head_pos_z + ceiling_ray_length
                )

                ray_node = CollisionNode('ceiling_segment')
                ray_node.addSolid(segment)
                ray_node.setFromCollideMask(BitMask32.bit(0))
                ray_node.setIntoCollideMask(BitMask32(0))

                ray_np = self._show_base.render.attachNewNode(ray_node)

                traverser = CollisionTraverser('ceiling_traverser')
                queue = CollisionHandlerQueue()
                traverser.addCollider(ray_np, queue)
                traverser.traverse(self._show_base.render)

                ceiling_hit = False

                if queue.getNumEntries() > 0:
                    entry = queue.getEntry(0)
                    hit_pos = entry.getSurfacePoint(self._show_base.render)

                    # Verifica se vai colidir com o teto neste frame
                    distance_to_ceiling = hit_pos.z - head_pos_z
                    if distance_to_ceiling < ceiling_ray_length:
                        ceiling_hit = True
                        self._vertical_velocity = 0.0  # Para o movimento para cima

                # Limpa recursos
                traverser.removeCollider(ray_np)
                ray_np.removeNode()

                # Se atingiu o teto, não move para cima
                if ceiling_hit:
                    new_z = current_pos.z  # Mantém a altura atual

            # Aplica a nova posição Z se mudou
            if abs(new_z - current_pos.z) > 0.001:
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
        Faz o jogador pular com tempo mínimo de salto garantido.
        """
        if self._debug_enabled:
            print(
                f"[DEBUG:jump] chamada jump() grounded={self._grounded}, cooldown={self._jump_cooldown:.3f}, is_jumping={self._is_jumping}")

        # Verifica condições para saltar
        if not self._grounded or self._jump_cooldown > 0 or self._is_jumping:
            print("[DEBUG:jump] ignorando pulo - não está no chão ou em cooldown")
            return

        # Inicia o pulo
        if self._debug_enabled:
            print("[DEBUG:jump] iniciando pulo")
        self._jump_requested = True
        self._jump_cooldown = 0.3  # Tempo de cooldown entre pulos
        self._jump_grace_period = 0.1  # Permite saltar logo após deixar uma plataforma

        # Define estados de pulo
        self._is_jumping = True
        self._grounded = False

        # Define tempo mínimo de pulo - forçando o jogador a ficar no ar
        self._min_jump_time = 0.3  # 300ms de pulo mínimo garantido

        # Define velocidade vertical inicial de salto
        self._vertical_velocity = self._jump_velocity

        # NOVO: Toca o som de pulo
        if self._jump_sound:
            self._jump_sound.play()

        # Dispara evento de pulo para efeitos sonoros ou visuais
        self._event_bus.publish("on_player_jump")
        print("Tecla de pulo pressionada - executando salto")

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

