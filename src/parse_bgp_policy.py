import argparse
import glob
import json
import os
import re
import sys
from logging import getLogger, Formatter, DEBUG, ERROR, FileHandler, StreamHandler
from typing import Dict, List
from ttp import ttp
from xr_translator import XRTranslator, PMEncoder


# constants
SRC_DIR = os.path.dirname(os.path.realpath(__file__))
TTP_TEMPLATES_DIR = os.path.join(SRC_DIR, "template")
TTP_CONFIGS_DIR = os.environ.get("MDDO_TTP_CONFIGS_DIR", "./configs")
TTP_OUTPUTS_DIR = os.environ.get("MDDO_TTP_OUTPUTS_DIR", "./ttp_output")
TTP_BGP_POLICIES_DIR = os.environ.get("MDDO_BGP_POLICIES_DIR", "./policy_model_output")


logger = getLogger("main")
logger.setLevel(DEBUG)
formatter = Formatter("[{asctime} @{funcName}-{lineno} - {levelname}] {message}", style="{")

fh = FileHandler("parser.log")
fh.setFormatter(formatter)
fh.setLevel(DEBUG)
logger.addHandler(fh)

sh = StreamHandler(sys.stdout)
sh.setFormatter(formatter)
sh.setLevel(ERROR)
logger.addHandler(sh)


def _ttp_parse(text: str, os_type: str) -> List:
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


def _file_basename(orig_file_name: str) -> str:
    file_name = os.path.basename(orig_file_name)
    file_name_wo_ext = file_name
    file_name_tokens = os.path.splitext(file_name)
    if file_name_tokens[-1] in [".txt", ".conf", ".json"]:
        file_name_wo_ext = file_name_tokens[0]

    return file_name_wo_ext


def _save_file(save_dir: str, file_name: str, data: List | Dict, use_pmenc: bool = False) -> None:
    os.makedirs(save_dir, exist_ok=True)
    file_name_wo_ext = _file_basename(file_name)
    save_file = os.path.join(save_dir, f"{file_name_wo_ext}.json")
    logger.info(f"Save file: {save_file}")
    with open(save_file, "w", encoding="utf-8") as f:
        if use_pmenc:
            f.write(json.dumps(data, indent=2, cls=PMEncoder))
        else:
            f.write(json.dumps(data, indent=2))


def _save_parsed_result(network: str, snapshot: str, os_type: str, config_file: str, parser_result: List) -> None:
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
    save_dir = os.path.join(TTP_OUTPUTS_DIR, network, snapshot, os_type)
    _save_file(save_dir, config_file, parser_result)


def _save_policy_model_output(network: str, snapshot: str, ttp_result_file: str, model_output: Dict) -> None:
    """Save policy model
    Args:
        network (str): Network name
        snapshot (str): Snapshot name
        ttp_result_file (str): File name of TTP result
        model_output (Dict): Policy model data
    Returns:
        None
    """
    save_dir = os.path.join(TTP_BGP_POLICIES_DIR, network, snapshot)
    _save_file(save_dir, ttp_result_file, model_output, use_pmenc=True)


def _parse_files(network: str, snapshot: str, os_type: str) -> None:
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
        logger.info(f"config dir:{config_dir} for os_type:{os_type} is not found")
        return

    config_files = glob.glob(os.path.join(config_dir, "*"))
    for config_file in config_files:
        with open(config_file, "r", encoding="utf-8") as f:
            config_txt = f.read()
            parsed = _ttp_parse(config_txt, os_type)
        _save_parsed_result(network, snapshot, os_type, config_file, parsed)


def _convert_juniper_ttp_to_policy_model(ttp_output: dict) -> dict:
    """Convert parsed juniper policy to policy model
    Args:
        ttp_output (dict): Policy data parsed by TTP
    Returns:
        dict: Policy model data
    """

    ttp_output = ttp_output[0][0][0]
    policy_model = {"node": "", "prefix-set": [], "as-path-set": [], "community-set": [], "policies": []}

    # node
    for item in ttp_output["interfaces"]:
        if item["name"] == "lo0":
            policy_model["node"] = item["address"]

    # prefix-set
    if "prefix-sets" in ttp_output.keys():
        for item in ttp_output["prefix-sets"]:
            policy_model["prefix-set"].append(item)
    else:
        logger.info("prefix-set not found")

    # as-path-set
    if "aspath-sets" in ttp_output.keys():
        for item in ttp_output["aspath-sets"]:
            policy_model["as-path-set"].append(item)
    else:
        logger.info("as-path-set not found")

    # community-set
    if "community-sets" in ttp_output.keys():
        for item in ttp_output["community-sets"]:
            data = {
                "name": item["community"],
                "communities": [{"community": member} for member in item["members"].split()],
            }
            policy_model["community-set"].append(data)
    else:
        logger.info("community-set not found")

    # policies
    if "policies" not in ttp_output:
        logger.info("policy not found")
        return policy_model

    for item in ttp_output["policies"]:
        statements = []

        if "statements" not in item.keys():
            logger.info(f"statements not found in {item['name']}")
            if "default" in item.keys():
                default = {"actions": item["default"]["actions"]}
                data = {
                    "name": item["name"],
                    "statements": "none",
                    "default": default,
                }
                policy_model["policies"].append(data)
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
                    # default
                    length = {}
                    match_type = ""
                    # exact
                    if len(match_type_elem) == 1:
                        # exact
                        match_type = match_type_elem[0]
                    elif len(match_type_elem) == 2:
                        if match_type_elem[0] == "prefix-length-range":
                            # ex. prefix-length-range /25-/27 -> {"min": 25, "max": 27}
                            min_length, max_length = [x.lstrip("/") for x in match_type_elem[1].split("-")]
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
                    prefix_list, match_type = condition["prefix-list-filter"].split()

                    conditions[i] = {
                        "prefix-list-filter": {
                            "prefix-list": prefix_list,
                            "match-type": match_type,
                        }
                    }

                if "community" in condition.keys():
                    communities = condition["community"].strip("[").strip("]").split()

                    conditions[i] = {"community": communities}

            for action in actions:
                tmp_action = {}
                if "as-path-prepend" in action.keys():
                    # logger.debug(f"as-path-prepend:::: " + str(action))
                    asn_list = action["as-path-prepend"].strip('"').split()
                    as_path_prepend_value = []
                    for asn in asn_list:
                        as_path_prepend_value.append({"asn": asn, "repeat": 1})
                    tmp_action.update({"as-path-prepend": as_path_prepend_value})
                    # conditions[i] = {"as-path-prepend": {"asn": asn}}

                if "community" in action.keys():
                    # logger.debug(f"community:::: " + str(action))
                    community_action, community_name = action["community"].split()

                    tmp_action.update(
                        {
                            "community": {
                                "action": community_action,
                                "name": community_name,
                            }
                        }
                    )
                action.update(tmp_action)

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
        policy_model["policies"].append(data)

    return policy_model


def valid_parsed_result(os_type: str, output_file: str, parsed_data: dict) -> bool:
    """
    Validate ttp parsed data (parsed data of cisco/juniper with ttp)
    Args:
        output_file (str): Output file name
        parsed_data (dict): Parsed data of ttp
    Returns:
        bool
    """
    if any(parsed_data) is False:
        logger.info(f"parse result:{output_file} is empty")
        return False

    if os_type == "juniper":
        parsed_data = parsed_data[0]  # One more nesting when juniper

    if all(len(parsed_data[k]) < 1 for k in parsed_data.keys()):
        logger.error(f"parse result:{output_file} ({os_type}) is empty")
        return False

    if "bgp" not in parsed_data:
        logger.error(f"parse result:{output_file} ({os_type}) doesn't have bgp configs")
        return False

    if not any(re.match(r"[Ll]o(opback)?\d", d["name"]) for d in parsed_data["interfaces"]):
        logger.error(parsed_data["interfaces"])
        logger.error(f"parse result:{output_file} ({os_type}) doesn't have loopback")
        return False

    return True


def parse_juniper_bgp_policy(network: str, snapshot: str) -> None:
    """
    Parse juniper configs and generate bgp-policy data
    Args:
        network (str): Network name
        snapshot (str): Snapshot name
    Returns:
        None
    """
    _parse_files(network, snapshot, "juniper")
    junos_ttp_outputs_dir = os.path.join(TTP_OUTPUTS_DIR, network, snapshot, "juniper")
    junos_ttp_outputs = glob.glob(os.path.join(junos_ttp_outputs_dir, "*"))

    for ttp_output_file in junos_ttp_outputs:
        logger.info(f"loading: {ttp_output_file}")

        with open(ttp_output_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        if valid_parsed_result("juniper", ttp_output_file, data[0][0]) is False:
            logger.error(f"skip parsed result:{ttp_output_file} because it is invalid")
            continue

        ttp_output = data
        policy_model = _convert_juniper_ttp_to_policy_model(ttp_output)
        _save_policy_model_output(network, snapshot, ttp_output_file, policy_model)


def parse_cisco_ios_xr_bgp_policy(network: str, snapshot: str) -> None:
    """
    Parse cisco_ios_xr configs and generate bgp policy data
    Args:
        network (str): Network name
        snapshot (str): Snapshot name
    Returns:
        None
    """
    _parse_files(network, snapshot, "cisco_ios_xr")
    xr_ttp_outputs_dir = os.path.join(TTP_OUTPUTS_DIR, network, snapshot, "cisco_ios_xr")
    xr_ttp_outputs = glob.glob(os.path.join(xr_ttp_outputs_dir, "*"))

    for xr_output_file in xr_ttp_outputs:
        logger.info(f"loading {xr_output_file}")

        with open(xr_output_file, "r", encoding="utf-8") as f:
            ttp_parsed_config = json.load(f)

        if valid_parsed_result("cisco_ios_xr", xr_output_file, ttp_parsed_config[0][0]) is False:
            logger.error(f"skip parsed result:{xr_output_file} because it is invalid")
            continue

        xr_translator = XRTranslator(ttp_parsed_config)
        xr_translator.translate_policies()
        policy_model_output = {
            "node": xr_translator.node,
            "prefix-set": xr_translator.prefix_set,
            "as-path-set": xr_translator.aspath_set,
            "community-set": xr_translator.community_set,
            "policies": xr_translator.policies,
            "bgp_neighbors": xr_translator.bgp_neighbors,
        }
        _save_policy_model_output(network, snapshot, xr_output_file, policy_model_output)


if __name__ == "__main__":
    # pylint: disable=duplicate-code
    parser = argparse.ArgumentParser(description="Collect configs to parse bgp-policy")
    parser.add_argument("--network", "-n", required=True, type=str, help="Specify a target network name")
    parser.add_argument(
        "--snapshot",
        "-s",
        default="original_asis",
        type=str,
        help="Specify a target snapshot name",
    )
    args = parser.parse_args()
    # pylint: enable=duplicate-code

    parse_juniper_bgp_policy(args.network, args.snapshot)
    parse_cisco_ios_xr_bgp_policy(args.network, args.snapshot)
