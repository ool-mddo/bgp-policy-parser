from ttp import ttp
import sys, os
import json
from pprint import pprint
import glob

# configs/junos > * 引っ張る
# for で回してparse
# result につっこむ xr > junos

def parse(text: str, template: str) -> str:
    parser = ttp(text,template)
    parser.parse()
    return json.dumps(parser.result(),indent=2)
    

junos_files = glob.glob("./configs/junos/*")
for junos_file in junos_files:
    filename = junos_file
    with open(junos_file, 'r') as f:
        config_txt = f.read()
        parsed = parse(config_txt, "./template/junos.ttp")
    with open(os.path.join("./ttp_output/junos/", filename.split('/')[-1])+".json", "w") as f:
        f.write(parsed)

xr_files = glob.glob("./configs/xr/*")
for xr_file in xr_files:
    filename = xr_file
    with open(xr_file, 'r') as f:
        config_txt = f.read()
        parsed = parse(config_txt, "./template/xr.ttp")
    with open(os.path.join("./ttp_output/xr/", filename.split('/')[-1])+".json", "w") as f:
        f.write(parsed)

#with open(sys.argv[1], 'r') as f:
#    config = f.read()
#
#with open(sys.argv[2], 'r') as f:
#    template = f.read()

# parser = ttp(config, template)
# parser.parse()
# result: list = parser.result()
# print(json.dumps(result, indent=2))
