import json, sys, yaml
from sys import stderr, stdout
from logging import getLogger, StreamHandler, Formatter, INFO
from dataclasses import dataclass, field, asdict, is_dataclass
from typing import Union
from enum import Enum

class PolicyPrefix(Enum):
    MATCH = "match-"
    NOT_MATCH = "not-match-"
    IF_CONDITION = "if-condition-"
    NOT_IF_CONDITION = "not-if-condition-"

class PMEncoder(json.JSONEncoder):
    def default(self, data):
        if is_dataclass(data):
            return asdict(data)
        return json.JSONEncoder.default(self, data)

@dataclass
class Statement:
    name: str = ""
    conditions: list[dict] = field(default_factory=list) 
    actions: list[dict] = field(default_factory=list)

@dataclass
class PolicyModel:
    name: str = ""
    statements: list[Statement] = field(default_factory=list)
    default: dict = field(default_factory=dict)

    def set_default_accept(self):
        self.default = { "actions": [{ "target": "accept" }]}
    
    def set_default_reject(self):
        self.default = { "actions": [{ "target": "reject" }]}

class XRTranslator():

    def __init__(self, ttp_parsed_data: dict):
        self.node = ""
        self.community_set = []
        self.aspath_set = []
        self.prefix_set = []
        self.policies: list[PolicyModel] = []
        self.ttp_parsed_data = ttp_parsed_data[0][0]

        self.logger = getLogger("xr")
        self.logger.setLevel(INFO)
        formatter = Formatter('[{asctime}:{levelname}] {message}', style='{')

        sh = StreamHandler(stdout)
        sh.setFormatter(formatter)
        sh.setLevel(INFO)
        self.logger.addHandler(sh)

        self.ttp_parsed_data = ttp_parsed_data[0][0]

        self.translate_node()
        self.translate_community_set()
        self.translate_aspath_set()
        self.translate_prefix_set()

    def get_policy_by_name(self, name: str) -> Union[PolicyModel, None]:
        result = [ p for p in self.policies if p.name == name ]
        if len(result) == 0:
            self.logger.info(f"No policy objects found for {name}.")
            return None
        if len(result) > 1:
            self.logger.info(f"multiple policy objects found for {name}.")
        return result[0]

    def get_opposite_policy_name(self, name: str) -> Union[str, None]:
        maps = {
            PolicyPrefix.IF_CONDITION    : PolicyPrefix.NOT_IF_CONDITION,
            PolicyPrefix.NOT_IF_CONDITION: PolicyPrefix.IF_CONDITION,
            PolicyPrefix.MATCH           : PolicyPrefix.NOT_MATCH,
            PolicyPrefix.NOT_MATCH       : PolicyPrefix.MATCH,
        }
        
        if name.startswith(PolicyPrefix.IF_CONDITION.value):
            opposite_policy_name = name.replace(
                PolicyPrefix.IF_CONDITION.value,
                maps[PolicyPrefix.IF_CONDITION].value
            )
        elif name.startswith(PolicyPrefix.NOT_IF_CONDITION.value):
            opposite_policy_name = name.replace(
                PolicyPrefix.NOT_IF_CONDITION.value,
                maps[PolicyPrefix.NOT_IF_CONDITION].value
            )
        elif name.startswith(PolicyPrefix.MATCH.value):
            opposite_policy_name = name.replace(
                PolicyPrefix.MATCH.value,
                maps[PolicyPrefix.MATCH].value
            )
        elif name.startswith(PolicyPrefix.NOT_MATCH.value):
            opposite_policy_name = name.replace(
                PolicyPrefix.NOT_MATCH.value,
                maps[PolicyPrefix.NOT_MATCH].value
            )
        else:
            self.logger.info("Could not find opposite policy for {name}.")
            opposite_policy_name = None

        if opposite_policy_name:
            self.logger.info(f"opposite policy for '{name}' is '{opposite_policy_name}'")
            return opposite_policy_name
        else:
            self.logger.info(f"opposite policy for '{name}' not found")
            return None

    def update_policy(self, policy: PolicyModel):
        name = policy.name
        target_policy = self.get_policy_by_name(name)
        target_index = self.policies.index(target_policy)
        self.policies[target_index] = policy

    def translate_node(self) -> None:
        self.logger.info("- node")
        for item in self.ttp_parsed_data["interfaces"]:
            if item["name"] == "Loopback0":
                self.logger.info(f"-- node: {item['ipv4']['address']}")
                self.node = item["ipv4"]["address"]

    def translate_community_set(self) -> None:
        self.logger.info("- community-set")
        if "community-sets" in self.ttp_parsed_data.keys():
            for community_obj in self.ttp_parsed_data["community-sets"]:
                self.logger.info(f"-- community: {community_obj}")
                community_data = {"name": community_obj["name"], "communities": community_obj["communities"]}
                self.community_set.append(community_data)
    
    def translate_aspath_set(self) -> None: 
        self.logger.info("- as-path-set")
        if "as-path-sets" in self.ttp_parsed_data.keys():
            for aspath_obj in self.ttp_parsed_data["as-path-sets"]:
                self.logger.info(f"-- as-path-set: {aspath_obj}")
                aspath_data = {
                    "group-name": aspath_obj["name"],
                    "as-path": {
                        "name": aspath_obj["name"]
                    }
                }

                if "conditions" in aspath_obj.keys():

                    for aspath_condition in aspath_obj["conditions"]:

                        if "pattern" in aspath_condition.keys():
                            aspath_data["as-path"]["pattern"] = aspath_condition["pattern"]

                        if "length" in aspath_condition.keys():
                            if aspath_condition["condition"] == "le":
                                aspath_data["as-path"]["length"] = { "max": aspath_condition["length"]}
                            elif aspath_condition["condition"] == "ge":
                                aspath_data["as-path"]["length"] = { "min": aspath_condition["length"]}
                self.aspath_set.append(aspath_data)

    def translate_prefix_set(self) -> None:
        self.logger.info("- prefix-set")
        if "prefix-sets" in self.ttp_parsed_data.keys():
            for item in self.ttp_parsed_data["prefix-sets"]:
                self.logger.info(f"-- prefix-set: {item}")
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
                        length = { "min": prefix_length, "max": prefix_length }

                    prefixes.append({
                        "prefix": prefix_obj["prefix"],
                        "match-type": match_type,
                        "length": length
                    })

                self.prefix_set.append({
                    "name": item["name"],
                    "prefixes": prefixes,
                })

    def translate_rule(self, rule: dict) -> dict:    
        self.logger.info(f"translate rule: {rule}")
        action = None
        if rule['action'] == 'set':
            attr = rule['attr']
            if attr == 'med':
                action = { "metric": rule['value'] } 
            elif attr == 'local-preference':
                action = { "local-preference": rule['value']}
            elif attr == 'community':
                community_name = rule['value'].split()[0]
                if 'additive' in rule['value']:
                    action = { "community": { "action": "add", "name": community_name }}
                else:
                    action = { "community": { "action": "set", "name": community_name }}
            elif attr == 'next-hop':
                action = { "next-hop": rule['value'] }

        elif rule['action'] == 'delete':
            attr = rule['attr']
            if attr == 'community':
                # TODO: not in ~ への対応
                community_name = rule['value'].split()[-1]
                action = { "community": { "action": "delete", "name": community_name } }
            
        elif rule['action'] == 'apply':
            action = { 'apply': rule['value'] }
        
        elif rule['action'] in ['pass', 'drop', 'done']:
            target_maps = { 
                'pass': 'next-term', 'drop': 'reject', 'done': 'accept'
            }
            action = { 'target': target_maps[rule['action']]  }

        if action:
            return action
        else:
            return { }

    def convert_prefix_list_into_route_filter(self,prefix_list_name: str) -> list:
        """Convert prefix-list into route-filter
        Args:
            prefix_list_name (str): prefix_list name of Conversion target
        Returns:
            route_fliter_list (list): converted route-fliter data 
        
        """
        route_filter_list = []
        for item in self.prefix_set:
            if item["name"] == prefix_list_name:
                for prefix_item in item["prefixes"]:
                    self.logger.info(f"- convert prefix-list:{prefix_list_name} into route-filter {prefix_item['prefix']}")
                    route_filter_list.append({"route-filter": prefix_item})
                return route_filter_list
        self.logger.info(f"{prefix_list_name} is not match in prefix-list_data")
        return route_filter_list 

    def translate_match(self, match: str) -> list:
        condition = []
        # destination in prefix-list
        if match.split()[0] == "destination":
            condition = self.convert_prefix_list_into_route_filter(match.split()[-1])
            return condition 
        
        # as-path in as-path-set
        elif match.split()[0] == "as-path":
            as_path_group_item = {"as-path-group": match.split()[-1]}
            condition.append(as_path_group_item)
            return condition
        
        # community match-any community-set
        elif match.split()[0] == "community":
            _, op, community = match.split()
            if op == "matches-any":
                condition.append({
                    "community": community
                })
                return condition
            elif op == "matches-every":
                self.logger.info("matches-every is not implemented")

    def generate_conditional_policies(self, basename: str, if_condition: dict) -> list[PolicyModel]:
        statement = Statement(name="10")
        matches = if_condition["matches"]
        for match in matches:
            conditions = self.translate_match(match)
            if conditions:
                statement.conditions.extend(conditions)
            else:
                self.logger.info(f"{match} could not be translated.")
                statement.conditions.extend([{ "_message": {"TRANSLATION_FAILED": match }}])
        
        statement.actions.append({ "target": "accept" })
        match_policy = PolicyModel(
            name=f"{PolicyPrefix.MATCH.value}{basename}",
            statements=[statement],
        )
        match_policy.set_default_reject()

        not_match_statement = Statement(name="10")
        not_match_statement.conditions.append({ "policy": f"{PolicyPrefix.MATCH.value}{basename}" })
        not_match_statement.actions.append({ "target": "reject" })
        not_match_policy = PolicyModel(
            name=f"{PolicyPrefix.NOT_MATCH.value}{basename}",
            statements=[not_match_statement],
            default={"actions": [{}]}
        )
        not_match_policy.set_default_accept()

        return [match_policy, not_match_policy]

    def translate_policies(self):
        for policy in self.ttp_parsed_data["policies"]:
            self.translate_policy(ttp_policy=policy)

    def translate_policy(self, ttp_policy: dict):
        self.logger.info(f"translating policy: {ttp_policy}")
        policy = PolicyModel(default={"actions": []})
        policy.name = ttp_policy["name"]

        count = 0
        past_if_condition_policies: list[PolicyModel] = []

        for rule in ttp_policy["rules"]:
            self.logger.info(f"start: {rule}")
            count += 10
            statement = Statement()
            statement.name = str(count)
            policy_basename = f"{policy.name}-{count}"

            if "if" not in rule.keys():
                action = self.translate_rule(rule)
                statement.actions.append(action)
                past_if_condition_policies = []

            elif rule["if"] == "if":
                self.logger.info(f"'if' rule found in {policy.name}: {rule}")
                past_if_condition_policies = []
                # if文の条件判定を行うためのポリシーを作成
                match_policy, not_match_policy = self.generate_conditional_policies(
                    basename=policy_basename,
                    if_condition=rule["condition"]
                )
                self.policies.extend([match_policy, not_match_policy])

                self.logger.info(rule)
                for inner_rule1 in rule["rules"]:
                    inner_action = self.translate_rule(inner_rule1)
                    if inner_action:
                        statement.actions.append(inner_action)
                    else:
                        self.logger.info(f"{inner_rule1} could not be translated.")

                if_policy = PolicyModel(
                    name=f"{PolicyPrefix.IF_CONDITION.value}{policy_basename}",
                    statements=[Statement(
                        name="10", conditions=[{"policy": match_policy.name}],
                        actions=[{ "target": "accept" }],
                    )]
                )
                if_policy.set_default_reject()

                statement.conditions.append({ "policy": if_policy.name })

                self.policies.append(if_policy)

                past_if_condition_policies.append(if_policy)

            elif rule["if"] == "elseif":
                self.logger.info(f"'elseif' rule found in {policy.name}: {rule}")

                # if文の条件判定を行うためのポリシーを作成
                match_policy, not_match_policy = self.generate_conditional_policies(
                    basename=policy_basename,
                    if_condition=rule["condition"]
                )
                self.policies.extend([match_policy, not_match_policy])

                for inner_rule1 in rule["rules"]:
                    inner_action = self.translate_rule(inner_rule1) 
                    if inner_action:
                        statement.actions.append(inner_action)
                    else:
                        self.logger.info(f"{inner_rule1} could not be translated.")


                if_policy = PolicyModel(
                    name=f"{PolicyPrefix.IF_CONDITION.value}{policy_basename}",
                    statements=[]
                )
                if_policy.set_default_accept()

                # elseifなので前にあるif/elseif節の条件に合致するものはrejectする
                for i, past_policy in enumerate(past_if_condition_policies):
                    if_policy.statements.append( 
                        Statement(
                            name=f"past-policy-{i}",
                            conditions=[{ "policy": past_policy.name}],
                            actions=[{ "target": "reject" }]
                        )
                    )

                if_policy.statements.append(Statement(
                    name="10", conditions=[{ "policy": not_match_policy.name }],
                    actions=[{"target": "reject"}]
                ))

                statement.conditions.append({"policy": if_policy.name})

                not_if_policy = PolicyModel(
                    name=f"{PolicyPrefix.NOT_IF_CONDITION.value}{policy_basename}",
                    statements=[Statement(
                        name="10", conditions=[{ "policy": if_policy.name }],
                        actions=[{"target": "reject"}]
                    )]
                )
                not_if_policy.set_default_accept()

                self.policies.extend([if_policy, not_if_policy])

                past_if_condition_policies.append(if_policy)

            elif rule["if"] == "else":
                else_policy = PolicyModel(
                    name=f"{PolicyPrefix.IF_CONDITION.value}{policy_basename}",
                    default = {"actions": []}
                )
                statement.conditions.append({
                    "policy": else_policy.name
                })

                # elseなので前にあるif/elseif節の条件に合致するものはrejectする
                for i, past_policy in enumerate(past_if_condition_policies):
                    else_policy.statements.append(Statement(
                        name=f"past-policy-{i}",
                        conditions=[{ "policy": past_policy.name }],
                        actions=[{ "target": "reject" }]
                    ))

                self.policies.append(else_policy)
                
                for inner_rule1 in rule["rules"]:
                    inner_action = self.translate_rule(inner_rule1)
                    if inner_action:
                        statement.actions.append(inner_action)
                    else:
                        self.logger.info(f"{inner_rule1} could not be translated.")
            else:
                self.logger.info(f"rule not translated: {rule}")

            policy.statements.append(statement)

        self.logger.info(f"appending policy: {policy}")
        self.policies.append(policy)

if __name__ == "__main__":
    ttp_file = sys.argv[1]
    output_file = sys.argv[2]

    with open(ttp_file, "r") as f:
        ttp_parsed_config = json.load(f)

    xrtranslator = XRTranslator(ttp_parsed_config)
    xrtranslator.translate_policies()
    policy_model_output = {
        "node": xrtranslator.node,
        "prefix-set": xrtranslator.prefix_set,
        "as-path-set": xrtranslator.aspath_set,
        "community-set": xrtranslator.community_set,
        "policies": xrtranslator.policies
    }

    with open(output_file, "w") as f:
        json.dump(policy_model_output, fp=f, indent=2, cls=PMEncoder)