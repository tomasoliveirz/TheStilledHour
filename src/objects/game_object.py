from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple, List
from panda3d.core import NodePath, Vec3, Point3, TextureStage, Texture, TransparencyAttrib
from panda3d.core import CollisionNode, CollisionBox, BitMask32, Material

from src.entities.entity import Entity
from src.entities.components.transform_component import TransformComponent
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
        
        Args:
            node_path: O NodePath onde aplicar a textura
            texture: A textura a ser aplicada
            repeat_x: Fator de repetição horizontal
            repeat_y: Fator de repetição vertical
        """
        # Limpa qualquer textura ou cor existente
        node_path.clearTexture()
        node_path.clearColor()
        
        # CORREÇÃO: Configurações avançadas para garantir opacidade
        # 1. Desativa transparência completamente
        node_path.setTransparency(TransparencyAttrib.M_none)
        
        # 2. Define cor branca sólida (totalmente opaca)
        node_path.setColor(1, 1, 1, 1)
        
        # 3. Mostra ambos os lados dos polígonos
        node_path.setTwoSided(True)
        
        # 4. Aplica a textura com repetição configurável
        ts = TextureStage.getDefault()
        
        # CORREÇÃO: Força formato RGB (sem alfa) para a textura
        texture.setFormat(Texture.F_rgb)
        
        # Aplica textura e escala
        node_path.setTexture(texture)
        node_path.setTexScale(ts, repeat_x, repeat_y)
        
        # CORREÇÃO: Aplica um material para garantir opacidade e solidez visual
        material = Material()
        material.setAmbient((1, 1, 1, 1))
        material.setDiffuse((1, 1, 1, 1))
        material.setSpecular((0.3, 0.3, 0.3, 1))
        material.setShininess(30)
        node_path.setMaterial(material)