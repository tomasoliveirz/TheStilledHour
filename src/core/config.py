"""
Arquivo de configuração central para o jogo The Stilled Hour.
Centraliza constantes, configurações e parâmetros do jogo.
"""

# Configurações gerais
GAME_TITLE = "The Stilled Hour"
VERSION = "0.1.0"
FULLSCREEN = False
WINDOW_SIZE = (1280, 720)
ENABLE_SHADOWS = True
ENABLE_PBR = True
ENABLE_PARTICLES = True

# Configurações de input
KEY_FORWARD = "w"
KEY_BACKWARD = "s"
KEY_LEFT = "a"
KEY_RIGHT = "d"
KEY_SPRINT = "shift"
KEY_INTERACT = "e"
KEY_INVENTORY = "i"
KEY_PAUSE = "escape"
KEY_CROUCH = "control"
KEY_JUMP = "space"
MOUSE_SENSITIVITY = 40

# Configurações do jogador
PLAYER_WALK_SPEED = 5
PLAYER_SPRINT_SPEED = 10
PLAYER_CROUCH_SPEED = 1
PLAYER_HEIGHT = 1.8
PLAYER_CROUCH_HEIGHT = 1.0
PLAYER_COLLISION_RADIUS = 0.3
PLAYER_HEAD_HEIGHT = 1.7
PLAYER_STEP_HEIGHT = 0.35
PLAYER_STEP_SOUND_INTERVAL = 0.5
PLAYER_CAMERA_FOV = 70.0
PLAYER_MASS = 80.0

# Configurações de física
GRAVITY = -9.81
PHYSICS_FRAME_RATE = 144  # Hz
MAX_SUBSTEPS = 10
FIXED_TIMESTEP = 1.0 / PHYSICS_FRAME_RATE

# Configurações de debug
DEBUG_MODE = True
SHOW_COLLISION_SHAPES = False
SHOW_FPS = True
LOG_LEVEL = "INFO"

# Paths para assets
MODELS_DIR = "assets/models"
TEXTURES_DIR = "assets/textures"
SOUNDS_DIR = "assets/sounds"
FONTS_DIR = "assets/fonts"

# Scene config
ROOM_SIZE = (20, 10, 4)  # width, length, height
NUMBER_OF_BOXES = 10
WALL_THICKNESS = 1