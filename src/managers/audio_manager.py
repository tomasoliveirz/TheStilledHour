from typing import Dict, Optional
from direct.showbase.ShowBase import ShowBase
from panda3d.core import AudioSound, AudioManager as Panda3DAudioManager
from direct.interval.SoundInterval import SoundInterval

from src.utils.singleton import Singleton
from src.services.interfaces.i_audio_service import IAudioService

class AudioManager(metaclass=Singleton):
    """
    Gerencia o áudio do jogo, implementando o padrão Singleton e Facade.
    Encapsula a funcionalidade de áudio do Panda3D e depende do IAudioService.
    """
    
    def __init__(self):
        self._show_base: Optional[ShowBase] = None
        self._audio_service: Optional[IAudioService] = None
        self._sounds: Dict[str, AudioSound] = {}
        self._music_tracks: Dict[str, AudioSound] = {}
        self._current_music: Optional[AudioSound] = None
        self._master_volume = 1.0
        self._sfx_volume = 1.0
        self._music_volume = 0.7
        self._muted = False
    
    def initialize(self, show_base: ShowBase, audio_service: IAudioService) -> None:
        """
        Inicializa o AudioManager com o ShowBase e o serviço de áudio.
        
        Args:
            show_base: Instância do ShowBase do Panda3D
            audio_service: Serviço de áudio implementando IAudioService
        """
        self._show_base = show_base
        self._audio_service = audio_service
        
        # Acesso ao AudioManager do Panda3D através do ShowBase
        if hasattr(self._show_base, 'sfxManagerList') and self._show_base.sfxManagerList:
            panda_audio_manager = self._show_base.sfxManagerList[0]
            
            # Verifica se os métodos existem antes de chamá-los
            # Esta verificação de segurança permite compatibilidade com diferentes versões do Panda3D
            if isinstance(panda_audio_manager, Panda3DAudioManager):
                # Configuração opcional do sistema de áudio 3D (se suportado)
                if hasattr(panda_audio_manager, 'setDistanceFactor'):
                    panda_audio_manager.setDistanceFactor(3.28084)  # 1 unidade = 1 metro
                
                if hasattr(panda_audio_manager, 'setDopplerFactor'):
                    panda_audio_manager.setDopplerFactor(0.5)  # Efeito Doppler reduzido
    
    def load_sound(self, sound_name: str, filepath: str) -> None:
        """
        Carrega um efeito sonoro (SFX).
        
        Args:
            sound_name: Nome para referenciar o som
            filepath: Caminho para o arquivo de som
        """
        if not self._show_base or not self._audio_service:
            return
        
        if sound_name in self._sounds:
            return  # Som já carregado
        
        sound = self._audio_service.load_sound(filepath)
        if sound:
            self._sounds[sound_name] = sound
    
    def load_music(self, track_name: str, filepath: str) -> None:
        """
        Carrega uma faixa de música (BGM).
        
        Args:
            track_name: Nome para referenciar a música
            filepath: Caminho para o arquivo de música
        """
        if not self._show_base or not self._audio_service:
            return
        
        if track_name in self._music_tracks:
            return  # Música já carregada
        
        music = self._audio_service.load_music(filepath)
        if music:
            self._music_tracks[track_name] = music
    
    def play_sound(self, sound_name: str, loop: bool = False, volume: Optional[float] = None) -> Optional[AudioSound]:
        """
        Reproduz um efeito sonoro carregado.
        
        Args:
            sound_name: Nome do som a reproduzir
            loop: Se o som deve ser reproduzido em loop
            volume: Volume para este som específico (0.0 a 1.0)
            
        Returns:
            Instância do AudioSound reproduzido, ou None se não encontrado
        """
        if not self._show_base or sound_name not in self._sounds or self._muted:
            return None
        
        sound = self._sounds[sound_name]
        
        # Configura o volume
        if volume is not None:
            sound.setVolume(volume * self._sfx_volume * self._master_volume)
        else:
            sound.setVolume(self._sfx_volume * self._master_volume)
        
        # Configura o loop
        if loop:
            sound.setLoop(True)
        else:
            sound.setLoop(False)
        
        # Reproduz o som
        sound.play()
        return sound
    
    def play_3d_sound(self, sound_name: str, position, loop: bool = False, volume: Optional[float] = None) -> Optional[AudioSound]:
        """
        Reproduz um som posicional em 3D.
        
        Args:
            sound_name: Nome do som a reproduzir
            position: Posição 3D do som (tupla x, y, z)
            loop: Se o som deve ser reproduzido em loop
            volume: Volume para este som específico (0.0 a 1.0)
            
        Returns:
            Instância do AudioSound reproduzido, ou None se não encontrado
        """
        if not self._show_base or sound_name not in self._sounds or self._muted:
            return None
        
        sound = self._sounds[sound_name]
        
        # Configura o volume
        if volume is not None:
            sound.setVolume(volume * self._sfx_volume * self._master_volume)
        else:
            sound.setVolume(self._sfx_volume * self._master_volume)
        
        # Configura o loop
        if loop:
            sound.setLoop(True)
        else:
            sound.setLoop(False)
        
        # Configura a posição 3D (se suportado)
        if isinstance(position, (list, tuple)) and len(position) >= 3 and hasattr(sound, 'set3dAttributes'):
            sound.set3dAttributes(position[0], position[1], position[2], 0, 0, 0)
        
        # Reproduz o som
        sound.play()
        return sound
    
    def play_music(self, track_name: str, loop: bool = True, volume: Optional[float] = None, fade_time: float = 1.0) -> None:
        """
        Reproduz uma faixa de música.
        
        Args:
            track_name: Nome da música a reproduzir
            loop: Se a música deve ser reproduzida em loop
            volume: Volume para esta música específica (0.0 a 1.0)
            fade_time: Tempo de transição em segundos
        """
        if not self._show_base or track_name not in self._music_tracks or self._muted:
            return
        
        # Se já estiver tocando uma música, faz fade out
        if self._current_music and self._current_music.status() == AudioSound.PLAYING:
            fade_out = SoundInterval(self._current_music, 
                                     duration=fade_time, 
                                     startTime=self._current_music.getTime(),
                                     volume=0)
            fade_out.start()
        
        # Prepara a nova música
        music = self._music_tracks[track_name]
        self._current_music = music
        
        # Configura o volume
        target_volume = self._music_volume * self._master_volume
        if volume is not None:
            target_volume = volume * self._music_volume * self._master_volume
        
        # Configura o loop
        music.setLoop(loop)
        
        # Inicia a música com fade in
        music.setVolume(0)
        music.play()
        fade_in = SoundInterval(music, duration=fade_time, volume=target_volume)
        fade_in.start()
    
    def stop_sound(self, sound_name: str) -> None:
        """
        Para a reprodução de um efeito sonoro.
        
        Args:
            sound_name: Nome do som a parar
        """
        if sound_name in self._sounds:
            self._sounds[sound_name].stop()
    
    def stop_music(self, fade_time: float = 1.0) -> None:
        """
        Para a reprodução da música atual.
        
        Args:
            fade_time: Tempo de fade out em segundos
        """
        if self._current_music and self._current_music.status() == AudioSound.PLAYING:
            if fade_time > 0:
                fade_out = SoundInterval(self._current_music, 
                                        duration=fade_time, 
                                        startTime=self._current_music.getTime(),
                                        volume=0)
                fade_out.setDoneEvent("music_fade_out_done")
                fade_out.start()
                
                # Registra um callback para parar a música no final do fade
                self._show_base.accept("music_fade_out_done", self._on_music_fade_out_done)
            else:
                self._current_music.stop()
    
    def _on_music_fade_out_done(self) -> None:
        """Callback chamado quando o fade out da música termina."""
        if self._current_music:
            self._current_music.stop()
    
    def set_master_volume(self, volume: float) -> None:
        """
        Define o volume master global.
        
        Args:
            volume: Novo volume master (0.0 a 1.0)
        """
        self._master_volume = max(0.0, min(1.0, volume))
        self._update_all_volumes()
    
    def set_sfx_volume(self, volume: float) -> None:
        """
        Define o volume dos efeitos sonoros.
        
        Args:
            volume: Novo volume de SFX (0.0 a 1.0)
        """
        self._sfx_volume = max(0.0, min(1.0, volume))
        self._update_all_volumes()
    
    def set_music_volume(self, volume: float) -> None:
        """
        Define o volume da música.
        
        Args:
            volume: Novo volume de música (0.0 a 1.0)
        """
        self._music_volume = max(0.0, min(1.0, volume))
        self._update_all_volumes()
    
    def toggle_mute(self) -> bool:
        """
        Alterna entre silenciar e não silenciar o áudio.
        
        Returns:
            Novo estado: True se silenciado, False caso contrário
        """
        self._muted = not self._muted
        
        if self._muted:
            # Silencia todos os sons
            for sound in self._sounds.values():
                if sound.status() == AudioSound.PLAYING:
                    sound.setVolume(0)
            
            if self._current_music and self._current_music.status() == AudioSound.PLAYING:
                self._current_music.setVolume(0)
        else:
            # Restaura volumes
            self._update_all_volumes()
        
        return self._muted
    
    def _update_all_volumes(self) -> None:
        """Atualiza o volume de todos os sons atualmente em reprodução."""
        if self._muted:
            return
        
        # Atualiza volume dos efeitos sonoros
        for sound in self._sounds.values():
            if sound.status() == AudioSound.PLAYING:
                sound.setVolume(self._sfx_volume * self._master_volume)
        
        # Atualiza volume da música
        if self._current_music and self._current_music.status() == AudioSound.PLAYING:
            self._current_music.setVolume(self._music_volume * self._master_volume)
    
    def cleanup(self) -> None:
        """Limpa todos os recursos de áudio."""
        for sound in self._sounds.values():
            sound.stop()
        
        for music in self._music_tracks.values():
            music.stop()
        
        self._sounds.clear()
        self._music_tracks.clear()
        self._current_music = None