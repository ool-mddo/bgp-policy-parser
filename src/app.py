import os
import logging
from flask import Flask, jsonify
from flask.logging import create_logger
import collect_configs as cc
import parse_bgp_policy as parse_bp
import post_bgp_policies as post_bp

app = Flask(__name__)
app_logger = create_logger(app)
logging.basicConfig(level=logging.WARNING)

MODEL_CONDUCTOR_HOST = os.environ.get("MODEL_CONDUCTOR_HOST", "localhost")
CONFIGS_DIR = os.environ.get("MDDO_CONFIGS_DIR", "./configs")
QUERIES_DIR = os.environ.get("MDDO_QUERIES_DIR", "./queries")


@app.route("/bgp_policy/<network>/<snapshot>", methods=["POST"])
def post_bgp_policies(network: str, snapshot: str):
    node_props = cc.read_node_props(network, snapshot)
    cc.copy_configs(network, snapshot, node_props)
    parse_bp.parse_juniper_bgp_policy()
    parse_bp.parse_cisco_ios_xr_bgp_policy()
    return jsonify({})


@app.route("/bgp_policy/<network>/<snapshot>", methods=["POST"])
def post_bgp_policies():
    pass


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
