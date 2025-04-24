from typing import Optional, Tuple, List
from panda3d.core import NodePath, Vec3, Point3, Texture, BitMask32, CollisionNode, CollisionBox
from panda3d.core import TextureStage, Material, CullFaceAttrib, TransparencyAttrib
from src.entities.entity import Entity
from src.entities.static_object import StaticObject
from src.objects.game_object import GameObject


class StaticGameObject(GameObject):
    """
    Classe base para objetos estáticos do jogo.
    Implementa o padrão Factory Method para criar objetos estáticos.
    """

    def __init__(self,
                 name: str,
                 model_path: str,
                 texture: Texture,
                 collision_dimensions: Optional[Tuple] = None):
        """
        Inicializa um objeto estático.

        Args:
            name: Nome base do objeto
            model_path: Caminho para o modelo 3D
            texture: Textura a ser aplicada
            collision_dimensions: Dimensões para colisão (se None, usa metade da escala)
        """
        self._name = name
        self._model_path = model_path
        self._texture = texture
        self._collision_dimensions = collision_dimensions

    def create(self, parent: NodePath, position: Vec3, scale: Vec3) -> Entity:
        """
        Cria uma instância do objeto estático.

        Args:
            parent: NodePath pai
            position: Posição (Vec3)
            scale: Escala (Vec3)

        Returns:
            A entidade criada
        """
        # Cria um objeto estático
        entity = StaticObject(f"{self._name}_{id(position)}")

        # Define as dimensões de colisão se não especificadas
        dims = self._collision_dimensions
        if dims is None:
            dims = (scale.x / 2, scale.y / 2, scale.z / 2)

        # Configura o objeto
        entity.setup(
            parent=parent,
            model_path=self._model_path,
            position=(position.x, position.y, position.z),
            scale=(scale.x, scale.y, scale.z),
            shape_type="box",
            dimensions=dims
        )

        # CORREÇÃO: Garante colisão sólida também no sistema Panda3D
        coll_node = CollisionNode(f'{entity.name}_collision')
        coll_node.addSolid(CollisionBox(Point3(0, 0, 0), dims[0], dims[1], dims[2]))
        coll_node.setIntoCollideMask(BitMask32.bit(0))  # Máscara padrão
        coll_np = entity.node_path.attachNewNode(coll_node)
        coll_np.setPos(0, 0, 0)

        # CORREÇÃO: Aplica a textura com configurações melhoradas para visibilidade
        self._enhanced_apply_texture(entity.node_path, self._texture, repeat_x=2.0, repeat_y=2.0)

        return entity

    def _enhanced_apply_texture(self, node_path: NodePath, texture: Texture, repeat_x: float = 1.0,
                                repeat_y: float = 1.0) -> None:
        """
        Versão melhorada para aplicar textura com mais garantias de visibilidade.

        Args:
            node_path: O NodePath onde aplicar a textura
            texture: A textura a ser aplicada
            repeat_x: Fator de repetição horizontal
            repeat_y: Fator de repetição vertical
        """
        if not node_path or not texture:
            print(f"Aviso: NodePath ou textura inválida para {self._name}")
            return

        try:
            # 1. Limpa texturas e cores existentes
            node_path.clearTexture()
            node_path.clearColor()
            node_path.clearColorScale()

            # CORREÇÃO: Não usar clearShaderInput sem argumentos
            try:
                if hasattr(node_path, 'clearShaderInput'):
                    # Passa um nome ou "*" para limpar todos
                    node_path.clearShaderInput("*")
            except:
                # Ignora erros aqui - opcional
                pass

            node_path.clearMaterial()

            # 2. Garante renderização dos dois lados
            node_path.setTwoSided(True)

            # 3. Desativa efeitos de transparência
            node_path.setTransparency(TransparencyAttrib.M_none)
            node_path.setAttrib(CullFaceAttrib.make(CullFaceAttrib.MCullNone))

            # 4. Define escala de cor para branco puro para não afetar a textura
            node_path.setColorScale(1, 1, 1, 1)

            # 5. Configura modo de textura e aplica a textura
            ts = TextureStage.getDefault()
            ts.setMode(TextureStage.MModulate)  # Modo modulate para melhor aparência
            node_path.setTexture(ts, texture)

            # 6. Configura repetição de textura
            if repeat_x != 1.0 or repeat_y != 1.0:
                node_path.setTexScale(ts, repeat_x, repeat_y)

            # 7. Adiciona material para melhorar a iluminação
            material = Material()
            material.setAmbient((0.8, 0.8, 0.8, 1))
            material.setDiffuse((1.0, 1.0, 1.0, 1))
            material.setSpecular((0.3, 0.3, 0.3, 1))
            material.setShininess(20)
            node_path.setMaterial(material)

            # 8. Desabilita shader automático que pode interferir
            if hasattr(node_path, 'setShaderOff'):
                node_path.setShaderOff()

            # 9. Se for um tipo específico de objeto, faz ajustes adicionais
            if "Wall" in self._name:
                # Paredes têm repetição vertical maior
                node_path.setTexScale(ts, repeat_x, repeat_y * 2)
            elif "Box" in self._name:
                # Caixas usam repetição ajustada ao tamanho
                size_factor = max(node_path.getScale().x, 1.0)
                adjusted_repeat = 1.0 / size_factor
                node_path.setTexScale(ts, adjusted_repeat, adjusted_repeat)

            print(f"Textura aplicada com sucesso ao objeto: {node_path.getName()}")
        except Exception as e:
            print(f"Erro ao aplicar textura a {self._name}: {e}")

            # Tentativa de recuperação - aplicação simplificada
            try:
                # Tenta aplicar a textura de forma simples
                node_path.setTexture(texture, 1)
                print(f"Textura aplicada com método simplificado")
            except Exception as e2:
                print(f"Falha completa ao aplicar textura: {e2}")

                # Última opção: definir uma cor sólida baseada no tipo
                if "Wall" in self._name:
                    node_path.setColor(0.7, 0.7, 0.7, 1.0)  # Cinza claro
                elif "Floor" in self._name:
                    node_path.setColor(0.4, 0.4, 0.4, 1.0)  # Cinza escuro
                elif "Ceiling" in self._name:
                    node_path.setColor(0.6, 0.6, 0.8, 1.0)  # Azulado
                else:  # Caixas ou outros
                    node_path.setColor(0.6, 0.3, 0.1, 1.0)  # Marrom