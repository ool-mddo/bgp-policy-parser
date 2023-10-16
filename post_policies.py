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
    bgp_policy_files = glob.glob(os.path.join(BGP_POLICIES_DIR, "*"))
    bgp_policies = []
    for bgp_policy_file in bgp_policy_files:
        with open(bgp_policy_file, "r") as f:
            bgp_policies.append(json.load(f))
    return bgp_policies


def pack_policy_data(bgp_policy: Dict) -> Dict:
    return {
        "node-id": re.sub(r"/\d+$", "", bgp_policy["node"]),
        "mddo-topology:bgp-proc-node-attributes": {
            "policy": bgp_policy["policies"],
            "prefix-set": bgp_policy["prefix-set"],
            "as-path-set": bgp_policy["as-path-set"],
            "community-set": bgp_policy["community-set"]
        }
    }


def pack_policies(bgp_policies: List) -> Dict:
    packed_data = {"node": [pack_policy_data(d) for d in bgp_policies]}
    return packed_data


def post_bgp_policy(network: str, snapshot: str, bgp_policy: Dict) -> None:
    url = f"http://{MODEL_CONDUCTOR_HOST}/conduct/{network}/{snapshot}/topology/bgp_proc/policies"
    payload = json.dumps(bgp_policy)
    print(payload)  # debug
    headers = {'Content-Type': 'application/json'}
    requests.post(url=url, data=payload, headers=headers)


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
    post_bgp_policy(args.network, args.snapshot, packed_policy)
