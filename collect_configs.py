import argparse
import csv
import os
import re
import shutil
import sys
from typing import List


CONFIGS_DIR = os.environ.get("MDDO_CONFIGS_DIR", "./configs")
QUERIES_DIR = os.environ.get("MDDO_QUERIES_DIR", "./queries")
TTP_CONFIGS_DIR = os.environ.get("MDDO_TTP_CONFIGS_DIR", "./configs")
OS_TYPES = ["JUNIPER", "CISCO_IOS_XR"]


def read_node_props(network: str, snapshot: str) -> List:
    """Read node_props csv
    Args:
        network (str): Network name
        snapshot (str): Snapshot name
    Returns:
        List: rows of csv data
    """
    snapshot_dir = os.path.join(QUERIES_DIR, network, snapshot)
    node_props_file = os.path.join(snapshot_dir, "node_props.csv")
    with open(node_props_file, "r") as f:
        reader = csv.DictReader(f)
        rows = [row for row in reader]
    return rows


def detect_src_file_name(src_dir: os.path, node_name: str) -> str:
    """Detect configuration file name using node name
    Args:
        src_dir (os.path): Source, snapshot directory (path)
        node_name (str): Node name to find configuration file
    Returns:
        str: configuration file name
    """
    file_names = os.listdir(src_dir)
    for file_name in file_names:
        # NOTE: search configuration file name starting node name
        if re.match(rf"{node_name}.*", file_name, flags=re.IGNORECASE):
            return file_name
    print(
        f"Error: source config is not found in {src_dir}, node_name:{node_name}",
        file=sys.stderr,
    )


def copy_configs(network: str, snapshot: str, node_props: List) -> None:
    """Copy configurations for bgp-policy-parser
    Args:
        network (str): Network name
        snapshot (str): Snapshot name
        node_props (List): node_props data
    Returns:
        None
    """
    src_dir = os.path.join(CONFIGS_DIR, network, snapshot, "configs")
    for node_prop in node_props:
        os_type = node_prop["Configuration_Format"].lower()
        if os_type not in [t.lower() for t in OS_TYPES]:
            continue

        print("* node_prop: ", node_prop)
        file_name = detect_src_file_name(src_dir, node_prop["Node"])
        src_file = os.path.join(src_dir, file_name)

        dst_dir = os.path.join(TTP_CONFIGS_DIR, os_type)
        os.makedirs(dst_dir, exist_ok=True)
        dst_file = os.path.join(dst_dir, file_name)
        print(f"  * copy {src_file} -> {dst_file}")
        shutil.copy(src_file, dst_file)


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

    node_props = read_node_props(args.network, args.snapshot)
    copy_configs(args.network, args.snapshot, node_props)
