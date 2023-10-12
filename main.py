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


junos_ttp_outputs = glob.glob("./ttp_output/junos/*")
xr_ttp_output     = glob.glob("./ttp_output/xr/*")


for junos_output_file in junos_ttp_outputs:

    print("=" * 60)
    print(junos_output_file)
    print("=" * 60)

    filename = os.path.basename(junos_output_file)
    with open(junos_output_file, "r") as f:
       result = json.load(f)[0][0][0]

    with open("policy_model.json", "r") as f:
        template = json.load(f)

    print(result)
    print(template)

    ## node
    for item in result["interfaces"]:
        if item["name"] == "lo0":
            template["node"] = item["address"]

    ## prefix-set
    if "prefix-sets" in result.keys():
        for item in result["prefix-sets"]:
            template['prefix-set'].append(item)


    ## as-path-set
    if "aspath-sets" in result.keys():
        for item in result["aspath-sets"]:
            template["as-path-set"].append(item)


    ## community-set
    if "community-sets" in result.keys():
        for item in result["community-sets"]:
            data = [
                {
                    "name": item["community"],
                    "community": item["members"]
                }
            ]
            template["community-set"].append(data)


    ## policies
    for item in result["policies"]:
        statements = list()
        for name, statement in item["statements"].items():

            conditions = []
            actions = []
            for rule in statement:
                if "actions" in rule:
                    actions.extend(rule["actions"])
                elif "conditions" in rule:
                    conditions.extend(rule["conditions"])
                else:
                    print(f"NO RULE MATCHED: {rule}")
            
            for i, condition in enumerate(conditions):
                print(condition)
                if "route-filter" in condition.keys():
                    prefix, *match_type_elem = condition["route-filter"].split()

                    # exact
                    if len(match_type_elem) == 1:
                        # exact
                        length = dict()
                        match_type = match_type_elem[0]
                    elif len(match_type_elem) == 4:
                        if match_type_elem[2] == "prefix-length-range":
                            # ex. /25-/27 -> [25, 27]
                            max_length, min_length = [ x.lstrip("/") for x in match_type_elem[3].split("-")]
                            lentgh = { "max": max_length, "min": min_length}
                        elif match_type_elem[2] == "upto":
                            # "/"の排除
                            length = { "max": match_type_elem[3].lstrip("/") }
                        
                        match_type = match_type_elem[2]
                        
                    conditions[i] = {
                        "route-filter": {
                            "prefix": prefix,
                            "length": length,
                            "match_type": match_type
                        }
                    }

                if "prefix-list-filter" in condition.keys():
                    prefix_list, match_type = condition["prefix-list-filter"].split()

                    conditions[i] = {
                        "prefix-list-filter": {
                            "prefix-list": prefix_list,
                            "match_type": match_type
                        }
                    }

                if "community" in condition.keys():
                    communities = condition["community"].strip("[").strip("]").split()

                    conditions[i] = {
                        "community": communities
                    }    
                
            for i, action in enumerate(actions): 
                if "as-path-prepend" in action.keys():
                    asn = action["as-path-prepend"].split()

                    conditions[i] = {
                        "as-path-prepend": {
                            "asn": asn
                        }
                    }

                if "community" in action.keys():
                    community_action, name = action["community"].split()

                    actions[i] = {
                        "community": {
                            "action": community_action,
                            "name": name
                        }
                    }

            statement_data = {
                "name": name,
                "if": "if",
                "conditions": conditions,
                "actions": actions
            }
            statements.append(statement_data)

        if "default" not in item:
            default = { "actions": [] }
        else:
            default = { "actions": item["default"]["actions"] }

        data = {
            "name": item["name"],
            "statements": statements,
            "default": default
        }
        template["policies"].append(data)

    with open(f"./policy_model_output/{filename}", "w") as f:
        f.write(json.dumps(template, indent=2))


    #with open(sys.argv[1], 'r') as f:
    #    config = f.read()
    #
    #with open(sys.argv[2], 'r') as f:
    #    template = f.read()

    # parser = ttp(config, template)
    # parser.parse()
    # result: list = parser.result()
    # print(json.dumps(result, indent=2))
