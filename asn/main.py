#!/usr/bin/env python3
from frrnet.topo import FrrTopo
from frrnet import frrnet_main

class FatTreeSharedASTopo(FrrTopo):
    def build(self, k=4):
        self.port_cnt = {}
        def alloc_intf(sw_name):
            self.port_cnt[sw_name] = self.port_cnt.get(sw_name, 1)
            name = f"Ethernet1-{self.port_cnt[sw_name]}"
            self.port_cnt[sw_name] += 1
            return name

        num_pods = k
        num_core = (k // 2) ** 2
        num_agg = k * (k // 2)
        num_edge = k * (k // 2)

        # 1. Switches
        core_sw = [self.addSwitch(f'c{i+1}', daemons=["bgpd"]) for i in range(num_core)]
        agg_sw  = [self.addSwitch(f'a{i+1}', daemons=["bgpd"]) for i in range(num_agg)]
        edge_sw = [self.addSwitch(f'e{i+1}', daemons=["bgpd"]) for i in range(num_edge)]

        # 2. Core-Agg links
        for i in range(num_agg):
            for j in range(k // 2):
                core_idx = j + (i % (k // 2)) * (k // 2)
                self.addLink(agg_sw[i], core_sw[core_idx],
                             intf1=alloc_intf(f'a{i+1}'),
                             intf2=alloc_intf(f'c{core_idx+1}'))

        # 3. Agg-Edge links (Within Pod)
        for p in range(num_pods):
            for a_idx in range(k // 2):
                c_agg = agg_sw[p * (k//2) + a_idx]
                for e_idx in range(k // 2):
                    c_edge = edge_sw[p * (k//2) + e_idx]
                    self.addLink(c_agg, c_edge,
                                 intf1=alloc_intf(f'a{p*(k//2)+a_idx+1}'),
                                 intf2=alloc_intf(f'e{p*(k//2)+e_idx+1}'))

        # 4. Edge-Host links
        host_id = 1
        for i in range(num_edge):
            for _ in range(k // 2):
                h_ip = f"172.16.{host_id}.2/24"
                h_gw = f"172.16.{host_id}.1"
                host = self.addHost(f'h{host_id}', ip=h_ip, defaultRoute=f"via {h_gw}")
                self.addLink(edge_sw[i], host, intf1=alloc_intf(f'e{i+1}'))
                host_id += 1

if __name__ == "__main__":
    frrnet_main(FatTreeSharedASTopo)