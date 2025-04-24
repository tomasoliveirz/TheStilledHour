from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple, List
from panda3d.core import NodePath, Vec3, Point3, TextureStage, Texture, TransparencyAttrib
from panda3d.core import CollisionNode, CollisionBox, BitMask32, Material

# Importação que estava faltando
from src.entities.entity import Entity
from src.entities.components.collider_component import ColliderComponent


class GameObject(ABC):
    """
    Classe base abstrata para todos os objetos do jogo.
    Implementa o padrão Template Method definindo o esqueleto da criação de objetos.
    """

    @abstractmethod
    def create(self, parent: NodePath, position: Vec3, scale: Vec3) -> Entity:
        """
        Método Template que define o processo de criação do objeto.

        Args:
            parent: NodePath pai onde o objeto será criado
            position: Posição (x, y, z) do objeto
            scale: Escala (sx, sy, sz) do objeto

        Returns:
            Entity: A entidade criada
        """
        pass

    def _add_collider(self,
                      entity: Entity,
                      shape_type: str = 'box',
                      dimensions: Tuple = None,
                      mass: float = 0.0,
                      is_trigger: bool = False) -> None:
        """
        Adiciona um collider à entidade.

        Args:
            entity: A entidade onde adicionar o collider
            shape_type: Tipo da forma de colisão ('box', 'sphere', 'capsule', etc.)
            dimensions: Dimensões da forma (depende do shape_type)
            mass: Massa do objeto (0 para estático)
            is_trigger: Se é um trigger (só detecta colisão) ou não
        """
        # CORREÇÃO: Configuração explícita de colisão
        collider = ColliderComponent(
            shape_type=shape_type,
            dimensions=dimensions,
            mass=mass,
            is_trigger=is_trigger
        )
        entity.add_component(collider)

        # CORREÇÃO: Adicionalmente, criar uma colisão Panda3D para garantir detecção
        if entity.node_path and shape_type == 'box' and dimensions:
            coll_node = CollisionNode(f'{entity.name}_collision')
            coll_node.addSolid(CollisionBox(Point3(0, 0, 0), dimensions[0], dimensions[1], dimensions[2]))
            coll_node.setIntoCollideMask(BitMask32.bit(0))  # Máscara de colisão padrão
            coll_np = entity.node_path.attachNewNode(coll_node)
            coll_np.setPos(0, 0, 0)

    def _apply_texture(self,
                       node_path: NodePath,
                       texture: Texture,
                       repeat_x: float = 1.0,
                       repeat_y: float = 1.0) -> None:
        """
        Aplica uma textura ao NodePath de forma segura e otimizada.
        Versão corrigida para garantir a visibilidade das texturas.

        Args:
            node_path: O NodePath onde aplicar a textura
            texture: A textura a ser aplicada
            repeat_x: Fator de repetição horizontal
            repeat_y: Fator de repetição vertical
        """
        if not node_path or not texture:
            print(f"Aviso: NodePath ou textura inválida")
            return

        try:
            # Limpa qualquer textura ou cor existente
            node_path.clearTexture()

            # CORREÇÃO: Configurações para garantir a visibilidade da textura
            node_path.clearColor()  # Remove qualquer cor que possa interferir
            node_path.setColorScale(1, 1, 1, 1)  # Escala de cor neutra

            # 1. Desativa transparência completamente
            node_path.setTransparency(TransparencyAttrib.M_none)

            # 2. Mostra ambos os lados dos polígonos (importante!)
            node_path.setTwoSided(True)

            # 3. Configura o estágio de textura e aplica
            ts = TextureStage.getDefault()
            node_path.setTexture(ts, texture)

            # 4. Configura repetição de textura
            if repeat_x != 1.0 or repeat_y != 1.0:
                node_path.setTexScale(ts, repeat_x, repeat_y)

            # 5. Configura um material simples para melhorar a aparência
            material = Material()
            material.setAmbient((0.8, 0.8, 0.8, 1))
            material.setDiffuse((1.0, 1.0, 1.0, 1))
            material.setSpecular((0.3, 0.3, 0.3, 1))
            material.setShininess(20)
            node_path.setMaterial(material)

            # 6. Desabilita shaders personalizados que possam interferir
            node_path.setShaderOff()

            # 7. Faz atualizações de hardware para garantir que a textura seja renderizada
            node_path.clearShaderInput()

            print(f"Textura aplicada com sucesso ao objeto: {node_path.getName()}")
        except Exception as e:
            print(f"Erro ao aplicar textura: {e}")

            # Tentativa de recuperação - aplicação simplificada
            try:
                # Tenta aplicar a textura de forma simples
                node_path.setTexture(texture, 1)
                print(f"Textura aplicada com método simplificado")
            except Exception as e2:
                print(f"Falha completa ao aplicar textura: {e2}")

                # Última opção: definir uma cor sólida
                node_path.setColor(0.7, 0.7, 0.7, 1.0)