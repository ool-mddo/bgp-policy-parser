import argparse
import sys
from ttp import ttp
import os
import json
import glob
from logging import getLogger, Formatter, DEBUG, INFO, FileHandler, StreamHandler
from typing import Dict, List
from XRTranslator import XRTranslator, PMEncoder


# constants
TTP_TEMPLATES_DIR = "./template"
TTP_CONFIGS_DIR = os.environ.get("MDDO_TTP_CONFIGS_DIR", "./configs")
TTP_OUTPUTS_DIR = os.environ.get("MDDO_TTP_OUTPUTS_DIR", "./ttp_output")
BGP_POLICIES_DIR = os.environ.get("MDDO_BGP_POLICIES_DIR", "./policy_model_output")


logger = getLogger('main')
logger.setLevel(DEBUG)
formatter = Formatter("[{asctime} @{funcName}-{lineno}] {message}", style="{")

fh = FileHandler('parser.log')
fh.setFormatter(formatter)
fh.setLevel(DEBUG)
logger.addHandler(fh)

sh = StreamHandler(sys.stdout)
sh.setFormatter(formatter)
sh.setLevel(INFO)
logger.addHandler(sh)

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
    logger.info(f"parse result saved: {save_file}")
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
    logger.info(f"bgp policy saved: {save_file}")
    with open(save_file, "w") as f:
        f.write(json.dumps(model_output, indent=2, cls=PMEncoder))


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
        logger.info(
            f"Error: config dir:{config_dir} for os_type:{os_type} is not found"
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
        logger.info(f"- target: {junos_output_file}")

        with open(junos_output_file, "r") as f:
            data = json.load(f)
            if any(data[0][0]) is False:
                logger.info("# parse result is empty (it seems non-bgp-speaker)")
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
        else:
            logger.info(f"prefix-set not found in {junos_output_file}")

        # as-path-set
        if "aspath-sets" in result.keys():
            for item in result["aspath-sets"]:
                template["as-path-set"].append(item)
        else:
            logger.info(f"as-path-set not found in {junos_output_file}")

        # community-set
        if "community-sets" in result.keys():
            for item in result["community-sets"]:
                data = {
                    "name": item["community"], 
                    "communities": [ {"community": member} for member in item["members"].split() ]
                }
                template["community-set"].append(data)
        else:
            logger.info(f"community-set not found in {junos_output_file}")

        # policies
        if "policies" not in result:
            logger.info(f"policy not found in {junos_output_file}")
            continue

        for item in result["policies"]:
            statements = list()

            if "statements" not in item.keys():
                logger.info(f"statements not found in {item['name']}")
                print (str(item))
                if "default" in item.keys():
                  default = {"actions": item["default"]["actions"]}
                  data = {"name": item["name"], "statements": "none" , "default": default}
                  template["policies"].append(data)
                continue

            for name, statement in item["statements"].items():
                conditions = []
                actions = []
                for rule in statement:
                    if "actions" in rule:
                        actions.extend(rule["actions"])
                    elif "conditions" in rule:
                        conditions.extend(rule["conditions"])
                    else:
                        logger.debug(f"# NO RULE MATCHED: {rule}")

                for i, condition in enumerate(conditions):
                    logger.debug(f"  - condition : {condition}")
                    if "route-filter" in condition.keys():
                        prefix, *match_type_elem = condition["route-filter"].split()
                        logger.debug(f"    - match_type_elem length: {len(match_type_elem)}")
                        # exact
                        if len(match_type_elem) == 1:
                            # exact
                            length = dict()
                            match_type = match_type_elem[0]
                        elif len(match_type_elem) == 2:
                            if match_type_elem[0] == "prefix-length-range":
                                # ex. prefix-length-range /25-/27 -> {"min": 25, "max": 27}
                                min_length, max_length = [
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
                    tmpactions = {}
                    if "as-path-prepend" in action.keys():
                        #logger.debug(f"as-path-prepend:::: " + str(action))
                        asn = action["as-path-prepend"].split()

                        tmpactions.update({"as-path-prepend": {"asn": asn}})
                        #conditions[i] = {"as-path-prepend": {"asn": asn}}

                    if "community" in action.keys():
                        #logger.debug(f"community:::: " + str(action))
                        community_action, community_name = action["community"].split()

                        tmpactions.update ({
                            "community": {
                                "action": community_action,
                                "name": community_name,
                            }
                        })
                    actions[i].update(tmpactions)

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

    xr_translator = XRTranslator()
    for xr_output_file in xr_ttp_outputs:
        with open(xr_output_file) as f:
            ttp_parsed_config = json.load(f)
        logger.info(f"loading {xr_output_file}")
        xr_translator.load_ttp_parsed_config(ttp_parsed_config)
        xr_translator.translate_policies()
        policy_model_output = {
            "node": xr_translator.node,
            "prefix-set": xr_translator.prefix_set,
            "as-path-set": xr_translator.aspath_set,
            "community-set": xr_translator.community_set,
            "policies": xr_translator.policies,
        }

        save_policy_model_output(network, snapshot, xr_output_file, policy_model_output)


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
