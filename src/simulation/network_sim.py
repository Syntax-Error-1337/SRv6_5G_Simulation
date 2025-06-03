import networkx as nx
import numpy as np
import yaml
import json
import time
from typing import List, Dict, Tuple

class NetworkSimulator:
    def __init__(self, config_path: str):
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        self.G = nx.Graph()
        self.setup_topology()
        self.segment_lists = {}  # SRv6 segment lists: {path_id: [node_ids]}

    def setup_topology(self):
        """Create a 5G+ network topology (Access, Aggregation, Core)."""
        num_nodes = self.config['topology']['num_nodes']
        edge_prob = self.config['topology']['edge_probability']
        self.G = nx.erdos_renyi_graph(num_nodes, edge_prob)

        # Assign attributes to edges (delay, bandwidth, cost)
        for u, v in self.G.edges():
            self.G.edges[u, v]['delay'] = np.random.uniform(1, 10)  # ms
            self.G.edges[u, v]['bandwidth'] = np.random.uniform(100, 1000)  # Mbps
            self.G.edges[u, v]['cost'] = np.random.uniform(1, 100)
            self.G.edges[u, v]['congestion'] = np.random.uniform(0, 0.5)  # 0-50% congestion

        # Save topology
        with open('data/topology.json', 'w') as f:
            json.dump(nx.node_link_data(self.G), f)

    def define_segment_list(self, src: int, dst: int, path_id: str) -> List[int]:
        """Define an SRv6 segment list from source to destination."""
        try:
            path = nx.shortest_path(self.G, src, dst, weight='cost')
            self.segment_lists[path_id] = path
            return path
        except nx.NetworkXNoPath:
            return []

    def simulate_packet_forwarding(self, segment_list: List[int], traffic_type: str) -> Dict:
        """Simulate packet forwarding with SRv6 segment list, considering congestion and QoS violations."""
        metrics = {'delay': 0.0, 'jitter': 0.0, 'packet_loss': 0.0, 'latency_variance': 0.0, 'qos_violations': 0}
        delays = []
        
        # Define QoS thresholds based on traffic type (simplified)
        qos_thresholds = {
            'URLLC': {'max_delay': 5, 'min_bandwidth': 200},
            'game_streaming': {'max_delay': 10, 'min_bandwidth': 300},
            'autonomous_vehicles': {'max_delay': 3, 'min_bandwidth': 200},
            'healthcare_monitoring': {'max_delay': 8, 'min_bandwidth': 150},
            'default': {'max_delay': 50, 'min_bandwidth': 100}
        }
        threshold = qos_thresholds.get(traffic_type, qos_thresholds['default'])
        
        for i in range(len(segment_list) - 1):
            u, v = segment_list[i], segment_list[i + 1]
            if (u, v) in self.G.edges:
                congestion = self.G.edges[u, v]['congestion']
                time_factor = np.sin(time.time() / 100)
                bandwidth = self.G.edges[u, v]['bandwidth']
                bandwidth_factor = bandwidth / 1000
                base_delay = self.G.edges[u, v]['delay']
                adjusted_delay = base_delay * (1 + congestion + time_factor) * (1 / bandwidth_factor) * np.random.uniform(0.7, 1.3)
                metrics['delay'] += adjusted_delay
                delays.append(adjusted_delay)
                metrics['jitter'] += np.random.uniform(0.1, 0.5) * (1 + congestion + time_factor)
                
                # Check QoS violations
                if adjusted_delay > threshold['max_delay'] or bandwidth < threshold['min_bandwidth']:
                    metrics['qos_violations'] += 1
                    # Increase packet loss due to QoS violation
                    metrics['packet_loss'] += np.random.uniform(0.05, 0.1) * (1 + congestion + time_factor)
                else:
                    metrics['packet_loss'] += np.random.uniform(0, 0.05) * (1 + congestion + time_factor)
            else:
                metrics['packet_loss'] = 1.0
                metrics['qos_violations'] += 1
                break
        
        if delays:
            metrics['latency_variance'] = np.var(delays)
        return metrics

    def simulate_link_failure(self, failure_rate: float = 0.03):
        """Simulate random link failures."""
        for u, v in list(self.G.edges):
            if np.random.random() < failure_rate:
                self.G.remove_edge(u, v)

    def simulate_node_failure(self, failure_rate: float = 0.01):
        """Simulate random node failures."""
        for node in list(self.G.nodes):
            if np.random.random() < failure_rate and node not in [0, 19]:
                self.G.remove_node(node)

    def simulate_congestion(self, congestion_increase: float = 0.15):
        """Simulate congestion by increasing congestion on random edges."""
        for u, v in self.G.edges:
            if np.random.random() < 0.3:
                self.G.edges[u, v]['congestion'] = min(1.0, self.G.edges[u, v]['congestion'] + congestion_increase)

    def simulate_bandwidth_fluctuation(self, fluctuation_rate: float = 0.2):
        """Simulate bandwidth fluctuations on random edges."""
        for u, v in self.G.edges:
            if np.random.random() < 0.4:
                self.G.edges[u, v]['bandwidth'] *= np.random.uniform(0.8, 1.2)
                self.G.edges[u, v]['bandwidth'] = max(50, min(1000, self.G.edges[u, v]['bandwidth']))
