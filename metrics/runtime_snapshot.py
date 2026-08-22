class RuntimeSnapshot:
    def __init__(self):
        self.data = {}

    def set(self, module: str, key: str, value):
        if module not in self.data:
            self.data[module] = {}
        self.data[module][key] = value

    def get(self, module: str, key: str, default=None):
        return self.data.get(module, {}).get(key, default)

    def dump(self):
        return self.data

    def clear(self):
        self.data = {}