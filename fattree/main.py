#!/usr/bin/env python3
from frrnet.topo import FrrTopo
from frrnet import frrnet_main

class FatTreeTopo(FrrTopo):
    """
    基于 Mininet 与 Frrnet 的 k=4 Fat-Tree 拓扑实现。
    设计原则：
    - 严格遵循 BGP 单路径选路，不启用 ECMP 或路由重分发。
    - 主机侧采用“单主机单 /24 子网”架构，彻底消除 Linux 内核多接口同网段转发冲突。
    - 接口命名与配置文件生成器保持严格一致，确保拓扑实例化后 FRR 自动加载生效。
    - 主机命名采用标准连续单序号格式，消除自定义 CLI 封装对连字符标识符的解析死锁。
    """
    def build(self, k=4):
        # 动态端口命名计数器，确保与配置生成器的 get_intf() 逻辑完全同步
        self.port_cnt = {}
        def alloc_intf(sw_name):
            self.port_cnt[sw_name] = self.port_cnt.get(sw_name, 1)
            name = f"Ethernet1-{self.port_cnt[sw_name]}"
            self.port_cnt[sw_name] += 1
            return name

        # 1. 拓扑规模参数
        num_pods = k
        num_core = (k // 2) ** 2
        num_agg = (k // 2) * k
        num_edge = (k // 2) * k

        # 2. 创建交换机节点并预加载 bgpd 守护进程
        core_sw = [self.addSwitch(f'c{i+1}', daemons=["bgpd"]) for i in range(num_core)]
        agg_sw  = [self.addSwitch(f'a{i+1}', daemons=["bgpd"]) for i in range(num_agg)]
        edge_sw = [self.addSwitch(f'e{i+1}', daemons=["bgpd"]) for i in range(num_edge)]

        # 3. 核心 <-> 汇聚 链路 (10Mbps, 10ms 延迟模拟骨干互联)
        for i in range(num_agg):
            for j in range(k // 2):
                core_idx = j + (i % (k // 2)) * (k // 2)
                self.addLink(agg_sw[i], core_sw[core_idx],
                             intf1=alloc_intf(f'a{i+1}'),
                             intf2=alloc_intf(f'c{core_idx+1}'),
                             bw=10, delay="10ms")

        # 4. 汇聚 <-> 边缘 Pod 内全互联 (10Mbps, 10ms 延迟)
        for p in range(num_pods):
            for a_idx in range(k // 2):
                curr_agg = agg_sw[p * (k//2) + a_idx]
                for e_idx in range(k // 2):
                    curr_edge = edge_sw[p * (k//2) + e_idx]
                    self.addLink(curr_agg, curr_edge,
                                 intf1=alloc_intf(f'a{p*(k//2)+a_idx+1}'),
                                 intf2=alloc_intf(f'e{p*(k//2)+e_idx+1}'),
                                 bw=10, delay="10ms")

        # 5. 边缘 <-> 主机链路 (默认带宽，直连网关)
        host_id = 1
        for i in range(num_edge):
            edge_name = f'e{i+1}'
            for h_idx in range(k // 2):
                # 主机 IP 与子网必须与配置生成器严格对齐 (192.168.X.0/24)
                h_ip = f"192.168.{host_id}.2/24"
                h_gw = f"192.168.{host_id}.1"
                
                host = self.addHost(f'h{host_id}', 
                                    ip=h_ip, 
                                    defaultRoute=f"via {h_gw}")
                
                self.addLink(edge_sw[i], host, intf1=alloc_intf(edge_name))
                host_id += 1

if __name__ == "__main__":
    frrnet_main(FatTreeTopo)