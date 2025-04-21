from typing import Dict, List, Callable, Any
from src.utils.singleton import Singleton

class EventBus(metaclass=Singleton):
    """
    Implementação do padrão Observer para comunicação entre sistemas.
    Permite que componentes publiquem e se inscrevam em eventos sem acoplamento direto.
    """
    
    def __init__(self):
        # Mapa de eventos para handlers: {event_name: [handler1, handler2, ...]}
        self._subscribers: Dict[str, List[Callable]] = {}
    
    def subscribe(self, event_name: str, handler: Callable) -> None:
        """Inscreve um handler em um tipo de evento específico."""
        if event_name not in self._subscribers:
            self._subscribers[event_name] = []
        
        if handler not in self._subscribers[event_name]:
            self._subscribers[event_name].append(handler)
    
    def unsubscribe(self, event_name: str, handler: Callable) -> None:
        """Remove a inscrição de um handler para um evento específico."""
        if event_name in self._subscribers and handler in self._subscribers[event_name]:
            self._subscribers[event_name].remove(handler)
            
            # Limpeza se não houver mais inscritos para este evento
            if not self._subscribers[event_name]:
                del self._subscribers[event_name]
    
    def publish(self, event_name: str, *args: Any, **kwargs: Any) -> None:
        """Publica um evento, notificando todos os handlers inscritos."""
        if event_name in self._subscribers:
            for handler in self._subscribers[event_name]:
                handler(*args, **kwargs)
    
    def clear_all_subscriptions(self) -> None:
        """Remove todas as inscrições. Útil para limpeza entre cenas ou testes."""
        self._subscribers.clear()