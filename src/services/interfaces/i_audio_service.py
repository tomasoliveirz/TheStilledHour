from abc import ABC, abstractmethod
from typing import Optional
from panda3d.core import AudioSound

class IAudioService(ABC):
    """
    Interface para o serviço de áudio.
    Define métodos necessários para carregar e gerenciar sons.
    """
    
    @abstractmethod
    def initialize(self) -> None:
        """Inicializa o sistema de áudio."""
        pass
    
    @abstractmethod
    def load_sound(self, filepath: str) -> Optional[AudioSound]:
        """
        Carrega um efeito sonoro a partir de um arquivo.
        
        Args:
            filepath: Caminho para o arquivo de som
            
        Returns:
            Instância do AudioSound carregado, ou None se falhar
        """
        pass
    
    @abstractmethod
    def load_music(self, filepath: str) -> Optional[AudioSound]:
        """
        Carrega uma faixa de música a partir de um arquivo.
        
        Args:
            filepath: Caminho para o arquivo de música
            
        Returns:
            Instância do AudioSound carregado, ou None se falhar
        """
        pass
    
    @abstractmethod
    def cleanup(self) -> None:
        """Limpa todos os recursos de áudio."""
        pass