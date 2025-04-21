class Singleton(type):
    """
    Implementação do padrão Singleton usando metaclasse.
    
    Exemplo de uso:
        class AudioManager(metaclass=Singleton):
            pass
    """
    _instances = {}
    
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]