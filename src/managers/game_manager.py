from enum import Enum, auto
from typing import Dict, Type, Optional, Callable
from src.utils.singleton import Singleton
from src.utils.event_bus import EventBus

class GameState(Enum):
    """Estados possíveis do jogo."""
    MAIN_MENU = auto()
    LOADING = auto()
    PLAYING = auto()
    PAUSED = auto()
    GAME_OVER = auto()
    CREDITS = auto()
    PHASE1_MOVEMENT = auto()  # Estado específico para a Fase 1 (movimento e colisões)

class GameStateHandler:
    """
    Classe base para handlers de estado de jogo (Padrão State).
    Implementa interface para entrar, atualizar e sair de estados.
    """
    def enter(self) -> None:
        """Chamado quando entramos neste estado."""
        pass
    
    def update(self, dt: float) -> None:
        """
        Atualiza a lógica deste estado.
        
        Args:
            dt: Delta time (tempo desde o último frame)
        """
        pass
    
    def exit(self) -> None:
        """Chamado quando saímos deste estado."""
        pass

class GameManager(metaclass=Singleton):
    """
    Gerencia os estados do jogo e a transição entre eles.
    Implementa o padrão State para gerenciar diferentes estados do jogo.
    """
    
    def __init__(self):
        self._states: Dict[GameState, GameStateHandler] = {}
        self._current_state: Optional[GameState] = None
        self._current_handler: Optional[GameStateHandler] = None
        self._event_bus = EventBus()
        self._paused = False
        
    def register_state(self, state: GameState, handler: GameStateHandler) -> None:
        """
        Registra um handler para um estado específico.
        
        Args:
            state: O estado do jogo a ser registrado
            handler: O handler para esse estado
        """
        self._states[state] = handler
    
    def change_state(self, new_state: GameState) -> None:
        """
        Muda o estado atual do jogo.
        
        Args:
            new_state: O novo estado para o qual mudar
        """
        # Verifica se o novo estado está registrado
        if new_state not in self._states:
            raise ValueError(f"Estado não registrado: {new_state}")
        
        # Sai do estado atual, se houver um
        if self._current_handler:
            self._current_handler.exit()
        
        # Registra o novo estado como atual
        self._current_state = new_state
        self._current_handler = self._states[new_state]
        
        # Entra no novo estado
        self._current_handler.enter()
        
        # Publica evento de mudança de estado
        self._event_bus.publish("on_game_state_changed", new_state)
    
    def update(self, dt: float) -> None:
        """
        Atualiza o estado atual do jogo.
        
        Args:
            dt: Delta time (tempo desde o último frame)
        """
        if self._current_handler and not self._paused:
            self._current_handler.update(dt)
    
    def pause(self) -> None:
        """Pausa a atualização do estado atual."""
        if not self._paused:
            self._paused = True
            self._event_bus.publish("on_game_paused")
    
    def resume(self) -> None:
        """Continua a atualização do estado atual."""
        if self._paused:
            self._paused = False
            self._event_bus.publish("on_game_resumed")
    
    def toggle_pause(self) -> None:
        """Alterna entre pausado e não pausado."""
        if self._paused:
            self.resume()
        else:
            self.pause()
    
    @property
    def current_state(self) -> Optional[GameState]:
        """Retorna o estado atual do jogo."""
        return self._current_state
    
    @property
    def is_paused(self) -> bool:
        """Retorna se o jogo está pausado."""
        return self._paused