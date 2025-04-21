from typing import Optional, Tuple, List
import os
import random
from direct.showbase.ShowBase import ShowBase
from panda3d.core import WindowProperties, LVector3, LVector4, NodePath, Vec3, Point3
from panda3d.core import Filename, PandaNode, PNMImage, Texture, TextureStage, TexGenAttrib
from panda3d.core import CollisionNode, CollisionBox, CollisionPlane, BitMask32, Plane
from panda3d.core import CullFaceAttrib, TransparencyAttrib

from src.managers.game_manager import GameManager, GameState, GameStateHandler
from src.managers.scene_manager import SceneManager
from src.managers.input_manager import InputManager
from src.managers.audio_manager import AudioManager

from src.services.physics_service import PhysicsService
from src.services.audio_service import AudioService
from src.services.interfaces.i_physics_service import IPhysicsService
from src.services.interfaces.i_audio_service import IAudioService

from src.systems.movement_system import MovementSystem
from src.systems.collision_system import CollisionSystem

from src.entities.player import Player
from src.entities.static_object import StaticObject

from src.ui.debug_overlay import DebugOverlay

from src.utils.service_locator import ServiceLocator
from src.utils.event_bus import EventBus

# Importar as novas classes para a arquitetura de objetos
from src.objects.factory.game_object_factory import GameObjectFactory
from src.objects.room_builder import RoomBuilder

from src.core.config import (GAME_TITLE, VERSION, WINDOW_SIZE, FULLSCREEN,
                            ROOM_SIZE, NUMBER_OF_BOXES, WALL_THICKNESS, KEY_PAUSE,
                            MODELS_DIR, TEXTURES_DIR, DEBUG_MODE)

class Phase1Handler(GameStateHandler):
    """Handler para o estado de jogo da Fase 1 (movimento e colisões)."""
    
    def __init__(self, game_app: 'GameApp'):
        """
        Inicializa o handler da Fase 1.
        
        Args:
            game_app: Referência para o GameApp
        """
        self._game_app = game_app
        self._show_base = self._game_app._show_base
        self._event_bus = EventBus()
    
    def enter(self) -> None:
        """Chamado quando entramos neste estado."""
        print("Entrando na Fase 1: Movimentação e Colisões")
        
        # Inicializa a cena da Fase 1
        self._game_app.load_phase1_scene()
    
    def update(self, dt: float) -> None:
        """
        Atualiza a lógica deste estado.
        
        Args:
            dt: Delta time (tempo desde o último frame)
        """
        # Atualiza sistemas
        self._game_app.update_systems(dt)
    
    def exit(self) -> None:
        """Chamado quando saímos deste estado."""
        print("Saindo da Fase 1")

class GameApp:
    """
    Classe principal do jogo que configura e coordena todos os sistemas.
    Implementa o padrão Facade para a aplicação.
    """
    
    def __init__(self):
        """Inicializa a aplicação do jogo."""
        self._show_base: Optional[ShowBase] = None
        self._managers_initialized = False
        self._services_initialized = False
        self._systems_initialized = False
        
        # Referências para sistemas e serviços
        self._game_manager: Optional[GameManager] = None
        self._scene_manager: Optional[SceneManager] = None
        self._input_manager: Optional[InputManager] = None
        self._audio_manager: Optional[AudioManager] = None
        
        self._physics_service: Optional[PhysicsService] = None
        self._audio_service: Optional[AudioService] = None
        
        self._movement_system: Optional[MovementSystem] = None
        self._collision_system: Optional[CollisionSystem] = None
        
        self._player: Optional[Player] = None
        self._debug_overlay: Optional[DebugOverlay] = None
        
        # Novas referências para o sistema de objetos
        self._object_factory: Optional[GameObjectFactory] = None
        self._room_builder: Optional[RoomBuilder] = None
        
        # Coleção de entidades
        self._static_objects: List[StaticObject] = []
    
    def _toggle_debug_overlay(self) -> None:
        if self._debug_overlay:
            enabled = self._debug_overlay.toggle()
            print(f"Debug overlay: {'Enabled' if enabled else 'Disabled'}")

    def _toggle_collision_visualization(self) -> None:
        if self._debug_overlay:
            enabled = self._debug_overlay.toggle_collision_shapes()
            print(f"Collision visualization: {'Enabled' if enabled else 'Disabled'}")

    def _toggle_fps_display(self) -> None:
        if self._debug_overlay:
            enabled = self._debug_overlay.toggle_fps()
            print(f"FPS display: {'Enabled' if enabled else 'Disabled'}")


    def _setup_inputs(self) -> None:
        self._show_base.accept(KEY_PAUSE, self._toggle_pause_game)

        if DEBUG_MODE:
            self._show_base.accept("f1", self._toggle_debug_overlay)
            self._show_base.accept("f2", self._toggle_collision_visualization)
            self._show_base.accept("f3", self._toggle_fps_display)

    def _setup_window(self) -> None:
        """Configura a janela do jogo."""
        props = WindowProperties()
        props.setTitle(f"{GAME_TITLE} v{VERSION}")
        props.setSize(WINDOW_SIZE[0], WINDOW_SIZE[1])
        props.setFullscreen(FULLSCREEN)
        props.setCursorHidden(True)
        self._show_base.win.requestProperties(props)
        
        # Configura o background color
        self._show_base.setBackgroundColor(0.1, 0.1, 0.12)
    
    def _init_managers(self) -> None:
        """Inicializa todos os managers."""
        if self._managers_initialized:
            return
        
        # Obtém instâncias dos managers (singletons)
        self._game_manager = GameManager()
        self._scene_manager = SceneManager()
        self._input_manager = InputManager()
        self._audio_manager = AudioManager()
        
        # Inicializa os managers que precisam do ShowBase
        self._scene_manager.initialize(self._show_base)
        self._input_manager.initialize(self._show_base)
        
        self._managers_initialized = True
    
    def _init_services(self) -> None:
        """Inicializa todos os serviços."""
        if self._services_initialized:
            return
        
        # Cria serviços
        self._physics_service = PhysicsService(self._show_base)
        self._physics_service.initialize()
        
        self._audio_service = AudioService(self._show_base)
        self._audio_service.initialize()
        
        # Registra serviços no Service Locator
        service_locator = ServiceLocator()
        service_locator.register(IPhysicsService, self._physics_service)
        service_locator.register(IAudioService, self._audio_service)
        
        # Completa inicialização de managers que dependem de serviços
        self._audio_manager.initialize(self._show_base, self._audio_service)
        
        self._services_initialized = True
    

    def _register_game_states(self) -> None:
        """Registra handlers para os estados do jogo."""
        self._game_manager.register_state(GameState.PHASE1_MOVEMENT, Phase1Handler(self))
        

    def _toggle_pause_game(self) -> None:
        """Alterna entre pausado e não pausado."""
        if self._game_manager:
            self._game_manager.toggle_pause()
            paused = self._game_manager.is_paused
            print(f"Jogo {'pausado' if paused else 'despausado'}")

    """
    Versão simplificada para criar paredes sem usar texturas complexas
    """
    def _create_room_new(self) -> None:
        """Cria uma sala usando abordagem simplificada para evitar problemas de textura"""
        # Limpa qualquer objeto anterior
        self._static_objects = []
        
        # Obtém dimensões da sala
        width, length, height = ROOM_SIZE
        hw, hl = width/2, length/2
        thick = WALL_THICKNESS
        
        # Cria o piso usando cor simples em vez de textura
        floor = StaticObject("Floor")
        floor.setup(
            parent=self._scene_manager.root_node,
            model_path=f"{MODELS_DIR}/environment/room.egg",
            position=(0, 0, -thick/2),  # Topo do chão em Z=0
            scale=(width, length, thick),
            shape_type="box",
            dimensions=(hw, hl, thick/2),
        )
        # Aplica cor simples
        floor.node_path.setColor(0.4, 0.4, 0.4, 1.0)  # Cinza escuro
        self._static_objects.append(floor)
        self._scene_manager.add_entity(floor)
        
        # Cria as 4 paredes com cores sólidas
        # Parede frontal
        wall_front = StaticObject("Wall_Front")
        wall_front.setup(
            parent=self._scene_manager.root_node,
            model_path=f"{MODELS_DIR}/environment/wall.egg",
            position=(0, hl+thick/2, height/2),
            scale=(width+thick*2, thick, height),
            shape_type="box",
            dimensions=(hw+thick, thick/2, height/2),
        )
        wall_front.node_path.setColor(0.7, 0.7, 0.7, 1.0)  # Cinza claro
        self._static_objects.append(wall_front)
        self._scene_manager.add_entity(wall_front)
        
        # Parede traseira
        wall_back = StaticObject("Wall_Back")
        wall_back.setup(
            parent=self._scene_manager.root_node,
            model_path=f"{MODELS_DIR}/environment/wall.egg",
            position=(0, -hl-thick/2, height/2),
            scale=(width+thick*2, thick, height),
            shape_type="box",
            dimensions=(hw+thick, thick/2, height/2),
        )
        wall_back.node_path.setColor(0.7, 0.7, 0.7, 1.0)  # Cinza claro
        self._static_objects.append(wall_back)
        self._scene_manager.add_entity(wall_back)
        
        # Parede esquerda
        wall_left = StaticObject("Wall_Left")
        wall_left.setup(
            parent=self._scene_manager.root_node,
            model_path=f"{MODELS_DIR}/environment/wall.egg",
            position=(-hw-thick/2, 0, height/2),
            scale=(thick, length+thick*2, height),
            shape_type="box",
            dimensions=(thick/2, hl+thick, height/2),
        )
        wall_left.node_path.setColor(0.7, 0.7, 0.7, 1.0)  # Cinza claro
        self._static_objects.append(wall_left)
        self._scene_manager.add_entity(wall_left)
        
        # Parede direita
        wall_right = StaticObject("Wall_Right")
        wall_right.setup(
            parent=self._scene_manager.root_node,
            model_path=f"{MODELS_DIR}/environment/wall.egg",
            position=(hw+thick/2, 0, height/2),
            scale=(thick, length+thick*2, height),
            shape_type="box",
            dimensions=(thick/2, hl+thick, height/2),
        )
        wall_right.node_path.setColor(0.7, 0.7, 0.7, 1.0)  # Cinza claro
        self._static_objects.append(wall_right)
        self._scene_manager.add_entity(wall_right)
        
        # Cria o teto
        ceiling = StaticObject("Ceiling")
        ceiling.setup(
            parent=self._scene_manager.root_node,
            model_path=f"{MODELS_DIR}/environment/room.egg", 
            position=(0, 0, height + thick/2),
            scale=(width, length, thick),
            shape_type="box",
            dimensions=(hw, hl, thick/2),
        )
        ceiling.node_path.setColor(0.6, 0.6, 0.8, 1.0)  # Cinza azulado
        self._static_objects.append(ceiling)
        self._scene_manager.add_entity(ceiling)
        
        # Adiciona caixas com cores sólidas
        for i in range(NUMBER_OF_BOXES):
            # Posição aleatória dentro dos limites da sala
            import random
            pos_x = random.uniform(-hw + 1.0, hw - 1.0)
            pos_y = random.uniform(-hl + 1.0, hl - 1.0)
            
            # Verifica distância do jogador (0,0,0)
            distance_from_player = ((pos_x)**2 + (pos_y)**2)**0.5
            if distance_from_player <= 2.0:  # Muito perto do jogador
                continue  # Pula esta caixa
                
            # Tamanho aleatório
            size = random.uniform(0.3, 0.8)
            
            # Cria a caixa
            box = StaticObject(f"Box_{i}")
            box.setup(
                parent=self._scene_manager.root_node,
                model_path=f"{MODELS_DIR}/environment/box.egg",
                position=(pos_x, pos_y, size/2),  # Base no chão
                scale=(size, size, size),
                shape_type="box",
                dimensions=(size/2, size/2, size/2),
            )
            box.node_path.setColor(0.6, 0.3, 0.1, 1.0)  # Marrom
            
            self._static_objects.append(box)
            self._scene_manager.add_entity(box)
        
        # Registra todas as entidades no sistema de colisão
        for entity in self._static_objects:
            if self._collision_system:
                self._collision_system.add_entity(entity)
        
        print(f"Sala criada com cores sólidas e {len(self._static_objects)} elementos")
    def _setup_lighting(self) -> None:
        """Configura iluminação difusa e especular da cena."""
        from panda3d.core import AmbientLight, DirectionalLight, PointLight, Vec4

        root = self._scene_manager.root_node

        # 1) Luz ambiente (difusa geral)
        ambient = AmbientLight("ambient")
        ambient.setColor(Vec4(0.3, 0.3, 0.3, 1))   # Aumentada para mais claridade
        ambient_np = root.attachNewNode(ambient)
        root.setLight(ambient_np)

        # 2) Key light (principal, trabalhar especular)
        key = DirectionalLight("key")
        key.setColor(Vec4(0.8, 0.8, 0.7, 1))        # ligeiramente quente
        key.setSpecularColor(Vec4(1.0, 1.0, 1.0, 1))# destaque especular
        key_np = root.attachNewNode(key)
        key_np.setHpr(45, -60, 0)                   # ângulo inclinado
        root.setLight(key_np)

        # 3) Fill light (suaviza sombras)
        fill = DirectionalLight("fill")
        fill.setColor(Vec4(0.3, 0.4, 0.5, 1))       # tom frio
        fill.setSpecularColor(Vec4(0.2, 0.2, 0.2, 1))
        fill_np = root.attachNewNode(fill)
        fill_np.setHpr(-30, -30, 0)
        root.setLight(fill_np)

        # 4) Back light (realça silhuetas)
        back = DirectionalLight("back")
        back.setColor(Vec4(0.2, 0.2, 0.3, 1))
        back.setSpecularColor(Vec4(0.2, 0.2, 0.2, 1))
        back_np = root.attachNewNode(back)
        back_np.setHpr(135, -10, 0)
        root.setLight(back_np)

        # 5) Point light no teto (reflexos especulares locais)
        pl = PointLight("pl_teto")
        pl.setColor(Vec4(0.8, 0.8, 0.8, 1))         # Aumentada para mais claridade
        pl.setSpecularColor(Vec4(1.0, 1.0, 1.0, 1))
        pl_np = root.attachNewNode(pl)
        # posiciona centralizado, um pouco abaixo do teto
        pl_np.setPos(0, 0, ROOM_SIZE[2] - 0.2)
        root.setLight(pl_np)

        # 6) Habilita shader generator para especular no pipeline fixo
        self._show_base.render.setShaderAuto()

        print("Iluminação difusa e especular configurada com sucesso")

    # Modificações no método initialize do GameApp

    def initialize(self, show_base: ShowBase) -> None:
        """
        Inicializa a aplicação com o ShowBase do Panda3D.
        
        Args:
            show_base: Instância do ShowBase do Panda3D
        """
        self._show_base = show_base
        
        # Disponibiliza a instância para acesso global
        self._show_base.gameApp = self
        
        # Configura a janela
        self._setup_window()
        
        # Inicializa componentes em ordem de dependência
        self._init_managers()
        self._init_services()
        self._init_systems()
        
        # Registra handlers de estado
        self._register_game_states()
        
        # Configura inputs globais
        self._setup_inputs()
        
        # Inicia o jogo
        self._game_manager.change_state(GameState.PHASE1_MOVEMENT)
        
        # Registra tarefa de atualização
        self._show_base.taskMgr.add(self._update_task, "GameUpdateTask")


    # Modificações no método _init_systems do GameApp

    def _init_systems(self) -> None:
        """Inicializa todos os sistemas."""
        if not self._managers_initialized or not self._services_initialized:
            return
        
        # Cria sistemas
        self._movement_system = MovementSystem(self._show_base)
        
        # O sistema de colisão agora é gerenciado pelo SceneManager
        # Obtemos a referência diretamente de lá
        if self._scene_manager:
            self._collision_system = self._scene_manager.get_collision_system()
        else:
            # Fallback - cria o sistema diretamente
            from src.systems.collision_system import CollisionSystem
            self._collision_system = CollisionSystem(self._show_base)
            self._collision_system.initialize()
        
        # Inicializa o overlay de debug
        self._debug_overlay = DebugOverlay(self._show_base)
        
        # Inicializa a fábrica de objetos e o construtor de salas
        self._object_factory = GameObjectFactory(self._show_base)
        self._room_builder = RoomBuilder(self._object_factory)
        
        self._systems_initialized = True


    # Modificações no método load_phase1_scene do GameApp

    def load_phase1_scene(self) -> None:
        """Carrega a cena para a Fase 1 (movimento e colisões)."""
        # Carrega a cena
        self._scene_manager.load_scene("phase1")
        
        # Cria a sala simples usando o novo sistema
        self._create_room_new()
        
        # Adiciona uma luz direcional para claridade
        self._setup_lighting()
        
        # IMPORTANTE: Cria o jogador APÓS criar o ambiente para evitar colisões iniciais
        self._player = Player(self._show_base)
        
        # Posiciona o jogador no centro da sala, exatamente no nível do chão
        player_start_position = (0, 0, 0)  # Z=0 para começar no nível do chão
        self._player.setup(self._scene_manager.root_node, position=player_start_position)
        self._scene_manager.add_entity(self._player)
        
        # Inicializa sistemas com o jogador
        self._movement_system.initialize(self._player)
        
        # O sistema de colisão já registra o jogador automaticamente através do scene_manager
        
        # Inicializa o debug overlay por último (depois que o jogador está pronto)
        if self._debug_overlay:
            self._debug_overlay.initialize(self._player)
        
        print("Fase 1 carregada com sucesso")


    # Modificações no método update_systems do GameApp

    def update_systems(self, dt: float) -> None:
        """
        Atualiza todos os sistemas do jogo.
        
        Args:
            dt: Delta time (tempo desde o último frame)
        """
        # Atualiza o InputManager primeiro
        if self._input_manager:
            self._input_manager.update()
        
        # Atualiza o sistema de movimento
        if self._movement_system:
            self._movement_system.update(dt)
        
        # Atualiza o sistema de colisão
        if self._collision_system:
            self._collision_system.update(dt)
        
        # Atualiza o overlay de debug
        if self._debug_overlay:
            self._debug_overlay.update(dt)
        
        # Atualiza o jogador
        if self._player:
            self._player.update(dt)
        
        # Atualiza objetos estáticos
        for obj in self._static_objects:
            obj.update(dt)


    def _update_task(self, task):
        """
        Tarefa de atualização principal do jogo.
        
        Args:
            task: Objeto Task do Panda3D
            
        Returns:
            Código de status da tarefa (Task.cont para continuar)
        """
        try:
            # Obtém o delta time
            dt = 0.016  # ~60 FPS como fallback
            
            if hasattr(task, 'time'):
                current_time = task.time
                if hasattr(task, 'prev_time'):
                    dt = current_time - task.prev_time
                    # Limite de dt para evitar problemas com framerate muito baixo
                    dt = min(dt, 0.1)
                task.prev_time = current_time
            
            # Atualiza o gerenciador de estados
            if self._game_manager:
                try:
                    self._game_manager.update(dt)
                except Exception as e:
                    print(f"Erro ao atualizar game_manager: {e}")
        except Exception as e:
            print(f"Erro na tarefa de atualização: {e}")
        
        return task.cont
    
    def _toggle_pause(self) -> None:
        """Alterna entre pausado e não pausado."""
        if self._game_manager:
            self._game_manager.toggle_pause()
    
    def cleanup(self) -> None:
        """Limpa todos os recursos da aplicação."""
        # Limpa sistemas
        if self._movement_system:
            self._movement_system.cleanup()
        
        if self._collision_system:
            self._collision_system.cleanup()
        
        if self._debug_overlay:
            self._debug_overlay.cleanup()
        
        # Limpa entidades
        if self._player:
            self._player.cleanup()
        
        for obj in self._static_objects:
            obj.cleanup()
        
        self._static_objects.clear()
        
        # Limpa serviços
        if self._physics_service:
            self._physics_service.cleanup()
        
        if self._audio_service:
            self._audio_service.cleanup()
        
        # Limpa managers
        if self._scene_manager:
            self._scene_manager.unload_current_scene()