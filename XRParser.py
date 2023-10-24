import json, sys
from logging import Logger

class XRParser():
    
    def __init__(self, ttp_parsed_data: dict):
        self.node = ""
        self.community_set = []
        self.aspath_set = []
        self.prefix_set = []
        self.policies = {}
        self.ttp_parsed_data = ttp_parsed_data
        self.logger = Logger()

    def translate_node(self) -> None:
        # node
        for item in self.ttp_parsed_data["interfaces"]:
            if item["name"] == "Loopback0":
                self.node["node"] = item["ipv4"]["address"]
        print("- prefix-set")

    def parse_community_set(self, ttp_parsed_data: dict) -> list:
        
        pass
    
    def parse_aspath_set(self):
        pass
    
    def parse_prefix_set(self):
        pass
    

    def translate_rule(self, rule: dict) -> dict:
    
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
                action = { "community": { "action": "remove", "name": community_name } }
            
        elif rule['action'] == 'apply':
            action = { 'apply': rule['value'] }
        
        elif rule['action'] in ['pass', 'drop', 'done']:
            target_maps = { 
                'pass': 'next-term', 'drop': 'reject', 'done': 'accept'
            }
            action = { 'target': target_maps[rule['action']]  }
        
        return action

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
                    print(f"- convert prefix-list:{prefix_list_name} into route-filter {prefix_item['prefix']}")
                    route_filter_list.append({"route-filter": prefix_item})
                return route_filter_list
        print(f"{prefix_list_name} is not match in prefix-list_data")
        return route_filter_list 


    def translate_match(self, match: str) -> list:
        print(match)
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
                raise NotImplementedError("matches-every is not implemented")

    def translate_policies(self):
        for policy in self.ttp_parsed_data["policies"]:
            self.translate_policy(policy=policy)

    def translate_policy(self, policy: dict, parent_name: str=None):
        policy_template = { "statements": [], "default": { "actions": [] } }
        count = 0

        if parent_name:
            name = f"{parent_name}-1"
        else:
            name = policy["name"]

        self.policies[name] = policy_template

        for rule in policy["rules"]:
            statement_template = { "name": str(count), "conditions": [], "actions": [] }

            if "if" in rule.keys():
                count += 10
                condition_op = rule["condition"]["op"]
                has_community_matches = len( 
                    [ match for match in rule["condition"]["matches"] 
                     if match.split()[0] =="community" ]
                ) > 0

                if condition_op == "and":

                    if has_community_matches:
                        members = [rule["condition"]["matches"].split()[-1]]
                        self.community_set.append({
                            # aaa-and-bbb-and-ccc
                            "name": "-and-".join(members),
                            "community": " ".join(members)
                        })
                        statement_template["conditions"].append({
                            "community": "-and-".join(members)
                        })
                    else:
                        for match in rule["condition"]["matches"]:
                            condition = self.translate_match(match)
                            statement_template["conditions"].extend(condition)

                elif condition_op == "or":
                    # TODO: orのときの実装
                    pass

                elif condition_op == "state":
                    match = rule["condition"]["matches"][0]
                    condition = self.translate_match(match)
                    statement_template["conditions"].extend(condition)

                else:
                    raise NotImplementedError()

                if parent_name:
                    statement_template["conditions"].append({
                        "policy": parent_name
                    })

                self.translate_policy(policy=rule, parent_name=name)
                policy_template = { "statements": [], "default": { "actions": [] } }
                policy_template['statements'].append(statement_template)
                self.policies[name] = policy_template

            else:
                action = self.translate_rule(rule)
                statement_template['name'] = str(count)
                statement_template['actions'].append(action)
                policy_template['statements'].append(statement_template)

        self.policies[name] = policy_template

if __name__ == "__main__":
    ttp_file = sys.argv[1]
    with open(ttp_file, "r") as f:
        ttp_parsed_policy = f.read()

    xrparser = XRParser()
    xrparser.translate_policies(ttp_parsed_policy)
    print(json.dumps(xrparser.policies, indent=2))



# def parse_rules(policy_data: dict):
#     obj = dict
#     if "if" in policy_data["rules"].keys:
#         # create_policy(rules.condition)  -> policy 
#         if rules.confition["op"] == "or":
#             # add_policy_term(confitions) -> policy 
#         return parse_rules(rules.rules), policy 
#     else:
#         pass