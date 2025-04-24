from __future__ import annotations
import math, random
from typing import List, Optional, Tuple, Dict

from panda3d.core import (
    Vec3, Vec4, Point3, Quat, LVecBase3f, LVecBase4f,
    CollisionBox, CollisionNode, CollisionHandlerPusher, CollisionTraverser,
    BitMask32, TransparencyAttrib, ColorBlendAttrib, AmbientLight,
    LVector3f, LineSegs, CollisionSegment, CardMaker, NodePath,
    PandaNode, OccluderNode, CullBinAttrib, CullFaceAttrib
)
from direct.particles.ParticleEffect import ParticleEffect
from direct.particles.Particles import Particles
from direct.showbase.Audio3DManager import Audio3DManager
from direct.interval.IntervalGlobal import Sequence, LerpColorScaleInterval, Wait, Func, LerpHprInterval, Parallel

from src.entities.entity import Entity
from src.entities.components.transform_component import TransformComponent
from src.entities.components.collider_component import ColliderComponent
from src.utils.event_bus import EventBus
from src.utils.service_locator import ServiceLocator
from src.services.interfaces.i_audio_service import IAudioService
from src.core.config import ROOM_SIZE, WALL_THICKNESS

# ───────── CONFIG ─────────
NPC_SIZE = Vec3(1.8, 1.8, 1.8)  # Dimensões da hitbox
NPC_RADIUS = NPC_SIZE.x / 2  # Raio de colisão
NPC_SPEED = 1.5  # Velocidade de movimento
NPC_WALK_INTERVAL = (1.5, 3.0)  # Intervalo entre mudanças de direção
NPC_SAFE_DISTANCE = 2.5  # Distância mínima do jogador
NPC_TELEPORT_ATTEMPTS = 30  # Tentativas de encontrar posição de teleporte
SFX_PATH = "assets/sounds/npc_whisper.wav"  # Som do NPC
NPC_DETECTION_RADIUS = 20.0  # Raio no qual o NPC detecta o jogador
NPC_STALKING_DISTANCE = 10.0  # Distância para começar a perseguir o jogador
NPC_FLEE_THRESHOLD = 8.0  # Distância em que o NPC foge se o jogador olhar para ele
NPC_AWARENESS_TIME = 3.0  # Tempo para o NPC perceber que está sendo observado
NPC_PARTICLE_COUNT = 750  # Número de partículas no efeito
NPC_HALO_SIZE = 0.35  # Tamanho do halo ao redor do NPC
NPC_SOUND_RANGE = 35.0  # Alcance do som 3D (aumentado)

# Margem para manter distância segura de paredes - MUITO MAIOR para evitar escape
_MARGIN = WALL_THICKNESS + NPC_RADIUS + 1.0  # Margem ampliada


# ──────────────────────────


class NPC(Entity):
    """Entidade espectral com face fantasmagórica e comportamento avançado."""

    # ──────────────────────── INICIALIZAÇÃO ────────────────────────
    def __init__(self, show_base, player: Optional[Entity], static_objs: List[Entity]):
        """Inicializa o NPC com referências para o sistema de jogo e outros objetos."""
        super().__init__(name="SpectralEntityNPC")
        self._show_base = show_base
        self._player = player
        self._static_objects = static_objs

        # Movimento e comportamento
        self._velocity = Vec3(0)
        self._walk_timer = random.uniform(*NPC_WALK_INTERVAL)
        self._behavior_state = "wander"  # Estados: "wander", "stalk", "flee", "teleport"
        self._state_timer = 0.0
        self._player_awareness = 0.0  # 0 a 1, representa o quanto o NPC percebe que está sendo observado
        self._facing_direction = Vec3(0, 1, 0)  # Direção inicial para onde a face aponta

        # Memória de posições e obstáculos
        self._position_history = []
        self._max_history = 15
        self._obstacle_memory: Dict[Tuple[int, int], float] = {}
        self._obstacle_memory_lifetime = 5.0
        self._box_check_cache = {}
        self._box_check_cache_lifetime = 1.0

        # Face e expressões
        self._face_node = None
        self._left_eye = None
        self._right_eye = None
        self._face_mood = "neutral"  # Estados: "neutral", "angry", "scared", "curious"
        self._expression_timer = 0.0
        self._expression_change_interval = random.uniform(3.0, 8.0)  # Tempo entre mudanças de expressão
        self._eye_animations = {}

        # Colisão e física
        self._pusher: Optional[CollisionHandlerPusher] = None
        self._collider_np = None
        self._boundary_check_timer = 0.0
        self._boundary_check_interval = 0.2  # Verificar limites 5x por segundo

        # Efeitos visuais e sonoros
        self._effect: Optional[ParticleEffect] = None
        self._sound = None
        self._audio3d = None
        self._halo_effect = None
        self._inner_halo = None
        self._pulse_sequence = None
        self._inner_pulse_sequence = None
        self._glow_intensity = 0.0
        self._color_shift_timer = 0.0
        self._face_opacity = 0.85  # Opacidade padrão da face

        # Comportamentos avançados
        self._last_known_player_pos = Vec3(0, 0, 0)
        self._path_points = []
        self._current_path_index = 0
        self._blocked_timer = 0.0
        self._event_bus = EventBus()

        # Grade de ocupação da sala para navegação espacial
        self._build_room_occupancy_grid()

        # Limites da sala (75% do tamanho total para segurança)
        half_w, half_l, _ = ROOM_SIZE
        self._room_limits = {
            'xmin': -half_w * 0.5,
            'xmax': half_w * 0.5,
            'ymin': -half_l * 0.5,
            'ymax': half_l * 0.5
        }

    def _build_room_occupancy_grid(self):
        """Constrói uma grade para navegação eficiente e verificação espacial."""
        half_w, half_l, _ = ROOM_SIZE
        grid_size = 1.0  # Tamanho de cada célula da grade em unidades do mundo

        # Calcula o número de células em cada direção
        width_cells = int(2 * half_w / grid_size) + 1
        length_cells = int(2 * half_l / grid_size) + 1

        # Inicializa a grade com zeros (livres)
        self._occupancy_grid = [[0 for _ in range(length_cells)] for _ in range(width_cells)]
        self._grid_size = grid_size
        self._grid_origin = (-half_w, -half_l)

        # Pré-marque as paredes e bordas da sala
        border_cells = 2  # Células a marcar como parede nas bordas

        # Marca bordas como ocupadas (1)
        for x in range(width_cells):
            for b in range(border_cells):
                if b < length_cells:
                    self._occupancy_grid[x][b] = 1  # Parede sul
                if length_cells - 1 - b < length_cells:
                    self._occupancy_grid[x][length_cells - 1 - b] = 1  # Parede norte

        for y in range(length_cells):
            for b in range(border_cells):
                if b < width_cells:
                    self._occupancy_grid[b][y] = 1  # Parede oeste
                if width_cells - 1 - b < width_cells:
                    self._occupancy_grid[width_cells - 1 - b][y] = 1  # Parede leste

    # ────────── Encontra ponto seguro dentro da sala ──────────

    def _find_spawn_point(self) -> Vec3:
        """Encontra um ponto seguro dentro da sala, longe do jogador e objetos."""
        # Usa 60% do espaço interno para garantir folga MAIOR das paredes
        half_w, half_l, _ = ROOM_SIZE
        xmin, xmax = -half_w * 0.6, half_w * 0.6  # Reduzido para 60%
        ymin, ymax = -half_l * 0.6, half_l * 0.6  # Reduzido para 60%

        # Obtém posição do jogador para manter distância
        player_pos = Vec3(0, 0, 0)
        if self._player and self._player.node_path:
            player_pos = self._player.node_path.getPos(self._show_base.render)

        # Realiza várias tentativas de encontrar um ponto adequado
        for _ in range(200):
            x, y = random.uniform(xmin, xmax), random.uniform(ymin, ymax)
            dist_to_player = math.sqrt((x - player_pos.x) ** 2 + (y - player_pos.y) ** 2)

            # Verifica se está longe do jogador e não dentro de caixas
            if dist_to_player > NPC_SAFE_DISTANCE * 2 and not self._inside_any_box(x, y):
                # Posiciona NPC com sua base no chão
                return Vec3(x, y, NPC_SIZE.z / 2)

        # Alternativa: tenta pontos em cantos específicos da sala
        corners = [
            (xmin + NPC_RADIUS * 2, ymin + NPC_RADIUS * 2),  # Sudoeste
            (xmin + NPC_RADIUS * 2, ymax - NPC_RADIUS * 2),  # Noroeste
            (xmax - NPC_RADIUS * 2, ymin + NPC_RADIUS * 2),  # Sudeste
            (xmax - NPC_RADIUS * 2, ymax - NPC_RADIUS * 2),  # Nordeste
        ]

        for x, y in corners:
            if not self._inside_any_box(x, y):
                return Vec3(x, y, NPC_SIZE.z / 2)

        # Último recurso: centro da sala com deslocamento aleatório
        return Vec3(
            random.uniform(-half_w * 0.3, half_w * 0.3),
            random.uniform(-half_l * 0.3, half_l * 0.3),
            NPC_SIZE.z / 2
        )

    # ──────────────────────── CONFIGURAÇÃO ────────────────────────
    def setup(self, parent, position: Optional[Tuple[float, float, float] | Vec3] = None):
        """Configura o NPC, inicializando seus componentes e efeitos visuais."""
        # 1. Determina posição inicial válida
        if position is None:
            pos = self._find_spawn_point()
        else:
            pos = Vec3(*position)
            half_w, half_l, _ = ROOM_SIZE
            # Verifica se a posição solicitada é válida - MAIS RESTRITIVA
            safe_w = half_w * 0.6  # Reduzido para 60% para maior segurança
            safe_l = half_l * 0.6
            if (
                    abs(pos.x) > safe_w or
                    abs(pos.y) > safe_l or
                    self._inside_any_box(pos.x, pos.y)
            ):
                print("[NPC] Posição solicitada fora dos limites ou em colisão – gerando spawn seguro.")
                pos = self._find_spawn_point()

        # 2. Inicializa NodePath e componentes
        self.init_node_path(parent)

        self._transform = TransformComponent(position=pos)
        self.add_component(self._transform)

        # Componente de colisão ligeiramente menor que o tamanho visual
        collision_size = Vec3(NPC_SIZE.x * 0.9, NPC_SIZE.y * 0.9, NPC_SIZE.z * 0.9)
        self.add_component(
            ColliderComponent(
                shape_type="box",
                dimensions=tuple(collision_size / 2),
                mass=60.0,
                is_character=False,
            )
        )

        # 3. Configura colisão Panda3D para detecção precisa
        hx, hy, hz = collision_size / 2
        cnode = CollisionNode(f"{self.name}_collision")
        cnode.addSolid(CollisionBox(Point3(0, 0, 0), hx, hy, hz))
        cnode.setIntoCollideMask(BitMask32.bit(0))
        cnode.setFromCollideMask(BitMask32.bit(0))
        self._collider_np = self.node_path.attachNewNode(cnode)

        # Configura o sistema de colisão e empurrão
        self._pusher = CollisionHandlerPusher()
        self._pusher.addCollider(self._collider_np, self.node_path)

        # Obtém ou cria o traverser de colisão global
        trav = getattr(self._show_base, "cTrav", None)
        if not isinstance(trav, CollisionTraverser):
            trav = CollisionTraverser("GlobalTraverser")
            self._show_base.cTrav = trav
        trav.addCollider(self._collider_np, self._pusher)

        # 4. Configura elementos visuais
        self._setup_particle_effect()
        self._setup_spatial_sound()
        self._setup_halo_effect()
        self._setup_face_and_eyes()
        self._setup_pulse_sequence()

        # 5. Configura oclusor para prevenir "wallhack" com brilho/halos
        self._setup_occlusion()

        # 6. Posiciona na cena
        self.node_path.setPos(pos)

        # 7. Registra para eventos do sistema
        self._event_bus.subscribe("on_player_teleported", self._on_player_teleported)

        print(f"[NPC] Espectro com rosto inicializado em ({pos.x:.1f}, {pos.y:.1f}, {pos.z:.1f})")

    def _setup_fake_shadow(self):
        """Cria uma sombra falsa sob o NPC para dar impressão de 3D."""
        try:
            from panda3d.core import CardMaker, TransparencyAttrib

            # Cria um disco achatado para parecer uma sombra
            cm = CardMaker('npc_shadow')
            shadow_size = NPC_SIZE.x * 1.2  # Um pouco maior que o NPC
            cm.setFrame(-shadow_size / 2, shadow_size / 2, -shadow_size / 2, shadow_size / 2)

            # Cria e configura o nó da sombra
            self._shadow = self.node_path.attachNewNode(cm.generate())
            self._shadow.setP(-90)  # Gira para ficar horizontal (plano XY)
            self._shadow.setPos(0, 0, -NPC_SIZE.z / 2 + 0.02)  # Posiciona um pouco acima do chão
            self._shadow.setTransparency(TransparencyAttrib.M_alpha)
            self._shadow.setColor(0, 0, 0, 0.3)  # Preto com alfa baixo
            self._shadow.setBin("transparent", 0)  # Garante ordem de renderização
            self._shadow.setDepthWrite(False)
            self._shadow.setDepthTest(True)

            # Escala elíptica para parecer uma sombra real projetada no chão
            self._shadow.setScale(1.0, 0.6, 1.0)

            # Configuração para pulsar a sombra sutilmente
            from direct.interval.IntervalGlobal import Sequence, LerpColorScaleInterval
            self._shadow_pulse = Sequence(
                LerpColorScaleInterval(self._shadow, 2.0,
                                       Vec4(1.0, 1.0, 1.0, 0.25),
                                       startColorScale=Vec4(1.0, 1.0, 1.0, 0.15)),
                LerpColorScaleInterval(self._shadow, 2.0,
                                       Vec4(1.0, 1.0, 1.0, 0.15),
                                       startColorScale=Vec4(1.0, 1.0, 1.0, 0.25))
            )
            self._shadow_pulse.loop()
        except Exception as e:
            print(f"[NPC] Erro ao criar sombra falsa: {e}")
            self._shadow = None

    def _setup_occlusion(self):
        """Configura oclusão para evitar que o brilho seja visível através das paredes."""
        # IMPORTANTE: Configura corretamente o CullBin para respeitar a oclusão
        self.node_path.setBin("opaque", 10)  # Bin que respeita a oclusão
        self.node_path.setDepthTest(True)  # Ativa teste de profundidade
        self.node_path.setDepthWrite(True)  # Escreve no buffer de profundidade

        # Se estiver usando halos, configura-os para oclusão correta
        if self._halo_effect:
            self._halo_effect.setBin("transparent", 20)
            self._halo_effect.setDepthTest(True)
            self._halo_effect.setDepthWrite(False)  # Não escreve no buffer, mas testa

        if hasattr(self, '_inner_halo') and self._inner_halo:
            self._inner_halo.setBin("transparent", 21)
            self._inner_halo.setDepthTest(True)
            self._inner_halo.setDepthWrite(False)

        # Configura partículas para respeitar oclusão
        try:
            for p_name in ["core", "mid_layer", "outer_aura"]:
                p = self._effect.getParticlesNamed(p_name)
                if p and hasattr(p, 'setBin'):
                    p.setBin("transparent", 20)
        except:
            pass

    def _setup_face_and_eyes(self):
        """Cria a face fantasmagórica com olhos expressivos."""
        # 1. Cria o nó para a face
        face_size = NPC_SIZE.x * 0.8  # Tamanho da face, proporcionalmente ao NPC

        # Face principal (plano quadrado)
        cm = CardMaker("npc_face")
        cm.setFrame(-face_size / 2, face_size / 2, -face_size / 2, face_size / 2)
        self._face_node = self.node_path.attachNewNode(cm.generate())
        self._face_node.setTransparency(TransparencyAttrib.MAlpha)
        self._face_node.setColor(0.85, 0.9, 1.0, self._face_opacity)  # Azulado translúcido
        self._face_node.setBillboardPointEye()  # Face sempre olha para a câmera
        self._face_node.setPos(0, 0.2, 0)  # Ligeiramente à frente do centro

        # Adiciona profundidade visual com blend aditivo suave
        try:
            self._face_node.setAttrib(ColorBlendAttrib.make(
                ColorBlendAttrib.MAdd,
                ColorBlendAttrib.OIncomingAlpha,
                ColorBlendAttrib.OOne))
        except:
            pass

        # 2. Cria os olhos como cubos pretos
        eye_size = face_size * 0.15  # Tamanho dos olhos proporcionais à face
        eye_spacing = face_size * 0.25  # Espaçamento entre os olhos

        # Olho esquerdo
        left_eye_pos = Point3(-eye_spacing, 0.05, face_size * 0.1)  # Posição lateral e altura
        self._left_eye = self._create_eye(eye_size, left_eye_pos)

        # Olho direito
        right_eye_pos = Point3(eye_spacing, 0.05, face_size * 0.1)  # Posição lateral e altura
        self._right_eye = self._create_eye(eye_size, right_eye_pos)

        # 3. Configura animações de expressão
        self._setup_eye_animations()

    def _create_eye(self, size, position):
        """Creates an eye as a solid, opaque black cube."""
        # Create a node for the eye
        eye = self._face_node.attachNewNode("eye_node")
        eye.setPos(position)

        # Create a cube using 6 cards for each face
        half_size = size / 2

        # Define the 6 faces of a cube (front, back, left, right, top, bottom)
        faces = [
            # Front face (facing camera)
            {"name": "front", "pos": (0, half_size, 0), "hpr": (0, 0, 0)},
            # Back face
            {"name": "back", "pos": (0, -half_size, 0), "hpr": (180, 0, 0)},
            # Left face
            {"name": "left", "pos": (-half_size, 0, 0), "hpr": (270, 0, 0)},
            # Right face
            {"name": "right", "pos": (half_size, 0, 0), "hpr": (90, 0, 0)},
            # Top face
            {"name": "top", "pos": (0, 0, half_size), "hpr": (0, 90, 0)},
            # Bottom face
            {"name": "bottom", "pos": (0, 0, -half_size), "hpr": (0, -90, 0)}
        ]

        # Create each face of the cube
        for face in faces:
            cm = CardMaker(f"eye_{face['name']}")
            cm.setFrame(-half_size, half_size, -half_size, half_size)
            # Use uv_range_cube for proper cube mapping
            cm.set_uv_range_cube(faces.index(face))

            face_np = eye.attachNewNode(cm.generate())
            face_np.setPos(*face["pos"])
            face_np.setHpr(*face["hpr"])
            face_np.setColor(0, 0, 0, 1.0)  # Fully opaque black
            # Ensure depth writing for solidity
            face_np.setDepthWrite(True)
            face_np.setDepthTest(True)

        # Make the eye rotate to face the camera
        eye.setBillboardPointEye()

        # Disable transparency since we want opaque cubes
        eye.clearTransparency()

        return eye
    def _setup_eye_animations(self):
        """Configura diferentes animações para os olhos baseadas no estado emocional."""
        # Expressão neutra (olhos padrão)
        neutral_seq = Sequence(
            Wait(0.1)  # Placeholder, apenas mantém os olhos na posição padrão
        )

        # Expressão assustada (olhos mais abertos)
        scared_seq = Sequence(
            LerpColorScaleInterval(self._left_eye, 0.2, Vec4(1.3, 1.3, 1.3, 1)),  # Aumenta escala
            LerpColorScaleInterval(self._right_eye, 0.2, Vec4(1.3, 1.3, 1.3, 1)),
            Wait(0.3),
            LerpColorScaleInterval(self._left_eye, 0.2, Vec4(1.0, 1.0, 1.0, 1)),  # Normaliza escala
            LerpColorScaleInterval(self._right_eye, 0.2, Vec4(1.0, 1.0, 1.0, 1))
        )

        # Expressão de raiva (olhos inclinados para baixo no centro)
        angry_seq = Sequence(
            Parallel(
                LerpHprInterval(self._left_eye, 0.3, Vec3(0, 0, 15)),  # Rotação
                LerpHprInterval(self._right_eye, 0.3, Vec3(0, 0, -15))
            ),
            Wait(0.5),
            Parallel(
                LerpHprInterval(self._left_eye, 0.3, Vec3(0, 0, 0)),  # Retorna
                LerpHprInterval(self._right_eye, 0.3, Vec3(0, 0, 0))
            )
        )

        # Expressão curiosa (olhos mais próximos e inclinados)
        curious_seq = Sequence(
            Parallel(
                LerpHprInterval(self._left_eye, 0.3, Vec3(0, 15, 0)),  # Pitch
                LerpHprInterval(self._right_eye, 0.3, Vec3(0, 15, 0))
            ),
            Wait(0.4),
            Parallel(
                LerpHprInterval(self._left_eye, 0.3, Vec3(0, 0, 0)),  # Retorna
                LerpHprInterval(self._right_eye, 0.3, Vec3(0, 0, 0))
            )
        )

        # Armazena todas as animações
        self._eye_animations = {
            "neutral": neutral_seq,
            "scared": scared_seq,
            "angry": angry_seq,
            "curious": curious_seq
        }

    def _play_expression(self, mood):
        """Reproduz a animação de expressão correspondente ao humor indicado."""
        if mood in self._eye_animations:
            # Para qualquer animação atual se estiver rodando
            for anim in self._eye_animations.values():
                if anim.isPlaying():
                    anim.finish()

            # Reproduz a nova animação
            self._eye_animations[mood].start()
            self._face_mood = mood

            # Ajusta a cor da face com base no humor
            if mood == "angry":
                self._face_node.setColor(0.9, 0.3, 0.3, self._face_opacity)  # Vermelho agressivo
            elif mood == "scared":
                self._face_node.setColor(0.7, 0.7, 0.9, self._face_opacity)  # Azul pálido
            elif mood == "curious":
                self._face_node.setColor(0.7, 0.9, 1.0, self._face_opacity)  # Azul claro
            else:
                self._face_node.setColor(0.85, 0.9, 1.0, self._face_opacity)  # Padrão azulado

    # ───────────────── Sistema de Partículas ─────────────────
    def _setup_particle_effect(self):
        """Configura o sistema de partículas em camadas para visual espectral impressionante."""
        if not getattr(self._show_base, "physicsMgr", None):
            self._show_base.enableParticles()

        self._effect = ParticleEffect()

        # Sistema de partículas em 3 camadas
        self._setup_core_particles()  # Núcleo central brilhante
        self._setup_mid_particles()  # Camada intermediária
        self._setup_outer_particles()  # Aura exterior difusa

        # Inicia todos os efeitos
        self._effect.start(parent=self.node_path, renderParent=self.node_path)

        # Garante transparência e blend corretos
        self.node_path.setTransparency(TransparencyAttrib.M_alpha)

        # Tenta aplicar blend aditivo para efeito mais brilhante
        try:
            from panda3d.core import ColorBlendAttrib
            self.node_path.setAttrib(
                ColorBlendAttrib.make(
                    ColorBlendAttrib.MAdd,
                    ColorBlendAttrib.OIncomingAlpha,
                    ColorBlendAttrib.OOne,
                )
            )
        except Exception as e:
            # Fallback para versões mais antigas
            print(f"[NPC] Usando modo de blend simplificado: {e}")
            try:
                for p_name in ["core", "mid_layer", "outer_aura"]:
                    particles = self._effect.getParticlesNamed(p_name)
                    if particles:
                        particles.renderer.setColorBlendMode(
                            particles.renderer.CMBAdd,
                            particles.renderer.CMBSrcAlpha,
                            particles.renderer.CMBDstAlpha,
                        )
            except:
                # Último recurso: apenas aumenta o brilho
                self.node_path.setColorScale(1.5, 1.5, 1.5, 1.0)

    def _setup_core_particles(self):
        """Configura o núcleo denso e brilhante de partículas."""
        p = Particles("core")
        p.setFactory("PointParticleFactory")
        p.setRenderer("SpriteParticleRenderer")
        p.setEmitter("SphereVolumeEmitter")  # Emissor esférico para núcleo

        # Configurações básicas
        p.setPoolSize(250)
        p.setBirthRate(0.01)
        p.setLitterSize(15)
        p.setLitterSpread(5)
        p.setSystemLifespan(0.0)
        p.setLocalVelocityFlag(True)
        p.setSystemGrowsOlderFlag(False)

        # Brilho intenso com aparência quase branca
        p.renderer.setAlphaMode(p.renderer.PRALPHAUSER)
        p.renderer.setUserAlpha(0.99)  # Quase totalmente opaco
        p.renderer.setColor(Vec3(0.95, 0.98, 1.0))  # Branco com sutil tom azulado

        # Partículas pequenas para o núcleo denso
        p.renderer.setInitialXScale(0.05)
        p.renderer.setFinalXScale(0.025)
        p.renderer.setInitialYScale(0.05)
        p.renderer.setFinalYScale(0.025)

        # Emissor esférico concentrado
        p.emitter.setRadius(NPC_SIZE.x * 0.25)
        p.emitter.setEmissionType(p.emitter.ETRADIATE)  # Radiação para fora

        # Movimento suave e rápido
        p.factory.setLifespanBase(1.2)
        p.factory.setLifespanSpread(0.4)
        p.factory.setMassBase(0.4)
        p.factory.setMassSpread(0.2)
        p.factory.setTerminalVelocityBase(12.0)

        self._effect.addParticles(p)

    def _setup_mid_particles(self):
        """Configura a camada intermediária de partículas."""
        p = Particles("mid_layer")
        p.setFactory("PointParticleFactory")
        p.setRenderer("SpriteParticleRenderer")
        p.setEmitter("BoxEmitter")

        # Configurações básicas - mais partículas nesta camada
        p.setPoolSize(300)
        p.setBirthRate(0.015)
        p.setLitterSize(20)
        p.setLitterSpread(8)
        p.setSystemLifespan(0.0)
        p.setLocalVelocityFlag(True)
        p.setSystemGrowsOlderFlag(False)

        # Tom azul mais evidente
        p.renderer.setAlphaMode(p.renderer.PRALPHAUSER)
        p.renderer.setUserAlpha(0.85)
        p.renderer.setColor(Vec3(0.7, 0.85, 1.0))  # Azul claro

        # Tamanho médio
        p.renderer.setInitialXScale(0.1)
        p.renderer.setFinalXScale(0.15)
        p.renderer.setInitialYScale(0.1)
        p.renderer.setFinalYScale(0.15)

        # Emissor que cobre a parte central do NPC
        inner_size = NPC_SIZE * 0.7
        hx, hy, hz = inner_size / 2
        p.emitter.setMinBound(Vec3(-hx, -hy, -hz))
        p.emitter.setMaxBound(Vec3(hx, hy, hz))

        # Movimento moderado
        p.emitter.setAmplitude(0.5)
        p.emitter.setAmplitudeSpread(0.2)

        # Vida média
        p.factory.setLifespanBase(2.0)
        p.factory.setLifespanSpread(0.7)

        self._effect.addParticles(p)

    def _setup_outer_particles(self):
        """Configura a aura exterior de partículas difusas."""
        p = Particles("outer_aura")
        p.setFactory("PointParticleFactory")
        p.setRenderer("SpriteParticleRenderer")
        p.setEmitter("BoxEmitter")

        # Menos partículas, mais espaçadas
        p.setPoolSize(200)
        p.setBirthRate(0.02)
        p.setLitterSize(10)
        p.setLitterSpread(5)
        p.setSystemLifespan(0.0)
        p.setLocalVelocityFlag(True)
        p.setSystemGrowsOlderFlag(False)

        # Aura externa mais transparente e azulada
        p.renderer.setAlphaMode(p.renderer.PRALPHAUSER)
        p.renderer.setUserAlpha(0.6)  # Bastante transparente
        p.renderer.setColor(Vec3(0.5, 0.7, 1.0))  # Azul mais intenso

        # Partículas maiores para aura difusa
        p.renderer.setInitialXScale(0.2)
        p.renderer.setFinalXScale(0.4)
        p.renderer.setInitialYScale(0.2)
        p.renderer.setFinalYScale(0.4)

        # Emissor cobre todo o NPC e um pouco além
        outer_size = NPC_SIZE * 1.2
        hx, hy, hz = outer_size / 2
        p.emitter.setMinBound(Vec3(-hx, -hy, -hz))
        p.emitter.setMaxBound(Vec3(hx, hy, hz))

        # Movimento amplo e lento
        p.emitter.setAmplitude(0.8)
        p.emitter.setAmplitudeSpread(0.4)

        # Vida longa para efeito persistente
        p.factory.setLifespanBase(3.5)
        p.factory.setLifespanSpread(1.2)

        self._effect.addParticles(p)

    def _setup_halo_effect(self):
        """Cria halos luminosos de diferentes intensidades ao redor do NPC."""
        try:
            # Halo externo grande e suave
            size_outer = NPC_SIZE.x + NPC_HALO_SIZE * 2.5
            from panda3d.core import CardMaker

            # Halo externo - grande e suave
            cm_outer = CardMaker('outer_halo')
            cm_outer.setFrame(-size_outer / 2, size_outer / 2, -size_outer / 2, size_outer / 2)
            self._halo_effect = self.node_path.attachNewNode(cm_outer.generate())
            self._halo_effect.setBillboardPointEye()
            self._halo_effect.setTransparency(TransparencyAttrib.M_alpha)
            self._halo_effect.setColor(0.5, 0.7, 1.0, 0.4)  # Azul etéreo
            self._halo_effect.setDepthWrite(False)

            # IMPORTANTE: Agora com teste de profundidade ativo
            self._halo_effect.setDepthTest(True)

            # Aplica blend aditivo
            try:
                from panda3d.core import ColorBlendAttrib
                self._halo_effect.setAttrib(ColorBlendAttrib.make(
                    ColorBlendAttrib.MAdd,
                    ColorBlendAttrib.OIncomingAlpha,
                    ColorBlendAttrib.OOne
                ))
            except:
                pass

            # Halo interno - menor e mais intenso
            size_inner = size_outer * 0.55
            cm_inner = CardMaker('inner_halo')
            cm_inner.setFrame(-size_inner / 2, size_inner / 2, -size_inner / 2, size_inner / 2)
            self._inner_halo = self.node_path.attachNewNode(cm_inner.generate())
            self._inner_halo.setBillboardPointEye()
            self._inner_halo.setTransparency(TransparencyAttrib.M_alpha)
            self._inner_halo.setColor(0.8, 0.9, 1.0, 0.6)  # Mais branco e brilhante
            self._inner_halo.setDepthWrite(False)

            # IMPORTANTE: Também ativa teste de profundidade para halo interno
            self._inner_halo.setDepthTest(True)

            try:
                self._inner_halo.setAttrib(ColorBlendAttrib.make(
                    ColorBlendAttrib.MAdd,
                    ColorBlendAttrib.OIncomingAlpha,
                    ColorBlendAttrib.OOne
                ))
            except:
                pass

            # Adiciona iluminação própria nos halos
            ambient = AmbientLight('halo_glow')
            ambient.setColor((0.6, 0.7, 0.9, 1.0))
            ambient_np = self._halo_effect.attachNewNode(ambient)
            self._halo_effect.setLight(ambient_np)
            self._inner_halo.setLight(ambient_np)

        except Exception as e:
            print(f"[NPC] Erro ao criar efeito de halo: {e}")
            self._halo_effect = None
            self._inner_halo = None

    def _setup_pulse_sequence(self):
        """Configura animações de pulsação para os halos."""
        try:
            # Sequência para o halo externo - pulsa lentamente
            if self._halo_effect:
                self._pulse_sequence = Sequence(
                    LerpColorScaleInterval(self._halo_effect, 2.5,
                                           Vec4(1.0, 1.0, 1.0, 0.7),  # Mais brilhante
                                           startColorScale=Vec4(1.0, 1.0, 1.0, 0.3)),  # Mais fraco
                    LerpColorScaleInterval(self._halo_effect, 2.5,
                                           Vec4(1.0, 1.0, 1.0, 0.3),
                                           startColorScale=Vec4(1.0, 1.0, 1.0, 0.7)),
                )
                self._pulse_sequence.loop()

            # Sequência para o halo interno - pulsa mais rápido em contraponto
            if hasattr(self, '_inner_halo') and self._inner_halo:
                self._inner_pulse_sequence = Sequence(
                    LerpColorScaleInterval(self._inner_halo, 1.5,
                                           Vec4(1.0, 1.0, 1.0, 0.9),  # Quase opaco no auge
                                           startColorScale=Vec4(1.0, 1.0, 1.0, 0.4)),  # Mais transparente
                    LerpColorScaleInterval(self._inner_halo, 1.5,
                                           Vec4(1.0, 1.0, 1.0, 0.4),
                                           startColorScale=Vec4(1.0, 1.0, 1.0, 0.9)),
                )
                self._inner_pulse_sequence.loop()

        except Exception as e:
            print(f"[NPC] Erro ao configurar animação de pulsação: {e}")
            self._pulse_sequence = None
            self._inner_pulse_sequence = None

    # ───────────────── Som Espacial 3D ─────────────────
    def _setup_spatial_sound(self):
        """Configura áudio posicional 3D para o NPC com maior alcance."""
        # Obtém o sistema de áudio da engine ou cria um novo
        svc = ServiceLocator().get(IAudioService)
        if svc and hasattr(svc, "audio3d"):
            self._audio3d = svc.audio3d
        else:
            try:
                self._audio3d = Audio3DManager(self._show_base.sfxManagerList[0], self._show_base.camera)
            except Exception as e:
                print(f"[NPC] Erro ao criar Audio3DManager: {e}")
                self._audio3d = None

        # Carrega e configura o som
        try:
            if self._audio3d:
                self._sound = self._audio3d.loadSfx(SFX_PATH)
                if self._sound:
                    self._sound.setLoop(True)
                    self._sound.setVolume(0.85)
                    self._audio3d.attachSoundToObject(self._sound, self.node_path)

                    # MODIFICADO: Aumenta o alcance do som significativamente
                    if hasattr(self._audio3d, 'setDistanceFactor'):
                        self._audio3d.setDistanceFactor(0.5)  # Valor menor = maior alcance

                    # Configura atenuação por distância para som 3D mais realista
                    if hasattr(self._audio3d, 'setDropOffFactor'):
                        self._audio3d.setDropOffFactor(2.0)  # Reduzido para atenuar mais gradualmente

                    # Define alcance máximo maior
                    if hasattr(self._sound, 'setMaxDistance'):
                        self._sound.setMaxDistance(NPC_SOUND_RANGE)

                    self._sound.play()
                    print(f"[NPC] Som 3D configurado com alcance aumentado: {NPC_SOUND_RANGE} unidades")
        except Exception as e:
            print(f"[NPC] Erro ao configurar som 3D: {e}")
            self._sound = None

    # ───────────────── ATUALIZAÇÃO PRINCIPAL ─────────────────
    def update(self, dt: float):
        """Atualiza o comportamento, movimento e efeitos visuais do NPC."""
        super().update(dt)

        # CRÍTICO: Verificação frequente dos limites da sala para garantir contenção
        self._enforce_room_boundaries()

        # Atualiza memória espacial
        self._update_obstacle_memory(dt)

        # Atualiza efeitos visuais com base na proximidade do jogador
        self._update_visual_effects(dt)

        # Detecta se o jogador está olhando para o NPC
        player_looking_at_npc = self._is_player_looking_at_me()

        # Atualiza o nível de percepção do NPC sobre ser observado
        self._update_awareness(dt, player_looking_at_npc)

        # Atualiza expressões faciais
        self._update_face_expressions(dt)

        # Executa o comportamento baseado no estado atual
        if self._behavior_state == "wander":
            self._update_wander_behavior(dt)
        elif self._behavior_state == "stalk":
            self._update_stalk_behavior(dt)
        elif self._behavior_state == "flee":
            self._update_flee_behavior(dt)

        # Verifica se o NPC está bloqueado e precisa teleportar
        if self._velocity.length_squared() > 0 and self._is_stuck():
            self._blocked_timer += dt
            if self._blocked_timer > 2.0:  # Bloqueado por mais de 2 segundos
                self._teleport_away()
                self._blocked_timer = 0.0
        else:
            self._blocked_timer = 0.0

        # Avalia transições de estado com base na distância do jogador
        self._check_state_transition(dt)

        # Atualiza orientação facial para apontar na direção do movimento
        if self._velocity.length_squared() > 0.01:
            self._update_face_orientation(dt)

    def _update_face_expressions(self, dt: float):
        """Atualiza as expressões faciais com base no estado e proximidade do jogador."""
        # Atualiza o timer para mudança de expressão
        self._expression_timer -= dt

        if self._expression_timer <= 0:
            # Determina a nova expressão com base em várias condições
            player_pos = None
            if self._player and self._player.node_path:
                player_pos = self._player.node_path.getPos(self._show_base.render)

            npc_pos = self.node_path.getPos(self._show_base.render)

            # Calcula distância ao jogador
            distance_to_player = 999.0
            if player_pos:
                distance_to_player = (player_pos - npc_pos).length()

            # Escolhe expressão com base no estado e distância
            if self._behavior_state == "flee":
                # Assustado quando fugindo
                self._play_expression("scared")
                mood_duration = random.uniform(1.5, 3.0)
            elif self._behavior_state == "stalk":
                # Curioso quando perseguindo
                if random.random() < 0.7:
                    self._play_expression("curious")
                else:
                    self._play_expression("angry")
                mood_duration = random.uniform(2.0, 4.0)
            else:  # "wander"
                # Varia entre neutro e curioso quando vagando
                if distance_to_player < NPC_DETECTION_RADIUS:
                    # Mais perto do jogador, mais alerta
                    expressions = ["neutral", "curious", "curious"]
                    self._play_expression(random.choice(expressions))
                    mood_duration = random.uniform(2.0, 5.0)
                else:
                    # Mais calmo quando longe
                    self._play_expression("neutral")
                    mood_duration = random.uniform(4.0, 8.0)

            # Configura o timer para a próxima mudança
            self._expression_timer = mood_duration

        # Ajusta opacidade da face com base na distância do jogador
        if self._player and self._player.node_path:
            player_pos = self._player.node_path.getPos(self._show_base.render)
            npc_pos = self.node_path.getPos(self._show_base.render)
            distance = (player_pos - npc_pos).length()

            # Mais visível quando perto, mais translúcido quando longe
            target_opacity = 0.85
            if distance < NPC_SAFE_DISTANCE * 2:
                target_opacity = 0.95  # Quase sólido quando perto
            elif distance > NPC_DETECTION_RADIUS:
                target_opacity = 0.7  # Mais translúcido quando longe

            # Suaviza a transição de opacidade
            self._face_opacity = self._face_opacity * 0.95 + target_opacity * 0.05

            # Aplica opacidade à face
            if self._face_node:
                current_color = self._face_node.getColor()
                self._face_node.setColor(current_color[0], current_color[1], current_color[2], self._face_opacity)

    def _update_face_orientation(self, dt: float):
        """Rotaciona a face para apontar na direção do movimento."""
        # Suaviza a transição da direção atual para a direção do movimento
        current_move_dir = Vec3(self._velocity)
        current_move_dir.normalize()

        # Taxa de interpolação para suavizar a rotação
        interp_rate = min(dt * 5.0, 1.0)

        # Calcula nova direção com interpolação suave
        self._facing_direction = self._facing_direction * (1.0 - interp_rate) + current_move_dir * interp_rate

        if self._facing_direction.length_squared() > 0.001:
            self._facing_direction.normalize()

            # Calcula a rotação necessária para olhar na direção do movimento
            # Apenas no plano horizontal (X e Y)
            if self._face_node:
                # Calcula o ângulo no plano XY
                angle = math.degrees(math.atan2(self._facing_direction.y, self._facing_direction.x))

                # Aplica a rotação à face
                self._face_node.setH(angle - 90)  # -90 para compensar a orientação padrão

                # Mantém o billboard efeito apenas para os olhos
                if self._left_eye and self._right_eye:
                    self._left_eye.setBillboardPointEye()
                    self._right_eye.setBillboardPointEye()

    def _enforce_room_boundaries(self):
        """Garante que o NPC permanece dentro dos limites da sala."""
        # Obtém a posição atual do NPC
        current_pos = Vec3(self.node_path.getPos())

        # Define margem de segurança AINDA MAIS RIGOROSA (60% da sala)
        half_w, half_l, _ = ROOM_SIZE
        safe_half_w = half_w * 0.45
        safe_half_l = half_l * 0.45

        # Verifica se o NPC está fora dos limites seguros
        outside_bounds = (abs(current_pos.x) > safe_half_w or
                          abs(current_pos.y) > safe_half_l)

        print(f"[NPC] Posição atual: {current_pos.x}, {current_pos.y}, limites seguros: {safe_half_w}, {safe_half_l}")
        if outside_bounds:
            # Restringe a posição aos limites seguros
            corrected_x = min(max(current_pos.x, -safe_half_w), safe_half_w)
            corrected_y = min(max(current_pos.y, -safe_half_l), safe_half_l)

            # Aplica a correção
            corrected_pos = Vec3(corrected_x, corrected_y, current_pos.z)

            print(f"[NPC] CORREÇÃO DE LIMITE: {current_pos} → {corrected_pos}")

            self.node_path.setPos(corrected_pos)
            self._transform.set_position(corrected_pos)

            # Inverte e reduz a velocidade para evitar bater nas paredes
            if abs(current_pos.x) > safe_half_w:
                self._velocity.x *= -0.5
            if abs(current_pos.y) > safe_half_l:
                self._velocity.y *= -0.5

            # Escolhe nova direção em breve
            self._walk_timer = min(self._walk_timer, 0.2)

            # Teleporta para uma posição segura se estiver muito fora dos limites
            extreme_violation = (abs(current_pos.x) > safe_half_w * 1.1 or
                                 abs(current_pos.y) > safe_half_l * 1.1)
            if extreme_violation:
                print(f"[NPC] TELEPORTANDO DE EMERGÊNCIA: Violação extrema de limite")
                self._teleport_away()

    def _update_obstacle_memory(self, dt: float):
        """Atualiza a memória de obstáculos, esquecendo-os gradualmente."""
        # Lista de chaves a remover
        to_remove = []

        # Atualiza todos os timers de obstáculos
        for pos, lifetime in list(self._obstacle_memory.items()):
            # Diminui o tempo de vida do obstáculo
            self._obstacle_memory[pos] = lifetime - dt

            # Se o tempo de vida acabou, marca para remoção
            if self._obstacle_memory[pos] <= 0:
                to_remove.append(pos)

        # Remove obstáculos esquecidos
        for pos in to_remove:
            del self._obstacle_memory[pos]

        # Limpa o cache de verificação de caixas periodicamente
        current_time = getattr(self._show_base.taskMgr.globalClock, 'getFrameTime', lambda: 0)()
        for key in list(self._box_check_cache.keys()):
            result, timestamp = self._box_check_cache[key]
            if current_time - timestamp > self._box_check_cache_lifetime:
                del self._box_check_cache[key]

    def _update_visual_effects(self, dt: float):
        """Atualiza efeitos visuais com base na proximidade do jogador e estado."""
        if not self._player or not self._player.node_path:
            return

        # Calcular distância atual ao jogador
        player_pos = self._player.node_path.getPos(self._show_base.render)
        npc_pos = self.node_path.getPos(self._show_base.render)
        distance = (player_pos - npc_pos).length()

        # Atualiza o timer para mudança de cor
        self._color_shift_timer += dt

        # Intensidade do brilho baseada em distância e estado
        target_intensity = 0.0

        if distance < NPC_SAFE_DISTANCE:
            # Muito perto: brilho intenso
            target_intensity = 1.0
        elif distance < NPC_DETECTION_RADIUS:
            # Dentro da faixa de detecção: brilho proporcional
            target_intensity = 1.0 - (distance - NPC_SAFE_DISTANCE) / (NPC_DETECTION_RADIUS - NPC_SAFE_DISTANCE)

        # Aumenta o brilho no estado de stalking
        if self._behavior_state == "stalk":
            target_intensity = min(1.0, target_intensity + 0.4)

            # Pulsa mais rápido quando perseguindo
            if self._pulse_sequence and hasattr(self._pulse_sequence, 'setPlayRate'):
                self._pulse_sequence.setPlayRate(1.5)

            # Partículas mais agitadas
            try:
                for p_name in ["core", "mid_layer", "outer_aura"]:
                    p = self._effect.getParticlesNamed(p_name)
                    if p and hasattr(p.emitter, 'setAmplitude'):
                        p.emitter.setAmplitude(min(1.0, p.emitter.getAmplitude() * 1.2))
            except:
                pass

        # Estado de fuga tem brilho vermelho pulsante
        if self._behavior_state == "flee":
            # Pulsa entre vermelho e azul para efeito de "alarme"
            red_component = 0.8 + 0.2 * math.sin(self._color_shift_timer * 5.0)

            if self._halo_effect:
                self._halo_effect.setColor(red_component, 0.3, max(0.3, 1.0 - red_component), 0.4)

            if hasattr(self, '_inner_halo') and self._inner_halo:
                self._inner_halo.setColor(red_component, 0.2, max(0.2, 1.0 - red_component), 0.6)

            # Partículas também mudam de cor
            try:
                for p_name in ["core", "mid_layer", "outer_aura"]:
                    p = self._effect.getParticlesNamed(p_name)
                    if p and hasattr(p.renderer, 'setColor'):
                        p.renderer.setColor(Vec3(red_component, 0.2, max(0.2, 1.0 - red_component)))
            except:
                pass

            # Aumenta amplitude do movimento para parecer mais agitado
            try:
                for p_name in ["core", "mid_layer", "outer_aura"]:
                    p = self._effect.getParticlesNamed(p_name)
                    if p and hasattr(p.emitter, 'setAmplitude'):
                        p.emitter.setAmplitude(min(1.2, p.emitter.getAmplitude() * 1.5))
            except:
                pass

        elif self._behavior_state == "wander" and self._halo_effect:
            # Restaura cores normais
            self._halo_effect.setColor(0.5, 0.7, 1.0, 0.4)  # Azul normal

            if hasattr(self, '_inner_halo') and self._inner_halo:
                self._inner_halo.setColor(0.8, 0.9, 1.0, 0.6)

            # Restaura velocidade normal de pulsação
            if self._pulse_sequence and hasattr(self._pulse_sequence, 'setPlayRate'):
                self._pulse_sequence.setPlayRate(1.0)

            # Restaura partículas à amplitude normal
            try:
                p = self._effect.getParticlesNamed("core")
                if p and hasattr(p.emitter, 'setAmplitude'):
                    p.emitter.setAmplitude(0.5)

                p = self._effect.getParticlesNamed("mid_layer")
                if p and hasattr(p.emitter, 'setAmplitude'):
                    p.emitter.setAmplitude(0.5)

                p = self._effect.getParticlesNamed("outer_aura")
                if p and hasattr(p.emitter, 'setAmplitude'):
                    p.emitter.setAmplitude(0.8)
            except:
                pass

        # Suaviza a transição do brilho
        self._glow_intensity = self._glow_intensity * 0.9 + target_intensity * 0.1

        # Aplica intensidade às partículas
        try:
            # Ajusta taxa de nascimento com base na intensidade
            for p_name in ["core", "mid_layer", "outer_aura"]:
                p = self._effect.getParticlesNamed(p_name)
                if p:
                    # Mais partículas quando mais intenso
                    birth_rate = 0.02 - self._glow_intensity * 0.01  # Mais rápido quando intenso
                    p.setBirthRate(max(0.005, birth_rate))
        except:
            pass

    def _update_awareness(self, dt: float, being_watched: bool):
        """Atualiza o nível de percepção do NPC sobre estar sendo observado."""
        if being_watched:
            # Aumenta awareness gradualmente quando observado
            self._player_awareness = min(1.0, self._player_awareness + dt / NPC_AWARENESS_TIME)

            # Quando percebe que está sendo observado, muda a expressão facial
            if self._player_awareness > 0.7 and self._face_mood != "scared":
                self._play_expression("scared")
        else:
            # Diminui awareness mais rapidamente quando não observado
            self._player_awareness = max(0.0, self._player_awareness - dt / (NPC_AWARENESS_TIME * 0.5))

    def _check_state_transition(self, dt: float):
        """Avalia e executa transições entre estados comportamentais."""
        if not self._player or not self._player.node_path:
            return

        # Obtém posições atuais
        player_pos = self._player.node_path.getPos(self._show_base.render)
        npc_pos = self.node_path.getPos(self._show_base.render)

        # Distância ao jogador
        distance = (player_pos - npc_pos).length()

        # Atualiza a última posição conhecida do jogador
        self._last_known_player_pos = Vec3(player_pos)

        # Avalia transições com base no estado atual
        if self._behavior_state == "wander":
            # Se o jogador estiver próximo, começa a perseguir
            if distance < NPC_DETECTION_RADIUS and distance > NPC_SAFE_DISTANCE:
                self._change_behavior("stalk")

        elif self._behavior_state == "stalk":
            # Volta a vagar se o jogador estiver muito perto ou muito longe
            if distance < NPC_SAFE_DISTANCE or distance > NPC_DETECTION_RADIUS * 1.5:
                self._change_behavior("wander")

            # Foge se estiver sendo observado por tempo suficiente
            if self._player_awareness > 0.8 and distance < NPC_FLEE_THRESHOLD:
                self._change_behavior("flee")

        elif self._behavior_state == "flee":
            # Após um tempo ou distância suficiente, volta a vagar
            self._state_timer += dt
            if self._state_timer > 5.0 or distance > NPC_DETECTION_RADIUS:
                self._change_behavior("wander")

    def _change_behavior(self, new_state: str):
        """Muda o comportamento do NPC para um novo estado com efeitos visuais."""
        if new_state == self._behavior_state:
            return  # Já está neste estado

        old_state = self._behavior_state
        self._behavior_state = new_state
        self._state_timer = 0.0

        # Efeitos específicos para cada transição
        if new_state == "stalk":
            # Acelera um pouco durante a perseguição
            self._walk_timer = random.uniform(*NPC_WALK_INTERVAL) * 0.7

            # Som mais intenso durante perseguição
            if self._sound:
                self._sound.setVolume(1.0)

            # Flash azul brilhante ao iniciar perseguição
            if self._halo_effect:
                # Sequência: flash brilhante -> normal
                Sequence(
                    LerpColorScaleInterval(self._halo_effect, 0.3,
                                           Vec4(1.5, 1.5, 1.5, 1.0),  # Super brilhante
                                           startColorScale=Vec4(1.0, 1.0, 1.0, 1.0)),
                    LerpColorScaleInterval(self._halo_effect, 0.7,
                                           Vec4(1.0, 1.0, 1.0, 1.0),  # Normal
                                           startColorScale=Vec4(1.5, 1.5, 1.5, 1.0))
                ).start()

            # Expressão facial para perseguição
            self._play_expression("curious")

        elif new_state == "flee":
            # Som mais suave durante fuga
            if self._sound:
                self._sound.setVolume(0.6)

            # Flash vermelho ao fugir
            if self._halo_effect:
                # Sequência: branco -> vermelho -> normal com pulso
                Sequence(
                    LerpColorScaleInterval(self._halo_effect, 0.2,
                                           Vec4(1.5, 1.5, 1.5, 1.0)),  # Flash branco
                    Func(lambda: self._halo_effect.setColor(1.0, 0.2, 0.2, 0.5)),  # Vermelho
                    LerpColorScaleInterval(self._halo_effect, 0.5,
                                           Vec4(1.0, 1.0, 1.0, 1.0))
                ).start()

            # Expressão de medo
            self._play_expression("scared")

        elif new_state == "wander":
            # Reset normal
            if self._sound:
                self._sound.setVolume(0.85)

            # Suaviza a transição visual
            if self._halo_effect:
                Sequence(
                    Wait(0.3),  # Pequena pausa
                    Func(lambda: self._halo_effect.setColor(0.5, 0.7, 1.0, 0.4)),  # Azul normal
                    LerpColorScaleInterval(self._halo_effect, 1.0,
                                           Vec4(1.0, 1.0, 1.0, 1.0))
                ).start()

            # Expressão neutra
            self._play_expression("neutral")

        print(f"[NPC] Comportamento: {old_state} -> {new_state}")

    # ───────────────── COMPORTAMENTOS ─────────────────
    def _update_wander_behavior(self, dt: float):
        """Movimenta o NPC em padrões aleatórios pela sala."""
        self._walk_timer -= dt
        if self._walk_timer <= 0:
            self._choose_new_direction()

        if self._velocity.length_squared() > 0:
            self._step(dt)

        # Teleporta se estiver muito perto do jogador
        if self._player and self._player.node_path:
            if (
                    self.node_path.getPos(self._show_base.render)
                    - self._player.node_path.getPos(self._show_base.render)
            ).length() < NPC_SAFE_DISTANCE:
                self._teleport_away()

    def _update_shadow_with_movement(self):
        """Atualiza a sombra falsa com base no movimento para melhorar o efeito 3D."""
        if not hasattr(self, '_shadow') or not self._shadow:
            return

        try:
            # Obtém a velocidade atual para calcular a inclinação da sombra
            velocity_len = self._velocity.length()

            if velocity_len > 0.1:
                # Determina direção do movimento no plano XY
                move_dir = Vec3(self._velocity)
                move_dir.normalize()

                # Calcula fatores de escala para a sombra
                # Movimento na direção X estica/comprime na direção Y
                x_factor = 1.0 - abs(move_dir.x) * 0.2
                # Movimento na direção Y estica/comprime na direção X
                y_factor = 1.0 - abs(move_dir.y) * 0.2

                # Velocidade aumenta o alongamento
                stretch_factor = min(1.0 + velocity_len * 0.05, 1.3)

                # Direção do movimento determina a direção do alongamento
                if abs(move_dir.x) > abs(move_dir.y):
                    # Movimento principalmente horizontal
                    y_scale = 0.6 * stretch_factor if move_dir.x != 0 else 0.6
                    x_scale = 1.0
                else:
                    # Movimento principalmente vertical
                    x_scale = 0.6 * stretch_factor if move_dir.y != 0 else 0.6
                    y_scale = 1.0

                # Aplica escala à sombra
                self._shadow.setScale(x_scale, y_scale, 1.0)

                # Sutil movimento da sombra na direção oposta ao movimento
                offset_x = -move_dir.x * 0.05
                offset_y = -move_dir.y * 0.05
                self._shadow.setPos(offset_x, offset_y, -NPC_SIZE.z / 2 + 0.02)
            else:
                # Em repouso, sombra normal
                self._shadow.setScale(1.0, 0.6, 1.0)
                self._shadow.setPos(0, 0, -NPC_SIZE.z / 2 + 0.02)
        except Exception as e:
            pass  # Ignora erros na atualização da sombra

    def _update_stalk_behavior(self, dt: float):
        """Persegue o jogador com movimentos inteligentes e pathing."""
        if not self._player or not self._player.node_path:
            return

        # Atualiza timer para movimentos não constantes
        self._walk_timer -= dt

        # Obtém posições atuais
        player_pos = self._player.node_path.getPos(self._show_base.render)
        npc_pos = self.node_path.getPos(self._show_base.render)

        # Calcula vetor direção ao jogador
        to_player = player_pos - npc_pos
        distance = to_player.length()

        # Normaliza para obter apenas a direção
        if distance > 0.001:
            to_player.normalize()

        # Verificar se há obstáculos no caminho direto
        direct_path_obstructed = self._is_path_obstructed(npc_pos, player_pos)

        # Decide a direção com base nas condições
        if direct_path_obstructed:
            # Path finding: encontra caminho alternativo
            if not self._path_points or self._walk_timer <= 0:
                self._find_path_to_player()
                self._walk_timer = random.uniform(1.0, 2.0)

            # Seguir o caminho atual
            if self._path_points and self._current_path_index < len(self._path_points):
                target = self._path_points[self._current_path_index]
                to_target = target - npc_pos

                # Se chegou perto do ponto atual, vai para o próximo
                if to_target.length() < 1.0:
                    self._current_path_index += 1

                    # Recalcula ao chegar ao fim do caminho
                    if self._current_path_index >= len(self._path_points):
                        self._find_path_to_player()
                else:
                    to_target.normalize()
                    self._velocity = to_target * NPC_SPEED
        else:
            # Caminho livre: vai direto mantendo distância adequada
            if distance < NPC_SAFE_DISTANCE * 1.5:
                # Mantém distância
                self._velocity = -to_player * NPC_SPEED
            else:
                # Aproxima-se gradualmente
                approach_speed = min(NPC_SPEED, NPC_SPEED * 0.7 + (distance / NPC_DETECTION_RADIUS) * NPC_SPEED * 0.3)
                self._velocity = to_player * approach_speed

        # Executa o movimento
        self._step(dt)

    def _update_flee_behavior(self, dt: float):
        """Foge do jogador quando observado por muito tempo."""
        if not self._player or not self._player.node_path:
            return

        # Posições atuais
        player_pos = self._player.node_path.getPos(self._show_base.render)
        npc_pos = self.node_path.getPos(self._show_base.render)

        # Direção oposta ao jogador
        away_from_player = npc_pos - player_pos
        distance = away_from_player.length()

        if distance > 0.001:
            away_from_player.normalize()

        # Velocidade de fuga mais rápida
        flee_speed = NPC_SPEED * 1.5

        # Adiciona variação à direção para movimento mais natural
        random_angle = random.uniform(-30, 30)  # ±30 graus
        rad_angle = math.radians(random_angle)

        # Rotaciona o vetor de fuga
        cos_a = math.cos(rad_angle)
        sin_a = math.sin(rad_angle)
        rotated_x = away_from_player.x * cos_a - away_from_player.y * sin_a
        rotated_y = away_from_player.x * sin_a + away_from_player.y * cos_a

        flee_dir = Vec3(rotated_x, rotated_y, 0)
        flee_dir.normalize()

        # CRÍTICO: Verifica se a direção de fuga levaria para fora dos limites da sala
        half_w, half_l, _ = ROOM_SIZE
        safe_half_w = half_w * 0.7
        safe_half_l = half_l * 0.7

        # Prevê a posição após um movimento nessa direção
        predicted_pos = npc_pos + flee_dir * flee_speed * 0.5  # 0.5 segundos de movimento

        # Se a posição prevista estiver fora dos limites, ajusta a direção
        if (abs(predicted_pos.x) > safe_half_w or abs(predicted_pos.y) > safe_half_l):
            # Inverte componentes que levariam para fora
            if abs(predicted_pos.x) > safe_half_w:
                flee_dir.x *= -1
            if abs(predicted_pos.y) > safe_half_l:
                flee_dir.y *= -1

            # Normaliza novamente
            if flee_dir.length_squared() > 0.001:
                flee_dir.normalize()
            else:
                # Se a direção acabou zerada, usa uma direção para o centro
                flee_dir = -npc_pos
                flee_dir.normalize()

        # Define a velocidade de fuga
        self._velocity = flee_dir * flee_speed

        # Se ficar muito longe, teleporta para outra área
        if distance > NPC_DETECTION_RADIUS * 1.2:
            self._teleport_away()
            return

        # Teleporta se chegar perto de obstáculo
        grid_x, grid_y = int(npc_pos.x), int(npc_pos.y)
        if (grid_x, grid_y) in self._obstacle_memory:
            self._teleport_away()
            return

        # Executa o movimento
        self._step(dt)

    # ───────────────── MOVIMENTO E NAVEGAÇÃO ─────────────────
    def _choose_new_direction(self):
        """Escolhe uma nova direção inteligente, evitando obstáculos e paredes."""
        # Verificar direções possíveis
        current_pos = self.node_path.getPos()
        possible_directions = []
        best_direction = None
        best_cost = float('inf')

        # CRÍTICO: Limites da sala para segurança extrema (70%)
        half_w, half_l, _ = ROOM_SIZE
        safe_half_w = half_w * 0.7
        safe_half_l = half_l * 0.7

        # Verifica 8 direções para movimento
        for ang in range(0, 360, 45):
            # Direção normalizada
            rad_ang = math.radians(ang)
            direction = Vec3(
                math.cos(rad_ang),
                math.sin(rad_ang),
                0
            )

            # Simula o movimento para verificar colisões
            test_distance = NPC_RADIUS * 2
            test_pos = current_pos + direction * test_distance

            # CRÍTICO: Verifica limites da sala com margem ampliada
            if (abs(test_pos.x) >= safe_half_w or
                    abs(test_pos.y) >= safe_half_l):
                continue  # Fora dos limites

            # Verifica colisão com caixas
            if self._inside_any_box(test_pos.x, test_pos.y):
                continue  # Colide com caixa

            # Verifica memória de obstáculos
            grid_x, grid_y = int(test_pos.x), int(test_pos.y)
            if (grid_x, grid_y) in self._obstacle_memory:
                continue  # Obstáculo recentemente encontrado

            # Calcula custo baseado no histórico de posições
            cost = 0
            for pos in self._position_history:
                distance_to_pos = (pos - test_pos).length()
                if distance_to_pos < 2.0:
                    cost += 10 / (distance_to_pos + 0.1)  # Penalidade por proximidade

            possible_directions.append((direction, cost))

            # Atualiza melhor direção
            if cost < best_cost:
                best_cost = cost
                best_direction = direction

        # Se não encontrou direção possível, teleporta ou escolhe direção para o centro
        if not possible_directions:
            # 30% de chance de teleportar quando bloqueado
            if random.random() < 0.3:
                self._teleport_away()
                return

            # Direção para o centro da sala como fallback seguro
            to_center = Vec3(0, 0, 0) - current_pos
            if to_center.length_squared() > 0.001:
                to_center.normalize()
                self._velocity = to_center * NPC_SPEED
            else:
                # Totalmente aleatório se já estiver no centro
                ang = random.uniform(0, 360)
                self._velocity = Vec3(
                    NPC_SPEED * math.cos(math.radians(ang)),
                    NPC_SPEED * math.sin(math.radians(ang)),
                    0,
                )
        else:
            # 20% de chance de movimento aleatório para imprevisibilidade
            if random.random() < 0.2:
                direction, _ = random.choice(possible_directions)
                self._velocity = direction * NPC_SPEED
            else:
                # Usa a melhor direção
                self._velocity = best_direction * NPC_SPEED

        # Define intervalo de movimento baseado no estado atual
        base_interval = random.uniform(*NPC_WALK_INTERVAL)
        if self._behavior_state == "stalk":
            # Movimentos mais rápidos durante perseguição
            self._walk_timer = base_interval * 0.7
        elif self._behavior_state == "flee":
            # Movimentos muito frequentes durante fuga
            self._walk_timer = base_interval * 0.4
        else:
            # Intervalo normal durante vagar
            self._walk_timer = base_interval

    def _step(self, dt: float):
        """Move o NPC com detecção de colisão e restrição de limites."""
        start = self.node_path.getPos()

        # Guarda posição anterior para histórico
        prev_pos = Vec3(start)

        # NOVO: Verifica antecipadamente se o movimento iria nos levar para fora dos limites
        proposed_pos = start + self._velocity * dt
        half_w, half_l, _ = ROOM_SIZE
        safe_half_w = half_w * 0.6  # Área segura reduzida para 60%
        safe_half_l = half_l * 0.6

        # Se o movimento ultrapassaria os limites, ajusta a velocidade
        if abs(proposed_pos.x) > safe_half_w:
            if (proposed_pos.x > 0 and self._velocity.x > 0) or (proposed_pos.x < 0 and self._velocity.x < 0):
                self._velocity.x = -self._velocity.x * 0.7  # Inverte e reduz

        if abs(proposed_pos.y) > safe_half_l:
            if (proposed_pos.y > 0 and self._velocity.y > 0) or (proposed_pos.y < 0 and self._velocity.y < 0):
                self._velocity.y = -self._velocity.y * 0.7  # Inverte e reduz

        # Aplica o movimento com velocidade ajustada
        self.node_path.setPos(start + self._velocity * dt)

        # DUPLA verificação: Garante que o NPC permanece dentro dos limites da sala
        new_pos = self.node_path.getPos()
        new_pos = self._enforce_position_in_room(new_pos)
        self.node_path.setPos(new_pos)

        # Atualiza e inclina a sombra com base no movimento para efeito 3D
        self._update_shadow_with_movement()

        # Verifica se moveu efetivamente
        movement = (new_pos - start).length()

        # Detecta colisão (movimento muito pequeno)
        hit_obstacle = movement < 0.2 * self._velocity.length() * dt

        if hit_obstacle:
            # Marca local como obstáculo na memória espacial
            grid_x, grid_y = int(start.x), int(start.y)
            self._obstacle_memory[(grid_x, grid_y)] = self._obstacle_memory_lifetime

            # Muda direção
            self._velocity *= -1
            self._walk_timer = 0.1  # Escolhe nova direção em breve

        # Atualiza transform component
        self._transform.set_position(self.node_path.getPos())

        # Registra posição no histórico se moveu o suficiente
        if (prev_pos - new_pos).length() > 0.5:
            self._position_history.append(Vec3(new_pos))
            if len(self._position_history) > self._max_history:
                self._position_history.pop(0)

    def _enforce_position_in_room(self, position: Vec3) -> Vec3:
        """Garante que a posição está dentro dos limites da sala."""
        half_w, half_l, _ = ROOM_SIZE

        # Margem de segurança MAIS RESTRITIVA (60% do tamanho da sala)
        safe_half_w = half_w * 0.6  # Reduzido para garantir distância das paredes
        safe_half_l = half_l * 0.6

        # Restringe a posição
        corrected_x = min(max(position.x, -safe_half_w), safe_half_w)
        corrected_y = min(max(position.y, -safe_half_l), safe_half_l)

        return Vec3(corrected_x, corrected_y, position.z)
    def _is_path_obstructed(self, start_pos: Vec3, end_pos: Vec3) -> bool:
        """Verifica se há obstáculos entre dois pontos usando raycast."""
        # Cria um raio do ponto inicial ao final
        direction = end_pos - start_pos
        distance = direction.length()

        if distance < 0.001:
            return False  # Pontos muito próximos

        direction.normalize()

        # Usa raycasting para verificar obstáculos
        ray = CollisionSegment(
            start_pos.x, start_pos.y, start_pos.z + 0.1,  # Ligeiramente acima do chão
            end_pos.x, end_pos.y, end_pos.z + 0.1
        )

        ray_node = CollisionNode("path_check_ray")
        ray_node.addSolid(ray)
        ray_node.setFromCollideMask(BitMask32.bit(0))  # Colide com objetos físicos
        ray_node.setIntoCollideMask(BitMask32(0))  # Não recebe colisões

        ray_np = self._show_base.render.attachNewNode(ray_node)

        queue = CollisionHandlerQueue()
        traverser = CollisionTraverser()
        traverser.addCollider(ray_np, queue)

        # Executa a verificação
        traverser.traverse(self._show_base.render)

        # Processa resultados
        has_collision = queue.getNumEntries() > 0

        # Limpa recursos
        traverser.removeCollider(ray_np)
        ray_np.removeNode()

        return has_collision

    def _find_path_to_player(self):
        """Encontra um caminho aproximado até o jogador usando pontos intermediários inteligentes."""
        if not self._player or not self._player.node_path:
            return

        # Posições atuais
        start_pos = self.node_path.getPos(self._show_base.render)
        end_pos = self._player.node_path.getPos(self._show_base.render)

        # Inicializa o caminho
        self._path_points = []
        self._current_path_index = 0

        # Verifica se o caminho direto está livre
        if not self._is_path_obstructed(start_pos, end_pos):
            # Caminho direto disponível
            self._path_points = [end_pos]
            return

        # Caso contrário, gera pontos intermediários para contornar obstáculos
        half_w, half_l, _ = ROOM_SIZE
        room_safe_w = half_w * 0.7
        room_safe_l = half_l * 0.7
        max_points = 5

        # Lista de pontos potenciais
        potential_points = []

        # Tenta gerar pontos estratégicos
        for _ in range(20):
            # Posição com bias (70% na direção do jogador, 30% aleatória)
            bias = 0.7

            # Componente aleatória
            rx = random.uniform(-room_safe_w, room_safe_w)
            ry = random.uniform(-room_safe_l, room_safe_l)
            random_pos = Vec3(rx, ry, start_pos.z)

            # Componente direcionada ao jogador
            direct_vector = end_pos - start_pos
            if direct_vector.length() > 0:
                direct_vector.normalize()
                direct_vector *= random.uniform(3.0, 10.0)  # Distância variável

            biased_pos = start_pos + direct_vector
            biased_pos.x = min(max(biased_pos.x, -room_safe_w), room_safe_w)
            biased_pos.y = min(max(biased_pos.y, -room_safe_l), room_safe_l)

            # Posição final com bias
            point = biased_pos * bias + random_pos * (1 - bias)
            point.z = start_pos.z  # Mantém a mesma altura

            # CRÍTICO: Garante que o ponto está dentro da sala
            point.x = min(max(point.x, -room_safe_w), room_safe_w)
            point.y = min(max(point.y, -room_safe_l), room_safe_l)

            # Verifica se o ponto não está dentro de obstáculos
            if not self._inside_any_box(point.x, point.y):
                # Calcula custo do ponto (distância até o jogador)
                cost = (point - end_pos).length()
                potential_points.append((point, cost))

        # Ordena pontos potenciais pelo custo (distância ao jogador)
        potential_points.sort(key=lambda x: x[1])

        # Constrói caminho com os melhores pontos
        current = start_pos
        path_points = []

        # Prefere pontos com caminho livre até o próximo ponto
        for point, _ in potential_points[:10]:  # Considera apenas os 10 melhores
            # Verifica se há caminho livre do ponto atual até este ponto
            if not self._is_path_obstructed(current, point):
                path_points.append(point)
                current = point

                # Verifica se agora há caminho livre até o jogador
                if not self._is_path_obstructed(current, end_pos):
                    path_points.append(end_pos)
                    break

                # Limita o número de pontos
                if len(path_points) >= max_points:
                    break

        # Se encontrou pelo menos um ponto, usa o caminho
        if path_points:
            self._path_points = path_points
        else:
            # Fallback: tenta ir direto (mesmo que haja obstáculos)
            # Isso pode fazer o NPC ficar preso, mas o sistema de desbloqueio vai resolver
            self._path_points = [end_pos]

            # 30% de chance de teleportar se realmente não encontrar caminho
            if random.random() < 0.3:
                self._teleport_away()

    def _is_player_looking_at_me(self) -> bool:
        """Verifica se o jogador está olhando na direção do NPC."""
        if not self._player or not self._player.node_path:
            return False

        # Posições atuais
        player_pos = self._player.node_path.getPos(self._show_base.render)
        npc_pos = self.node_path.getPos(self._show_base.render)

        # Distância ao jogador
        distance = (player_pos - npc_pos).length()

        # Se estiver muito longe, não considera olhar
        if distance > NPC_DETECTION_RADIUS:
            return False

        # Verifica câmera do jogador
        camera_np = None
        if hasattr(self._player, 'camera_node'):
            camera_np = self._player.camera_node

        if not camera_np:
            # Fallback: usa a câmera principal do jogo
            camera_np = self._show_base.camera

        if not camera_np:
            return False

        # Obtém vetor direção da câmera
        quat = camera_np.getQuat(self._show_base.render)
        forward = quat.getForward()

        # Verifica se há linha de visão livre
        if self._is_path_obstructed(player_pos, npc_pos):
            return False

        # Direção da câmera ao NPC
        to_npc = npc_pos - player_pos
        if to_npc.length() > 0:
            to_npc.normalize()

        # Produto escalar (cos do ângulo entre os vetores)
        dot_product = forward.dot(to_npc)

        # Olhando se o ângulo for menor que 30 graus (cos > 0.866)
        return dot_product > 0.866

    def _teleport_away(self):
        """Teleporta o NPC para uma posição aleatória segura dentro dos limites da sala."""
        half_w, half_l, _ = ROOM_SIZE
        safe_w = half_w * 0.6  # 60% para garantir distância das paredes
        safe_l = half_l * 0.6

        # Posição do jogador para manter distância
        player_pos = (
            self._player.node_path.getPos(self._show_base.render)
            if self._player and self._player.node_path else Vec3(1e6)
        )

        # Tenta encontrar uma posição ótima
        best_pos, best_d2 = None, 0.0

        for _ in range(NPC_TELEPORT_ATTEMPTS):
            # Gera posição aleatória dentro dos limites seguros
            x = random.uniform(-safe_w, safe_w)
            y = random.uniform(-safe_l, safe_l)

            # Verifica colisão com caixas
            if self._inside_any_box(x, y):
                continue

            # Calcula distância ao jogador
            d2 = (Vec3(x, y, 0) - Vec3(player_pos.x, player_pos.y, 0)).length_squared()

            # Precisa estar longe do jogador
            if d2 < NPC_SAFE_DISTANCE ** 2:
                continue

            # Prefere posições mais distantes
            if d2 > best_d2:
                best_d2, best_pos = d2, Vec3(x, y, NPC_SIZE.z / 2)

            # Se encontrou uma posição muito boa, interrompe a busca
            if d2 > (NPC_SAFE_DISTANCE * 3) ** 2:
                break

        # Se encontrou posição válida, teleporta
        if best_pos:
            # Efeito de teleporte
            if self._halo_effect:
                # Sequência: fade out -> teleporte -> fade in
                fade_sequence = Sequence(
                    LerpColorScaleInterval(self.node_path, 0.3, Vec4(1, 1, 1, 0)),  # Fade out
                    Func(self._do_teleport, best_pos),  # Teleporta
                    LerpColorScaleInterval(self.node_path, 0.3, Vec4(1, 1, 1, 1))  # Fade in
                )
                fade_sequence.start()
            else:
                # Teleporte direto
                self._do_teleport(best_pos)

            # Publica evento
            self._event_bus.publish("on_npc_teleported")
        else:
            # Fallback: teleporta para o centro da sala com offset aleatório
            x_offset = random.uniform(-safe_w * 0.5, safe_w * 0.5)
            y_offset = random.uniform(-safe_l * 0.5, safe_l * 0.5)
            fallback_pos = Vec3(x_offset, y_offset, NPC_SIZE.z / 2)
            self._do_teleport(fallback_pos)

    def _do_teleport(self, position: Vec3):
        """Executa o teleporte após os efeitos visuais."""
        # CRÍTICO: Verifica novamente que a posição está dentro dos limites da sala
        half_w, half_l, _ = ROOM_SIZE
        safe_w = half_w * 0.6
        safe_l = half_l * 0.6

        # Restringe a posição
        safe_x = min(max(position.x, -safe_w), safe_w)
        safe_y = min(max(position.y, -safe_l), safe_l)
        safe_position = Vec3(safe_x, safe_y, position.z)

        # Aplica a posição
        self.node_path.setPos(safe_position)
        self._transform.set_position(safe_position)

        # Reseta movimento
        self._velocity = Vec3(0)
        self._walk_timer = 0

        # Limpa memória de movimento
        self._position_history.clear()
        self._path_points = []
        self._current_path_index = 0

        # Efeito visual de teleporte
        try:
            if hasattr(self, '_face_node') and self._face_node:
                self._play_expression("scared")
        except:
            pass

    def _is_stuck(self) -> bool:
        """Verifica se o NPC está preso sem conseguir se mover efetivamente."""
        if len(self._position_history) < 3:
            return False

        # Verifica se as últimas posições estão muito próximas
        current_pos = self.node_path.getPos()
        total_distance = 0

        # Calcula a distância total percorrida nas últimas 3 posições
        for i in range(min(3, len(self._position_history))):
            total_distance += (current_pos - self._position_history[-1 - i]).length()

        # Se a distância total for muito pequena, está preso
        return total_distance < NPC_RADIUS * 0.8

    def _on_player_teleported(self):
        """Reage quando o jogador é teleportado."""
        # Limpa caminho quando o jogador teleporta
        self._path_points = []
        self._current_path_index = 0

        # 20% de chance de também teleportar
        if random.random() < 0.2:
            self._teleport_away()
            return

        # Volta para comportamento de vagar
        if self._behavior_state != "wander":
            self._change_behavior("wander")

    # ───────────────── UTILIDADES E VERIFICAÇÕES ─────────────────
    def _inside_any_box(self, x: float, y: float) -> bool:
        """Verifica se um ponto está dentro de alguma caixa com cache para otimização"""
        # Usa cache para evitar verificações repetidas em pontos semelhantes
        # Aproxima para a grade de 0.5 unidades para ter caching mais efetivo
        grid_x, grid_y = int(x * 2) / 2.0, int(y * 2) / 2.0
        cache_key = (grid_x, grid_y)

        # Verifica cache primeiro
        current_time = getattr(self._show_base.taskMgr.globalClock, 'getFrameTime', lambda: 0)()
        if cache_key in self._box_check_cache:
            result, timestamp = self._box_check_cache[cache_key]
            if current_time - timestamp <= self._box_check_cache_lifetime:
                return result

        # Realiza a verificação
        for ent in self._static_objects:
            if "box" in ent.name.lower() and ent.node_path:
                # Obtém posição e escala da caixa
                pos = ent.node_path.getPos(self._show_base.render)
                sx = ent.node_path.getScale(self._show_base.render).x
                sy = ent.node_path.getScale(self._show_base.render).y

                # Metade das dimensões com margem para o NPC
                hx = sx / 2 + NPC_RADIUS
                hy = sy / 2 + NPC_RADIUS

                # Verifica se o ponto está dentro da caixa estendida
                if (pos.x - hx <= x <= pos.x + hx and
                        pos.y - hy <= y <= pos.y + hy):
                    # Armazena no cache
                    self._box_check_cache[cache_key] = (True, current_time)
                    return True

        # Não está dentro de nenhuma caixa
        self._box_check_cache[cache_key] = (False, current_time)
        return False

    # ───────────────── LIMPEZA DE RECURSOS ─────────────────

    def cleanup(self):
        """Libera todos os recursos utilizados pelo NPC."""
        # Para o som
        if self._sound:
            self._sound.stop()
            if self._audio3d:
                self._audio3d.detachSound(self._sound)

        # Desativa e limpa o sistema de partículas
        if self._effect:
            self._effect.disable()
            self._effect.cleanup()

        # Para as animações
        if self._pulse_sequence:
            self._pulse_sequence.finish()

        if hasattr(self, '_inner_pulse_sequence') and self._inner_pulse_sequence:
            self._inner_pulse_sequence.finish()

        # Para a animação da sombra
        if hasattr(self, '_shadow_pulse') and self._shadow_pulse:
            self._shadow_pulse.finish()

        # Remove os halos
        if self._halo_effect:
            self._halo_effect.removeNode()

        if hasattr(self, '_inner_halo') and self._inner_halo:
            self._inner_halo.removeNode()

        # Remove a sombra
        if hasattr(self, '_shadow') and self._shadow:
            self._shadow.removeNode()

        # Cancela inscrições em eventos
        self._event_bus.unsubscribe("on_player_teleported", self._on_player_teleported)

        # Limpa caches e memória
        self._box_check_cache.clear()
        self._obstacle_memory.clear()
        self._position_history.clear()
        self._path_points.clear()

        # Chama limpeza da classe pai
        super().cleanup()