def drawflow_to_pseudo(json_data):
    nodes = json_data.get('drawflow', {}).get('Home', {}).get('data', {})
    start_id = next((k for k, v in nodes.items() if v['name'] == 'start'), None)
    if not start_id: return 'START\nSTOP'

    code = []
    visited = set()
    
    # Calculate in-degree to find merge points
    in_degree = {str(k): 0 for k in nodes}
    for k, v in nodes.items():
        for out_name, out_data in v.get('outputs', {}).items():
            for conn in out_data.get('connections', []):
                in_degree[str(conn['node'])] += 1

    def get_child(node, port):
        conns = node.get('outputs', {}).get(port, {}).get('connections', [])
        return str(conns[0]['node']) if conns else None

    def traverse(node_id, stop_at_merge=False):
        if not node_id: return None
        if node_id in visited: return None
        if stop_at_merge and in_degree[node_id] > 1:
            return node_id # Return the merge node to be processed later
            
        visited.add(node_id)
        node = nodes[node_id]
        name = node['name']
        data = node['data']

        merge_to_process = None

        if name == 'start':
            code.append('START')
            merge_to_process = traverse(get_child(node, 'output_1'), stop_at_merge)
        elif name == 'end':
            code.append('STOP')
        elif name == 'process':
            code.append(data.get('process', ''))
            merge_to_process = traverse(get_child(node, 'output_1'), stop_at_merge)
        elif name == 'input':
            code.append(f"READ {data.get('input', '')}")
            merge_to_process = traverse(get_child(node, 'output_1'), stop_at_merge)
        elif name == 'output':
            code.append(f"PRINT {data.get('output', '')}")
            merge_to_process = traverse(get_child(node, 'output_1'), stop_at_merge)
        elif name == 'decision':
            code.append(f"IF {data.get('condition', '')} THEN")
            true_node = get_child(node, 'output_1')
            false_node = get_child(node, 'output_2')
            
            # Traverse true branch until merge
            m1 = traverse(true_node, stop_at_merge=True)
            code.append('ELSE')
            # Traverse false branch until merge
            m2 = traverse(false_node, stop_at_merge=True)
            code.append('ENDIF')
            
            # Continue from merge node
            if m1: merge_to_process = m1
            elif m2: merge_to_process = m2
            
        elif name == 'while':
            code.append(f"WHILE {data.get('condition', '')}")
            body_node = get_child(node, 'output_1')
            exit_node = get_child(node, 'output_2')
            
            # Traverse body until merge
            m_body = traverse(body_node, stop_at_merge=True)
            code.append('ENDWHILE')
            
            # Loop body continues to the beginning or exit node
            merge_to_process = exit_node
            
        if merge_to_process and merge_to_process not in visited:
            # We hit a merge point and finished the branches, now continue from merge point
            traverse(merge_to_process, stop_at_merge)
            
        return merge_to_process

    traverse(start_id, stop_at_merge=False)
    
    # If anything was left unvisited (disconnected graphs), ignore or append
    return '\n'.join(code)
