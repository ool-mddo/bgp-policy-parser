from ttp import ttp
import sys
import json
from pprint import pprint

with open(sys.argv[1], 'r') as f:
    config = f.read()

with open(sys.argv[2], 'r') as f:
    template = f.read()

parser = ttp(config, template)
parser.parse()
result: list = parser.result()
print(json.dumps(result, indent=2))
