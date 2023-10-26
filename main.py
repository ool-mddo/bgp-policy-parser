import sys
from ttp import ttp
import os
import json
import glob
from typing import Dict, List
from XRTranslator import XRTranslator, PMEncoder


# configs/junos > * 引っ張る
# for で回してparse
# result につっこむ xr > junos


# constants
TTP_TEMPLATES_DIR = os.environ.get("MDDO_TTP_TEMPLATES_DIR", "./template")
TTP_CONFIGS_DIR = os.environ.get("MDDO_TTP_CONFIGS_DIR", "./configs")
TTP_OUTPUTS_DIR = os.environ.get("MDDO_TTP_OUTPUTS_DIR", "./ttp_output")
BGP_POLICIES_DIR = os.environ.get("MDDO_BGP_POLICIES_DIR", "./policy_model_output")


def ttp_parse(text: str, os_type: str) -> List:
    """Parse a config file with TTP according to its OS-type
    Args:
        text (str): Text data of config file (parse target contents)
        os_type: (str): OS type string (junos, xr)
    Returns:
        str: TTP parsed result (json string)
    """
    template_file = os.path.join(TTP_TEMPLATES_DIR, f"{os_type}.ttp")
    parser = ttp(text, template_file)
    parser.parse()
    return parser.result()


def save_parsed_result(os_type: str, config_file: str, parser_result: List) -> None:
    """Save parsed result
    Args:
        os_type (str): OS type string (junos, xr)
        config_file (str): File path of a config file (parse target file)
        parser_result (List): TTP parsed result
    Returns:
        None
    """
    file_name = os.path.basename(config_file)
    file_name_wo_ext = os.path.splitext(file_name)[0]
    save_dir = os.path.join(TTP_OUTPUTS_DIR, os_type)
    os.makedirs(save_dir, exist_ok=True)
    save_file = os.path.join(save_dir, f"{file_name_wo_ext}.json")
    print(f"parse result saved: {save_file}")
    with open(save_file, "w") as f:
        f.write(json.dumps(parser_result, indent=2))


def save_policy_model_output(ttp_result_file: str, model_output: Dict) -> None:
    """Save policy model
    Args:
        ttp_result_file (str): File name of TTP result
        model_output (Dict): Policy model data
    Returns:
        None
    """
    file_name = os.path.basename(ttp_result_file)
    file_name_wo_ext = os.path.splitext(file_name)[0]
    save_dir = BGP_POLICIES_DIR
    os.makedirs(save_dir, exist_ok=True)
    save_file = os.path.join(save_dir, file_name_wo_ext)
    print(f"bgp policy saved: {save_file}")
    with open(save_file, "w") as f:
        f.write(json.dumps(model_output, indent=2, cls=PMEncoder))


def parse_files(os_type: str) -> None:
    """Parse config files according to OS-type
    Args:
        os_type (str): OS type string (junos, xr)
    Returns:
        None:
    """
    config_dir = os.path.join(TTP_CONFIGS_DIR, os_type)
    if not os.path.isdir(config_dir):
        print(
            f"Error: config dir:{config_dir} for os_type:{os_type} is not found",
            file=sys.stderr,
        )
        sys.exit(1)

    config_files = glob.glob(os.path.join(config_dir, "*"))
    for config_file in config_files:
        with open(config_file, "r") as f:
            config_txt = f.read()
            parsed = ttp_parse(config_txt, os_type)
        save_parsed_result(os_type, config_file, parsed)

def convert_prefix_list_into_route_filter(prefix_list_name: str, policy_data: dict) -> list:
    """Convert prefix-list into route-filter
    Args:
        prefix_list_name (str): prefix_list name of Conversion target
        policy_data (dict): policy data containing prefix-list 
    Returns:
        route_fliter_list (list): converted route-fliter data 
    
    """
    route_filter_list = []
    for item in policy_data["prefix-set"]:
        if item["name"] == prefix_list_name:
            for prefix_item in item["prefixes"]:
                print(f"- convert prefix-list:{prefix_list_name} into route-filter {prefix_item['prefix']}")
                route_filter_list.append({"route-filter": prefix_item})
            return route_filter_list
    print(f"{prefix_list_name} is not match in input_data")
    return route_filter_list 

if __name__ == "__main__":
    parse_files("juniper")
    junos_ttp_outputs = glob.glob(os.path.join(TTP_OUTPUTS_DIR, "juniper", "*"))

    for junos_output_file in junos_ttp_outputs:
        print(f"- target: {junos_output_file}")

        with open(junos_output_file, "r") as f:
            data = json.load(f)
            if any(data[0][0]) is False:
                print("# parse result is empty (it seems non-bgp-speaker)")
                continue
            result = data[0][0][0]

        with open("policy_model.json", "r") as f:
            template = json.load(f)

        # node
        for item in result["interfaces"]:
            if item["name"] == "lo0":
                template["node"] = item["address"]

        # prefix-set
        if "prefix-sets" in result.keys():
            for item in result["prefix-sets"]:
                template["prefix-set"].append(item)

        # as-path-set
        if "aspath-sets" in result.keys():
            for item in result["aspath-sets"]:
                template["as-path-set"].append(item)

        # community-set
        if "community-sets" in result.keys():
            for item in result["community-sets"]:
                data = {"name": item["community"], "community": item["members"]}
                template["community-set"].append(data)

        # policies
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
                        print(f"# NO RULE MATCHED: {rule}")

                for i, condition in enumerate(conditions):
                    print("  - condition : ", condition)
                    if "route-filter" in condition.keys():
                        prefix, *match_type_elem = condition["route-filter"].split()
                        print("    - match_type_elem length: ", len(match_type_elem))
                        # exact
                        if len(match_type_elem) == 1:
                            # exact
                            length = dict()
                            match_type = match_type_elem[0]
                        elif len(match_type_elem) == 2:
                            if match_type_elem[0] == "prefix-length-range":
                                # ex. prefix-length-range /25-/27 -> {"min": 25, "max": 27}
                                max_length, min_length = [
                                    x.lstrip("/") for x in match_type_elem[1].split("-")
                                ]
                                length = {"max": max_length, "min": min_length}
                            elif match_type_elem[0] == "upto":
                                # ex. upto /24 -> {"max": 24}
                                length = {"max": match_type_elem[1].lstrip("/")}
                            match_type = match_type_elem[0]

                        conditions[i] = {
                            "route-filter": {
                                "prefix": prefix,
                                "length": length,
                                "match-type": match_type,
                            }
                        }

                    if "prefix-list-filter" in condition.keys():
                        prefix_list, match_type = condition[
                            "prefix-list-filter"
                        ].split()

                        conditions[i] = {
                            "prefix-list-filter": {
                                "prefix-list": prefix_list,
                                "match-type": match_type,
                            }
                        }

                    if "community" in condition.keys():
                        communities = (
                            condition["community"].strip("[").strip("]").split()
                        )

                        conditions[i] = {"community": communities}

                for i, action in enumerate(actions):
                    if "as-path-prepend" in action.keys():
                        asn = action["as-path-prepend"].split()

                        conditions[i] = {"as-path-prepend": {"asn": asn}}

                    if "community" in action.keys():
                        community_action, community_name = action["community"].split()

                        actions[i] = {
                            "community": {"action": community_action, "name": community_name}
                        }

                statement_data = {
                    "name": name,
                    "if": "if",
                    "conditions": conditions,
                    "actions": actions,
                }
                statements.append(statement_data)

            if "default" not in item:
                default = {"actions": []}
            else:
                default = {"actions": item["default"]["actions"]}

            data = {"name": item["name"], "statements": statements, "default": default}
            template["policies"].append(data)

        save_policy_model_output(junos_output_file, template)


    parse_files("cisco_ios_xr")
    xr_ttp_outputs = glob.glob(os.path.join(TTP_OUTPUTS_DIR, "cisco_ios_xr", "*"))
    for xr_output_file in xr_ttp_outputs:
        with open(xr_output_file) as f:
            ttp_parsed_config = json.load(f)
        xr_translator = XRTranslator(ttp_parsed_config)
        xr_translator.translate_policies() 

        save_policy_model_output(xr_output_file, xr_translator.policies)
