import json
from sys import argv
from logging import getLogger
from dataclasses import dataclass, field, asdict, is_dataclass
from typing import Union, Self
from enum import Enum


class PolicyPrefix(Enum):
    IF_CONDITION = "if-condition-"
    NOT_IF_CONDITION = "not-if-condition-"


class PMEncoder(json.JSONEncoder):
    def default(self, o):
        if is_dataclass(o):
            return asdict(o)
        return json.JSONEncoder.default(self, o)


@dataclass
class Statement:
    name: str = ""
    conditions: list[dict] = field(default_factory=list)
    actions: list[dict] = field(default_factory=list)

    def is_empty(self) -> bool:
        return len(self.actions) == 0

    @staticmethod
    def generate_empty_statement() -> Self:
        return Statement(name="", conditions=[], actions=[])


@dataclass
class PolicyModel:
    name: str = ""
    statements: list[Statement] = field(default_factory=list)
    default: dict = field(default_factory=dict)

    def set_default_accept(self):
        self.default = {"actions": [{"target": "accept"}]}

    def set_default_reject(self):
        self.default = {"actions": [{"target": "reject"}]}

    def insert_policy_as_reject_statement(self, policy: Self, statement_name: str):
        self.statements.insert(
            0,
            Statement(
                name=statement_name,
                conditions=[{"policy": policy.name}],
                actions=[{"target": "reject"}],
            ),
        )

    def has_next_hop_self_in_head(self) -> bool:
        return self.statements[0].name == "_generated_next-hop-self"

    def insert_next_hop_self_in_head(self):
        self.statements.insert(
            0, Statement(name="_generated_next-hop-self", conditions=[], actions=[{"next-hop": "self"}])
        )


@dataclass
class AddressFamily:
    afi: str
    safi: str
    send_community_ebgp: bool = False
    next_hop_self: bool = False
    remove_private_as: bool = False
    route_policy_in: str = ""
    route_policy_out: str = ""


@dataclass
class BGPNeighbor:
    remote_as: int
    remote_ip: str
    address_families: list[AddressFamily] = field(default_factory=list)


class XRTranslator:
    def __init__(self, ttp_parsed_data: dict):
        self.logger = getLogger("main")
        self.node = ""
        self.community_set = []
        self.aspath_set = []
        self.prefix_set = []
        self.bgp_neighbors: list[BGPNeighbor] = []
        self.policies: list[PolicyModel] = []

        self.ttp_parsed_data = ttp_parsed_data[0][0]

        self.translate_bgp_neighbors()
        self.translate_node()
        self.translate_community_set()
        self.translate_aspath_set()
        self.translate_prefix_set()

    def auto_gen_ibgp_export(self):
        if not self.get_policy_by_name("ibgp-export"):
            self.logger.info("ibgp-export policy not found.")
            ibgp_export = PolicyModel(name="ibgp-export", statements=[], default={"actions": []})
            ibgp_export.statements.append(
                Statement(
                    name="_generated_next-hop-self",
                    conditions=[{"protocol": "bgp"}],
                    actions=[{"local-preference": "100"}, {"next-hop": "self"}],
                )
            )
            self.policies.append(ibgp_export)
        else:
            self.logger.info("ibgp-export policy found.")

    def get_policy_by_name(self, name: str) -> Union[PolicyModel, None]:
        result = [p for p in self.policies if p.name == name]
        if len(result) == 0:
            self.logger.info(f"No policy objects found for {name}.")
            return None
        if len(result) > 1:
            self.logger.info(f"multiple policy objects found for {name}.")
        return result[0]

    def get_opposite_policy(self, policy: PolicyModel) -> Union[PolicyModel, None]:
        maps = {
            PolicyPrefix.IF_CONDITION: PolicyPrefix.NOT_IF_CONDITION,
            PolicyPrefix.NOT_IF_CONDITION: PolicyPrefix.IF_CONDITION,
        }

        if policy.name.startswith(PolicyPrefix.IF_CONDITION.value):
            opposite_policy_name = policy.name.replace(
                PolicyPrefix.IF_CONDITION.value, maps[PolicyPrefix.IF_CONDITION].value
            )
        elif policy.name.startswith(PolicyPrefix.NOT_IF_CONDITION.value):
            opposite_policy_name = policy.name.replace(
                PolicyPrefix.NOT_IF_CONDITION.value,
                maps[PolicyPrefix.NOT_IF_CONDITION].value,
            )
        else:
            self.logger.info("Could not find opposite policy for {name}.")
            opposite_policy_name = None

        if opposite_policy_name:
            self.logger.info(f"opposite policy for '{policy}' is '{opposite_policy_name}'")
            opposite_policy = self.get_policy_by_name(opposite_policy_name)
            return opposite_policy

        self.logger.info(f"opposite policy for '{policy}' not found")
        return None

    def update_policy(self, policy: PolicyModel):
        name = policy.name
        target_policy = self.get_policy_by_name(name)
        target_index = self.policies.index(target_policy)
        self.policies[target_index] = policy

    def translate_bgp_neighbors(self) -> None:
        for ttp_neighbor in self.ttp_parsed_data["bgp"]["neighbors"]:
            self.logger.info(f"translate bgp neighbor: {ttp_neighbor}")
            if "remote-as" not in ttp_neighbor or "remote-ip" not in ttp_neighbor:
                self.logger.error(f"not found remote-as/ip info in {ttp_neighbor} (use neighbor-group?)")
                continue
            neighbor = BGPNeighbor(remote_as=ttp_neighbor["remote-as"], remote_ip=ttp_neighbor["remote-ip"])
            for ttp_af in ttp_neighbor["address-families"]:
                af = self.translate_af(ttp_af)
                neighbor.address_families.append(af)

            self.logger.info(f"append neighbor; {neighbor}")
            self.bgp_neighbors.append(neighbor)

    def translate_af(self, ttp_af: [dict]) -> AddressFamily:
        af = AddressFamily(afi=ttp_af["afi"], safi=ttp_af["safi"])
        if "route-policy" in ttp_af["configs"]:
            policy = ttp_af["configs"]["route-policy"]

            if "in" in policy:
                af.route_policy_in = policy["in"]
            if "out" in policy:
                af.route_policy_out = policy["out"]
        if "attrs" in ttp_af["configs"]:
            for attr in ttp_af["configs"]["attrs"]:
                if attr["value"] == "send-community-ebgp":
                    af.send_community_ebgp = True
                elif attr["value"] == "next-hop-self":
                    af.next_hop_self = True
                    if "route-policy" not in ttp_af["configs"]:
                        self.logger.info(f"auto generate ibgp-export: {str(ttp_af)}")
                        af.route_policy_out = "ibgp-export"
                elif attr["value"] == "remove-private-AS":
                    af.remove_private_as = True

        return af

    def translate_node(self) -> None:
        _loopback0 = [
            interface for interface in self.ttp_parsed_data["interfaces"] if interface["name"] == "Loopback0"
        ]

        if not _loopback0:
            self.logger.info("Loopback0 not found")
            return

        loopback0: dict = _loopback0[0]

        if "ipv4" not in loopback0.keys():
            self.logger.info("ipv4 address not found.")
            return

        self.logger.info(f"-- node: {loopback0['ipv4']['address']}")
        self.node = loopback0["ipv4"]["address"]

    def translate_community_set(self) -> None:
        self.logger.info("- community-set")
        if "community-sets" in self.ttp_parsed_data.keys():
            for community_obj in self.ttp_parsed_data["community-sets"]:
                self.logger.info(f"-- community: {community_obj}")
                community_data = {
                    "name": community_obj["name"],
                    "communities": community_obj["communities"],
                }
                self.community_set.append(community_data)

    def translate_aspath_set(self) -> None:
        if "as-path-sets" not in self.ttp_parsed_data.keys():
            self.logger.info("no as-path-set found")
            return
        self.logger.info("- as-path-set")
        for aspath_obj in self.ttp_parsed_data["as-path-sets"]:
            self.logger.info(f"-- as-path-set: {aspath_obj}")

            aspath_data = {
                "group-name": aspath_obj["name"],
                "as-path": [],
            }

            # 空のas-path-set
            if "conditions" not in aspath_obj.keys():
                aspath_data["as-path"].append(
                    {
                        "name": aspath_obj["name"],
                        "pattern": "*",
                    }
                )
                self.aspath_set.append(aspath_data)
                continue

            for i, aspath_condition in enumerate(aspath_obj["conditions"]):
                if "pattern" in aspath_condition.keys():
                    aspath_data["as-path"].append(
                        {
                            "name": f"{aspath_obj['name']}_{i+1}",
                            "pattern": self.translate_aspath_pattern(aspath_condition["pattern"]),
                        }
                    )

                if "length" in aspath_condition.keys():
                    if aspath_condition["condition"] == "le":
                        aspath_data["as-path"].append({"length": {"max": aspath_condition["length"]}})
                    elif aspath_condition["condition"] == "ge":
                        aspath_data["as-path"].append(
                            {"name": f"{aspath_obj['name']}_{i+1}", "length": {"min": aspath_condition["length"]}}
                        )
            self.aspath_set.append(aspath_data)

    def translate_aspath_pattern(self, pattern: str) -> str:
        """
        IOS-XRからJunosの正規表現に変換する
        """
        result = pattern.replace("_", " ")
        return result

    def translate_prefix_set(self) -> None:
        self.logger.info("- prefix-set")
        if "prefix-sets" in self.ttp_parsed_data.keys():
            for item in self.ttp_parsed_data["prefix-sets"]:
                self.logger.info(f"-- prefix-set: {item}")
                prefixes = []

                if "prefixes" not in item:
                    self.logger.info(f"prefixes not found in {item}")
                    continue

                for prefix_obj in item["prefixes"]:

                    prefix_length = prefix_obj["prefix"].split("/")[-1]

                    length = {}
                    match_type = ""

                    if "condition" in prefix_obj.keys():
                        conditions = prefix_obj["condition"].split()
                        if len(conditions) == 2:
                            if "ge" in conditions:
                                match_type = "prefix-length-range"
                                length["min"] = conditions[1]
                                length["max"] = "32"
                            elif "le" in conditions:
                                match_type = "upto"
                                length["max"] = conditions[1]
                        elif len(conditions) == 4:
                            match_type = "prefix-length-range"
                            length["min"] = conditions[1]
                            length["max"] = conditions[3]
                    else:
                        match_type = "exact"
                        length = {"min": prefix_length, "max": prefix_length}

                    prefixes.append(
                        {
                            "prefix": prefix_obj["prefix"],
                            "match-type": match_type,
                            "length": length,
                        }
                    )

                self.prefix_set.append(
                    {
                        "name": item["name"],
                        "prefixes": prefixes,
                    }
                )

    def translate_rule(self, rule: dict) -> dict:
        self.logger.info(f"translate rule: {rule}")
        action = {}
        if rule["action"] == "set":
            attr = rule["attr"]
            if attr == "med":
                action = {"metric": rule["value"]}
            elif attr == "local-preference":
                action = {"local-preference": rule["value"]}
            elif attr == "community":
                community_name = rule["value"].split()[0]
                if "additive" in rule["value"]:
                    action = {"community": {"action": "add", "name": community_name}}
                else:
                    action = {"community": {"action": "set", "name": community_name}}
            elif attr == "next-hop":
                action = {"next-hop": rule["value"]}
            elif attr == "origin":
                action = {"origin": rule["value"]}

        elif rule["action"] == "delete":
            attr = rule["attr"]
            if attr == "community":
                # TODO: not in ~ への対応
                community_name = rule["value"].split()[-1]
                action = {"community": {"action": "delete", "name": community_name}}

        elif rule["action"] == "prepend":
            attr = rule["attr"]
            asn, *repeat = rule["value"].split()
            if repeat:
                repeat = int(repeat[0])
            else:
                repeat = 1
            action = {"as-path-prepend": [{"asn": asn, "repeat": repeat}]}

        elif rule["action"] == "apply":
            action = {"apply": rule["value"]}

        elif rule["action"] in ["pass", "drop", "done"]:
            target_maps = {"pass": "next term", "drop": "reject", "done": "accept"}
            action = {"target": target_maps[rule["action"]]}

        return action

    def convert_prefix_list_into_route_filter(self, prefix_list_name: str) -> list:
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
                    self.logger.info(
                        f"- convert prefix-list:{prefix_list_name} into route-filter {prefix_item['prefix']}"
                    )
                    route_filter_list.append({"route-filter": prefix_item})
                return route_filter_list
        self.logger.info(f"{prefix_list_name} is not match in prefix-list_data")
        return route_filter_list

    def check_prefix_list_only_exact_matchtype(self, prefix_list_name: str) -> bool:
        """Check prefix-list contain match-type only exact
        Args:
            prefix_list_name (str): prefix_list name of Conversion target
        Returns:
            Bool: True if prefix-list contain only exact match-type, False if not
        """

        for item in self.prefix_set:
            if item["name"] == prefix_list_name:
                for prefix_item in item["prefixes"]:
                    if prefix_item["match-type"] == "exact":
                        continue
                    else:
                        self.logger.info(f"{prefix_list_name} contain not exact match-type")
                        return False
                return True

    def translate_match(self, match: str) -> list | None:
        condition = []
        # destination in prefix-list
        if match.split()[0] == "destination":
            ## if prefix-listの中身がexactのみの場合、prefix-listをroute-policyへ変換せずにポリシーモデルに入れる
            if self.check_prefix_list_only_exact_matchtype(match.split()[-1]):
                condition = [{"prefix-list": match.split()[-1]}]
            else:
                condition = self.convert_prefix_list_into_route_filter(match.split()[-1])
            return condition

        # as-path in as-path-set
        if match.split()[0] == "as-path":
            if "length" in match:
                name = match.replace(" ", "_")
                op = "max" if "le" in match.split() else "min"
                self.aspath_set.append(
                    {
                        "group-name": f"_generated_{name}",
                        "as-path": {
                            "name": f"_generated_{name}",
                            "length": {op: match.split()[-1]},
                        },
                    }
                )
                condition.append({"as-path-group": f"_generated_{name}"})
                return condition

            as_path_group_item = {"as-path-group": match.split()[-1]}
            condition.append(as_path_group_item)
            return condition

        # community match-any community-set
        if match.split()[0] == "community":
            _, op, community = match.split()
            if op == "matches-any":
                condition.append({"community": [community]})
                return condition
            if op == "matches-every":
                self.logger.info("matches-every is not implemented")
        return None

    def generate_conditional_policies(self, basename: str, if_condition: dict) -> list[PolicyModel]:
        if if_condition["op"] in ["and", "state"]:
            statement = Statement(name="10")
            matches = if_condition["matches"]
            for match in matches:
                conditions = self.translate_match(match)
                if conditions:
                    statement.conditions.extend(conditions)
                else:
                    self.logger.info(f"{match} could not be translated.")
                    statement.conditions.extend([{"_message": {"TRANSLATION_FAILED": match}}])
            statement.actions.append({"target": "accept"})
            if if_condition["op"] == "and":
                community_condition = []
                for match in if_condition["matches"]:
                    if "community" in match:
                        community_condition.append(self.translate_match(match)[0])
                        self.logger.info(self.translate_match(match)[0])
                if len(community_condition) > 1:
                    new_community_set_name = self.create_community_set_in_and_condition(community_condition)
                    statement.conditions = [item for item in statement.conditions if "community" not in item]
                    statement.conditions.append({"community": [new_community_set_name]})
                    self.logger.info(f"update condition community: {new_community_set_name}")
            if_policy = PolicyModel(
                name=f"{PolicyPrefix.IF_CONDITION.value}{basename}",
                statements=[statement],
            )
            if_policy.set_default_reject()

        elif if_condition["op"] == "or":
            matches = if_condition["matches"]
            statement_list = []
            for i, match in enumerate(matches):
                statement = Statement(name=i)
                conditions = self.translate_match(match)
                if conditions:
                    statement.conditions.extend(conditions)
                else:
                    self.logger.info(f"{match} could not be translated.")
                    statement.conditions.extend([{"_message": {"TRANSLATION_FAILED": match}}])
                statement.actions.append({"target": "accept"})
                statement_list.append(statement)
            if_policy = PolicyModel(
                name=f"{PolicyPrefix.IF_CONDITION.value}{basename}",
                statements=statement_list,
            )
            if_policy.set_default_reject()

        not_match_statement = Statement(name="10")
        not_match_statement.conditions.append({"policy": f"{PolicyPrefix.IF_CONDITION.value}{basename}"})
        not_match_statement.actions.append({"target": "reject"})
        not_if_policy = PolicyModel(
            name=f"{PolicyPrefix.NOT_IF_CONDITION.value}{basename}",
            statements=[not_match_statement],
            default={"actions": [{}]},
        )
        not_if_policy.set_default_accept()

        return [if_policy, not_if_policy]

    def create_community_set_in_and_condition(self, communities: list):
        new_community_set_name = []
        new_community_set_communities = []
        for item in communities:
            for i in self.community_set:
                if "community" in item:
                    if i["name"] == item["community"][0]:
                        new_community_set_name.append(item["community"][0])
                        new_community_set_communities.extend(i["communities"])
                # if i["name"] == item["community"][0]:
                #   new_community_set_name.append(item["community"][0])
                #   new_community_set_communities.extend(i["communities"])
        self.community_set.append(
            {
                "name": "-and-".join(new_community_set_name),
                "communities": new_community_set_communities,
            }
        )
        self.logger.info(f"create new_community-set: {self.community_set[-1]['name']}")
        return self.community_set[-1]["name"]

    def translate_policies(self):
        for policy in self.ttp_parsed_data["policies"]:
            self.translate_policy(ttp_policy=policy)

        # neighborのコンフィグ配下に記述される設定への対応
        for neighbor in self.bgp_neighbors:
            for af in neighbor.address_families:
                # next-hop-self
                if af.next_hop_self:
                    if af.route_policy_out:
                        if "ibgp-export" in str(af.route_policy_out):
                            self.logger.info("auto generate af data:" + str(af))
                            self.logger.info("execute auto_gen_ibgp_export:" + str(self.auto_gen_ibgp_export()))
                        export_policy = self.get_policy_by_name(af.route_policy_out)

                        # すでにnext-hop-selfが反映されたポリシーには追加しない
                        if export_policy and not export_policy.has_next_hop_self_in_head():
                            export_policy.insert_next_hop_self_in_head()
                    else:
                        self.logger.info(f"no export policy found: {af}")

    def translate_policy(
        self, ttp_policy: dict, parent_conditional_policy: PolicyModel = None
    ) -> Union[list[Statement], None]:

        self.logger.info(f"translating policy: {ttp_policy}")
        policy = PolicyModel(default={"actions": []})
        policy.name = ttp_policy["name"]

        count = 0
        past_conditional_policies: list[PolicyModel] = []

        statement = Statement.generate_empty_statement()

        for rule in ttp_policy["rules"]:
            self.logger.info(f"start: {rule}")
            count += 10
            policy_basename = f"{policy.name}-{count}"

            if "if" not in rule.keys():
                if parent_conditional_policy:
                    conditions = [{"policy": parent_conditional_policy.name}]
                else:
                    conditions = []
                action = self.translate_rule(rule)
                past_conditional_policies = []

                if not statement.is_empty():
                    statement.actions.append(action)
                else:
                    statement = Statement(name=policy_basename, conditions=conditions, actions=[action])

            elif rule["if"] == "if":
                self.logger.info(f"'if' rule found in {policy.name}: {rule}")

                past_conditional_policies = []

                # ---------- from句の組み立て開始(if) ----------
                # if文の条件判定を行うためのポリシーを作成
                if_policy, not_if_policy = self.generate_conditional_policies(
                    basename=policy_basename, if_condition=rule["condition"]
                )

                # ネストされたifの場合は上の階層の条件にマッチしていることが前提
                # それにマッチしない経路はrejectする
                if parent_conditional_policy:
                    if_policy.insert_policy_as_reject_statement(
                        policy=self.get_opposite_policy(parent_conditional_policy), statement_name="parent-policy"
                    )

                if_policy.set_default_reject()
                self.policies.extend([if_policy, not_if_policy])
                past_conditional_policies.append(if_policy)

                base_conditions = [{"policy": if_policy.name}]
                # ---------- from句の組み立て終わり(if) ----------

                # ifが現れた場合は一旦そこでactionsは区切る
                if not statement.is_empty():
                    policy.statements.append(statement)

                statement = Statement(name=f"{policy_basename}", conditions=base_conditions, actions=[])

                # ---------- then句の組み立て開始(if) ----------
                self.logger.info(rule)
                child_count = 10

                for inner_rule in rule["rules"]:
                    if "if" in inner_rule.keys():

                        self.logger.info(f"translate nested if/elseif: {inner_rule}")

                        if not statement.is_empty():
                            policy.statements.append(statement)

                        statement = Statement(name=f"{policy_basename}", conditions=base_conditions, actions=[])

                        _dummy_ttp_policy = {
                            "name": f"{policy_basename}-{child_count}",
                            "rules": [inner_rule],
                        }
                        self.logger.info(f"dummy policy: {_dummy_ttp_policy}")
                        child_statements = self.translate_policy(
                            ttp_policy=_dummy_ttp_policy,
                            parent_conditional_policy=if_policy,
                        )
                        self.logger.info(f"inner rule: {child_statements}")
                        policy.statements.extend(child_statements)
                    else:
                        inner_action = self.translate_rule(inner_rule)
                        if inner_action:
                            statement.actions.append(inner_action)
                        else:
                            self.logger.info(f"{inner_rule} could not be translated.")
                    child_count += 10

                # ---------- then句の組み立て終わり(if) ----------

                if not statement.is_empty():
                    policy.statements.append(statement)

                statement = Statement.generate_empty_statement()

            elif rule["if"] == "elseif":
                self.logger.info(f"'elseif' rule found in {policy.name}: {rule}")

                # ---------- from句の組み立て開始(elseif) ----------
                # if文の条件判定を行うためのポリシーを作成
                if_policy, not_if_policy = self.generate_conditional_policies(
                    basename=policy_basename, if_condition=rule["condition"]
                )

                # elseifなので事前のif句の条件はすべて否定する
                for i, past_policy in enumerate(past_conditional_policies):
                    if_policy.insert_policy_as_reject_statement(policy=past_policy, statement_name=f"past-policy-{i}")

                # ネストされたelseifの場合は上の階層の条件にマッチしていることが前提
                # マッチしない場合はreject
                if parent_conditional_policy:
                    if_policy.insert_policy_as_reject_statement(
                        policy=self.get_opposite_policy(parent_conditional_policy), statement_name="parent-policy"
                    )

                if_policy.set_default_reject()
                self.policies.extend([if_policy, not_if_policy])
                base_conditions = [{"policy": if_policy.name}]
                past_conditional_policies.append(if_policy)

                self.logger.info(rule)
                child_count = 10

                # ---------- from句の組み立て終わり(elseif) ----------

                # elseifが現れた場合はそこでactionsを区切る
                if not statement.is_empty():
                    policy.statements.append(statement)

                statement = Statement(name=f"{policy_basename}", conditions=base_conditions, actions=[])

                # ---------- then句の組み立て開始(elseif) ----------

                for inner_rule in rule["rules"]:
                    if "if" in inner_rule.keys():
                        self.logger.info(f"translate nested if/elseif: {inner_rule}")

                        if not statement.is_empty():
                            policy.statements.append(statement)

                        statement = Statement(name=f"{policy_basename}", conditions=base_conditions, actions=[])

                        _dummy_ttp_policy = {
                            "name": f"{policy_basename}-{child_count}",
                            "rules": [inner_rule],
                        }
                        self.logger.info(f"dummy policy: {_dummy_ttp_policy}")
                        child_statements = self.translate_policy(
                            ttp_policy=_dummy_ttp_policy,
                            parent_conditional_policy=if_policy,
                        )
                        self.logger.info(f"inner rule: {child_statements}")
                        policy.statements.extend(child_statements)
                    else:
                        inner_action = self.translate_rule(inner_rule)
                        if inner_action:
                            statement.actions.append(inner_action)
                        else:
                            self.logger.info(f"{inner_rule} could not be translated.")

                    child_count += 10

                if not statement.is_empty():
                    policy.statements.append(statement)

                statement = Statement.generate_empty_statement()

            elif rule["if"] == "else":
                self.logger.info(f"'else' rule found in {policy.name}: {rule}")

                # ---------- from句の組み立て開始(else) ----------
                else_policy = PolicyModel(
                    name=f"{PolicyPrefix.IF_CONDITION.value}{policy_basename}-else",
                )
                else_policy.set_default_accept()
                base_conditions = [{"policy": else_policy.name}]

                # elseなので前にあるif/elseif節の条件に合致するものはrejectする
                for i, past_policy in enumerate(past_conditional_policies):
                    else_policy.insert_policy_as_reject_statement(
                        policy=past_policy, statement_name=f"past-policy-{i}"
                    )

                self.policies.append(else_policy)

                # ---------- from句の組み立て終わり(else) ----------

                if not statement.is_empty():
                    policy.statements.append(statement)

                statement = Statement(name=f"{policy_basename}", conditions=base_conditions, actions=[])

                # ---------- then句の組み立て開始(else) ----------

                child_count = 10
                for inner_rule in rule["rules"]:
                    inner_action = self.translate_rule(inner_rule)
                    if inner_action:
                        statement.actions.append(inner_action)
                    else:
                        self.logger.info(f"{inner_rule} could not be translated.")
                    child_count += 10

                if statement.actions:
                    policy.statements.append(statement)

                statement = Statement.generate_empty_statement()

            else:
                self.logger.info(f"rule not translated: {rule}")

        if not statement.is_empty():
            policy.statements.append(statement)
            statement = Statement(name="", conditions=[], actions=[])

        if parent_conditional_policy:
            return policy.statements

        self.logger.info(f"appending policy: {policy}")
        self.policies.append(policy)
        return None


if __name__ == "__main__":

    def main(ttp_file, output_file):
        with open(ttp_file, "r", encoding="utf-8") as f:
            ttp_parsed_config = json.load(f)

        xrtranslator = XRTranslator(ttp_parsed_config)
        xrtranslator.translate_policies()
        policy_model_output = {
            "node": xrtranslator.node,
            "prefix-set": xrtranslator.prefix_set,
            "as-path-set": xrtranslator.aspath_set,
            "community-set": xrtranslator.community_set,
            "policies": xrtranslator.policies,
        }

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(policy_model_output, fp=f, indent=2, cls=PMEncoder)

    main(argv[1], argv[2])
