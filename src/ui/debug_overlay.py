from typing import Dict, Any, Optional
from direct.showbase.ShowBase import ShowBase
from direct.gui.OnscreenText import OnscreenText
from panda3d.core import TextNode, Vec4
import time

from src.core.config import DEBUG_MODE, SHOW_FPS

class DebugOverlay:
    """
    Interface de usuário para informações de debug.
    Mostra FPS, posição do jogador, e outras informações úteis para desenvolvimento.
    """
    
    def __init__(self, show_base: ShowBase):
        """
        Inicializa o overlay de debug.
        
        Args:
            show_base: Instância do ShowBase do Panda3D
        """
        self._show_base = show_base
        self._player = None
        self._physics_service = None
        
        # Textos na tela
        self._fps_text = None
        self._position_text = None
        self._debug_texts = {}
        
        # Estado de visualização
        self._enabled = DEBUG_MODE
        self._show_fps = SHOW_FPS
        self._show_collision_shapes = False
        
        # Para cálculo manual de FPS
        self._last_time = time.time()
        self._frame_count = 0
        self._fps_avg = 0
        self._fps_update_interval = 0.5  # Atualiza o FPS a cada 0.5 segundos
        self._last_fps_update = 0
    
    def initialize(self, player):
        """
        Inicializa o overlay com a referência ao jogador.
        
        Args:
            player: A entidade do jogador
        """
        self._player = player
        
        # Obtém o serviço de física (com tratamento de erro)
        try:
            from src.utils.service_locator import ServiceLocator
            from src.services.interfaces.i_physics_service import IPhysicsService
            
            service_locator = ServiceLocator()
            if service_locator:
                self._physics_service = service_locator.get(IPhysicsService)
        except Exception as e:
            print(f"Aviso: Não foi possível obter serviço de física: {e}")
        
        # Cria os textos de debug
        self._create_debug_texts()
        
        # Atualiza a visibilidade inicial
        self.set_enabled(self._enabled)
    
    def _create_debug_texts(self):
        """Cria os textos do overlay de debug."""
        try:
            # Texto de FPS
            self._fps_text = OnscreenText(
                text="FPS: Calculando...",
                pos=(-1.3, 0.95),
                scale=0.05,
                fg=(1, 1, 0, 1),
                align=TextNode.ALeft,
                mayChange=True
            )
            
            # Texto de posição
            self._position_text = OnscreenText(
                text="Pos: (0, 0, 0)",
                pos=(-1.3, 0.90),
                scale=0.05,
                fg=(1, 1, 0, 1),
                align=TextNode.ALeft,
                mayChange=True
            )
            
            # Textos adicionais
            self._add_debug_text("velocity", "Vel: (calculando...)", -1.3, 0.85)
            self._add_debug_text("camera", "Cam: (calculando...)", -1.3, 0.80)
            self._add_debug_text("state", "State: Inicializando...", -1.3, 0.75)
        except Exception as e:
            print(f"Erro ao criar textos de debug: {e}")
    
    def _add_debug_text(self, key, initial_text, x, y, fg=(1, 1, 0, 1)):
        """
        Adiciona um novo texto de debug.
        
        Args:
            key: Chave para acessar o texto posteriormente
            initial_text: Texto inicial
            x: Posição X na tela
            y: Posição Y na tela
            fg: Cor do texto
        """
        try:
            text = OnscreenText(
                text=initial_text,
                pos=(x, y),
                scale=0.05,
                fg=fg,
                align=TextNode.ALeft,
                mayChange=True
            )
            
            self._debug_texts[key] = text
        except Exception as e:
            print(f"Erro ao adicionar texto de debug '{key}': {e}")
    
    def _calculate_fps(self):
        """
        Calcula o FPS manualmente baseado no tempo entre frames.
        
        Returns:
            FPS atual
        """
        try:
            current_time = time.time()
            dt = current_time - self._last_time
            self._last_time = current_time
            self._frame_count += 1
            
            # Atualiza o FPS médio a cada intervalo
            if current_time - self._last_fps_update > self._fps_update_interval:
                if dt > 0:
                    self._fps_avg = self._frame_count / (current_time - self._last_fps_update)
                else:
                    self._fps_avg = 0
                
                self._frame_count = 0
                self._last_fps_update = current_time
            
            return self._fps_avg
        except Exception as e:
            print(f"Erro ao calcular FPS: {e}")
            return 0
    
    def update(self, dt):
        """
        Atualiza o overlay de debug.
        
        Args:
            dt: Delta time (tempo desde o último frame)
        """
        if not self._enabled:
            return
        
        try:
            # Atualiza o FPS
            if self._show_fps and self._fps_text:
                # Calcula FPS manualmente (mais seguro)
                fps = round(self._calculate_fps(), 1)
                self._fps_text.setText(f"FPS: {fps}")
            
            # Atualiza informações do jogador
            if self._player:
                # Posição
                if self._position_text:
                    try:
                        if hasattr(self._player, '_transform') and self._player._transform:
                            pos = self._player._transform.position
                            pos_text = f"Pos: ({pos.x:.2f}, {pos.y:.2f}, {pos.z:.2f})"
                        else:
                            pos_text = "Pos: (indisponível)"
                        self._position_text.setText(pos_text)
                    except Exception as e:
                        print(f"Erro ao atualizar posição: {e}")
                        self._position_text.setText("Pos: (erro)")
                
                # Estado do jogador
                if "state" in self._debug_texts:
                    try:
                        state_text = "State: "
                        
                        if hasattr(self._player, 'is_walking'):
                            walking = getattr(self._player, 'is_walking', False)
                            sprinting = getattr(self._player, 'is_sprinting', False)
                            crouching = getattr(self._player, 'is_crouching', False)
                            
                            if walking:
                                if sprinting:
                                    state_text += "Sprinting"
                                elif crouching:
                                    state_text += "Crouching"
                                else:
                                    state_text += "Walking"
                            else:
                                state_text += "Standing"
                        else:
                            state_text += "Desconhecido"
                        
                        self._debug_texts["state"].setText(state_text)
                    except Exception as e:
                        print(f"Erro ao atualizar estado: {e}")
                        self._debug_texts["state"].setText("State: (erro)")
                
                # Câmera
                if "camera" in self._debug_texts:
                    try:
                        if hasattr(self._player, 'camera_node') and self._player.camera_node:
                            h = self._player.camera_node.getH()
                            p = self._player.camera_node.getP()
                            self._debug_texts["camera"].setText(f"Cam: H:{h:.1f} P:{p:.1f}")
                        else:
                            self._debug_texts["camera"].setText("Cam: (indisponível)")
                    except Exception as e:
                        print(f"Erro ao atualizar câmera: {e}")
                        self._debug_texts["camera"].setText("Cam: (erro)")
        except Exception as e:
            print(f"Erro ao atualizar debug overlay: {e}")
    
    def set_enabled(self, enabled):
        """
        Ativa ou desativa o overlay de debug.
        
        Args:
            enabled: True para ativar, False para desativar
        """
        try:
            self._enabled = enabled
            
            # Atualiza a visibilidade dos textos
            self._set_texts_visible(enabled and self._show_fps, enabled)
            
            # Atualiza a visualização de debug da física
            if self._physics_service:
                self._physics_service.toggle_debug_visualization(enabled and self._show_collision_shapes)
        except Exception as e:
            print(f"Erro ao definir overlay como {enabled}: {e}")
    
    def _set_texts_visible(self, show_fps, show_others):
        """
        Define a visibilidade dos textos.
        
        Args:
            show_fps: Se deve mostrar o FPS
            show_others: Se deve mostrar os outros textos
        """
        try:
            if self._fps_text:
                self._fps_text.show() if show_fps else self._fps_text.hide()
            
            if self._position_text:
                self._position_text.show() if show_others else self._position_text.hide()
            
            for text in self._debug_texts.values():
                text.show() if show_others else text.hide()
        except Exception as e:
            print(f"Erro ao definir visibilidade de textos: {e}")
    
    def toggle(self):
        """
        Alterna a visibilidade do overlay.
        
        Returns:
            Novo estado de visibilidade
        """
        self.set_enabled(not self._enabled)
        return self._enabled
    
    def toggle_collision_shapes(self):
        """
        Alterna a visualização de formas de colisão.
        
        Returns:
            Novo estado de visualização
        """
        try:
            self._show_collision_shapes = not self._show_collision_shapes
            
            if self._physics_service and self._enabled:
                self._physics_service.toggle_debug_visualization(self._show_collision_shapes)
            
            return self._show_collision_shapes
        except Exception as e:
            print(f"Erro ao alternar formas de colisão: {e}")
            return False
    
    def toggle_fps(self):
        """
        Alterna a visualização do FPS.
        
        Returns:
            Novo estado de visualização
        """
        try:
            self._show_fps = not self._show_fps
            
            if self._fps_text:
                if self._enabled and self._show_fps:
                    self._fps_text.show()
                else:
                    self._fps_text.hide()
            
            return self._show_fps
        except Exception as e:
            print(f"Erro ao alternar FPS: {e}")
            return False
    
    def cleanup(self):
        """Limpa todos os recursos do overlay."""
        try:
            # Remove os textos
            if self._fps_text:
                self._fps_text.destroy()
            
            if self._position_text:
                self._position_text.destroy()
            
            for text in self._debug_texts.values():
                text.destroy()
            
            # Limpa dicionários
            self._debug_texts.clear()
            
            # Limpa referências
            self._fps_text = None
            self._position_text = None
            self._player = None
        except Exception as e:
            print(f"Erro ao limpar debug overlay: {e}")