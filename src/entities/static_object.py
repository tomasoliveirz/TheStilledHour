"""
Implementação de objetos estáticos do jogo (paredes, caixas, etc).
Versão corrigida com suporte a sombras.
"""

from typing import Optional, Tuple
from panda3d.core import NodePath, Vec3, Point3, LineSegs
from panda3d.core import GeomNode, Geom, GeomVertexFormat, GeomVertexData
from panda3d.core import GeomTriangles, GeomVertexWriter, GeomEnums, CullFaceAttrib
from panda3d.core import InternalName, CollisionNode, CollisionBox, BitMask32
# Importação explícita do GeomVertexArrayFormat
from panda3d.core import GeomVertexArrayFormat, Material, TextureStage, Texture, TransparencyAttrib

from src.entities.entity import Entity
from src.entities.components.transform_component import TransformComponent
from src.entities.components.collider_component import ColliderComponent

class StaticObject(Entity):
    """
    Entidade para objetos estáticos do cenário (paredes, caixas, etc).
    Implementa o padrão Facade para encapsular os componentes relacionados a objetos estáticos.
    Versão corrigida com suporte a sombras.
    """

    def __init__(self, name: str = None):
        """
        Inicializa um objeto estático.

        Args:
            name: Nome do objeto
        """
        super().__init__(name=name or "StaticObject")

        # Componentes serão adicionados em setup()
        self._transform: Optional[TransformComponent] = None
        self._collider: Optional[ColliderComponent] = None
        self._model_path: Optional[str] = None
        self._collision_np: Optional[NodePath] = None

        # Configurações de sombra
        self._casts_shadow = True
        self._receives_shadow = True

    def _add_panda3d_collision(self, shape_type: str, dimensions: Tuple) -> None:
        """
        Adiciona colisão nativa do Panda3D ao objeto.

        Args:
            shape_type: Tipo da forma ('box', 'sphere', 'capsule')
            dimensions: Dimensões da forma
        """
        from panda3d.core import CollisionNode, CollisionBox, CollisionSphere
        from panda3d.core import CollisionCapsule, BitMask32, Point3

        # Cria o nó de colisão
        coll_node = CollisionNode(f"{self.name}_collision")

        # Configuramos para receber colisões, mas não detectar
        coll_node.setIntoCollideMask(BitMask32.allOn())  # Tudo pode colidir com este objeto
        coll_node.setFromCollideMask(BitMask32(0))      # Não detecta colisões

        # Adiciona a forma apropriada
        if shape_type == 'box':
            # Cria um box com as dimensões fornecidas
            box = CollisionBox(Point3(0, 0, 0), dimensions[0], dimensions[1], dimensions[2])
            coll_node.addSolid(box)

        elif shape_type == 'sphere':
            # Cria uma esfera
            radius = dimensions[0] if len(dimensions) > 0 else 0.5
            sphere = CollisionSphere(0, 0, 0, radius)
            coll_node.addSolid(sphere)

        elif shape_type == 'capsule':
            # Cria uma cápsula
            radius = dimensions[0] if len(dimensions) > 0 else 0.3
            height = dimensions[1] if len(dimensions) > 1 else 1.0

            # Cria a cápsula entre dois pontos
            capsule = CollisionCapsule(
                0, 0, -height/2,  # Ponto inferior
                0, 0, height/2,   # Ponto superior
                radius            # Raio
            )
            coll_node.addSolid(capsule)

        # Adiciona o nó à hierarquia
        if self.node_path:
            self._collision_np = self.node_path.attachNewNode(coll_node)
            self._collision_np.setPos(0, 0, 0)

            # Para depuração visual (descomentar para visualizar colisões)
            # self._collision_np.show()

        print(f"Colisão Panda3D adicionada para {self.name}")

    def setup(self, parent: NodePath, model_path: str,
                position: Tuple[float, float, float] = (0, 0, 0),
                rotation: Tuple[float, float, float] = (0, 0, 0),
                scale: Tuple[float, float, float] = (1, 1, 1),
                shape_type: str = 'box',
                dimensions: Tuple = None,
                cast_shadow: bool = True,
                receive_shadow: bool = True) -> None:
        """
        Configura o objeto estático com sistema de colisão aprimorado e suporte a sombras.

        Args:
            parent: NodePath pai
            model_path: Caminho para o modelo 3D
            position: Posição inicial
            rotation: Rotação inicial em graus (h, p, r)
            scale: Escala inicial
            shape_type: Tipo da forma de colisão ('box', 'sphere', 'capsule', etc.)
            dimensions: Dimensões da forma de colisão (depende do shape_type)
            cast_shadow: Se o objeto projeta sombras
            receive_shadow: Se o objeto recebe sombras
        """
        # Inicializa o NodePath
        self.init_node_path(parent)
        self._model_path = model_path

        # Salva as configurações de sombra
        self._casts_shadow = cast_shadow
        self._receives_shadow = receive_shadow

        # Tenta carregar o modelo - CORRIGIDO: Não usa mais Loader.getGlobalPtr()
        try:
            # Tenta carregar o modelo usando o loader do ShowBase
            if hasattr(parent, 'getShowBase'):
                # Se o pai tem método getShowBase
                show_base = parent.getShowBase()
                model = show_base.loader.loadModel(model_path)
            else:
                # Alternativa: procura o loader no contexto global
                from direct.showbase.ShowBase import ShowBase
                import builtins
                if hasattr(builtins, 'base'):
                    model = builtins.base.loader.loadModel(model_path)
                else:
                    # Se tudo falhar, cria uma forma básica
                    print(f"Aviso: Não foi possível acessar loader. Criando forma básica para {model_path}")
                    model = None

            if model:
                model.reparentTo(self.node_path)
                # Aplica configurações de sombra ao modelo
                self._configure_shadows(model)
            else:
                # Se falhar o carregamento, cria uma forma simples
                print(f"Aviso: Não foi possível carregar modelo {model_path}. Criando forma básica.")
                self._create_proper_box()
        except Exception as e:
            print(f"Erro ao carregar modelo {model_path}: {e}")
            # Em caso de erro, cria uma forma simples
            self._create_proper_box()

        # Adiciona o componente de transformação
        self._transform = TransformComponent(position, rotation, scale)
        self.add_component(self._transform)

        # Calcula dimensões de colisão padrão se não fornecidas
        if dimensions is None:
            if shape_type == 'box':
                # Usa metade do tamanho da escala para o box de colisão
                half_x = scale[0] / 2.0
                half_y = scale[1] / 2.0
                half_z = scale[2] / 2.0
                dimensions = (half_x, half_y, half_z)
            else:
                # Dimensões padrão para outros tipos
                dimensions = (0.5, 0.5, 0.5)

        # Adiciona o componente de colisão - ainda mantemos isso para compatibilidade
        self._collider = ColliderComponent(
            shape_type=shape_type,
            dimensions=dimensions,
            mass=0.0  # Objetos estáticos têm massa zero
        )
        self.add_component(self._collider)

        # Ajustes específicos para paredes e caixas
        if "Wall" in self.name or "wall" in self.name.lower():
            self._setup_as_wall()
        elif "Box" in self.name or "box" in self.name.lower():
            self._setup_as_box()
        elif "Floor" in self.name or "floor" in self.name.lower():
            self._setup_as_floor()
        elif "Ceiling" in self.name or "ceiling" in self.name.lower():
            self._setup_as_ceiling()

        # Adiciona colisão explícita adicional para garantir detecção sólida
        self._add_explicit_collision(shape_type, dimensions)

        # Aplica transformações finais
        self._apply_transformations()

        # Configura sombras para o NodePath
        self._configure_shadows(self.node_path)

        # Aplica material adequado para sombras
        self._apply_material()

    def _configure_shadows(self, node_path: Optional[NodePath]) -> None:
        """
        Configura as propriedades de sombra para o NodePath.

        Args:
            node_path: O NodePath a configurar
        """
        if not node_path:
            return

        try:
            # CORRIGIDO: Configuração de sombras compatível com diversas versões do Panda3D
            if hasattr(node_path, 'setShaderInput'):
                # Configurar recebimento e projeção de sombras
                if self._casts_shadow:
                    node_path.setShaderInput("castShadow", 1)
                else:
                    node_path.setShaderInput("castShadow", 0)

                if self._receives_shadow:
                    node_path.setShaderInput("receiveShadow", 1)
                else:
                    node_path.setShaderInput("receiveShadow", 0)

            # Habilitar o shader automático (necessário para sombras)
            if hasattr(node_path, 'setShaderAuto'):
                node_path.setShaderAuto()

        except Exception as e:
            print(f"Erro ao configurar sombras para {self.name}: {e}")

    def _apply_transformations(self) -> None:
        """Aplica todas as transformações ao modelo."""
        if not self._transform or not self.node_path:
            return

        # Aplica posição, rotação e escala
        self.node_path.setPos(*self._transform.position)
        self.node_path.setHpr(*self._transform.rotation)
        self.node_path.setScale(*self._transform.scale)

    def _apply_material(self) -> None:
        """
        Aplica um material ao objeto para garantir boa aparência com sombras.
        """
        if not self.node_path:
            return

        try:
            # Cria um material básico
            material = Material()

            # Configura propriedades do material com base no tipo de objeto
            if "Wall" in self.name or "wall" in self.name.lower():
                # Material para paredes
                material.setAmbient((0.7, 0.7, 0.7, 1))  # Luz ambiente
                material.setDiffuse((0.9, 0.9, 0.9, 1))  # Luz difusa
                material.setSpecular((0.1, 0.1, 0.1, 1))  # Reflexos especulares
                material.setShininess(10)  # Brilho (menor = mais fosco)

            elif "Floor" in self.name or "floor" in self.name.lower():
                # Material para piso
                material.setAmbient((0.6, 0.6, 0.6, 1))
                material.setDiffuse((0.8, 0.8, 0.8, 1))
                material.setSpecular((0.3, 0.3, 0.3, 1))
                material.setShininess(30)  # Mais brilhante que paredes

            elif "Ceiling" in self.name or "ceiling" in self.name.lower():
                # Material para teto
                material.setAmbient((0.6, 0.6, 0.8, 1))  # Tom azulado
                material.setDiffuse((0.8, 0.8, 0.9, 1))
                material.setSpecular((0.2, 0.2, 0.2, 1))
                material.setShininess(15)

            elif "Box" in self.name or "box" in self.name.lower():
                # Material para caixas
                material.setAmbient((0.5, 0.3, 0.1, 1))  # Tom marrom
                material.setDiffuse((0.7, 0.4, 0.2, 1))
                material.setSpecular((0.2, 0.2, 0.2, 1))
                material.setShininess(20)

            else:
                # Material padrão para outros objetos
                material.setAmbient((0.5, 0.5, 0.5, 1))
                material.setDiffuse((0.7, 0.7, 0.7, 1))
                material.setSpecular((0.2, 0.2, 0.2, 1))
                material.setShininess(20)

            # Aplica o material
            self.node_path.setMaterial(material)

        except Exception as e:
            print(f"Erro ao aplicar material para {self.name}: {e}")

    def apply_texture(self, texture: Texture, repeat_x: float = 1.0, repeat_y: float = 1.0) -> None:
        """
        Aplica uma textura ao objeto.

        Args:
            texture: A textura a aplicar
            repeat_x: Fator de repetição horizontal
            repeat_y: Fator de repetição vertical
        """
        if not self.node_path or not texture:
            return

        try:
            # Limpa texturas existentes
            self.node_path.clearTexture()

            # Configura estágio de textura
            ts = TextureStage.getDefault()
            ts.setMode(TextureStage.MModulate)  # Modo de modulação para sombras

            # Aplica a textura
            self.node_path.setTexture(ts, texture)

            # Configura repetição
            if repeat_x != 1.0 or repeat_y != 1.0:
                self.node_path.setTexScale(ts, repeat_x, repeat_y)

            # Garante que a textura é exibida corretamente
            self.node_path.setTwoSided(True)

            print(f"Textura aplicada com sucesso ao objeto {self.name}")

        except Exception as e:
            print(f"Erro ao aplicar textura para {self.name}: {e}")

    def _add_explicit_collision(self, shape_type: str, dimensions: Tuple) -> None:
        """
        Adiciona colisão explícita para garantir detecção sólida.
        Este método adiciona colisões redundantes para maior robustez.

        Args:
            shape_type: Tipo de forma ('box', 'sphere', 'capsule')
            dimensions: Dimensões da forma
        """
        from panda3d.core import CollisionNode, CollisionBox, CollisionSphere
        from panda3d.core import CollisionCapsule, BitMask32, Point3

        if not self.node_path or not dimensions:
            return

        try:
            # Cria nó de colisão principal
            coll_node = CollisionNode(f"{self.name}_collision")

            # Objetos estáticos só recebem colisões mas não detectam
            coll_node.setFromCollideMask(BitMask32(0))
            coll_node.setIntoCollideMask(BitMask32.allOn())

            # Adiciona forma de colisão baseada no tipo
            if shape_type == 'box':
                box = CollisionBox(Point3(0, 0, 0),
                                dimensions[0], dimensions[1], dimensions[2])
                coll_node.addSolid(box)
            elif shape_type == 'sphere':
                radius = dimensions[0] if dimensions and len(dimensions) > 0 else 0.5
                sphere = CollisionSphere(0, 0, 0, radius)
                coll_node.addSolid(sphere)
            elif shape_type == 'capsule':
                radius = dimensions[0] if dimensions and len(dimensions) > 0 else 0.3
                height = dimensions[1] if dimensions and len(dimensions) > 1 else 1.0
                capsule = CollisionCapsule(0, 0, -height/2, 0, 0, height/2, radius)
                coll_node.addSolid(capsule)

            # Adiciona à hierarquia
            coll_np = self.node_path.attachNewNode(coll_node)
            coll_np.setPos(0, 0, 0)  # Relativo ao nó pai

            # Armazena referência
            self._collision_np = coll_np

            # Adiciona um segundo nó de colisão redundante com margens maiores
            # para garantir que não haja "vazamentos" nas colisões
            margin_node = CollisionNode(f"{self.name}_margin")
            margin_node.setFromCollideMask(BitMask32(0))
            margin_node.setIntoCollideMask(BitMask32.allOn())

            # Cria forma com margem ligeiramente maior (2%)
            if shape_type == 'box':
                margin_box = CollisionBox(Point3(0, 0, 0),
                                        dimensions[0] * 1.02,
                                        dimensions[1] * 1.02,
                                        dimensions[2] * 1.02)
                margin_node.addSolid(margin_box)
            elif shape_type == 'sphere':
                radius = dimensions[0] if dimensions and len(dimensions) > 0 else 0.5
                margin_sphere = CollisionSphere(0, 0, 0, radius * 1.02)
                margin_node.addSolid(margin_sphere)
            elif shape_type == 'capsule':
                radius = dimensions[0] if dimensions and len(dimensions) > 0 else 0.3
                height = dimensions[1] if dimensions and len(dimensions) > 1 else 1.0
                margin_capsule = CollisionCapsule(0, 0, -height/2, 0, 0, height/2, radius * 1.02)
                margin_node.addSolid(margin_capsule)

            # Adiciona à hierarquia
            margin_np = self.node_path.attachNewNode(margin_node)
            margin_np.setPos(0, 0, 0)

            # Armazena referência
            self._margin_collision_np = margin_np

            # Debug: mostrar formas de colisão (descomentado apenas para debug)
            debug_collisions = False
            if debug_collisions:
                coll_np.show()
                margin_np.show()

        except Exception as e:
            print(f"Erro ao adicionar colisão explícita para {self.name}: {e}")

    def _create_proper_box(self) -> None:
        """
        Cria uma caixa 3D com geometria correta para renderização.
        Versão corrigida que não depende do Loader.getGlobalPtr().
        """
        try:
            # Define a cor baseada no tipo de objeto
            if self.name.startswith("Floor") or "floor" in self.name.lower():
                color = (0.4, 0.4, 0.4, 1)  # Cinza escuro
            elif self.name.startswith("Wall") or "wall" in self.name.lower():
                color = (0.7, 0.7, 0.7, 1)  # Cinza claro
            elif self.name.startswith("Box") or "box" in self.name.lower():
                color = (0.6, 0.3, 0.1, 1)  # Marrom
            elif self.name.startswith("Ceiling") or "ceiling" in self.name.lower():
                color = (0.5, 0.5, 0.6, 1)  # Cinza azulado
            else:
                color = (0.5, 0.5, 0.5, 1)  # Cinza médio

            # Criação do formato do vértice
            from panda3d.core import GeomVertexArrayFormat, GeomVertexFormat, GeomVertexData
            from panda3d.core import Geom, GeomTriangles, GeomVertexWriter, GeomNode
            from panda3d.core import InternalName, GeomEnums, Point3

            array = GeomVertexArrayFormat()
            array.addColumn(InternalName.getVertex(), 3, GeomEnums.NTFloat32, GeomEnums.CPoint)
            array.addColumn(InternalName.getNormal(), 3, GeomEnums.NTFloat32, GeomEnums.CVector)
            array.addColumn(InternalName.getTexcoord(), 2, GeomEnums.NTFloat32, GeomEnums.CTexcoord)
            array.addColumn(InternalName.getColor(), 4, GeomEnums.NTFloat32, GeomEnums.CColor)

            format = GeomVertexFormat()
            format.addArray(array)
            format = GeomVertexFormat.registerFormat(format)

            vdata = GeomVertexData('box', format, Geom.UHStatic)

            # Cria escritores para todos os atributos
            vertex = GeomVertexWriter(vdata, 'vertex')
            normal = GeomVertexWriter(vdata, 'normal')
            texcoord = GeomVertexWriter(vdata, 'texcoord')
            color_writer = GeomVertexWriter(vdata, 'color')

            # Define os vértices da caixa (1x1x1 centrada na origem)
            # Frente (Y+)
            vertex.addData3f(-0.5, 0.5, -0.5)  # 0
            normal.addData3f(0, 1, 0)
            texcoord.addData2f(0, 0)
            color_writer.addData4f(*color)

            vertex.addData3f(0.5, 0.5, -0.5)  # 1
            normal.addData3f(0, 1, 0)
            texcoord.addData2f(1, 0)
            color_writer.addData4f(*color)

            vertex.addData3f(0.5, 0.5, 0.5)  # 2
            normal.addData3f(0, 1, 0)
            texcoord.addData2f(1, 1)
            color_writer.addData4f(*color)

            vertex.addData3f(-0.5, 0.5, 0.5)  # 3
            normal.addData3f(0, 1, 0)
            texcoord.addData2f(0, 1)
            color_writer.addData4f(*color)

            # Traseira (Y-)
            vertex.addData3f(-0.5, -0.5, -0.5)  # 4
            normal.addData3f(0, -1, 0)
            texcoord.addData2f(1, 0)
            color_writer.addData4f(*color)

            vertex.addData3f(0.5, -0.5, -0.5)  # 5
            normal.addData3f(0, -1, 0)
            texcoord.addData2f(0, 0)
            color_writer.addData4f(*color)

            vertex.addData3f(0.5, -0.5, 0.5)  # 6
            normal.addData3f(0, -1, 0)
            texcoord.addData2f(0, 1)
            color_writer.addData4f(*color)

            vertex.addData3f(-0.5, -0.5, 0.5)  # 7
            normal.addData3f(0, -1, 0)
            texcoord.addData2f(1, 1)
            color_writer.addData4f(*color)

            # Direita (X+)
            vertex.addData3f(0.5, -0.5, -0.5)  # 8
            normal.addData3f(1, 0, 0)
            texcoord.addData2f(0, 0)
            color_writer.addData4f(*color)

            vertex.addData3f(0.5, 0.5, -0.5)  # 9
            normal.addData3f(1, 0, 0)
            texcoord.addData2f(1, 0)
            color_writer.addData4f(*color)

            vertex.addData3f(0.5, 0.5, 0.5)  # 10
            normal.addData3f(1, 0, 0)
            texcoord.addData2f(1, 1)
            color_writer.addData4f(*color)

            vertex.addData3f(0.5, -0.5, 0.5)  # 11
            normal.addData3f(1, 0, 0)
            texcoord.addData2f(0, 1)
            color_writer.addData4f(*color)

            # Esquerda (X-)
            vertex.addData3f(-0.5, -0.5, -0.5)  # 12
            normal.addData3f(-1, 0, 0)
            texcoord.addData2f(1, 0)
            color_writer.addData4f(*color)

            vertex.addData3f(-0.5, 0.5, -0.5)  # 13
            normal.addData3f(-1, 0, 0)
            texcoord.addData2f(0, 0)
            color_writer.addData4f(*color)

            vertex.addData3f(-0.5, 0.5, 0.5)  # 14
            normal.addData3f(-1, 0, 0)
            texcoord.addData2f(0, 1)
            color_writer.addData4f(*color)

            vertex.addData3f(-0.5, -0.5, 0.5)  # 15
            normal.addData3f(-1, 0, 0)
            texcoord.addData2f(1, 1)
            color_writer.addData4f(*color)

            # Topo (Z+)
            vertex.addData3f(-0.5, -0.5, 0.5)  # 16
            normal.addData3f(0, 0, 1)  # Normal para cima
            texcoord.addData2f(0, 0)
            color_writer.addData4f(*color)

            vertex.addData3f(0.5, -0.5, 0.5)  # 17
            normal.addData3f(0, 0, 1)
            texcoord.addData2f(1, 0)
            color_writer.addData4f(*color)

            vertex.addData3f(0.5, 0.5, 0.5)  # 18
            normal.addData3f(0, 0, 1)
            texcoord.addData2f(1, 1)
            color_writer.addData4f(*color)

            vertex.addData3f(-0.5, 0.5, 0.5)  # 19
            normal.addData3f(0, 0, 1)
            texcoord.addData2f(0, 1)
            color_writer.addData4f(*color)

            # Base (Z-)
            vertex.addData3f(-0.5, -0.5, -0.5)  # 20
            normal.addData3f(0, 0, -1)
            texcoord.addData2f(0, 0)
            color_writer.addData4f(*color)

            vertex.addData3f(0.5, -0.5, -0.5)  # 21
            normal.addData3f(0, 0, -1)
            texcoord.addData2f(1, 0)
            color_writer.addData4f(*color)

            vertex.addData3f(0.5, 0.5, -0.5)  # 22
            normal.addData3f(0, 0, -1)
            texcoord.addData2f(1, 1)
            color_writer.addData4f(*color)

            vertex.addData3f(-0.5, 0.5, -0.5)  # 23
            normal.addData3f(0, 0, -1)
            texcoord.addData2f(0, 1)
            color_writer.addData4f(*color)

            # Cria os triângulos para cada face
            tris = GeomTriangles(Geom.UHStatic)

            # Frente
            tris.addVertices(0, 1, 2)
            tris.addVertices(0, 2, 3)

            # Traseira
            tris.addVertices(4, 6, 5)
            tris.addVertices(4, 7, 6)

            # Direita
            tris.addVertices(8, 9, 10)
            tris.addVertices(8, 10, 11)

            # Esquerda
            tris.addVertices(12, 14, 13)
            tris.addVertices(12, 15, 14)

            # Topo
            tris.addVertices(16, 17, 18)
            tris.addVertices(16, 18, 19)

            # Base
            tris.addVertices(20, 22, 21)
            tris.addVertices(20, 23, 22)

            # Cria o Geom e o adiciona ao GeomNode
            geom = Geom(vdata)
            geom.addPrimitive(tris)

            node = GeomNode('box')
            node.addGeom(geom)

            # Cria e anexa o NodePath
            np = self.node_path.attachNewNode(node)

            # Configuração para garantir visibilidade
            # Paredes e caixas renderizam ambos os lados
            from panda3d.core import CullFaceAttrib
            if "Box" in self.name or "Wall" in self.name or "wall" in self.name.lower():
                np.setTwoSided(True)
                np.setAttrib(CullFaceAttrib.make(CullFaceAttrib.MCullNone))
            else:
                # Outros objetos apenas o lado de fora
                np.setTwoSided(False)

            # Adiciona wireframe para melhor visibilidade
            self._add_wireframe_to_box(color)

            # Configura shader para sombras
            np.setShaderAuto()

            print(f"Caixa geométrica criada com sucesso para {self.name}")

        except Exception as e:
            print(f"Erro ao criar caixa: {e}")
            self._create_fallback_shape()

    # Restante dos métodos permanece igual...
    def _setup_as_wall(self) -> None:
        """Configurações específicas para paredes."""
        if self.node_path:
            self.node_path.setColor(0.7, 0.7, 0.7, 1.0)  # Cinza claro
            self.node_path.setTwoSided(True)  # Mostra ambos os lados

        # Configurações específicas para componente de colisão
        if self._collider and self._collider.physics_node:
            try:
                # Configurar para alta fricção
                if hasattr(self._collider.physics_node, 'setFriction'):
                    self._collider.physics_node.setFriction(1.0)

                # Sem restituição (bounce)
                if hasattr(self._collider.physics_node, 'setRestitution'):
                    self._collider.physics_node.setRestitution(0.0)

                # Garantir que colide com tudo
                if hasattr(self._collider.physics_node, 'setIntoCollideMask'):
                    self._collider.physics_node.setIntoCollideMask(BitMask32.allOn())

                # Não detecta colisões (apenas recebe)
                if hasattr(self._collider.physics_node, 'setFromCollideMask'):
                    self._collider.physics_node.setFromCollideMask(BitMask32(0))
            except Exception as e:
                print(f"Aviso ao configurar propriedades de colisão para parede: {e}")

        # Configuração de sombra para paredes (recebem mas não projetam)
        self._casts_shadow = False
        self._receives_shadow = True

    def _setup_as_floor(self) -> None:
        """Configurações específicas para o chão."""
        if self.node_path:
            self.node_path.setColor(0.4, 0.4, 0.4, 1.0)  # Cinza escuro
            self.node_path.setTwoSided(True)  # Mostra ambos os lados

        # Configurações específicas para componente de colisão
        if self._collider and self._collider.physics_node:
            try:
                # Boa fricção, mas não máxima
                if hasattr(self._collider.physics_node, 'setFriction'):
                    self._collider.physics_node.setFriction(0.8)

                # Sem restituição (bounce)
                if hasattr(self._collider.physics_node, 'setRestitution'):
                    self._collider.physics_node.setRestitution(0.0)

                # Garantir que colide com tudo
                if hasattr(self._collider.physics_node, 'setIntoCollideMask'):
                    self._collider.physics_node.setIntoCollideMask(BitMask32.allOn())

                # Não detecta colisões (apenas recebe)
                if hasattr(self._collider.physics_node, 'setFromCollideMask'):
                    self._collider.physics_node.setFromCollideMask(BitMask32(0))
            except Exception as e:
                print(f"Aviso ao configurar propriedades de colisão para chão: {e}")

        # Configuração de sombra para piso (recebe mas não projeta)
        self._casts_shadow = False
        self._receives_shadow = True

    def _setup_as_ceiling(self) -> None:
        """Configurações específicas para o teto."""
        if self.node_path:
            self.node_path.setColor(0.6, 0.6, 0.8, 1.0)  # Cinza azulado
            self.node_path.setTwoSided(True)  # Mostra ambos os lados

        # Configurações específicas para componente de colisão
        if self._collider and self._collider.physics_node:
            try:
                # Alta fricção
                if hasattr(self._collider.physics_node, 'setFriction'):
                    self._collider.physics_node.setFriction(1.0)

                # Sem restituição (bounce)
                if hasattr(self._collider.physics_node, 'setRestitution'):
                    self._collider.physics_node.setRestitution(0.0)

                # Garantir que colide com tudo
                if hasattr(self._collider.physics_node, 'setIntoCollideMask'):
                    self._collider.physics_node.setIntoCollideMask(BitMask32.allOn())

                # Não detecta colisões (apenas recebe)
                if hasattr(self._collider.physics_node, 'setFromCollideMask'):
                    self._collider.physics_node.setFromCollideMask(BitMask32(0))
            except Exception as e:
                print(f"Aviso ao configurar propriedades de colisão para teto: {e}")

        # Configuração de sombra para teto (recebe mas não projeta)
        self._casts_shadow = False
        self._receives_shadow = True

    def _setup_as_box(self) -> None:
        """Configurações específicas para caixas."""
        if self.node_path:
            self.node_path.setColor(0.6, 0.3, 0.1, 1.0)  # Marrom
            self.node_path.setTwoSided(True)  # Mostra ambos os lados

        # Configurações específicas para componente de colisão
        if self._collider and self._collider.physics_node:
            try:
                # Boa fricção
                if hasattr(self._collider.physics_node, 'setFriction'):
                    self._collider.physics_node.setFriction(0.9)

                # Pequena restituição (bounce)
                if hasattr(self._collider.physics_node, 'setRestitution'):
                    self._collider.physics_node.setRestitution(0.1)

                # Garantir que colide com tudo
                if hasattr(self._collider.physics_node, 'setIntoCollideMask'):
                    self._collider.physics_node.setIntoCollideMask(BitMask32.allOn())

                # Não detecta colisões (apenas recebe)
                if hasattr(self._collider.physics_node, 'setFromCollideMask'):
                    self._collider.physics_node.setFromCollideMask(BitMask32(0))
            except Exception as e:
                print(f"Aviso ao configurar propriedades de colisão para caixa: {e}")

        # Configuração de sombra para caixas (projeta e recebe)
        self._casts_shadow = True
        self._receives_shadow = True

    def _add_wireframe_to_box(self, color: Tuple[float, float, float, float]) -> None:
        """
        Adiciona linhas de contorno à forma para melhor visualização.

        Args:
            color: Cor do wireframe (RGBA)
        """
        try:
            # Cria linhas
            ls = LineSegs()
            ls.setThickness(1)

            # Cor ligeiramente mais clara para o wireframe
            wire_color = (
                min(color[0] + 0.2, 1.0),
                min(color[1] + 0.2, 1.0),
                min(color[2] + 0.2, 1.0),
                color[3]
            )
            ls.setColor(*wire_color)

            # Desenha o contorno da caixa
            # Base
            ls.moveTo(-0.5, -0.5, -0.5)
            ls.drawTo(0.5, -0.5, -0.5)
            ls.drawTo(0.5, 0.5, -0.5)
            ls.drawTo(-0.5, 0.5, -0.5)
            ls.drawTo(-0.5, -0.5, -0.5)

            # Topo
            ls.moveTo(-0.5, -0.5, 0.5)
            ls.drawTo(0.5, -0.5, 0.5)
            ls.drawTo(0.5, 0.5, 0.5)
            ls.drawTo(-0.5, 0.5, 0.5)
            ls.drawTo(-0.5, -0.5, 0.5)

            # Laterais
            ls.moveTo(-0.5, -0.5, -0.5)
            ls.drawTo(-0.5, -0.5, 0.5)

            ls.moveTo(0.5, -0.5, -0.5)
            ls.drawTo(0.5, -0.5, 0.5)

            ls.moveTo(0.5, 0.5, -0.5)
            ls.drawTo(0.5, 0.5, 0.5)

            ls.moveTo(-0.5, 0.5, -0.5)
            ls.drawTo(-0.5, 0.5, 0.5)

            # Cria e anexa o nó
            node = ls.create()
            self.node_path.attachNewNode(node)
        except Exception as e:
            print(f"Erro ao adicionar wireframe: {e}")

    def _create_fallback_shape(self) -> None:
        """Cria uma forma simples como fallback em caso de erro."""
        try:
            ls = LineSegs()
            ls.setThickness(3)
            ls.setColor(1, 0, 0, 1)  # Vermelho

            # Cria uma cruz simples
            ls.moveTo(-0.5, 0, 0)
            ls.drawTo(0.5, 0, 0)

            ls.moveTo(0, -0.5, 0)
            ls.drawTo(0, 0.5, 0)

            ls.moveTo(0, 0, -0.5)
            ls.drawTo(0, 0, 0.5)

            # Cria e anexa o nó
            node = ls.create()
            self.node_path.attachNewNode(node)

            print(f"Forma de fallback criada para {self.name}")
        except Exception as e:
            print(f"Erro ao criar forma de fallback: {e}")