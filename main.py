import argparse
import sys
from ttp import ttp
import os
import json
import glob
from typing import Dict, List


# configs/junos > * 引っ張る
# for で回してparse
# result につっこむ xr > junos


# constants
TTP_TEMPLATES_DIR = "./template"
TTP_CONFIGS_DIR = os.environ.get("MDDO_TTP_CONFIGS_DIR", "./configs")
TTP_OUTPUTS_DIR = os.environ.get("MDDO_TTP_OUTPUTS_DIR", "./ttp_output")
BGP_POLICIES_DIR = os.environ.get("MDDO_BGP_POLICIES_DIR", "./policy_model_output")


def ttp_parse(text: str, os_type: str) -> List:
    """Parse a config file with TTP according to its OS-type
    Args:
        text (str): Text data of config file (parse target contents)
        os_type: (str): OS type string (juniper, cisco_ios_xr)
    Returns:
        str: TTP parsed result (json string)
    """
    template_file = os.path.join(TTP_TEMPLATES_DIR, f"{os_type}.ttp")
    parser = ttp(text, template_file)
    parser.parse()
    return parser.result()


def save_parsed_result(
    network: str, snapshot: str, os_type: str, config_file: str, parser_result: List
) -> None:
    """Save parsed result
    Args:
        network (str): Network name
        snapshot (str): Snapshot name
        os_type (str): OS type string (juniper, cisco_ios_xr)
        config_file (str): File path of a config file (parse target file)
        parser_result (List): TTP parsed result
    Returns:
        None
    """
    file_name = os.path.basename(config_file)
    file_name_wo_ext = os.path.splitext(file_name)[0]
    save_dir = os.path.join(TTP_OUTPUTS_DIR, network, snapshot, os_type)
    os.makedirs(save_dir, exist_ok=True)
    save_file = os.path.join(save_dir, f"{file_name_wo_ext}.json")
    print(f"parse result saved: {save_file}")
    with open(save_file, "w") as f:
        f.write(json.dumps(parser_result, indent=2))


def save_policy_model_output(
    network: str, snapshot: str, ttp_result_file: str, model_output: Dict
) -> None:
    """Save policy model
    Args:
        network (str): Network name
        snapshot (str): Snapshot name
        ttp_result_file (str): File name of TTP result
        model_output (Dict): Policy model data
    Returns:
        None
    """
    file_name = os.path.basename(ttp_result_file)
    file_name_wo_ext = os.path.splitext(file_name)[0]
    save_dir = os.path.join(BGP_POLICIES_DIR, network, snapshot)
    os.makedirs(save_dir, exist_ok=True)
    save_file = os.path.join(save_dir, file_name_wo_ext)
    print(f"bgp policy saved: {save_file}")
    with open(save_file, "w") as f:
        f.write(json.dumps(model_output, indent=2))


def parse_files(network: str, snapshot: str, os_type: str) -> None:
    """Parse config files according to OS-type
    Args:
        network (str): Network name
        snapshot (str): Snapshot name
        os_type (str): OS type string (junos, xr)
    Returns:
        None
    """
    config_dir = os.path.join(TTP_CONFIGS_DIR, network, snapshot, os_type)
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
        save_parsed_result(network, snapshot, os_type, config_file, parsed)


def parse_juniper_bgp_policy(network: str, snapshot: str) -> None:
    """
    Parse juniper configs and generate bgp-policy data
    Args:
        network (str): Network name
        snapshot (str): Snapshot name
    Returns:
        None
    """
    parse_files(network, snapshot, "juniper")
    junos_ttp_outputs_dir = os.path.join(TTP_OUTPUTS_DIR, network, snapshot, "juniper")
    junos_ttp_outputs = glob.glob(os.path.join(junos_ttp_outputs_dir, "*"))

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
                                "match_type": match_type,
                            }
                        }

                    if "prefix-list-filter" in condition.keys():
                        prefix_list, match_type = condition[
                            "prefix-list-filter"
                        ].split()

                        conditions[i] = {
                            "prefix-list-filter": {
                                "prefix-list": prefix_list,
                                "match_type": match_type,
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
                            "community": {
                                "action": community_action,
                                "name": community_name,
                            }
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

        save_policy_model_output(network, snapshot, junos_output_file, template)


def parse_cisco_ios_xr_bgp_policy(network: str, snapshot: str) -> None:
    """
    Parse cisco_ios_xr configs and generate bgp policy data
    Args:
        network (str): Network name
        snapshot (str): Snapshot name
    Returns:
        None
    """
    parse_files(network, snapshot, "cisco_ios_xr")
    xr_ttp_outputs_dir = os.path.join(
        TTP_OUTPUTS_DIR, network, snapshot, "cisco_ios_xr"
    )
    xr_ttp_outputs = glob.glob(os.path.join(xr_ttp_outputs_dir, "*"))

    for xr_output_file in xr_ttp_outputs:
        print(f"- target: {xr_output_file}")

        with open(xr_output_file, "r") as f:
            data = json.load(f)
            if any(data[0][0]) is False:
                print("# parse result is empty (it seems non-bgp-speaker)")
                continue
            result = data[0][0]

        with open("policy_model.json", "r") as f:
            template = json.load(f)

        # node
        for item in result["interfaces"]:
            if item["name"] == "Loopback0":
                template["node"] = item["ipv4"]["address"]

        print("- prefix-set")
        # prefix-set
        if "prefix-sets" in result.keys():
            for item in result["prefix-sets"]:
                print(f"-- prefix-set: {item}")
                prefixes = []
                for prefix_obj in item["prefixes"]:

                    prefix_length = prefix_obj["prefix"].split("/")[-1]

                    length = {}

                    if "condition" in prefix_obj.keys():
                        conditions = prefix_obj["condition"].split()
                        if len(conditions) == 2:
                            if "ge" in conditions:
                                match_type = "orlonger"
                                length["min"] = conditions[1]
                            elif "le" in conditions:
                                match_type = "upto"
                                length["max"] = conditions[1]
                        elif len(conditions) == 4:
                            match_type = "prefix-length-range"
                            length["min"] = conditions[1]
                            length["max"] = conditions[3]
                    else:
                        match_type = "exact"
                        length = {"min": prefix_length, "max": prefix_length}

                    prefixes.append(
                        {
                            "prefix": prefix_obj["prefix"],
                            "match-type": match_type,
                            "length": length,
                        }
                    )

                template["prefix-set"].append(
                    {
                        "name": item["name"],
                        "prefixes": prefixes,
                    }
                )

        print("- as-path-set")
        # as-path-set
        if "as-path-sets" in result.keys():
            for aspath_obj in result["as-path-sets"]:
                print(f"-- as-path-set: {aspath_obj}")
                aspath_data = {
                    "group-name": aspath_obj["name"],
                    "as-path": {"name": aspath_obj["name"]},
                }

                if "conditions" in aspath_obj.keys():

                    for aspath_condition in aspath_obj["conditions"]:

                        if "pattern" in aspath_condition.keys():
                            aspath_data["as-path"]["pattern"] = aspath_condition[
                                "pattern"
                            ]

                        if "length" in aspath_condition.keys():
                            if aspath_condition["condition"] == "le":
                                aspath_data["as-path"]["length"] = {
                                    "max": aspath_condition["length"]
                                }
                            elif aspath_condition["condition"] == "ge":
                                aspath_data["as-path"]["length"] = {
                                    "min": aspath_condition["length"]
                                }

                template["as-path-set"].append(aspath_data)

        print("- community-set")
        # community-set
        if "community-sets" in result.keys():
            for community_obj in result["community-sets"]:
                print(f"-- community: {community_obj}")
                community_data = {
                    "name": community_obj["name"],
                    "communities": community_obj["communities"],
                }

                template["community-set"].append(community_data)

        # policies
        for item in result["policies"]:
            statements = list()

        save_policy_model_output(network, snapshot, xr_output_file, template)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Collect configs to parse bgp-policy")
    parser.add_argument(
        "--network", "-n", required=True, type=str, help="Specify a target network name"
    )
    parser.add_argument(
        "--snapshot",
        "-s",
        default="original_asis",
        type=str,
        help="Specify a target snapshot name",
    )
    args = parser.parse_args()

    parse_juniper_bgp_policy(args.network, args.snapshot)
    parse_cisco_ios_xr_bgp_policy(args.network, args.snapshot)
