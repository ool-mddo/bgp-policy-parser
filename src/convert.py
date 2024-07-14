import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as f:
    result = json.load(f)[0][0][0]

with open(sys.argv[2], "r", encoding="utf-8") as f:
    output = json.load(f)

# node
try:
    for item in result["interfaces"]:
        if item["name"] == "lo0":
            output["node"] = item["address"]
except KeyError:
    pass

# prefix-set
try:
    for item in result["prefix-sets"]:
        output["prefix-set"].append(item)
except KeyError:
    pass


# as-path-set
try:
    for item in result["aspath-sets"]:
        output["as-path-set"].append(item)
except KeyError:
    pass


# community-set
try:
    for item in result["community-sets"]:
        data = [{"name": item["community"], "community": item["members"]}]
        output["community-set"].append(data)
except KeyError:
    pass


print(json.dumps(output, indent=2))
