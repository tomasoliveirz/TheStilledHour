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
        print("Inicializando recursos e carregando texturas...")
        
        # Carrega textura de parede (tenta múltiplas extensões)
        self._load_texture_with_fallbacks("wall", ["wall.jpg", "wall.jpeg", "wall.png"])
        
        # Carrega outras texturas
        self._load_texture_with_fallbacks("floor", ["floor.jpg"])
        self._load_texture_with_fallbacks("ceiling", ["ceiling.jpg"])
        self._load_texture_with_fallbacks("box", ["box.jpg"])
        
        # Cria protótipos para objetos comuns
        self._register_wall_prototype()
        self._register_floor_prototype()
        self._register_ceiling_prototype()
        self._register_box_prototype()
        self._register_movable_box_prototype()
        
        print(f"GameObjectFactory inicializado com {len(self._textures)} texturas carregadas")
    
    def _load_texture_with_fallbacks(self, name: str, filenames: list) -> None:
        """
        Tenta carregar uma textura com vários possíveis nomes de arquivo.
        
        Args:
            name: Nome de referência para a textura
            filenames: Lista de possíveis nomes de arquivo para tentar
        """
        # Armazena todos os possíveis caminhos para tentar
        paths_to_try = []
        
        # 1. Caminhos na pasta principal de texturas
        for filename in filenames:
            paths_to_try.append(os.path.join(TEXTURES_DIR, filename))
        
        # 2. Caminhos na pasta environment dentro de texturas
        for filename in filenames:
            paths_to_try.append(os.path.join(TEXTURES_DIR, "environment", filename))
            
        # 3. Caminhos na pasta de modelos (algumas texturas podem estar lá)
        for filename in filenames:
            paths_to_try.append(os.path.join(MODELS_DIR, "environment", filename))
        
        # Tenta cada caminho até encontrar um válido
        for path in paths_to_try:
            if os.path.exists(path):
                print(f"Encontrada textura '{name}' em: {path}")
                self._load_texture(name, path)
                if name in self._textures:
                    return  # Sucesso!
        
        # Se chegamos aqui, nenhum arquivo foi encontrado
        print(f"AVISO: Nenhum arquivo de textura encontrado para '{name}'")
        print(f"Caminhos verificados: {paths_to_try}")
        
        # Cria uma textura procedural como fallback
        self._create_procedural_texture(name)
    
    def _load_texture(self, name: str, path: str) -> None:
        """
        Carrega uma textura a partir de um arquivo.
        
        Args:
            name: Nome de referência para a textura
            path: Caminho para o arquivo de textura
        """
        try:
            print(f"Carregando textura '{name}' de: {path}")
            
            # Usa o loader do Panda3D para carregar a textura
            texture = self._show_base.loader.loadTexture(path)
            
            if texture:
                # Configura as propriedades da textura
                texture.setMagfilter(Texture.FT_linear)
                texture.setMinfilter(Texture.FT_linear)
                texture.setWrapU(Texture.WM_repeat)
                texture.setWrapV(Texture.WM_repeat)
                
                # Armazena a textura carregada
                self._textures[name] = texture
                print(f"Textura '{name}' carregada com sucesso!")
            else:
                print(f"Falha ao carregar textura '{name}' - o loader retornou None")
                
        except Exception as e:
            print(f"ERRO ao carregar textura '{name}' de {path}: {e}")
    
    def _create_procedural_texture(self, name: str) -> None:
        """
        Cria uma textura procedural como fallback quando não é possível carregar de arquivo.
        
        Args:
            name: Nome de referência para a textura
        """
        from panda3d.core import PNMImage
        
        print(f"Criando textura procedural para '{name}'")
        
        try:
            # Cria uma imagem em memória
            img = PNMImage(64, 64)
            
            # Define a cor base baseada no tipo
            if name == "wall":
                base_color = (0.7, 0.7, 0.7)  # Cinza claro
                pattern = "bricks"
            elif name == "floor":
                base_color = (0.5, 0.5, 0.5)  # Cinza médio
                pattern = "tiles"
            elif name == "ceiling":
                base_color = (0.6, 0.6, 0.8)  # Azulado claro
                pattern = "noise"
            else:  # box ou padrão
                base_color = (0.6, 0.3, 0.1)  # Marrom
                pattern = "wood"
            
            # Preenche com a cor base
            img.fill(base_color[0], base_color[1], base_color[2])
            
            # Adiciona um padrão
            if pattern == "bricks":
                # Padrão de tijolos para paredes
                for y in range(0, 64, 8):
                    offset = 8 if (y // 8) % 2 == 0 else 0
                    for x in range(0, 64, 16):
                        # Desenha "tijolos"
                        for i in range(min(16, 64 - (x + offset))):
                            for j in range(min(8, 64 - y)):
                                if i == 0 or i == 15 or j == 0 or j == 7:
                                    # Linhas escuras entre os tijolos
                                    img.setXel(x + offset + i, y + j, *[c * 0.7 for c in base_color])
                                else:
                                    # Variação dentro do tijolo
                                    noise = ((i + j) % 2) * 0.05
                                    img.setXel(x + offset + i, y + j, 
                                              min(1.0, base_color[0] + noise),
                                              min(1.0, base_color[1] + noise),
                                              min(1.0, base_color[2] + noise))
            
            elif pattern == "tiles":
                # Padrão de ladrilhos para chão
                for y in range(64):
                    for x in range(64):
                        tile_x = (x // 16) % 2
                        tile_y = (y // 16) % 2
                        
                        # Alterna cores como um tabuleiro
                        if (tile_x + tile_y) % 2 == 0:
                            factor = 0.9  # Mais escuro
                        else:
                            factor = 1.1  # Mais claro
                            
                        # Adiciona uma borda escura
                        if x % 16 == 0 or y % 16 == 0:
                            factor = 0.7
                            
                        img.setXel(x, y, 
                                  min(1.0, base_color[0] * factor),
                                  min(1.0, base_color[1] * factor),
                                  min(1.0, base_color[2] * factor))
            
            elif pattern == "wood":
                # Padrão de madeira para caixas
                for y in range(64):
                    for x in range(64):
                        # Granulação vertical da madeira
                        grain = (x + y//4) % 16
                        if grain < 3 or grain > 13:
                            # Linhas mais escuras
                            factor = 0.8
                        else:
                            # Variação sutil
                            factor = 0.95 + ((x*y) % 10) / 100.0
                            
                        img.setXel(x, y, 
                                  base_color[0] * factor,
                                  base_color[1] * factor,
                                  base_color[2] * factor)
            
            else:  # noise (teto)
                # Padrão de ruído para teto
                for y in range(64):
                    for x in range(64):
                        # Ruído simples
                        noise = ((x*3 + y*5) % 10) / 50.0
                        
                        img.setXel(x, y, 
                                  min(1.0, base_color[0] + noise),
                                  min(1.0, base_color[1] + noise),
                                  min(1.0, base_color[2] + noise))
            
            # Cria uma textura a partir da imagem
            texture = Texture(name)
            texture.load(img)
            
            # Configura a textura
            texture.setMagfilter(Texture.FT_linear)
            texture.setMinfilter(Texture.FT_linear)
            texture.setWrapU(Texture.WM_repeat)
            texture.setWrapV(Texture.WM_repeat)
            
            # Armazena a textura
            self._textures[name] = texture
            print(f"Textura procedural '{name}' criada com sucesso!")
            
        except Exception as e:
            print(f"ERRO ao criar textura procedural '{name}': {e}")
            
            # Último recurso: textura sólida simples
            try:
                # Cria uma imagem muito simples 2x2
                img = PNMImage(2, 2)
                img.fill(base_color[0], base_color[1], base_color[2])
                
                texture = Texture(name)
                texture.load(img)
                
                # Configurações básicas
                texture.setMagfilter(Texture.FT_nearest)
                texture.setMinfilter(Texture.FT_nearest)
                texture.setWrapU(Texture.WM_repeat)
                texture.setWrapV(Texture.WM_repeat)
                
                self._textures[name] = texture
                print(f"Textura sólida de emergência '{name}' criada como último recurso")
            except Exception as e2:
                print(f"ERRO CRÍTICO! Não foi possível criar nenhuma textura para '{name}': {e2}")
    
    def _register_wall_prototype(self) -> None:
        """Registra o protótipo para paredes."""
        if "wall" in self._textures:
            self._prototypes["wall"] = StaticGameObject(
                name="Wall",
                model_path=f"{MODELS_DIR}/environment/wall.egg",
                texture=self._textures["wall"]
            )
            print("Protótipo de parede registrado")
    
    def _register_floor_prototype(self) -> None:
        """Registra o protótipo para pisos."""
        texture = self._textures.get("floor")
        if not texture and "box" in self._textures:
            texture = self._textures["box"]
            print("Usando textura de caixa como fallback para piso")
            
        if texture:
            self._prototypes["floor"] = StaticGameObject(
                name="Floor",
                model_path=f"{MODELS_DIR}/environment/room.egg",
                texture=texture
            )
            print("Protótipo de piso registrado")
    
    def _register_ceiling_prototype(self) -> None:
        """Registra o protótipo para tetos."""
        texture = self._textures.get("ceiling")
        if not texture and "box" in self._textures:
            texture = self._textures["box"]
            print("Usando textura de caixa como fallback para teto")
            
        if texture:
            self._prototypes["ceiling"] = StaticGameObject(
                name="Ceiling",
                model_path=f"{MODELS_DIR}/environment/room.egg",
                texture=texture
            )
            print("Protótipo de teto registrado")
    
    def _register_box_prototype(self) -> None:
        """Registra o protótipo para caixas estáticas."""
        if "box" in self._textures:
            self._prototypes["box"] = StaticGameObject(
                name="Box",
                model_path=f"{MODELS_DIR}/environment/box.egg",
                texture=self._textures["box"]
            )
            print("Protótipo de caixa registrado")
    
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
            print("Protótipo de caixa móvel registrado")
    
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
        if "ceiling" not in self._prototypes:
            print("ERRO: Protótipo de teto não registrado!")
            return None
            
        entity = self._prototypes["ceiling"].create(
            parent, Vec3(*position), Vec3(*scale))
        
        # Configurações extras para garantir que o teto seja visível
        if entity and entity.node_path:
            np = entity.node_path
            
            # Limpa configurações que possam interferir
            np.clearColor()
            np.clearColorScale()
            np.setTwoSided(True)  # Mostra ambos os lados
            
            # Aplicação explícita da textura para garantir visibilidade
            if "ceiling" in self._textures:
                texture = self._textures["ceiling"]
                ts = TextureStage('ts')
                np.setTexture(ts, texture)
                np.setTexScale(ts, 2, 2)
                
                # Aplica material para melhorar iluminação
                from panda3d.core import Material
                material = Material()
                material.setAmbient((0.8, 0.8, 0.8, 1))
                material.setDiffuse((1.0, 1.0, 1.0, 1))
                material.setSpecular((0.3, 0.3, 0.3, 1))
                material.setShininess(20)
                np.setMaterial(material)
        
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
        if "wall" not in self._prototypes:
            print("ERRO: Protótipo de parede não registrado!")
            return None
            
        entity = self._prototypes["wall"].create(
            parent, Vec3(*position), Vec3(*scale))
        
        # Configurações extras para garantir que a parede seja visível
        if entity and entity.node_path:
            np = entity.node_path
            
            # Limpa configurações que possam interferir
            np.clearColor()
            np.clearColorScale()
            np.setTwoSided(True)  # Mostra ambos os lados
            
            # Aplicação explícita da textura para garantir visibilidade
            if "wall" in self._textures:
                texture = self._textures["wall"]
                ts = TextureStage('ts')
                np.setTexture(ts, texture)
                np.setTexScale(ts, 2, 2)
                
                # Aplica material para melhorar iluminação
                from panda3d.core import Material
                material = Material()
                material.setAmbient((0.8, 0.8, 0.8, 1))
                material.setDiffuse((1.0, 1.0, 1.0, 1))
                material.setSpecular((0.3, 0.3, 0.3, 1))
                material.setShininess(20)
                np.setMaterial(material)
            
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
        if "floor" not in self._prototypes:
            print("ERRO: Protótipo de piso não registrado!")
            return None
            
        entity = self._prototypes["floor"].create(
            parent, Vec3(*position), Vec3(*scale))
        
        # Configurações extras para garantir que o piso seja visível
        if entity and entity.node_path:
            np = entity.node_path
            
            # Limpa configurações que possam interferir
            np.clearColor()
            np.clearColorScale()
            np.setTwoSided(True)  # Mostra ambos os lados
            
            # Aplicação explícita da textura para garantir visibilidade
            if "floor" in self._textures:
                texture = self._textures["floor"]
                ts = TextureStage('ts')
                np.setTexture(ts, texture)
                np.setTexScale(ts, 2, 2)
                
                # Aplica material para melhorar iluminação
                from panda3d.core import Material
                material = Material()
                material.setAmbient((0.8, 0.8, 0.8, 1))
                material.setDiffuse((1.0, 1.0, 1.0, 1))
                material.setSpecular((0.3, 0.3, 0.3, 1))
                material.setShininess(20)
                np.setMaterial(material)
            
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
        
        if prototype_key not in self._prototypes:
            print(f"ERRO: Protótipo de caixa '{prototype_key}' não registrado!")
            return None
            
        entity = self._prototypes[prototype_key].create(
            parent, Vec3(*position), Vec3(*scale))
        
        # Configurações extras para garantir que a caixa seja visível
        if entity and entity.node_path:
            np = entity.node_path
            
            # Limpa configurações que possam interferir
            np.clearColor()
            np.clearColorScale()
            np.setTwoSided(True)  # Mostra ambos os lados
            
            # Aplicação explícita da textura para garantir visibilidade
            if "box" in self._textures:
                texture = self._textures["box"]
                ts = TextureStage('ts')
                np.setTexture(ts, texture)
                
                # Escala de textura baseada no tamanho da caixa
                size_factor = max(scale[0], 1.0)
                repeat = 1.0 / size_factor
                np.setTexScale(ts, repeat, repeat)
                
                # Aplica material para melhorar iluminação
                from panda3d.core import Material
                material = Material()
                material.setAmbient((0.8, 0.8, 0.8, 1))
                material.setDiffuse((1.0, 1.0, 1.0, 1))
                material.setSpecular((0.3, 0.3, 0.3, 1))
                material.setShininess(20)
                np.setMaterial(material)
            
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
        
        # Configurações extras para garantir que o objeto seja visível
        if entity and entity.node_path:
            np = entity.node_path
            
            # Limpa configurações que possam interferir
            np.clearColor()
            np.clearColorScale()
            np.setTwoSided(True)  # Mostra ambos os lados
            
            # Aplicação explícita da textura para garantir visibilidade
            texture = self._textures[texture_name]
            ts = TextureStage('ts')
            np.setTexture(ts, texture)
            np.setTexScale(ts, 2, 2)
            
            # Aplica material para melhorar iluminação
            from panda3d.core import Material
            material = Material()
            material.setAmbient((0.8, 0.8, 0.8, 1))
            material.setDiffuse((1.0, 1.0, 1.0, 1))
            material.setSpecular((0.3, 0.3, 0.3, 1))
            material.setShininess(20)
            np.setMaterial(material)
        
        return entity