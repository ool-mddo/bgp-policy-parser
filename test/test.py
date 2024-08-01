from ttp import ttp
import os
import json
import sys
from dataclasses import asdict


FILE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(FILE_DIR, "inputs")
OUTPUT_DIR = os.path.join(FILE_DIR,"outputs")
TEMPLATE_DIR = os.path.join(FILE_DIR,os.pardir,"src", "template")
EXPECTS_DIR = os.path.join(FILE_DIR, "expects")

sys.path.append(os.path.join(FILE_DIR,os.pardir,"src"))
from XRTranslator import XRTranslator, PMEncoder
from parse_bgp_policy import _convert_juniper_ttp_to_policy_model

def _ttp_parse(file,template) -> list:
    parser = ttp(file,template)
    parser.parse()
    return parser.result()

def test_cisco_ios_xr_policy_model():
    ttp_parsed_file = os.path.join(EXPECTS_DIR,"cisco_ios_xr","ttp.json")
    output_file = os.path.join(OUTPUT_DIR,"cisco_ios_xr","policy_model.json")
    expect_file = os.path.join(EXPECTS_DIR,"cisco_ios_xr","policy_model.json")
    with open(ttp_parsed_file, "r") as f:
       ttp_parsed_config = json.load(f)

    xr_translator = XRTranslator(ttp_parsed_config)
    xr_translator.translate_policies()
    policy_model_output = {
        "node": xr_translator.node,
        "prefix-set": xr_translator.prefix_set,
        "as-path-set": xr_translator.aspath_set,
        "community-set": xr_translator.community_set,
        "policies": xr_translator.policies,
        "bgp_neighbors": xr_translator.bgp_neighbors
    }
    with open(output_file,"w") as f:
        json.dump(policy_model_output, f, indent=2, cls=PMEncoder)

    with open(expect_file,"r") as f:
        expect_data = json.load(f)

    with open(output_file,"r") as f:
        output_data = json.load(f)

    assert  expect_data == output_data

def test_cisco_ios_xr_ttp():
    input_file = os.path.join(INPUT_DIR,"cisco_ios_xr.conf")
    template_file = os.path.join(TEMPLATE_DIR,"cisco_ios_xr.ttp")
    output_file = os.path.join(OUTPUT_DIR, "cisco_ios_xr","ttp.json")
    expect_file = os.path.join(EXPECTS_DIR, "cisco_ios_xr","ttp.json")
    ttp_result = _ttp_parse(input_file,template_file)

    with open(output_file, "w") as f:
        json.dump(ttp_result, f, indent=2)

    with open(expect_file, "r") as f:
        expect_data = json.load(f)

    assert  ttp_result == expect_data

def test_juniper_policy_model():
    ttp_parsed_file = os.path.join(EXPECTS_DIR,"juniper","ttp.json")
    output_file = os.path.join(OUTPUT_DIR,"juniper","policy_model.json")
    expect_file = os.path.join(EXPECTS_DIR,"juniper","policy_model.json")
    with open(ttp_parsed_file, "r") as f:
        ttp_parsed_config = json.load(f)
    output_data = _convert_juniper_ttp_to_policy_model(ttp_parsed_config)

    with open(output_file,"w") as f:
        json.dump(output_data,f,indent=2)
    with open(expect_file,"r") as f:
        expect_data = json.load(f)

    assert expect_data == output_data


def test_juniper_ttp():
    input_file = os.path.join(INPUT_DIR,"juniper.conf")
    template_file = os.path.join(TEMPLATE_DIR,"juniper.ttp")
    output_file = os.path.join(OUTPUT_DIR, "juniper","ttp.json")
    expect_file = os.path.join(EXPECTS_DIR, "juniper","ttp.json")
    ttp_result = _ttp_parse(input_file,template_file)

    with open(output_file, "w") as f:
        json.dump(ttp_result, f, indent=2)

    with open(expect_file, "r") as f:
        expect_data = json.load(f)
            
    assert  ttp_result == expect_data

