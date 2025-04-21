from typing import Dict, List, Callable, Set, Tuple, Any, Optional
from direct.showbase.ShowBase import ShowBase
from panda3d.core import WindowProperties

from src.utils.singleton import Singleton
from src.utils.event_bus import EventBus
from src.core.config import MOUSE_SENSITIVITY, KEY_FORWARD, KEY_BACKWARD, KEY_LEFT, KEY_RIGHT

class InputState:
    """Representa o estado atual de um dispositivo de entrada."""
    def __init__(self):
        self.key_down: Set[str] = set()  # Teclas pressionadas neste frame
        self.key_pressed: Set[str] = set()  # Teclas que acabaram de ser pressionadas neste frame
        self.key_released: Set[str] = set()  # Teclas que acabaram de ser liberadas neste frame
        self.mouse_position: Tuple[float, float] = (0, 0)  # Posição do mouse
        self.mouse_delta: Tuple[float, float] = (0, 0)  # Movimento do mouse neste frame
        self.mouse_buttons_down: Set[str] = set()  # Botões do mouse pressionados
        self.mouse_wheel_delta: float = 0  # Movimento da roda do mouse neste frame

class InputManager(metaclass=Singleton):
    """
    Gerencia inputs do usuário, abstraindo teclado e mouse.
    Implementa o padrão Singleton e Observer para notificar mudanças nos inputs.
    """
    
    def __init__(self):
        self._show_base: Optional[ShowBase] = None
        self._event_bus = EventBus()
        self._current_state = InputState()
        self._previous_state = InputState()
        
        # Estado do mouse
        self._mouse_x = 0
        self._mouse_y = 0
        self._last_mouse_x = 0
        self._last_mouse_y = 0
        self._mouse_visible = True
        
        # Mapeamento de teclas para ações
        self._key_action_map: Dict[str, str] = {
            KEY_FORWARD: "move_forward",
            KEY_BACKWARD: "move_backward",
            KEY_LEFT: "move_left",
            KEY_RIGHT: "move_right",
        }
        
        # Callbacks para eventos de input
        self._action_callbacks: Dict[str, List[Callable[..., None]]] = {}
    
    def initialize(self, show_base: ShowBase) -> None:
        """
        Inicializa o InputManager com o ShowBase e configura os event handlers.
        
        Args:
            show_base: Instância do ShowBase do Panda3D
        """
        self._show_base = show_base
        
        # Registra eventos de teclado
        for key in self._key_action_map.keys():
            self._show_base.accept(key, self._on_key_down, [key])
            self._show_base.accept(key + "-up", self._on_key_up, [key])
            
        # Registra eventos do mouse
        self._show_base.accept("mouse1", self._on_mouse_button_down, ["mouse1"])
        self._show_base.accept("mouse1-up", self._on_mouse_button_up, ["mouse1"])
        self._show_base.accept("mouse2", self._on_mouse_button_down, ["mouse2"])
        self._show_base.accept("mouse2-up", self._on_mouse_button_up, ["mouse2"])
        self._show_base.accept("mouse3", self._on_mouse_button_down, ["mouse3"])
        self._show_base.accept("mouse3-up", self._on_mouse_button_up, ["mouse3"])
        self._show_base.accept("wheel_up", self._on_mouse_wheel, [1])
        self._show_base.accept("wheel_down", self._on_mouse_wheel, [-1])
        
        # Configuração inicial do mouse
        self.set_mouse_visible(False)
    
    def update(self) -> None:
        """Atualiza o estado de input para este frame."""
        # Guarda o estado anterior
        self._previous_state = self._current_state
        
        # Cria novo estado
        new_state = InputState()
        new_state.key_down = self._current_state.key_down.copy()
        new_state.key_pressed = set()  # Limpa teclas pressionadas
        new_state.key_released = set()  # Limpa teclas liberadas
        
        # Atualiza posição e delta do mouse
        if self._show_base:
            if self._show_base.mouseWatcherNode.hasMouse():
                self._mouse_x = self._show_base.mouseWatcherNode.getMouseX()
                self._mouse_y = self._show_base.mouseWatcherNode.getMouseY()
                
                # Calcula delta do mouse
                mouse_delta_x = self._mouse_x - self._last_mouse_x
                mouse_delta_y = self._mouse_y - self._last_mouse_y
                
                new_state.mouse_position = (self._mouse_x, self._mouse_y)
                new_state.mouse_delta = (mouse_delta_x * MOUSE_SENSITIVITY, 
                                        mouse_delta_y * MOUSE_SENSITIVITY)
                
                self._last_mouse_x = self._mouse_x
                self._last_mouse_y = self._mouse_y
            else:
                new_state.mouse_position = self._current_state.mouse_position
                new_state.mouse_delta = (0, 0)
        
        # Mantém botões de mouse pressionados
        new_state.mouse_buttons_down = self._current_state.mouse_buttons_down.copy()
        
        # Atualiza o estado atual
        self._current_state = new_state
        
        # Recentraliza o mouse se estiver capturado
        if self._show_base and not self._mouse_visible:
            props = WindowProperties()
            props.setCursorHidden(True)
            props.setMouseMode(WindowProperties.M_relative)
            self._show_base.win.requestProperties(props)
    
    def register_action_callback(self, action: str, callback: Callable[..., None]) -> None:
        """
        Registra um callback para uma ação específica.
        
        Args:
            action: Nome da ação
            callback: Função a ser chamada quando a ação for acionada
        """
        if action not in self._action_callbacks:
            self._action_callbacks[action] = []
        
        if callback not in self._action_callbacks[action]:
            self._action_callbacks[action].append(callback)
    
    def unregister_action_callback(self, action: str, callback: Callable[..., None]) -> None:
        """
        Remove o registro de um callback para uma ação.
        
        Args:
            action: Nome da ação
            callback: Função registrada anteriormente
        """
        if action in self._action_callbacks and callback in self._action_callbacks[action]:
            self._action_callbacks[action].remove(callback)
    
    def is_key_down(self, key: str) -> bool:
        """
        Verifica se uma tecla está pressionada.
        
        Args:
            key: A tecla a verificar
            
        Returns:
            True se a tecla estiver pressionada, False caso contrário
        """
        return key in self._current_state.key_down
    
    def is_key_pressed(self, key: str) -> bool:
        """
        Verifica se uma tecla acabou de ser pressionada neste frame.
        
        Args:
            key: A tecla a verificar
            
        Returns:
            True se a tecla acabou de ser pressionada, False caso contrário
        """
        return key in self._current_state.key_pressed
    
    def is_key_released(self, key: str) -> bool:
        """
        Verifica se uma tecla acabou de ser liberada neste frame.
        
        Args:
            key: A tecla a verificar
            
        Returns:
            True se a tecla acabou de ser liberada, False caso contrário
        """
        return key in self._current_state.key_released
    
    def is_mouse_button_down(self, button: str) -> bool:
        """
        Verifica se um botão do mouse está pressionado.
        
        Args:
            button: O botão a verificar ('mouse1', 'mouse2', etc.)
            
        Returns:
            True se o botão estiver pressionado, False caso contrário
        """
        return button in self._current_state.mouse_buttons_down
    
    def get_mouse_position(self) -> Tuple[float, float]:
        """
        Retorna a posição atual do mouse.
        
        Returns:
            Tupla (x, y) com a posição do mouse
        """
        return self._current_state.mouse_position
    
    def get_mouse_delta(self) -> Tuple[float, float]:
        """
        Retorna o movimento do mouse neste frame.
        
        Returns:
            Tupla (delta_x, delta_y) com o movimento do mouse
        """
        return self._current_state.mouse_delta
    
    def set_mouse_visible(self, visible: bool) -> None:
        """
        Define se o cursor do mouse deve estar visível.
        
        Args:
            visible: True para mostrar o cursor, False para ocultar
        """
        if self._show_base and self._mouse_visible != visible:
            self._mouse_visible = visible
            
            props = WindowProperties()
            props.setCursorHidden(not visible)
            
            if visible:
                props.setMouseMode(WindowProperties.M_absolute)
            else:
                props.setMouseMode(WindowProperties.M_relative)
                
            self._show_base.win.requestProperties(props)
    
    def _on_key_down(self, key: str) -> None:
        """
        Callback para tecla pressionada.
        
        Args:
            key: A tecla pressionada
        """
        if key not in self._current_state.key_down:
            self._current_state.key_down.add(key)
            self._current_state.key_pressed.add(key)
            
            # Verifica se a tecla está mapeada para uma ação
            if key in self._key_action_map:
                action = self._key_action_map[key]
                
                # Notifica callbacks registrados para esta ação
                if action in self._action_callbacks:
                    for callback in self._action_callbacks[action]:
                        callback(True)
                        
                # Publica evento
                self._event_bus.publish(f"on_action_{action}", True)
    
    def _on_key_up(self, key: str) -> None:
        """
        Callback para tecla liberada.
        
        Args:
            key: A tecla liberada
        """
        if key in self._current_state.key_down:
            self._current_state.key_down.remove(key)
            self._current_state.key_released.add(key)
            
            # Verifica se a tecla está mapeada para uma ação
            if key in self._key_action_map:
                action = self._key_action_map[key]
                
                # Notifica callbacks registrados para esta ação
                if action in self._action_callbacks:
                    for callback in self._action_callbacks[action]:
                        callback(False)
                        
                # Publica evento
                self._event_bus.publish(f"on_action_{action}", False)
    
    def _on_mouse_button_down(self, button: str) -> None:
        """
        Callback para botão do mouse pressionado.
        
        Args:
            button: O botão pressionado
        """
        self._current_state.mouse_buttons_down.add(button)
        self._event_bus.publish(f"on_mouse_button_down", button)
    
    def _on_mouse_button_up(self, button: str) -> None:
        """
        Callback para botão do mouse liberado.
        
        Args:
            button: O botão liberado
        """
        if button in self._current_state.mouse_buttons_down:
            self._current_state.mouse_buttons_down.remove(button)
        self._event_bus.publish(f"on_mouse_button_up", button)
    
    def _on_mouse_wheel(self, delta: int) -> None:
        """
        Callback para movimento da roda do mouse.
        
        Args:
            delta: A quantidade e direção do movimento
        """
        self._current_state.mouse_wheel_delta = delta
        self._event_bus.publish("on_mouse_wheel", delta)