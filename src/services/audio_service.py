from typing import Optional, Dict
import os
from direct.showbase.ShowBase import ShowBase
from panda3d.core import AudioSound, Filename

from src.services.interfaces.i_audio_service import IAudioService

class AudioService(IAudioService):
    """
    Implementação do serviço de áudio usando Panda3D.
    """
    
    def __init__(self, show_base: ShowBase):
        """
        Inicializa o serviço de áudio.
        
        Args:
            show_base: Instância do ShowBase do Panda3D
        """
        self._show_base = show_base
        self._loaded_sounds: Dict[str, AudioSound] = {}
    
    def initialize(self) -> None:
        """Inicializa o sistema de áudio."""
        # Verifica se o sistema de áudio está disponível
        if not hasattr(self._show_base, 'sfxManagerList') or not self._show_base.sfxManagerList:
            print("Aviso: Sistema de áudio não disponível")
    
    def load_sound(self, filepath: str) -> Optional[AudioSound]:
        """
        Carrega um efeito sonoro a partir de um arquivo.
        
        Args:
            filepath: Caminho para o arquivo de som
            
        Returns:
            Instância do AudioSound carregado, ou None se falhar
        """
        # Verifica se o som já foi carregado
        if filepath in self._loaded_sounds:
            return self._loaded_sounds[filepath]
        
        try:
            # Converte o caminho para o formato do Panda3D
            panda_path = Filename.fromOsSpecific(filepath)
            
            # Carrega o som
            sound = self._show_base.loader.loadSfx(panda_path)
            
            # Verifica se o carregamento foi bem-sucedido
            if sound:
                self._loaded_sounds[filepath] = sound
                return sound
        except Exception as e:
            print(f"Erro ao carregar som {filepath}: {e}")
        
        print(f"Erro: Falha ao carregar som: {filepath}")
        return None
    
    def load_music(self, filepath: str) -> Optional[AudioSound]:
        """
        Carrega uma faixa de música a partir de um arquivo.
        Usa o mesmo método de carregamento dos efeitos sonoros.
        
        Args:
            filepath: Caminho para o arquivo de música
            
        Returns:
            Instância do AudioSound carregado, ou None se falhar
        """
        return self.load_sound(filepath)
    
    def cleanup(self) -> None:
        """Limpa todos os recursos de áudio."""
        # Para todos os sons carregados
        for sound in self._loaded_sounds.values():
            sound.stop()
        
        # Limpa o dicionário
        self._loaded_sounds.clear()