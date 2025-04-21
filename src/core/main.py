#!/usr/bin/env python
"""
The Stilled Hour - Um jogo de horror em primeira pessoa.
Ponto de entrada principal para o jogo.
"""

import sys
import os
import argparse
from direct.showbase.ShowBase import ShowBase

# Adiciona o diretório raiz ao path para os imports funcionarem corretamente
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.core.game_app import GameApp
from src.core.config import DEBUG_MODE

class TheStilledHour(ShowBase):
    """
    Classe principal do jogo, derivada do ShowBase do Panda3D.
    """
    
    def __init__(self, debug_mode: bool = False):
        """
        Inicializa o jogo.
        
        Args:
            debug_mode: Se deve iniciar em modo de debug
        """
        # Inicializa o ShowBase
        ShowBase.__init__(self)
        
        # Desabilita o controle padrão de mouse do Panda3D
        self.disableMouse()
        
        # Cria e inicializa a aplicação do jogo
        self._game_app = GameApp()
        self._game_app.initialize(self)
        
        # Flag para saber se estamos em modo de debug
        self._debug_mode = debug_mode
        
        # Registra handler para saída limpa
        self.accept("escape", self.request_exit)
        self.accept("q", self.request_exit)
    
    def request_exit(self) -> None:
        """Solicita a saída do jogo com limpeza adequada."""
        # Limpa recursos
        self._game_app.cleanup()
        
        # Sai do jogo
        sys.exit(0)

def parse_arguments():
    """
    Processa argumentos de linha de comando.
    
    Returns:
        Namespace com os argumentos processados
    """
    parser = argparse.ArgumentParser(description='The Stilled Hour - Um jogo de horror em primeira pessoa.')
    parser.add_argument('--debug', action='store_true', help='Inicia o jogo em modo de debug')
    return parser.parse_args()

def main():
    """Função principal do jogo."""
    # Processa argumentos de linha de comando
    args = parse_arguments()
    
    # Determina se deve iniciar em modo de debug
    debug_mode = args.debug or DEBUG_MODE
    
    # Configura variáveis de ambiente para o Panda3D
    if debug_mode:
        # Em modo de debug, exibe mais mensagens
        os.environ["PANDA_PRC_DIR"] = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../config/debug"))
    else:
        # Em modo normal, configura para produção
        os.environ["PANDA_PRC_DIR"] = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../config/release"))
    
    try:
        # Cria e inicia o jogo
        app = TheStilledHour(debug_mode=debug_mode)
        app.run()
    except Exception as e:
        # Em caso de erro, mostra o erro e sai
        print(f"Erro fatal: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()