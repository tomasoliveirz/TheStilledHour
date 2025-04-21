from typing import Optional
from direct.showbase.ShowBase import ShowBase
from panda3d.core import Vec3, Point3, BitMask32
from math import sin, cos, radians

from src.entities.player import Player
from src.managers.input_manager import InputManager
from src.utils.event_bus import EventBus
from src.services.interfaces.i_physics_service import IPhysicsService
from src.utils.service_locator import ServiceLocator
from src.core.config import (KEY_FORWARD, KEY_BACKWARD, KEY_LEFT, KEY_RIGHT, 
                           KEY_SPRINT, KEY_CROUCH, KEY_JUMP, PLAYER_WALK_SPEED, 
                           PLAYER_SPRINT_SPEED, PLAYER_CROUCH_SPEED, MOUSE_SENSITIVITY)

class MovementSystem:
    """
    Sistema responsável por processar inputs e mover o jogador.
    Implementa o padrão Observer para comunicação com outros sistemas.
    """
    
    def __init__(self, show_base: ShowBase):
        """
        Inicializa o sistema de movimento.
        
        Args:
            show_base: Instância do ShowBase do Panda3D
        """
        self._show_base = show_base
        self._input_manager = InputManager()
        self._event_bus = EventBus()
        self._player: Optional[Player] = None
        self._physics_service: Optional[IPhysicsService] = None
        
        # Direções de movimento
        self._move_forward = False
        self._move_backward = False
        self._move_left = False
        self._move_right = False
        self._sprint = False
        self._crouch = False
        
        # Flag para evitar saltos automáticos
        self._jump_pressed = False
        
        # Para detecção de colisão durante o movimento
        self._wall_collision_detected = False
        self._last_movement_direction = Vec3(0, 0, 0)
        self._wall_collision_normals = []
        
        # Obtém o serviço de física
        service_locator = ServiceLocator()
        self._physics_service = service_locator.get(IPhysicsService)
    
    def initialize(self, player: Player) -> None:
        """
        Inicializa o sistema com a referência ao jogador.
        
        Args:
            player: A entidade do jogador
        """
        self._player = player
        
        # Registra callbacks para inputs
        self._register_input_callbacks()
        
        # Subscreve para eventos de colisão
        self._event_bus.subscribe("on_wall_collision", self._on_wall_collision)
        
        print("Sistema de movimento inicializado com jogador")
    
    def _register_input_callbacks(self) -> None:
        """Registra callbacks para inputs de movimento."""
        # Movimento
        self._input_manager.register_action_callback("move_forward", self._on_move_forward)
        self._input_manager.register_action_callback("move_backward", self._on_move_backward)
        self._input_manager.register_action_callback("move_left", self._on_move_left)
        self._input_manager.register_action_callback("move_right", self._on_move_right)
        
        # Ações
        self._show_base.accept(KEY_SPRINT, self._on_sprint, [True])
        self._show_base.accept(KEY_SPRINT + "-up", self._on_sprint, [False])
        self._show_base.accept(KEY_CROUCH, self._on_crouch, [True])
        self._show_base.accept(KEY_CROUCH + "-up", self._on_crouch, [False])
        self._show_base.accept(KEY_JUMP, self._on_jump_down)
        self._show_base.accept(KEY_JUMP + "-up", self._on_jump_up)
        self._show_base.accept("f", self._on_stand_up)       # Tecla para levantar
        
        # Controle de estado direto do teclado (alternativa para o input_manager)
        self._show_base.accept(KEY_FORWARD, self._on_move_forward, [True])
        self._show_base.accept(KEY_FORWARD + "-up", self._on_move_forward, [False])
        self._show_base.accept(KEY_BACKWARD, self._on_move_backward, [True])
        self._show_base.accept(KEY_BACKWARD + "-up", self._on_move_backward, [False])
        self._show_base.accept(KEY_LEFT, self._on_move_left, [True])
        self._show_base.accept(KEY_LEFT + "-up", self._on_move_left, [False])
        self._show_base.accept(KEY_RIGHT, self._on_move_right, [True])
        self._show_base.accept(KEY_RIGHT + "-up", self._on_move_right, [False])
        
        print(f"Controles registrados: WASD={KEY_FORWARD}{KEY_LEFT}{KEY_BACKWARD}{KEY_RIGHT}, Pulo={KEY_JUMP}, Sprint={KEY_SPRINT}, Agachar={KEY_CROUCH}, Levantar=F")

    def _on_stand_up(self) -> None:
        """
        Callback para tecla de levantar.
        Força o jogador a ficar em pé se estiver caído.
        """
        if self._player and hasattr(self._player, 'stand_up'):
            self._player.stand_up()
            print("Tecla de levantar pressionada")
    
    def _on_wall_collision(self, player, entity, normal, position) -> None:
        """
        Callback para quando o jogador colide com uma parede.
        
        Args:
            player: O jogador
            entity: A entidade com a qual colidiu
            normal: A normal da superfície no ponto de colisão
            position: A posição da colisão
        """
        if player != self._player:
            return
        
        # Marca que detectamos colisão com parede
        self._wall_collision_detected = True
        
        # Armazena a normal (limitamos a no máximo 5 normais por frame)
        if len(self._wall_collision_normals) < 5:
            self._wall_collision_normals.append(normal)

    def update(self, dt: float) -> None:
        """
        Atualiza o sistema de movimento.
        
        Args:
            dt: Delta time (tempo desde o último frame)
        """
        if not self._player:
            return
        
        # Reseta detecção de colisão com parede no início de cada frame
        self._wall_collision_detected = False
        self._wall_collision_normals = []
        
        # Processa movimento baseado no teclado
        self._process_keyboard_movement(dt)
        
        # Processa rotação baseada no mouse
        self._process_mouse_rotation()
        
        # Garante que o jogador está em pé a cada frame (estabilização automática)
        if hasattr(self._player, '_stabilize_player'):
            self._player._stabilize_player()

    def _process_keyboard_movement(self, dt: float) -> None:
        """
        Processa o movimento baseado nas teclas pressionadas.
        Implementa deslizamento ao longo de paredes quando em colisão.
        
        Args:
            dt: Delta time (tempo desde o último frame)
        """
        # Calcula o vetor de direção baseado nas teclas pressionadas
        move_dir = Vec3(0, 0, 0)
        
        if self._move_forward:
            move_dir.y += 1
        if self._move_backward:
            move_dir.y -= 1
        if self._move_right:
            move_dir.x += 1
        if self._move_left:
            move_dir.x -= 1
        
        # Normaliza se houver movimento em duas direções
        if move_dir.length_squared() > 0.1:
            move_dir.normalize()
            self._last_movement_direction = move_dir
        
        # Obtém a direção local do jogador (relativa à câmera)
        if self._player.camera_node:
            h = self._player.camera_node.getH()
            
            # Converte direção global para local (relativa à rotação da câmera)
            # Apenas rotaciona no eixo horizontal (mantém movimento no plano XY)
            heading_rad = radians(h)  # Converte graus para radianos
            cos_h = cos(heading_rad)
            sin_h = sin(heading_rad)
            
            local_x = move_dir.x * cos_h - move_dir.y * sin_h
            local_y = move_dir.x * sin_h + move_dir.y * cos_h
            
            move_dir = Vec3(local_x, local_y, 0)
        
        # Define a velocidade baseada no estado do jogador
        speed = PLAYER_WALK_SPEED
        
        if self._sprint and not self._crouch:
            speed = PLAYER_SPRINT_SPEED
        elif self._crouch:
            speed = PLAYER_CROUCH_SPEED
        
        # Se temos colisão com parede, ajusta o movimento para deslizar ao longo da parede
        if self._wall_collision_detected and len(self._wall_collision_normals) > 0:
            # Calcula a normal média de todas as colisões detectadas
            avg_normal = Vec3(0, 0, 0)
            for normal in self._wall_collision_normals:
                avg_normal += normal
            
            if avg_normal.length_squared() > 0:
                avg_normal.normalize()
                
                # Calcula o componente perpendicular à parede (que seria bloqueado)
                perpendicular_component = move_dir.dot(avg_normal) * avg_normal
                
                # Se estamos tentando mover na direção da parede (produto escalar positivo)
                if move_dir.dot(avg_normal) < 0:
                    # Removemos o componente perpendicular para deslizar ao longo da parede
                    move_dir = move_dir - perpendicular_component
                    
                    # Renormaliza se necessário
                    if move_dir.length_squared() > 0.001:
                        move_dir.normalize()
                    else:
                        # Se praticamente zero, não movemos (tentando ir perpendicular à parede)
                        move_dir = Vec3(0, 0, 0)
        
        # Aplica o movimento ao jogador - não escala pelo dt aqui
        # pois será escalado dentro do método move() do jogador
        if move_dir.length_squared() > 0.001:  # Se houver movimento
            self._player.move(move_dir, speed)
        
        # Atualiza o estado do jogador
        self._player.sprint(self._sprint)
        self._player.crouch(self._crouch)
    
    def _process_mouse_rotation(self) -> None:
        """Processa a rotação da câmera baseada no movimento do mouse."""
        # Obtém o delta do mouse
        mouse_delta = self._input_manager.get_mouse_delta()
        
        # Aplica a rotação à câmera do jogador
        if mouse_delta[0] != 0 or mouse_delta[1] != 0:
            # mouse_delta[0] controla a rotação horizontal (heading), sem inversão
            # mouse_delta[1] controla a rotação vertical (pitch), com inversão para comportamento natural
            self._player.rotate_head(-mouse_delta[0], mouse_delta[1])
    
    def _on_move_forward(self, pressed: bool) -> None:
        """
        Callback para tecla de movimento para frente.
        
        Args:
            pressed: True se a tecla foi pressionada, False se liberada
        """
        self._move_forward = pressed
    
    def _on_move_backward(self, pressed: bool) -> None:
        """
        Callback para tecla de movimento para trás.
        
        Args:
            pressed: True se a tecla foi pressionada, False se liberada
        """
        self._move_backward = pressed
    
    def _on_move_left(self, pressed: bool) -> None:
        """
        Callback para tecla de movimento para esquerda.
        
        Args:
            pressed: True se a tecla foi pressionada, False se liberada
        """
        self._move_left = pressed
    
    def _on_move_right(self, pressed: bool) -> None:
        """
        Callback para tecla de movimento para direita.
        
        Args:
            pressed: True se a tecla foi pressionada, False se liberada
        """
        self._move_right = pressed
    
    def _on_sprint(self, pressed: bool) -> None:
        """
        Callback para tecla de sprint.
        
        Args:
            pressed: True se a tecla foi pressionada, False se liberada
        """
        self._sprint = pressed
    
    def _on_crouch(self, pressed: bool) -> None:
        """
        Callback para tecla de agachamento.
        
        Args:
            pressed: True se a tecla foi pressionada, False se liberada
        """
        self._crouch = pressed
        
        # Aplica imediatamente ao jogador para resposta instantânea
        if self._player:
            self._player.crouch(pressed)
    
    def _on_jump_down(self) -> None:
        """Callback para quando a tecla de pulo é pressionada."""
        # Verificar se a tecla já estava pressionada (evita pulo automático contínuo)
        if not self._jump_pressed:
            self._jump_pressed = True
            self._execute_jump()
    
    def _on_jump_up(self) -> None:
        """Callback para quando a tecla de pulo é liberada."""
        self._jump_pressed = False
    
    def _execute_jump(self) -> None:
        """Executa o pulo se o jogador estiver no chão."""
        if self._player and self._player.is_grounded:
            self._player.jump()
            print("Tecla de pulo pressionada - executando salto")
        else:
            if self._player:
                print("Tecla de pulo pressionada - ignorando (não está no chão)")
    
    def perform_raycast_ahead(self, distance: float) -> Optional[Point3]:
        """
        Realiza um raycast na direção do movimento para detectar obstáculos.
        
        Args:
            distance: Distância máxima do raycast
            
        Returns:
            Ponto de colisão ou None se não houver colisão
        """
        if not self._player or not self._physics_service:
            return None
        
        try:
            # Obtém a posição atual do jogador
            current_pos = self._player._transform.position
            
            # Usa a direção de movimento ou a direção da câmera se não estiver se movendo
            direction = self._last_movement_direction
            if direction.length_squared() < 0.001 and self._player.camera_node:
                # Usa a direção para onde a câmera está olhando
                h = self._player.camera_node.getH()
                heading_rad = radians(h)
                direction = Vec3(sin(heading_rad), cos(heading_rad), 0)
            
            # Normaliza a direção
            if direction.length_squared() > 0.001:
                direction.normalize()
                
                # Calcula o ponto final do raycast
                end_pos = current_pos + direction * distance
                
                # Realiza o raycast
                result = self._physics_service.perform_ray_test(
                    (current_pos.x, current_pos.y, current_pos.z),
                    (end_pos.x, end_pos.y, end_pos.z)
                )
                
                if result and result.hasHit():
                    # Retorna o ponto de colisão
                    hit_pos = result.getHitPos()
                    return Point3(hit_pos.x, hit_pos.y, hit_pos.z)
            
            return None
        except Exception as e:
            print(f"Erro ao realizar raycast: {e}")
            return None
    
    def cleanup(self) -> None:
        """Limpa recursos e remove listeners."""
        # Remove os callbacks de input
        input_manager = self._input_manager
        
        if input_manager:
            input_manager.unregister_action_callback("move_forward", self._on_move_forward)
            input_manager.unregister_action_callback("move_backward", self._on_move_backward)
            input_manager.unregister_action_callback("move_left", self._on_move_left)
            input_manager.unregister_action_callback("move_right", self._on_move_right)
        
        # Remove os accepts do Panda3D
        if self._show_base:
            self._show_base.ignore(KEY_SPRINT)
            self._show_base.ignore(KEY_SPRINT + "-up")
            self._show_base.ignore(KEY_CROUCH)
            self._show_base.ignore(KEY_CROUCH + "-up")
            self._show_base.ignore(KEY_JUMP)
            self._show_base.ignore(KEY_JUMP + "-up")
            self._show_base.ignore("f")  # Tecla para levantar
            self._show_base.ignore(KEY_FORWARD)
            self._show_base.ignore(KEY_FORWARD + "-up")
            self._show_base.ignore(KEY_BACKWARD)
            self._show_base.ignore(KEY_BACKWARD + "-up")
            self._show_base.ignore(KEY_LEFT)
            self._show_base.ignore(KEY_LEFT + "-up")
            self._show_base.ignore(KEY_RIGHT)
            self._show_base.ignore(KEY_RIGHT + "-up")
        
        # Remove inscrições de eventos
        self._event_bus.unsubscribe("on_wall_collision", self._on_wall_collision)
        
        # Limpa referências
        self._player = None
        self._physics_service = None