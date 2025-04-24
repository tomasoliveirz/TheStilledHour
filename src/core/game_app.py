from typing import Optional, Tuple, List
import os
import random
from direct.showbase.ShowBase import ShowBase
from panda3d.core import WindowProperties, LVector3, LVector4, NodePath, Vec3, Point3, Shader
from panda3d.core import Filename, PandaNode, PNMImage, Texture, TextureStage, TexGenAttrib
from panda3d.core import CollisionNode, CollisionBox, CollisionPlane, BitMask32, Plane
from panda3d.core import CullFaceAttrib, TransparencyAttrib

from src.entities.entity import Entity
from src.entities.npc import NPC
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
                             MODELS_DIR, TEXTURES_DIR, DEBUG_MODE, ENABLE_PBR)

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
        self._npcs: List[NPC] = []
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

    def _create_room_new(self) -> None:
        """Cria uma sala com texturas aplicadas corretamente."""
        # Limpa qualquer objeto anterior
        self._static_objects = []

        # Obtém dimensões da sala
        width, length, height = ROOM_SIZE
        hw, hl = width / 2, length / 2
        thick = WALL_THICKNESS

        # CORREÇÃO: Vamos usar o construtor de sala que usa as texturas corretamente
        if self._room_builder:
            # Constrói a sala com o RoomBuilder
            room_objects = self._room_builder.build_rectangular_room(
                parent=self._scene_manager.root_node,
                width=width,
                length=length,
                height=height,
                wall_thickness=thick,
                position=(0, 0, 0)
            )

            # Adiciona os objetos da sala à lista de objetos estáticos
            self._static_objects.extend(room_objects)

            # Registra os objetos no SceneManager
            for entity in room_objects:
                self._scene_manager.add_entity(entity)

            # Adiciona caixas pelo ambiente
            box_objects = self._room_builder.add_boxes(
                parent=self._scene_manager.root_node,
                count=NUMBER_OF_BOXES,
                min_size=1,
                max_size=1.5,
                movable=True
            )

            # Adiciona as caixas à lista de objetos estáticos
            self._static_objects.extend(box_objects)

            # Registra as caixas no SceneManager
            for entity in box_objects:
                self._scene_manager.add_entity(entity)

            # Registra todas as entidades no sistema de colisão
            if self._collision_system:
                for entity in self._static_objects:
                    self._collision_system.add_entity(entity)

            print(f"Sala criada com {len(self._static_objects)} elementos usando RoomBuilder")
            return

        # FALLBACK: Se não tiver RoomBuilder, cria a sala manualmente com cores
        print("Aviso: RoomBuilder não disponível, criando sala com cores sólidas")

        # Cria o piso usando cor simples em vez de textura
        floor = StaticObject("Floor")
        floor.setup(
            parent=self._scene_manager.root_node,
            model_path=f"{MODELS_DIR}/environment/room.egg",
            position=(0, 0, -thick / 2),  # Topo do chão em Z=0
            scale=(width, length, thick),
            shape_type="box",
            dimensions=(hw, hl, thick / 2),
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
            position=(0, hl + thick / 2, height / 2),
            scale=(width + thick * 2, thick, height),
            shape_type="box",
            dimensions=(hw + thick, thick / 2, height / 2),
        )
        wall_front.node_path.setColor(0.7, 0.7, 0.7, 1.0)  # Cinza claro
        self._static_objects.append(wall_front)
        self._scene_manager.add_entity(wall_front)

        # Parede traseira
        wall_back = StaticObject("Wall_Back")
        wall_back.setup(
            parent=self._scene_manager.root_node,
            model_path=f"{MODELS_DIR}/environment/wall.egg",
            position=(0, -hl - thick / 2, height / 2),
            scale=(width + thick * 2, thick, height),
            shape_type="box",
            dimensions=(hw + thick, thick / 2, height / 2),
        )
        wall_back.node_path.setColor(0.7, 0.7, 0.7, 1.0)  # Cinza claro
        self._static_objects.append(wall_back)
        self._scene_manager.add_entity(wall_back)

        # Parede esquerda
        wall_left = StaticObject("Wall_Left")
        wall_left.setup(
            parent=self._scene_manager.root_node,
            model_path=f"{MODELS_DIR}/environment/wall.egg",
            position=(-hw - thick / 2, 0, height / 2),
            scale=(thick, length + thick * 2, height),
            shape_type="box",
            dimensions=(thick / 2, hl + thick, height / 2),
        )
        wall_left.node_path.setColor(0.7, 0.7, 0.7, 1.0)  # Cinza claro
        self._static_objects.append(wall_left)
        self._scene_manager.add_entity(wall_left)

        # Parede direita
        wall_right = StaticObject("Wall_Right")
        wall_right.setup(
            parent=self._scene_manager.root_node,
            model_path=f"{MODELS_DIR}/environment/wall.egg",
            position=(hw + thick / 2, 0, height / 2),
            scale=(thick, length + thick * 2, height),
            shape_type="box",
            dimensions=(thick / 2, hl + thick, height / 2),
        )
        wall_right.node_path.setColor(0.7, 0.7, 0.7, 1.0)  # Cinza claro
        self._static_objects.append(wall_right)
        self._scene_manager.add_entity(wall_right)

        # Cria o teto
        ceiling = StaticObject("Ceiling")
        ceiling.setup(
            parent=self._scene_manager.root_node,
            model_path=f"{MODELS_DIR}/environment/room.egg",
            position=(0, 0, height + thick / 2),
            scale=(width, length, thick),
            shape_type="box",
            dimensions=(hw, hl, thick / 2),
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
            distance_from_player = ((pos_x) ** 2 + (pos_y) ** 2) ** 0.5
            if distance_from_player <= 2.0:  # Muito perto do jogador
                continue  # Pula esta caixa

            # Tamanho aleatório
            size = random.uniform(0.3, 0.8)

            # Cria a caixa
            box = StaticObject(f"Box_{i}")
            box.setup(
                parent=self._scene_manager.root_node,
                model_path=f"{MODELS_DIR}/environment/box.egg",
                position=(pos_x, pos_y, size / 2),  # Base no chão
                scale=(size, size, size),
                shape_type="box",
                dimensions=(size / 2, size / 2, size / 2),
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
        """
         Configura iluminação básica compatível com qualquer versão do Panda3D.
         Sem depender de funcionalidades de sombra avançadas.
         """
        from panda3d.core import AmbientLight, DirectionalLight, PointLight
        from panda3d.core import Vec4, Vec3

        root = self._scene_manager.root_node

        # Luz ambiente forte para garantir visibilidade básica
        ambient = AmbientLight("ambient")
        ambient.setColor(Vec4(0.6, 0.6, 0.65, 1))  # Luz ambiente bastante intensa
        ambient_np = root.attachNewNode(ambient)
        root.setLight(ambient_np)

        # Luz direcional principal
        sun = DirectionalLight("sun")
        sun.setColor(Vec4(0.9, 0.9, 0.8, 1))  # Luz branca/amarelada
        sun_np = root.attachNewNode(sun)
        sun_np.setHpr(45, -60, 0)  # Ângulo que simula sol
        root.setLight(sun_np)

        # Luz direcional secundária (para preencher sombras)
        fill = DirectionalLight("fill")
        fill.setColor(Vec4(0.6, 0.6, 0.8, 1))  # Tom azulado suave
        fill_np = root.attachNewNode(fill)
        fill_np.setHpr(-120, -30, 0)  # Direção oposta à luz principal
        root.setLight(fill_np)

        # Luz central para iluminar o meio da sala
        width, length, height = ROOM_SIZE
        central_light = PointLight("central_light")
        central_light.setColor(Vec4(1.0, 0.98, 0.9, 1))  # Branco levemente amarelado

        # Atenuação mais suave para maior alcance
        central_light.setAttenuation(Vec3(1.0, 0.005, 0.0))

        central_light_np = root.attachNewNode(central_light)
        central_light_np.setPos(0, 0, height * 0.75)  # Posicionada a 75% da altura da sala
        root.setLight(central_light_np)

        # Luzes das extremidades para iluminar os cantos
        corner1 = PointLight("corner1")
        corner1.setColor(Vec4(0.8, 0.7, 0.6, 1))  # Amarelada
        corner1.setAttenuation(Vec3(1.0, 0.007, 0.0001))
        corner1_np = root.attachNewNode(corner1)
        corner1_np.setPos(width * 0.4, length * 0.4, height * 0.5)
        root.setLight(corner1_np)

        corner2 = PointLight("corner2")
        corner2.setColor(Vec4(0.6, 0.6, 0.9, 1))  # Azulada
        corner2.setAttenuation(Vec3(1.0, 0.007, 0.0001))
        corner2_np = root.attachNewNode(corner2)
        corner2_np.setPos(-width * 0.4, -length * 0.4, height * 0.5)
        root.setLight(corner2_np)

        # Armazena referências às luzes
        self._lights = {
            "ambient": ambient_np,
            "sun": sun_np,
            "fill": fill_np,
            "central": central_light_np,
            "corner1": corner1_np,
            "corner2": corner2_np
        }

        # Configura materiais para todos os objetos
        self._apply_materials_to_scene()

        print("Sistema de iluminação básica configurado com sucesso")

        print("Sistema de iluminação otimizado configurado com sombras suavizadas")
    def _configure_shadows_for_entity(self, entity: Entity, cast_shadow: bool = True,
                                      receive_shadow: bool = True) -> None:
        """
        Configura as propriedades de sombra para uma entidade específica.

        Args:
            entity: A entidade a configurar
            cast_shadow: Se a entidade deve projetar sombras
            receive_shadow: Se a entidade deve receber sombras
        """
        if not entity or not entity.node_path:
            return

        try:
            np = entity.node_path

            # Configura projeção de sombras
            if cast_shadow:
                np.setShaderInput("castShadow", 1)
            else:
                np.setShaderInput("castShadow", 0)

            # Configura recepção de sombras
            if receive_shadow:
                np.setShaderInput("receiveShadow", 1)
            else:
                np.setShaderInput("receiveShadow", 0)

        except Exception as e:
            print(f"Erro ao configurar sombras para {entity.name}: {e}")

    def activate_basic_shadows(self) -> None:
        """
        Ativa sombras básicas automáticas no Panda3D.
        Versão melhorada para produzir sombras mais suaves e iluminação mais balanceada.
        """
        try:
            from panda3d.core import AmbientLight, DirectionalLight, Spotlight
            from panda3d.core import PerspectiveLens, NodePath, Vec3, Vec4

            print("Ativando sistema de sombras básicas otimizado...")

            # Primeiro, habilita o shader automático (necessário para sombras)
            self._show_base.render.setShaderAuto()

            # Determina a resolução dos shadow maps com base no hardware
            # Valores mais baixos para melhor performance e sombras mais suaves
            try:
                shader_quality = self._show_base.win.getGsg().getShaderModel()
                if shader_quality >= 4:  # SM 4.0 ou superior
                    shadow_map_size = 1024
                else:
                    shadow_map_size = 512
            except:
                # Fallback para valor seguro
                shadow_map_size = 512

            print(f"Usando shadow maps de {shadow_map_size}x{shadow_map_size}")

            # Pegando a referência da cena
            scene_root = self._scene_manager.root_node

            # 1. Configura luz ambiente AUMENTADA para iluminar melhor áreas de sombra
            ambient = AmbientLight("ambient")
            ambient.setColor(Vec4(0.5, 0.5, 0.55, 1))  # Aumentado para 0.5 (era 0.35)
            ambient_np = scene_root.attachNewNode(ambient)
            scene_root.setLight(ambient_np)

            # 2. Luz direcional principal com sombras suavizadas
            sun = DirectionalLight("sun")
            sun.setColor(Vec4(0.9, 0.85, 0.7, 1))  # Ligeiramente reduzida e mais quente
            sun.setSpecularColor(Vec4(0.8, 0.8, 0.7, 1))  # Especular menos intenso

            # Configurações de sombra mais suaves para a luz direcional
            sun.setShadowCaster(True)
            sun.setScene(scene_root)
            sun.setShadowMapSize(shadow_map_size)

            # ADIÇÕES: Parâmetros para sombras mais suaves
            if hasattr(sun, 'setShadowSoftness'):
                sun.setShadowSoftness(0.03)  # Sombras mais suaves
            if hasattr(sun, 'setShadowSamples'):
                sun.setShadowSamples(4)  # Menos amostras = mais suave/menos detalhado

            # Posiciona a luz direcional com ângulo mais elevado
            sun_np = scene_root.attachNewNode(sun)
            sun_np.setHpr(45, -75, 0)  # Ângulo mais alto para sombras menos pronunciadas
            scene_root.setLight(sun_np)

            # 3. Luz de preenchimento para reduzir dureza das sombras (NOVA)
            fill = DirectionalLight("fill_light")
            fill.setColor(Vec4(0.5, 0.5, 0.6, 1))  # Luz azulada suave
            fill_np = scene_root.attachNewNode(fill)
            fill_np.setHpr(-135, -35, 0)  # Direção oposta à luz principal
            scene_root.setLight(fill_np)

            # 4. Luz spotlight no teto com posicionamento melhorado
            from src.core.config import ROOM_SIZE
            width, length, height = ROOM_SIZE

            ceiling_light = Spotlight("ceiling_light")
            ceiling_light.setColor(Vec4(1.0, 0.95, 0.9, 1))

            # Configura o cone de luz para ser mais amplo
            lens = PerspectiveLens()
            lens.setFov(120)  # Ângulo maior (era 100)
            ceiling_light.setLens(lens)
            ceiling_light.setAttenuation(Vec3(1.0, 0.02, 0.002))  # Menor atenuação = mais alcance

            # Ativa sombras para o spotlight, mas com suavidade
            ceiling_light.setShadowCaster(True)
            ceiling_light.setScene(scene_root)
            ceiling_light.setShadowMapSize(shadow_map_size // 2)  # Menor resolução = sombras mais suaves

            if hasattr(ceiling_light, 'setShadowSoftness'):
                ceiling_light.setShadowSoftness(0.05)

            # CORREÇÃO IMPORTANTE: Posiciona o spotlight mais abaixo do teto
            ceiling_light_np = scene_root.attachNewNode(ceiling_light)
            ceiling_light_np.setPos(0, 0, height - 0.6)  # 60cm abaixo do teto em vez de apenas 10cm
            ceiling_light_np.setP(-90)  # Apontando para baixo
            scene_root.setLight(ceiling_light_np)

            # 5. Luzes pontuais adicionais para melhorar a iluminação geral
            from panda3d.core import PointLight

            # Luz de canto 1
            corner_light1 = PointLight("corner_light1")
            corner_light1.setColor(Vec4(0.7, 0.7, 0.3, 1))
            corner_light1.setAttenuation(Vec3(1.0, 0.03, 0.003))
            corner_light1_np = scene_root.attachNewNode(corner_light1)
            corner_light1_np.setPos(width / 3, length / 3, height / 2)
            scene_root.setLight(corner_light1_np)

            # Luz de canto 2
            corner_light2 = PointLight("corner_light2")
            corner_light2.setColor(Vec4(0.5, 0.4, 0.7, 1))
            corner_light2.setAttenuation(Vec3(1.0, 0.03, 0.003))
            corner_light2_np = scene_root.attachNewNode(corner_light2)
            corner_light2_np.setPos(-width / 3, -length / 3, height / 2)
            scene_root.setLight(corner_light2_np)

            # Luz de piso para iluminar a área central de baixo para cima
            floor_light = PointLight("floor_light")
            floor_light.setColor(Vec4(0.6, 0.6, 0.7, 1))
            floor_light.setAttenuation(Vec3(1.0, 0.04, 0.004))
            floor_light_np = scene_root.attachNewNode(floor_light)
            floor_light_np.setPos(0, 0, 1.0)  # 1 metro acima do chão
            scene_root.setLight(floor_light_np)

            # Armazena referências para as luzes
            self._shadow_lights = {
                "ambient": ambient_np,
                "sun": sun_np,
                "fill": fill_np,
                "ceiling": ceiling_light_np,
                "corner1": corner_light1_np,
                "corner2": corner_light2_np,
                "floor": floor_light_np
            }

            # IMPORTANTE: Usar o método centralizado para configurar sombras
            self._configure_shadows_for_entities()

            print("Sistema de sombras básicas otimizado ativado com sucesso!")

        except Exception as e:
            print(f"ERRO ao ativar sombras otimizadas: {e}")
            print("Continuando sem sombras...")

    # --------------------------------------------------------------------------
    # GameApp::load_phase1_scene
    # --------------------------------------------------------------------------

    def load_phase1_scene(self) -> None:
        """Carrega a cena da Fase 1 (movimento e colisões) com iluminação básica."""
        self._scene_manager.load_scene("phase1")

        # cria a sala, caixas, etc.
        self._create_room_new()

        # --- NPC – sem posição explícita: ele escolhe ponto livre ---
        npc = NPC(self._show_base, self._player, self._static_objects)
        npc.setup(self._scene_manager.root_node)  # sem posição → spawn interno seguro
        self._scene_manager.add_entity(npc)
        if self._collision_system:
            self._collision_system.add_entity(npc)
        self._npcs.append(npc)
        print(f"NPC-enxame criado em {npc.node_path.getPos()}")

        # jogador
        self._player = Player(self._show_base)
        self._player.setup(self._scene_manager.root_node, position=(0, 0, 0))
        self._scene_manager.add_entity(self._player)
        self._movement_system.initialize(self._player)

        # Configura iluminação simples (sem tentar usar sombras avançadas)
        try:
            # SUBSTITUIR por iluminação básica que funciona em qualquer versão do Panda3D
            self._setup_basic_lighting()
        except Exception as e:
            print(f"Erro ao configurar iluminação básica: {e}")
            # Sistema super simples de fallback como último recurso
            self._setup_fallback_lighting()

        if self._debug_overlay:
            self._debug_overlay.initialize(self._player)

        print("Fase 1 carregada com sucesso")

    def _setup_fallback_lighting(self):
        """
        Sistema de iluminação mínimo para garantir visibilidade básica
        caso todos os outros sistemas falhem.
        """
        try:
            from panda3d.core import AmbientLight, DirectionalLight
            from panda3d.core import Vec4

            # Luz ambiente forte
            alight = AmbientLight('ambient')
            alight.setColor(Vec4(0.7, 0.7, 0.7, 1))  # Luz ambiente bem forte

            alnp = self._scene_manager.root_node.attachNewNode(alight)
            self._scene_manager.root_node.setLight(alnp)

            # Luz direcional simples
            dlight = DirectionalLight('dlight')
            dlight.setColor(Vec4(0.9, 0.9, 0.9, 1))  # Branco

            dlnp = self._scene_manager.root_node.attachNewNode(dlight)
            dlnp.setHpr(0, -60, 0)  # De cima para baixo
            self._scene_manager.root_node.setLight(dlnp)

            # Guarda referências
            self._lights = {
                "ambient": alnp,
                "main": dlnp
            }

            print("Sistema de iluminação fallback configurado")
        except Exception as e:
            print(f"ERRO CRÍTICO: Falha total no sistema de iluminação: {e}")


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


    def _setup_basic_lighting(self) -> None:
        """
         Configura iluminação básica compatível com qualquer versão do Panda3D.
         Sem depender de funcionalidades de sombra avançadas.
         """
        from panda3d.core import AmbientLight, DirectionalLight, PointLight
        from panda3d.core import Vec4, Vec3

        root = self._scene_manager.root_node

        # Luz ambiente forte para garantir visibilidade básica
        ambient = AmbientLight("ambient")
        ambient.setColor(Vec4(0.6, 0.6, 0.65, 1))  # Luz ambiente bastante intensa
        ambient_np = root.attachNewNode(ambient)
        root.setLight(ambient_np)

        # Luz direcional principal
        sun = DirectionalLight("sun")
        sun.setColor(Vec4(0.9, 0.9, 0.8, 1))  # Luz branca/amarelada
        sun_np = root.attachNewNode(sun)
        sun_np.setHpr(45, -60, 0)  # Ângulo que simula sol
        root.setLight(sun_np)

        # Luz direcional secundária (para preencher sombras)
        fill = DirectionalLight("fill")
        fill.setColor(Vec4(0.6, 0.6, 0.8, 1))  # Tom azulado suave
        fill_np = root.attachNewNode(fill)
        fill_np.setHpr(-120, -30, 0)  # Direção oposta à luz principal
        root.setLight(fill_np)

        # Luz central para iluminar o meio da sala
        width, length, height = ROOM_SIZE
        central_light = PointLight("central_light")
        central_light.setColor(Vec4(1.0, 0.98, 0.9, 1))  # Branco levemente amarelado

        # Atenuação mais suave para maior alcance
        central_light.setAttenuation(Vec3(1.0, 0.005, 0.0))

        central_light_np = root.attachNewNode(central_light)
        central_light_np.setPos(0, 0, height * 0.75)  # Posicionada a 75% da altura da sala
        root.setLight(central_light_np)

        # Luzes das extremidades para iluminar os cantos
        corner1 = PointLight("corner1")
        corner1.setColor(Vec4(0.8, 0.7, 0.6, 1))  # Amarelada
        corner1.setAttenuation(Vec3(1.0, 0.007, 0.0001))
        corner1_np = root.attachNewNode(corner1)
        corner1_np.setPos(width * 0.4, length * 0.4, height * 0.5)
        root.setLight(corner1_np)

        corner2 = PointLight("corner2")
        corner2.setColor(Vec4(0.6, 0.6, 0.9, 1))  # Azulada
        corner2.setAttenuation(Vec3(1.0, 0.007, 0.0001))
        corner2_np = root.attachNewNode(corner2)
        corner2_np.setPos(-width * 0.4, -length * 0.4, height * 0.5)
        root.setLight(corner2_np)

        # Armazena referências às luzes
        self._lights = {
            "ambient": ambient_np,
            "sun": sun_np,
            "fill": fill_np,
            "central": central_light_np,
            "corner1": corner1_np,
            "corner2": corner2_np
        }

        # Configura materiais para todos os objetos
        self._apply_materials_to_scene()

        print("Sistema de iluminação básica configurado com sucesso")


    # Modificações no método update_systems do GameApp
    # --------------------------------------------------------------------------
    # GameApp::update_systems
    # --------------------------------------------------------------------------
    def update_systems(self, dt: float) -> None:
        """Atualiza todos os sistemas e entidades por frame."""
        if self._input_manager:
            self._input_manager.update()

        if self._movement_system:
            self._movement_system.update(dt)
        if self._collision_system:
            self._collision_system.update(dt)

        if self._debug_overlay:
            self._debug_overlay.update(dt)

        if self._player:
            self._player.update(dt)

        for npc in self._npcs:
            npc.update(dt)

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

    def _configure_shadows_for_entities(self) -> None:
        """
        Configura explicitamente as propriedades de sombra para todas as entidades na cena.
        Isso garante que as sombras sejam renderizadas corretamente.
        """
        print("Configurando propriedades de sombra para entidades...")

        try:
            # Configura objetos estáticos para receber/projetar sombras
            for entity in self._static_objects:
                if not entity.node_path:
                    continue

                if "Wall" in entity.name or "wall" in entity.name.lower():
                    # Paredes recebem sombras mas não projetam
                    self._set_shadow_properties(entity.node_path, cast_shadow=False, receive_shadow=True)

                elif "Floor" in entity.name or "floor" in entity.name.lower():
                    # Piso recebe sombras fortemente mas não projeta
                    self._set_shadow_properties(entity.node_path, cast_shadow=False, receive_shadow=True,
                                                shadow_intensity=1.0)

                elif "Ceiling" in entity.name or "ceiling" in entity.name.lower():
                    # Teto recebe sombras mas não projeta
                    self._set_shadow_properties(entity.node_path, cast_shadow=False, receive_shadow=True)

                elif "Box" in entity.name or "box" in entity.name.lower():
                    # Caixas projetam e recebem sombras
                    self._set_shadow_properties(entity.node_path, cast_shadow=True, receive_shadow=True)

            # Configura o jogador para projetar sombras
            if self._player and self._player.node_path:
                self._set_shadow_properties(self._player.node_path, cast_shadow=True, receive_shadow=True)

                # Também configura a câmera do jogador para não projetar sombras
                if hasattr(self._player, 'camera_node') and self._player.camera_node:
                    self._set_shadow_properties(self._player.camera_node, cast_shadow=False, receive_shadow=False)

            # Agora, vamos garantir que todas as luzes tenham as opções de sombra configuradas
            if hasattr(self, '_lights'):
                for light_name, light_np in self._lights.items():
                    if light_name in ['sun', 'ceiling']:  # Apenas estas luzes projetam sombras
                        if hasattr(light_np.node(), 'setShadowCaster'):
                            light_np.node().setShadowCaster(True)

                        # Ajustar qualidade das sombras
                        if hasattr(light_np.node(), 'setShadowSoftness'):
                            light_np.node().setShadowSoftness(0.03)  # Sombras mais suaves

            print("Propriedades de sombra configuradas com sucesso!")

        except Exception as e:
            print(f"Erro ao configurar propriedades de sombra: {e}")

    def _set_shadow_properties(self, node_path, cast_shadow=True, receive_shadow=True, shadow_intensity=0.7):
        """
        Define as propriedades de sombra para um NodePath.

        Args:
            node_path: O NodePath a configurar
            cast_shadow: Se o objeto projeta sombras
            receive_shadow: Se o objeto recebe sombras
            shadow_intensity: Intensidade das sombras (0.0 a 1.0)
        """
        if not node_path:
            return

        try:
            # Configurações recomendadas do Panda3D para sombras
            node_path.setShaderInput("receiveShadow", receive_shadow)
            node_path.setShaderInput("castShadow", cast_shadow)
            node_path.setShaderInput("shadowIntensity", shadow_intensity)

            # Garantir que o shader automático está ativado para este nó
            node_path.setShaderAuto()

            # Se for receber sombras, garantir que o material está configurado corretamente
            if receive_shadow:
                from panda3d.core import Material

                # Se já tem material, apenas ajustamos
                material = node_path.getMaterial()
                if not material:
                    # Cria um novo material
                    material = Material()
                    material.setAmbient((0.8, 0.8, 0.8, 1))
                    material.setDiffuse((1.0, 1.0, 1.0, 1))
                    material.setSpecular((0.3, 0.3, 0.3, 1))
                    material.setShininess(20)
                    node_path.setMaterial(material)
        except Exception as e:
            print(f"Erro ao definir propriedades de sombra: {e}")


    def _apply_materials_to_scene(self):
        """Aplica materiais básicos aos objetos para melhorar sua aparência com iluminação"""
        from panda3d.core import Material

        # Percorre todas as entidades na cena
        for entity in self._scene_manager.get_entities():
            if not entity.node_path:
                continue

            # Cria material base
            material = Material()

            # Paredes
            if "Wall" in entity.name or "wall" in entity.name.lower():
                material.setAmbient((0.6, 0.6, 0.6, 1))
                material.setDiffuse((0.9, 0.9, 0.9, 1))
                material.setSpecular((0.1, 0.1, 0.1, 1))
                material.setShininess(5)  # Pouco brilho
                entity.node_path.setMaterial(material)

            # Piso
            elif "Floor" in entity.name or "floor" in entity.name.lower():
                material.setAmbient((0.5, 0.5, 0.5, 1))
                material.setDiffuse((0.8, 0.8, 0.8, 1))
                material.setSpecular((0.3, 0.3, 0.3, 1))
                material.setShininess(15)  # Brilho médio
                entity.node_path.setMaterial(material)

            # Teto
            elif "Ceiling" in entity.name or "ceiling" in entity.name.lower():
                material.setAmbient((0.5, 0.5, 0.6, 1))  # Tom levemente azulado
                material.setDiffuse((0.7, 0.7, 0.8, 1))
                material.setSpecular((0.2, 0.2, 0.2, 1))
                material.setShininess(10)
                entity.node_path.setMaterial(material)

            # Caixas
            elif "Box" in entity.name or "box" in entity.name.lower():
                material.setAmbient((0.4, 0.25, 0.1, 1))  # Tom marrom
                material.setDiffuse((0.7, 0.4, 0.2, 1))
                material.setSpecular((0.2, 0.2, 0.2, 1))
                material.setShininess(20)  # Mais brilhante
                entity.node_path.setMaterial(material)

            # NPC
            elif "NPC" in entity.name or "Particle" in entity.name:
                # Material luminoso para o NPC
                material.setAmbient((0.7, 0.7, 0.9, 1))  # Azulado brilhante
                material.setDiffuse((1.0, 1.0, 1.0, 1))  # Branco intenso
                material.setEmission((0.2, 0.2, 0.5, 1))  # Emissão azulada - luz própria!
                material.setSpecular((1.0, 1.0, 1.0, 1))  # Reflexo intenso
                material.setShininess(100)  # Muito brilhante
                entity.node_path.setMaterial(material)