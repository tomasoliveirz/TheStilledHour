from typing import Dict, List, Callable, Optional
from direct.showbase.ShowBase import ShowBase
from panda3d.core import NodePath, Filename
import os

from src.utils.singleton import Singleton
from src.utils.event_bus import EventBus
from src.entities.entity import Entity

class SceneManager(metaclass=Singleton):
    """
    Gerencia cenas do jogo, responsável por carregar, limpar e mudar entre cenas.
    Mantém registro de todas as entidades na cena atual.
    """
    
    def __init__(self, show_base: Optional[ShowBase] = None):
        """
        Inicializa o SceneManager.
        
        Args:
            show_base: Instância do ShowBase do Panda3D
        """
        self._show_base = show_base
        self._current_scene: Optional[str] = None
        self._root_node: Optional[NodePath] = None
        self._entities: List[Entity] = []
        self._models_cache: Dict[str, NodePath] = {}
        self._event_bus = EventBus()
        
        # Sistema de colisão adicionado como parte do SceneManager
        self._collision_system = None
        
        # Callbacks chamados durante o carregamento/descarga de cena
        self._on_scene_load_start: List[Callable[[str], None]] = []
        self._on_scene_load_complete: List[Callable[[str], None]] = []
        self._on_scene_unload: List[Callable[[str], None]] = []
    
    def initialize(self, show_base: ShowBase) -> None:
        """
        Inicializa o SceneManager com o ShowBase.
        
        Args:
            show_base: Instância do ShowBase do Panda3D
        """
        self._show_base = show_base
        self._root_node = self._show_base.render.attachNewNode("scene_root")
        
        # Inicializa o sistema de colisão
        self._init_collision_system()
    
    def _init_collision_system(self) -> None:
        """Inicializa o sistema de colisão da cena."""
        if self._show_base:
            from src.systems.collision_system import CollisionSystem
            self._collision_system = CollisionSystem(self._show_base)
            self._collision_system.initialize()
            print("Sistema de colisão inicializado no SceneManager")
    
    def get_collision_system(self):
        """Retorna o sistema de colisão da cena."""
        return self._collision_system
    
    def load_scene(self, scene_name: str) -> None:
        """
        Carrega uma nova cena, limpando a anterior se necessário.
        
        Args:
            scene_name: Nome da cena a ser carregada
        """
        # Notifica início do carregamento
        for callback in self._on_scene_load_start:
            callback(scene_name)
        
        # Limpa cena atual se existir
        if self._current_scene:
            self.unload_current_scene()
        
        # Configura nova cena
        self._current_scene = scene_name
        
        # Recria o nó raiz da cena
        if self._root_node:
            self._root_node.removeNode()
        self._root_node = self._show_base.render.attachNewNode(f"scene_{scene_name}")
        
        # Reinicializa o sistema de colisão para a nova cena
        if not self._collision_system:
            self._init_collision_system()
        
        # Notifica que o carregamento foi concluído
        self._event_bus.publish("on_scene_loaded", scene_name)
        for callback in self._on_scene_load_complete:
            callback(scene_name)
    
    def unload_current_scene(self) -> None:
        """Descarrega a cena atual, limpando todos os objetos."""
        if not self._current_scene:
            return
        
        # Notifica handlers de unload
        scene_name = self._current_scene
        for callback in self._on_scene_unload:
            callback(scene_name)
        
        # Remove todas as entidades
        for entity in self._entities[:]:
            self.remove_entity(entity)
        
        # Limpa o nó raiz
        if self._root_node:
            self._root_node.removeNode()
            self._root_node = None
        
        # Publica evento
        self._event_bus.publish("on_scene_unloaded", scene_name)
        
        self._current_scene = None
    
    def add_entity(self, entity: Entity) -> None:
        """
        Adiciona uma entidade à cena atual.
        
        Args:
            entity: A entidade a ser adicionada
        """
        if entity not in self._entities:
            self._entities.append(entity)
            
            # Parenta o node da entidade ao root da cena
            if self._root_node and entity.node_path:
                entity.node_path.reparentTo(self._root_node)
                
            # Registra a entidade no sistema de colisão, se apropriado
            if self._collision_system:
                self._collision_system.add_entity(entity)
                
                # Registro especial para o jogador
                if entity.name == "Player":
                    self._collision_system.register_player(entity)
                
            # Publica evento
            self._event_bus.publish("on_entity_added", entity)
    
    def remove_entity(self, entity: Entity) -> None:
        """
        Remove uma entidade da cena atual.
        
        Args:
            entity: A entidade a ser removida
        """
        if entity in self._entities:
            self._entities.remove(entity)
            
            # Remove nó da cena
            if entity.node_path:
                entity.node_path.detachNode()
            
            # Publica evento
            self._event_bus.publish("on_entity_removed", entity)
    
    def get_entities(self) -> List[Entity]:
        """
        Retorna todas as entidades na cena atual.
        
        Returns:
            Lista de entidades
        """
        return self._entities.copy()
    
    def load_model(self, model_path: str) -> NodePath:
        """
        Carrega um modelo com cache.
        
        Args:
            model_path: Caminho para o modelo
            
        Returns:
            NodePath do modelo
        """
        # Verifica o cache primeiro
        if model_path in self._models_cache:
            # Retorna uma cópia do modelo em cache
            return self._models_cache[model_path].copyTo(self._root_node)
        
        # Carrega o modelo
        model = self._show_base.loader.loadModel(Filename.fromOsSpecific(model_path))
        
        if not model:
            raise ValueError(f"Falha ao carregar modelo: {model_path}")
        
        # Armazena no cache
        self._models_cache[model_path] = model
        
        # Retorna uma cópia
        return model.copyTo(self._root_node)
    
    def clear_cache(self) -> None:
        """Limpa o cache de modelos."""
        self._models_cache.clear()
    
    def register_on_scene_load_start(self, callback: Callable[[str], None]) -> None:
        """Registra callback para início de carregamento de cena."""
        if callback not in self._on_scene_load_start:
            self._on_scene_load_start.append(callback)
    
    def register_on_scene_load_complete(self, callback: Callable[[str], None]) -> None:
        """Registra callback para conclusão de carregamento de cena."""
        if callback not in self._on_scene_load_complete:
            self._on_scene_load_complete.append(callback)
    
    def register_on_scene_unload(self, callback: Callable[[str], None]) -> None:
        """Registra callback para descarregamento de cena."""
        if callback not in self._on_scene_unload:
            self._on_scene_unload.append(callback)
    
    @property
    def current_scene(self) -> Optional[str]:
        """Retorna o nome da cena atual."""
        return self._current_scene
    
    @property
    def root_node(self) -> Optional[NodePath]:
        """Retorna o nó raiz da cena atual."""
        return self._root_node