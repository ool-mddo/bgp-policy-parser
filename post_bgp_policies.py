import argparse
import glob
import json
import os
import re
import requests
from typing import List, Dict


BGP_POLICIES_DIR = os.environ.get("MDDO_BGP_POLICIES_DIR", "./policy_model_output")
MODEL_CONDUCTOR_HOST = os.environ.get("MODEL_CONDUCTOR_HOST", "model-conductor:9292")


def read_bgp_policy_data() -> List:
    """Read bgp-policy data from files
    Returns:
        List: all bgp policies
    """
    bgp_policy_files = glob.glob(os.path.join(BGP_POLICIES_DIR, "*"))
    bgp_policies = []
    for bgp_policy_file in bgp_policy_files:
        with open(bgp_policy_file, "r") as f:
            bgp_policies.append(json.load(f))
    return bgp_policies


def convert_policy(bgp_policy: Dict) -> Dict:
    """Convert a policy (to merge topology data)
    Args:
        bgp_policy (Dict): A BGP policy
    Returns:
        Dict: A BGP policy (node-attribute patch format)
    """
    return {
        "node-id": re.sub(r"/\d+$", "", bgp_policy["node"]),
        "mddo-topology:bgp-proc-node-attributes": {
            "policy": bgp_policy["policies"],
            "prefix-set": bgp_policy["prefix-set"],
            "as-path-set": bgp_policy["as-path-set"],
            "community-set": bgp_policy["community-set"],
        },
    }


def pack_policies(bgp_policies: List) -> Dict:
    """Pack policy data to single Object
    Args:
        bgp_policies (List): Policies (list of policy)
    Returns:
        Dict: Node-attribute patches (includes attribute patch for several node)
    """
    packed_data = {"node": [convert_policy(d) for d in bgp_policies]}
    return packed_data


def post_bgp_policy(network: str, snapshot: str, bgp_policy: Dict) -> requests.Response:
    """Post node-attribute patches to merge topology data
    Args:
        network (str): Network name
        snapshot (str): Snapshot name
        bgp_policy (Dict): Node attribute patches (packed policy data)
    Returns:
        requests.Response
    """
    url = f"http://{MODEL_CONDUCTOR_HOST}/conduct/{network}/{snapshot}/topology/bgp_proc/policies"
    payload = json.dumps(bgp_policy)
    headers = {"Content-Type": "application/json"}
    return requests.post(url=url, data=payload, headers=headers)


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

    bgp_policies = read_bgp_policy_data()
    packed_policy = pack_policies(bgp_policies)

    print("Post policy data")
    response = post_bgp_policy(args.network, args.snapshot, packed_policy)
    print(f"- status: {response.status_code}")
    # print(f"- status: {response.text}")
