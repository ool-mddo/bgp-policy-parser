from typing import List, Dict
import argparse
import glob
import json
import os
import re
import requests

BGP_POLICIES_DIR = os.environ.get("MDDO_BGP_POLICIES_DIR", "./policy_model_output")
MODEL_CONDUCTOR_HOST = os.environ.get("MODEL_CONDUCTOR_HOST", "model-conductor:9292")


def _read_bgp_policy_data(network: str, snapshot: str) -> List:
    """Read bgp-policy data from files
    Args:
        network (str): Network name
        snapshot (str): Snapshot name
    Returns:
        List: all bgp policies
    """
    bgp_policy_dir = os.path.join(BGP_POLICIES_DIR, network, snapshot)
    bgp_policy_files = glob.glob(os.path.join(bgp_policy_dir, "*"))
    bgp_policies = []
    for bgp_policy_file in bgp_policy_files:
        with open(bgp_policy_file, "r", encoding="utf-8") as f:
            bgp_policies.append(json.load(f))
    return bgp_policies


def _convert_policy(bgp_policy: Dict) -> Dict:
    """Convert a policy (to merge topology data)
    Args:
        bgp_policy (Dict): A BGP policy
    Returns:
        Dict: A BGP policy (node-attribute patch format)
    """
    # patches for node attribute
    node_patches = {
        "node-id": re.sub(r"/\d+$", "", bgp_policy["node"]),
        "mddo-topology:bgp-proc-node-attributes": {
            "policy": bgp_policy["policies"],
            "prefix-set": bgp_policy["prefix-set"],
            "as-path-set": bgp_policy["as-path-set"],
            "community-set": bgp_policy["community-set"],
        },
    }
    if "bgp_neighbors" not in bgp_policy:
        return node_patches

    # patches for term-point attribute
    tp_patches = []
    for bgp_neighbor in bgp_policy["bgp_neighbors"]:
        af_key = "address_families"  # alias
        af_data = next(
            (af for af in bgp_neighbor[af_key] if af["afi"] == "ipv4" and af["next_hop_self"] is True),
            None,
        )
        if not af_data:
            continue

        in_out_policy_patch = {}
        if af_data["route_policy_in"] != "":
            in_out_policy_patch["import-policy"] = [af_data["route_policy_in"]]
        if af_data["route_policy_out"] != "":
            in_out_policy_patch["export-policy"] = [af_data["route_policy_out"]]

        if "ibgp-export" in af_data["route_policy_out"]:
            print("# DEBUG: af_data: ", af_data)
            tp_patch = {
                "tp-id": f"peer_{bgp_neighbor['remote_ip']}",
                "mddo-topology:bgp-proc-termination-point-attributes": in_out_policy_patch,
            }
            tp_patches.append(tp_patch)

    node_patches["ietf-network-topology:termination-point"] = tp_patches
    return node_patches


def _pack_policies(bgp_policies: List) -> Dict:
    """Pack policy data to single Object
    Args:
        bgp_policies (List): Policies (list of policy)
    Returns:
        Dict: Node-attribute patches (includes attribute patch for several node)
    """
    packed_data = {"node": [_convert_policy(d) for d in bgp_policies]}
    return packed_data


def post_bgp_policy(network: str, snapshot: str) -> requests.Response:
    """Post node-attribute patches to merge topology data
    Args:
        network (str): Network name
        snapshot (str): Snapshot name
    Returns:
        requests.Response
    """
    bgp_policies = _read_bgp_policy_data(network, snapshot)
    packed_policy = _pack_policies(bgp_policies)

    url = f"http://{MODEL_CONDUCTOR_HOST}/conduct/{network}/{snapshot}/topology/bgp_proc/policies"
    payload = json.dumps(packed_policy)
    headers = {"Content-Type": "application/json"}
    return requests.post(url=url, data=payload, headers=headers, timeout=180)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Post BGP policies")
    parser.add_argument("--network", "-n", required=True, type=str, help="Specify a target network name")
    parser.add_argument(
        "--snapshot",
        "-s",
        default="original_asis",
        type=str,
        help="Specify a target snapshot name",
    )
    args = parser.parse_args()

    print("Post policy data")
    response = post_bgp_policy(args.network, args.snapshot)
    print(f"- status: {response.status_code}")
    # print(f"- status: {response.text}")
