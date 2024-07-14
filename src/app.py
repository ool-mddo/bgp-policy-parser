import logging
from flask import Flask, jsonify
from flask.logging import create_logger
import collect_configs as cc
import parse_bgp_policy as parse_bp
import post_bgp_policies as post_bp

app = Flask(__name__)
app_logger = create_logger(app)
logging.basicConfig(level=logging.DEBUG)
# logging.basicConfig(level=logging.WARNING)


@app.route("/bgp_policy/<network>/<snapshot>/parsed_result", methods=["POST"])
def post_parsed_result(network: str, snapshot: str):
    # collect configs
    node_props = cc.read_node_props(network, snapshot)
    cc.copy_configs(network, snapshot, node_props)
    # parse bgp policy
    parse_bp.parse_juniper_bgp_policy(network, snapshot)
    parse_bp.parse_cisco_ios_xr_bgp_policy(network, snapshot)
    # response
    return jsonify({})


@app.route("/bgp_policy/<network>/<snapshot>/topology", methods=["POST"])
def post_topology_data(network: str, snapshot: str):
    response = post_bp.post_bgp_policy(network, snapshot)
    return jsonify({"status": response.status_code})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
