from .errors import Problem
from .plan_versions import version_plan
from .releases import get_release
from .version_workbench import get_version_release


def _load_snapshot(connection, span_id, plan_version, revision):
    """旧签件按原摘要读回：版本 1 兼容首版表，其余读版本签发表。"""
    if plan_version == 1:
        return get_release(connection, span_id, revision)['snapshot']
    return get_version_release(connection, span_id, plan_version, revision)['snapshot']


def _all_versions(connection, span_id):
    rows = connection.execute('SELECT plan_version FROM plan_versions WHERE span_id = ? ORDER BY plan_version',
                              (span_id,)).fetchall()
    return [1] + [row['plan_version'] for row in rows]


def _edges_between(connection, span_id, low, high):
    """每个换版步按确认关系连边：旧版点 (version-1:from) 连到新版点 (version:to)。

    拆分/合并形成多对多连边；新增只有新版点、退役只有旧版点，不产生连边，自然成单侧组。
    """
    rows = connection.execute(
        'SELECT plan_version, relation, from_site, to_site FROM plan_relations '
        'WHERE span_id = ? AND ? < plan_version AND plan_version <= ? ORDER BY plan_version, rowid',
        (span_id, low, high)).fetchall()
    edges = []
    for row in rows:
        version = row['plan_version']
        left_node = f'{version - 1}:{row["from_site"]}' if row['from_site'] is not None else None
        right_node = f'{version}:{row["to_site"]}' if row['to_site'] is not None else None
        edges.append((version, row['relation'], left_node, right_node))
    return edges


def _union_groups(connection, span_id, low, high):
    parent = {}

    def find(node):
        parent.setdefault(node, node)
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(a, b):
        root_a, root_b = find(a), find(b)
        if root_a != root_b:
            parent[root_b] = root_a

    # 节点覆盖区间内每个版本的全部点位
    present = {}
    for version in _all_versions(connection, span_id):
        if low <= version <= high:
            present[version] = {site['site_id'] for site in version_plan(connection, span_id, version)['sites']}
    for version, sites in present.items():
        for site_id in sites:
            find(f'{version}:{site_id}')
    edge_list = []
    for version, relation, left_node, right_node in _edges_between(connection, span_id, low, high):
        if left_node is not None and right_node is not None:
            if left_node not in parent or right_node not in parent:
                raise Problem('换版关系引用了区间外的点位', 409)
            union(left_node, right_node)
            edge_list.append((left_node, right_node, version, relation))
    # 连边在全部并查操作完成后再按最终根归集，避免并根过程中的旧根失效
    root_edges = {}
    for left_node, right_node, version, relation in edge_list:
        root_edges.setdefault(find(right_node), set()).add((version, relation))
    groups = {}
    for node in parent:
        groups.setdefault(find(node), []).append(node)
    return groups, root_edges, present


def _site_loss(snapshot, site_id):
    for site in snapshot['sites']:
        if site['site_id'] == site_id:
            return site
    return None


def reconcile(connection, span_id, left_version, left_revision, right_version, right_revision):
    if left_version > right_version:
        raise Problem('对账方向必须从较早版本指向较晚版本')
    left_snapshot = _load_snapshot(connection, span_id, left_version, left_revision)
    right_snapshot = _load_snapshot(connection, span_id, right_version, right_revision)
    if left_snapshot['ruleset'] != right_snapshot['ruleset']:
        raise Problem('两个签发件的核算口径不同', 409)
    groups, root_edges, present = _union_groups(connection, span_id, left_version, right_version)
    left_points = present[left_version]
    right_points = present[right_version]
    grouped_left, grouped_right = set(), set()
    paired, single_side = [], []
    for root, nodes in groups.items():
        by_version = {}
        for node in nodes:
            version_text, site_id = node.split(':', 1)
            by_version.setdefault(int(version_text), []).append(site_id)
        left_ids = by_version.get(left_version, [])
        right_ids = by_version.get(right_version, [])
        grouped_left.update(left_ids)
        grouped_right.update(right_ids)
        chain = sorted(by_version)
        edge_steps = root_edges.get(root, set())
        relation_kinds = sorted({relation for _, relation in edge_steps})
        # 一次拆/并为一项工程变更：同一版本同一关系的多条连边只计一次
        change_count = len(edge_steps)
        item = {
            'left_sites': _entries(left_snapshot, left_ids),
            'right_sites': _entries(right_snapshot, right_ids),
            'versions': chain,
            'relations': relation_kinds,
            'change_count': change_count,
            'left_loss_total_x2_mdb': _sum_loss(left_snapshot, left_ids),
            'right_loss_total_x2_mdb': _sum_loss(right_snapshot, right_ids),
        }
        item['delta_x2_mdb'] = _delta(item['right_loss_total_x2_mdb'], item['left_loss_total_x2_mdb'])
        if left_ids and right_ids:
            paired.append(item)
        else:
            item['side'] = 'left' if left_ids else 'right'
            single_side.append(item)
    if grouped_left != left_points or grouped_right != right_points:
        raise Problem('换版关系证据不完整，无法覆盖两版全部点位', 409)
    paired.sort(key=lambda group: [site['at_mm'] for site in group['left_sites'] + group['right_sites']])
    single_side.sort(key=lambda group: [site['at_mm'] for site in group['left_sites'] + group['right_sites']])
    return {
        'span_id': span_id,
        'left': {'plan_version': left_version, 'revision': left_revision},
        'right': {'plan_version': right_version, 'revision': right_revision},
        'groups': paired,
        'single_side_groups': single_side,
        'left_budget': left_snapshot['budget'],
        'right_budget': right_snapshot['budget'],
    }


def _entries(snapshot, site_ids):
    sites = []
    for site_id in site_ids:
        site = _site_loss(snapshot, site_id)
        if site is not None:
            sites.append(site)
    return sorted(sites, key=lambda site: site['at_mm'])


def _sum_loss(snapshot, site_ids):
    values = [_site_loss(snapshot, site_id)['mean_x2_mdb'] for site_id in site_ids]
    if any(value is None for value in values):
        return None
    return sum(values)


def _delta(right_total, left_total):
    if right_total is None or left_total is None:
        return None
    return right_total - left_total
