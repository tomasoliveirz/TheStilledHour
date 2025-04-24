from panda3d.core import Shader, ShaderAttrib, TransparencyAttrib
from panda3d.core import Texture, GraphicsOutput, GraphicsStateGuardian
from panda3d.core import FrameBufferProperties, WindowProperties, NodePath
from panda3d.core import PerspectiveLens, OrthographicLens, Camera, ModelNode
from panda3d.core import Vec3, Vec4, Point3, BitMask32


class ShadowManager:
    """
    Gerencia sombras usando Shadow Mapping para uma ou mais luzes.
    Implementa um sistema otimizado para sombras com alta qualidade visual.
    """

    def __init__(self, show_base, scene_root=None):
        """
        Inicializa o gerenciador de sombras.

        Args:
            show_base: Instância do ShowBase
            scene_root: Nó raiz da cena (opcional)
        """
        self.show_base = show_base
        self.scene_root = scene_root or show_base.render

        # Configuração dos shadow maps
        self.shadow_size = 1024  # Resolução dos shadow maps (potência de 2)
        self.shadow_buffers = []  # Lista de buffers para shadow maps
        self.shadow_cameras = []  # Câmeras para renderizar do ponto de vista das luzes
        self.shadow_textures = []  # Texturas de shadow maps

        # Luzes que projetam sombras
        self.shadow_lights = []

        # Objetos que recebem ou projetam sombras
        self.shadow_casters = set()  # Objetos que projetam sombras
        self.shadow_receivers = set()  # Objetos que recebem sombras

        # Shaders
        self.shadow_shader = None  # Shader para renderizar sombras
        self.scene_shader = None  # Shader para renderizar a cena com sombras

        # Inicialização
        self._init_system()

    def _init_system(self):
        """Inicializa o sistema de sombras."""
        try:
            # Verificar se o hardware suporta sombras
            gsg = self.show_base.win.getGsg()
            if not gsg.getSupportsBasicShaders():
                print("Aviso: Hardware não suporta shaders básicos, sombras desativadas.")
                return

            # Verificar se o hardware suporta shadow maps
            if not gsg.getSupportsShadowFilter():
                print("Aviso: Hardware não suporta shadow filtering, qualidade de sombras reduzida.")

            print("Inicializando sistema avançado de sombras...")

            # Ativar shader automático para objetos que não têm shader personalizado
            self.scene_root.setShaderAuto()

            # Carregar shaders de sombra
            self._load_shaders()

            print("Sistema de sombras inicializado com sucesso!")

        except Exception as e:
            print(f"Erro ao inicializar sistema de sombras: {e}")

    def _load_shaders(self):
        """Carrega os shaders para sombras e cena."""
        try:
            # Aqui definimos os shaders GLSL para sombras
            # Normalmente carregados de arquivos .vert e .frag
            # Como não temos certeza da existência dos arquivos no projeto, usamos strings inline

            # Shader para renderizar sombras (shadow pass)
            shadow_vertex = """
            #version 330

            // Inputs do vértice
            in vec4 p3d_Vertex;

            // Uniforms (variáveis globais)
            uniform mat4 p3d_ModelViewProjectionMatrix;

            void main() {
                // Posição do vértice no espaço de clip
                gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
            }
            """

            shadow_fragment = """
            #version 330

            // Saída do fragmento
            out vec4 fragColor;

            void main() {
                // No shadow pass apenas salvamos a profundidade
                // O valor de cor não importa
                fragColor = vec4(1.0);
            }
            """

            # Shader da cena com sombras (main pass)
            scene_vertex = """
            #version 330

            // Inputs do vértice
            in vec4 p3d_Vertex;
            in vec3 p3d_Normal;
            in vec2 p3d_MultiTexCoord0;

            // Outputs para o fragment shader
            out vec3 vPosition;
            out vec3 vNormal;
            out vec2 vTexCoord;
            out vec4 vShadowCoord;

            // Uniforms
            uniform mat4 p3d_ModelViewMatrix;
            uniform mat4 p3d_ProjectionMatrix;
            uniform mat4 p3d_ModelMatrix;
            uniform mat4 p3d_LightViewProjectionMatrix;
            uniform mat3 p3d_NormalMatrix;

            void main() {
                // Coordenadas de textura
                vTexCoord = p3d_MultiTexCoord0;

                // Normal no espaço de visão
                vNormal = normalize(p3d_NormalMatrix * p3d_Normal);

                // Posição no espaço de visão
                vPosition = vec3(p3d_ModelViewMatrix * p3d_Vertex);

                // Posição no espaço de coordenadas da luz (para shadow mapping)
                vShadowCoord = p3d_LightViewProjectionMatrix * p3d_ModelMatrix * p3d_Vertex;

                // Posição final no espaço de clip
                gl_Position = p3d_ProjectionMatrix * vec4(vPosition, 1.0);
            }
            """

            scene_fragment = """
            #version 330

            // Inputs do vertex shader
            in vec3 vPosition;
            in vec3 vNormal;
            in vec2 vTexCoord;
            in vec4 vShadowCoord;

            // Output
            out vec4 fragColor;

            // Uniforms
            uniform sampler2D p3d_Texture0;   // Textura difusa
            uniform sampler2D shadowMap;      // Shadow map

            uniform vec3 lightDir;            // Direção da luz
            uniform vec4 lightColor;          // Cor da luz
            uniform vec4 ambientColor;        // Cor ambiente

            uniform bool receiveShadow;       // Se este objeto recebe sombras

            // Função para calcular sombra com PCF (Percentage Closer Filtering)
            float calculateShadow(vec4 shadowCoord) {
                if (!receiveShadow) 
                    return 1.0;

                // Transformar coordenadas para range [0,1]
                vec3 projCoords = shadowCoord.xyz / shadowCoord.w;
                projCoords = projCoords * 0.5 + 0.5;

                // Verificar se está fora do shadow map
                if (projCoords.x < 0.0 || projCoords.x > 1.0 ||
                    projCoords.y < 0.0 || projCoords.y > 1.0 ||
                    projCoords.z < 0.0 || projCoords.z > 1.0)
                    return 1.0;

                // Profundidade atual
                float currentDepth = projCoords.z;

                // Bias para evitar shadow acne
                float bias = max(0.005 * (1.0 - dot(normalize(vNormal), lightDir)), 0.0005);

                // PCF (melhora a qualidade da sombra)
                float shadow = 0.0;
                vec2 texelSize = 1.0 / textureSize(shadowMap, 0);

                for (int x = -2; x <= 2; x++) {
                    for (int y = -2; y <= 2; y++) {
                        float pcfDepth = texture(shadowMap, projCoords.xy + vec2(x, y) * texelSize).r;
                        shadow += currentDepth - bias > pcfDepth ? 0.0 : 1.0;
                    }
                }

                shadow /= 25.0; // 5x5 kernel

                return shadow;
            }

            void main() {
                // Cor da textura
                vec4 texColor = texture(p3d_Texture0, vTexCoord);

                // Cálculo de iluminação básica
                vec3 normal = normalize(vNormal);
                float diffuse = max(dot(normal, normalize(lightDir)), 0.0);

                // Cálculo de sombra
                float shadow = calculateShadow(vShadowCoord);

                // Cor final
                vec4 diffuseColor = texColor * lightColor * diffuse * shadow;
                vec4 ambientTerm = texColor * ambientColor;

                fragColor = ambientTerm + diffuseColor;
                fragColor.a = texColor.a;
            }
            """

            # Criar os shaders
            self.shadow_shader = Shader.make(Shader.SL_GLSL, shadow_vertex, shadow_fragment)
            self.scene_shader = Shader.make(Shader.SL_GLSL, scene_vertex, scene_fragment)

            print("Shaders de sombra carregados com sucesso")

        except Exception as e:
            print(f"Erro ao carregar shaders: {e}")

    def create_shadow_buffer(self, light, lens):
        """
        Cria um buffer para shadow mapping.

        Args:
            light: A luz para a qual criar o shadow map
            lens: A lente da câmera para a visão da luz

        Returns:
            (buffer, camera, texture) - Os objetos criados
        """
        # Configurar as propriedades do buffer
        fb_props = FrameBufferProperties()
        fb_props.setRgbColor(False)  # Não precisamos de cor, apenas profundidade
        fb_props.setRgbaBits(0, 0, 0, 0)
        fb_props.setDepthBits(24)  # 24 bits de profundidade

        # Configurar propriedades da janela
        win_props = WindowProperties()
        win_props.setSize(self.shadow_size, self.shadow_size)

        # Criar o buffer
        buffer = self.show_base.graphicsEngine.makeOutput(
            self.show_base.pipe, f"shadowBuffer_{len(self.shadow_buffers)}",
            -100, fb_props, win_props,
            GraphicsOutput.BFRefuseWindow | GraphicsOutput.BFRtaColor | GraphicsOutput.BFCanBindEvery
        )

        if not buffer:
            print("Erro: Não foi possível criar buffer para shadow mapping")
            return None, None, None

        # Criar a textura para o shadow map
        shadow_tex = Texture(f"shadowMap_{len(self.shadow_textures)}")
        buffer.addRenderTexture(
            shadow_tex,
            GraphicsOutput.RTMBindOrCopy,
            GraphicsOutput.RTPDepth
        )

        # Configurar filtragem da textura
        shadow_tex.setMagfilter(Texture.FTLinear)
        shadow_tex.setMinfilter(Texture.FTLinear)
        shadow_tex.setWrapU(Texture.WMClamp)
        shadow_tex.setWrapV(Texture.WMClamp)

        # Criar a câmera para renderizar do ponto de vista da luz
        shadow_cam = Camera(f"shadowCam_{len(self.shadow_cameras)}")
        shadow_cam.setLens(lens)

        # Criar o nó da câmera e anexá-lo ao nó da luz
        shadow_cam_np = light.attachNewNode(shadow_cam)

        # Configurar a câmera para renderizar no buffer
        dr = buffer.makeDisplayRegion()
        dr.setCamera(shadow_cam_np)

        # Adicionar à lista de buffers, câmeras e texturas
        self.shadow_buffers.append(buffer)
        self.shadow_cameras.append(shadow_cam_np)
        self.shadow_textures.append(shadow_tex)

        # Configurar o shader para a câmera de sombra
        shadow_cam_np.node().setInitialState(
            shadow_cam_np.node().getInitialState().addAttrib(
                ShaderAttrib.make(self.shadow_shader)
            )
        )

        # Agora apenas objetos que projetam sombras serão renderizados pela câmera de sombra
        shadow_cam.setCameraMask(BitMask32.bit(1))

        return buffer, shadow_cam_np, shadow_tex

    def add_shadow_light(self, light_np, light_type="directional"):
        """
        Adiciona uma luz que projeta sombras.

        Args:
            light_np: NodePath da luz
            light_type: Tipo de luz ("directional", "spotlight", "point")

        Returns:
            Índice da luz na lista de luzes com sombra
        """
        if not self.shadow_shader or not self.scene_shader:
            print("Erro: Shaders não foram carregados.")
            return -1

        # Criar lente apropriada para o tipo de luz
        if light_type == "directional":
            lens = OrthographicLens()
            # Área de cobertura da luz direcional
            lens.setFilmSize(60, 60)
            lens.setNearFar(1, 100)
        elif light_type == "spotlight":
            lens = PerspectiveLens()
            # Ângulo do cone do spotlight
            lens.setFov(90)
            lens.setNearFar(1, 100)
        else:  # point (omni-direcional)
            print("Aviso: Luzes pontuais não são suportadas para shadow mapping simples")
            return -1

        # Criar buffer, câmera e textura para esta luz
        buffer, camera, texture = self.create_shadow_buffer(light_np, lens)
        if not buffer:
            return -1

        # Adicionar à lista de luzes com sombra
        light_index = len(self.shadow_lights)
        self.shadow_lights.append((light_np, camera, texture, light_type))

        # Retornar o índice da luz
        return light_index

    def add_caster(self, node_path):
        """
        Adiciona um objeto que projeta sombras.

        Args:
            node_path: NodePath do objeto
        """
        if not node_path:
            return

        # Define a máscara para ser visível pelas câmeras de sombra
        node_path.show(BitMask32.bit(1))

        # Adiciona ao conjunto de objetos que projetam sombras
        self.shadow_casters.add(node_path)

    def add_receiver(self, node_path, light_index=0):
        """
        Adiciona um objeto que recebe sombras.

        Args:
            node_path: NodePath do objeto
            light_index: Índice da luz (se houver múltiplas luzes)
        """
        if not node_path or light_index >= len(self.shadow_lights):
            return

        # Adiciona ao conjunto de objetos que recebem sombras
        self.shadow_receivers.add(node_path)

        # Configura o shader para renderizar com sombras
        light_np, _, texture, _ = self.shadow_lights[light_index]

        # Inputs para o shader
        node_path.setShaderInput("shadowMap", texture)
        node_path.setShaderInput("receiveShadow", True)

        # Direção da luz (no espaço global)
        light_dir = Vec3(0, 0, -1)  # Direção padrão
        light_rot = light_np.getQuat()
        light_dir = light_rot.xform(light_dir)
        node_path.setShaderInput("lightDir", light_dir)

        # Cor da luz e ambiente
        node_path.setShaderInput("lightColor", Vec4(1, 1, 1, 1))
        node_path.setShaderInput("ambientColor", Vec4(0.2, 0.2, 0.2, 1))

        # Configurar matriz de visualização da luz
        light_mat = light_np.getMat()
        node_path.setShaderInput("p3d_LightViewProjectionMatrix", light_mat)

        # Aplicar o shader de cena
        node_path.setShader(self.scene_shader)

    def update(self):
        """Atualiza as matrizes de sombra e outros parâmetros que mudam a cada frame."""
        for i, (light_np, camera, texture, _) in enumerate(self.shadow_lights):
            # Atualizar a direção da luz
            light_dir = Vec3(0, 0, -1)  # Direção padrão
            light_rot = light_np.getQuat()
            light_dir = light_rot.xform(light_dir)

            for receiver in self.shadow_receivers:
                # Atualizar direção da luz
                receiver.setShaderInput("lightDir", light_dir)

                # Atualizar matriz de visualização da luz
                light_mat = camera.getMat(self.scene_root)
                receiver.setShaderInput("p3d_LightViewProjectionMatrix", light_mat)


def setup_advanced_shadows(show_base, scene_root, light_np, casters, receivers, light_type="directional"):
    """
    Configura sombras avançadas para a cena.

    Args:
        show_base: Instância do ShowBase
        scene_root: Nó raiz da cena
        light_np: NodePath da luz
        casters: Lista de objetos que projetam sombras
        receivers: Lista de objetos que recebem sombras
        light_type: Tipo de luz ("directional", "spotlight", "point")

    Returns:
        ShadowManager: O gerenciador de sombras criado
    """
    # Criar o gerenciador de sombras
    shadow_manager = ShadowManager(show_base, scene_root)

    # Adicionar luz com sombras
    light_index = shadow_manager.add_shadow_light(light_np, light_type)

    if light_index < 0:
        print("Erro: Não foi possível adicionar luz com sombras")
        return None

    # Adicionar objetos que projetam sombras
    for caster in casters:
        shadow_manager.add_caster(caster)

    # Adicionar objetos que recebem sombras
    for receiver in receivers:
        shadow_manager.add_receiver(receiver, light_index)

    return shadow_manager