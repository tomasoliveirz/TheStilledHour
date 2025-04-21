from typing import Dict, Optional, Tuple
from panda3d.core import Texture, NodePath, Vec3, CullFaceAttrib, TextureStage, TransparencyAttrib
from direct.showbase.ShowBase import ShowBase
import os

from src.entities.entity import Entity
from src.objects.static_game_object import StaticGameObject
from src.objects.physics_game_object import PhysicsGameObject
from src.core.config import MODELS_DIR, TEXTURES_DIR

class GameObjectFactory:
    """
    Fábrica para criar diferentes tipos de objetos do jogo.
    Implementa o padrão Abstract Factory, gerenciando diferentes tipos de objetos.
    Também implementa Flyweight para recursos compartilhados como texturas.
    """
    
    def __init__(self, show_base: ShowBase):
        """
        Inicializa a fábrica.
        
        Args:
            show_base: Instância do ShowBase do Panda3D
        """
        self._show_base = show_base
        self._textures: Dict[str, Texture] = {}
        self._prototypes: Dict[str, StaticGameObject] = {}
        
        # Inicializa recursos
        self._init_resources()
    
    def _init_resources(self) -> None:
        """Inicializa os recursos compartilhados (texturas, etc)."""
        # Carrega texturas comuns
        self._load_texture("wall", os.path.join(TEXTURES_DIR, "wall.jpg"))
        self._load_texture("floor", os.path.join(TEXTURES_DIR, "floor.jpg"))
        self._load_texture("ceiling", os.path.join(TEXTURES_DIR, "ceiling.jpg"))
        self._load_texture("box", os.path.join(TEXTURES_DIR, "box.jpg"))
        
        # Cria protótipos para objetos comuns
        self._register_wall_prototype()
        self._register_floor_prototype()
        self._register_ceiling_prototype()
        self._register_box_prototype()
        self._register_movable_box_prototype()
    
    """
    Substituição completa do método _load_texture no GameObjectFactory 
    para ignorar completamente o sistema de mipmaps que está causando o erro
    """

    def _load_texture(self, name: str, path: str) -> None:
        """
        Carrega uma textura de forma super simplificada, evitando mipmaps completamente.
        
        Args:
            name: Nome de referência para a textura
            path: Caminho para o arquivo de textura
        """
        try:
            # MUDANÇA RADICAL: Em vez de carregar a textura real, criar uma textura em memória
            # com uma cor simples para evitar completamente o problema de mipmaps
            from panda3d.core import Texture, PNMImage
            
            # Criar uma imagem simples de 2x2 pixels
            if name == "wall":
                color = (0.7, 0.7, 0.7)  # Cinza claro para parede
            elif name == "floor":
                color = (0.4, 0.4, 0.4)  # Cinza escuro para chão
            elif name == "ceiling":
                color = (0.6, 0.6, 0.8)  # Azulado para teto
            else:  # box ou qualquer outro
                color = (0.6, 0.3, 0.1)  # Marrom para caixas
            
            # Cria uma imagem simples
            img = PNMImage(2, 2)
            img.fill(color[0], color[1], color[2])
            
            # Cria uma textura a partir da imagem
            texture = Texture(name)
            texture.load(img)
            
            # Configurações super básicas
            texture.setMagfilter(Texture.FT_nearest)  # Filtro mais simples possível
            texture.setMinfilter(Texture.FT_nearest)  # Sem mipmaps
            texture.setWrapU(Texture.WM_repeat)
            texture.setWrapV(Texture.WM_repeat)
            
            self._textures[name] = texture
            print(f"Textura simples '{name}' criada com sucesso - cor: {color}")
        except Exception as e:
            print(f"ERRO ao criar textura '{name}': {e}")
            
            # Fallback absoluto: se falhar, cria uma textura vazia
            texture = Texture(name)
            self._textures[name] = texture
            print(f"Textura vazia '{name}' criada como fallback de emergência")
            
    def _register_wall_prototype(self) -> None:
        """Registra o protótipo para paredes."""
        if "wall" in self._textures:
            self._prototypes["wall"] = StaticGameObject(
                name="Wall",
                model_path=f"{MODELS_DIR}/environment/wall.egg",
                texture=self._textures["wall"]
            )
    
    def _register_floor_prototype(self) -> None:
        """Registra o protótipo para pisos."""
        if "floor" in self._textures:
            # Se a textura "floor" não existir, usa a textura "box" como fallback
            texture = self._textures.get("floor", self._textures.get("box"))
            self._prototypes["floor"] = StaticGameObject(
                name="Floor",
                model_path=f"{MODELS_DIR}/environment/room.egg",
                texture=texture
            )
    
    def _register_ceiling_prototype(self) -> None:
        """Registra o protótipo para tetos."""
        if "ceiling" in self._textures:
            # Se a textura "ceiling" não existir, usa a textura "box" como fallback
            texture = self._textures.get("ceiling", self._textures.get("box"))
            self._prototypes["ceiling"] = StaticGameObject(
                name="Ceiling",
                model_path=f"{MODELS_DIR}/environment/room.egg",
                texture=texture
            )
    
    def _register_box_prototype(self) -> None:
        """Registra o protótipo para caixas estáticas."""
        if "box" in self._textures:
            self._prototypes["box"] = StaticGameObject(
                name="Box",
                model_path=f"{MODELS_DIR}/environment/box.egg",
                texture=self._textures["box"]
            )
    
    def _register_movable_box_prototype(self) -> None:
        """Registra o protótipo para caixas movíveis (com física)."""
        if "box" in self._textures:
            self._prototypes["movable_box"] = PhysicsGameObject(
                name="MovableBox",
                model_path=f"{MODELS_DIR}/environment/box.egg",
                texture=self._textures["box"],
                mass=10.0,  # 10kg - peso razoável para uma caixa pequena
                friction=0.5,
                restitution=0.2  # Pequeno bounce quando cai
            )
    


    def create_ceiling(self, parent: NodePath, position: Tuple[float, float, float], 
                      scale: Tuple[float, float, float]) -> Entity:
        """
        Cria um teto.
        
        Args:
            parent: NodePath pai
            position: Posição (x, y, z)
            scale: Escala (sx, sy, sz)
            
        Returns:
            A entidade do teto
        """
        entity = self._prototypes["ceiling"].create(
            parent, Vec3(*position), Vec3(*scale))
        
        # CORREÇÃO: Configurações extras para garantir que o teto seja opaco e sólido
        if entity.node_path:
            np = entity.node_path
            np.setTransparency(TransparencyAttrib.M_none)  # Desativa transparência
            np.setColor(1, 1, 1, 1)  # Cor branca opaca
            np.setAttrib(CullFaceAttrib.make(CullFaceAttrib.MCullNone))  # Desativa culling
            
            # Aplicação adicional da textura para garantir
            if "ceiling" in self._textures:
                texture = self._textures["ceiling"]
                ts = TextureStage('ts')
                np.setTexture(ts, texture)
                np.setTexScale(ts, 2, 2)
        
        return entity
    

    def create_wall(self, parent: NodePath, position: Tuple[float, float, float], 
                scale: Tuple[float, float, float]) -> Entity:
        """
        Cria uma parede.
        
        Args:
            parent: NodePath pai
            position: Posição (x, y, z)
            scale: Escala (sx, sy, sz)
            
        Returns:
            A entidade da parede
        """
        entity = self._prototypes["wall"].create(
            parent, Vec3(*position), Vec3(*scale))
        
        # CORREÇÃO: Configurações extras para garantir que a parede seja opaca e sólida
        if entity.node_path:
            np = entity.node_path
            np.setTransparency(TransparencyAttrib.M_none)  # Desativa transparência
            np.setColor(1, 1, 1, 1)  # Cor branca opaca
            np.setAttrib(CullFaceAttrib.make(CullFaceAttrib.MCullNone))  # Desativa culling
            
            # Aplicação adicional da textura para garantir
            if "wall" in self._textures:
                texture = self._textures["wall"]
                ts = TextureStage('ts')
                np.setTexture(ts, texture)
                np.setTexScale(ts, 2, 2)
            
            # Adiciona uma caixa de colisão explícita adicional
            from panda3d.core import CollisionNode, CollisionBox, BitMask32, Point3
            coll_node = CollisionNode(f'{entity.name}_solid_collision')
            
            # Dimensões da parede
            half_x, half_y, half_z = scale[0]/2, scale[1]/2, scale[2]/2
            
            # Cria uma caixa de colisão ligeiramente maior para garantir colisões sólidas
            coll_node.addSolid(CollisionBox(Point3(0, 0, 0), half_x*1.01, half_y*1.01, half_z*1.01))
            coll_node.setIntoCollideMask(BitMask32.allOn())  # Colide com tudo
            coll_node.setFromCollideMask(BitMask32(0))  # Não detecta colisões
            
            # Adiciona o nó de colisão à hierarquia
            coll_np = entity.node_path.attachNewNode(coll_node)
            coll_np.setPos(0, 0, 0)
        
        return entity

    def create_floor(self, parent: NodePath, position: Tuple[float, float, float], 
                    scale: Tuple[float, float, float]) -> Entity:
        """
        Cria um piso.
        
        Args:
            parent: NodePath pai
            position: Posição (x, y, z)
            scale: Escala (sx, sy, sz)
            
        Returns:
            A entidade do piso
        """
        entity = self._prototypes["floor"].create(
            parent, Vec3(*position), Vec3(*scale))
        
        # CORREÇÃO: Configurações extras para garantir que o piso seja opaco e sólido
        if entity.node_path:
            np = entity.node_path
            np.setTransparency(TransparencyAttrib.M_none)  # Desativa transparência
            np.setColor(1, 1, 1, 1)  # Cor branca opaca
            np.setAttrib(CullFaceAttrib.make(CullFaceAttrib.MCullNone))  # Desativa culling
            
            # Aplicação adicional da textura para garantir
            if "floor" in self._textures:
                texture = self._textures["floor"]
                ts = TextureStage('ts')
                np.setTexture(ts, texture)
                np.setTexScale(ts, 2, 2)
            
            # Adiciona uma caixa de colisão explícita adicional
            from panda3d.core import CollisionNode, CollisionBox, BitMask32, Point3
            coll_node = CollisionNode(f'{entity.name}_solid_collision')
            
            # Dimensões do piso
            half_x, half_y, half_z = scale[0]/2, scale[1]/2, scale[2]/2
            
            # Cria uma caixa de colisão ligeiramente maior para garantir colisões sólidas
            coll_node.addSolid(CollisionBox(Point3(0, 0, 0), half_x*1.01, half_y*1.01, half_z*1.01))
            coll_node.setIntoCollideMask(BitMask32.allOn())  # Colide com tudo
            coll_node.setFromCollideMask(BitMask32(0))  # Não detecta colisões
            
            # Adiciona o nó de colisão à hierarquia
            coll_np = entity.node_path.attachNewNode(coll_node)
            coll_np.setPos(0, 0, 0)
        
        return entity

    def create_box(self, parent: NodePath, position: Tuple[float, float, float], 
                scale: Tuple[float, float, float], movable: bool = False) -> Entity:
        """
        Cria uma caixa.
        
        Args:
            parent: NodePath pai
            position: Posição (x, y, z)
            scale: Escala (sx, sy, sz)
            movable: Se a caixa pode ser movida pela física
            
        Returns:
            A entidade da caixa
        """
        prototype_key = "movable_box" if movable else "box"
        entity = self._prototypes[prototype_key].create(
            parent, Vec3(*position), Vec3(*scale))
        
        # CORREÇÃO: Configurações extras para garantir que a caixa seja opaca e sólida
        if entity.node_path:
            np = entity.node_path
            np.setTransparency(TransparencyAttrib.M_none)  # Desativa transparência
            np.setColor(1, 1, 1, 1)  # Cor branca opaca
            np.setAttrib(CullFaceAttrib.make(CullFaceAttrib.MCullNone))  # Desativa culling
            
            # Aplicação adicional da textura para garantir
            if "box" in self._textures:
                texture = self._textures["box"]
                ts = TextureStage('ts')
                np.setTexture(ts, texture)
                size_factor = scale[0]
                repeat = 1.0 / size_factor if size_factor > 0 else 1.0
                np.setTexScale(ts, repeat, repeat)
            
            # Para caixas não-móveis, adiciona uma caixa de colisão explícita adicional
            if not movable:
                from panda3d.core import CollisionNode, CollisionBox, BitMask32, Point3
                coll_node = CollisionNode(f'{entity.name}_solid_collision')
                
                # Dimensões da caixa
                half_x, half_y, half_z = scale[0]/2, scale[1]/2, scale[2]/2
                
                # Cria uma caixa de colisão ligeiramente maior para garantir colisões sólidas
                coll_node.addSolid(CollisionBox(Point3(0, 0, 0), half_x*1.01, half_y*1.01, half_z*1.01))
                coll_node.setIntoCollideMask(BitMask32.allOn())  # Colide com tudo
                coll_node.setFromCollideMask(BitMask32(0))  # Não detecta colisões
                
                # Adiciona o nó de colisão à hierarquia
                coll_np = entity.node_path.attachNewNode(coll_node)
                coll_np.setPos(0, 0, 0)
        
        return entity



    def create_custom_static_object(self, parent: NodePath, 
                                  name: str,
                                  model_path: str,
                                  texture_name: str,
                                  position: Tuple[float, float, float],
                                  scale: Tuple[float, float, float],
                                  collision_dimensions: Optional[Tuple] = None) -> Optional[Entity]:
        """
        Cria um objeto estático personalizado.
        
        Args:
            parent: NodePath pai
            name: Nome do objeto
            model_path: Caminho para o modelo
            texture_name: Nome da textura a usar
            position: Posição (x, y, z)
            scale: Escala (sx, sy, sz)
            collision_dimensions: Dimensões de colisão ou None para usar escala
            
        Returns:
            A entidade criada ou None se falhar
        """
        if texture_name not in self._textures:
            print(f"Erro: Textura '{texture_name}' não encontrada")
            return None
            
        # Cria um objeto personalizado
        custom_object = StaticGameObject(
            name=name,
            model_path=model_path,
            texture=self._textures[texture_name],
            collision_dimensions=collision_dimensions
        )
        
        entity = custom_object.create(parent, Vec3(*position), Vec3(*scale))
        
        # CORREÇÃO: Configurações extras para garantir que o objeto seja opaco e sólido
        if entity.node_path:
            np = entity.node_path
            np.setTransparency(TransparencyAttrib.M_none)  # Desativa transparência
            np.setColor(1, 1, 1, 1)  # Cor branca opaca
            np.setAttrib(CullFaceAttrib.make(CullFaceAttrib.MCullNone))  # Desativa culling
            
            # Aplicação adicional da textura para garantir
            texture = self._textures[texture_name]
            ts = TextureStage('ts')
            np.setTexture(ts, texture)
            np.setTexScale(ts, 2, 2)
        
        return entity