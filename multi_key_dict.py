# flighttracker/multi_key_dict.py

"""
For use with datasets that have multiple important ID's
"""

class MultiKeyDict:
    """Class def"""
    def __init__(self):
        self.key_map = {}

    def add_mapping(self, value, *keys):
        for key in keys:
            self.key_map[key] = value

    def add_key(self, value, key):
        if key not in self.key_map:
            self.key_map[key] = value

    def __getitem__(self, key):
        return self.key_map[key]

    def __setitem__(self, key, value):
        self.key_map[key] = value

    def __delitem__(self, key):
        del self.key_map[key]

    def __len__(self) -> int:
        return len(self.key_map.values())