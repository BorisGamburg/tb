class BaseStrategy:
    def resolve(self, ctx):
        """
        Должен вернуть:
        ActionCommand
        """
        raise NotImplementedError