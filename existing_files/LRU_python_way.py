from collections import OrderedDict


class LRUCache:
    def __init__(self, capacity):
        self.capacity = capacity
        self.cache = OrderedDict()

    def make_recently(self, key):
        val = self.cache.pop(key, None)
        if val is not None:
            self.cache[key] = val

    def get_value(self, key):
        val = self.cache.get(key)
        if val is not None:
            self.make_recently(key)
        return val

    def put(self, key, val):
        if key in self.cache:
            self.cache[key] = val
            self.make_recently(key)
        else:
            if len(self.cache) >= self.capacity:
                self.cache.popitem(last=False)
            self.cache[key] = val


if __name__ == "__main__":
    need_to_save = [11, 22, 33, 44, 55, 66]
    lru_cache = LRUCache(5)
    n = len(need_to_save)
    for i in range(n):
        lru_cache.put(i, need_to_save[i])
    for key in range(n):
        print(f"Current key is {key} and value is {lru_cache.get_value(key)}")
