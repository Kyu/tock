import enum
import json

with open('../common/enums/game_play_type.json') as p:
    GamePlayType = enum.Enum('GamePlayType', json.loads(p.read()))


with open('../common/enums/game_end_type.json') as e:
    GameEndType = enum.Enum('GameEndType', json.loads(e.read()))


def generic_event(name: str, data):
    return json.dumps({"name": name, "data": data})
