#!/usr/bin/env python3
import os

def generate_frr_configs(k=4):
    """
    生成 Fat-Tree 拓扑的 FRR BGP 配置文件。
    架构说明：
    - 核心/汇聚/边缘交换机采用标准 k=4 Fat-Tree 结构。
    - P2P 互联链路统一使用 10.0.0.0/16 网段内的 /31 地址动态分配。
    - 每台主机独占一个 192.168.X.0/24 子网，彻底消除 Linux 内核多接口同网段转发冲突。
    - 边缘交换机通过 BGP network 精确宣告主机网段，上游按需收敛单路径最优路由。
    - 已预留 ECMP 路径宽松指令（默认注释），解除 AS-Path 唯一性校验以支持多等价路径并发。
    """
    os.makedirs("config", exist_ok=True)
    
    # 1. 拓扑规模计算
    num_pods = k
    num_core = (k // 2) ** 2
    num_agg = (k // 2) * k
    num_edge = (k // 2) * k
    
    all_switches = ([f'c{i+1}' for i in range(num_core)] + 
                    [f'a{i+1}' for i in range(num_agg)] + 
                    [f'e{i+1}' for i in range(num_edge)])
    
    # AS 号分配策略：Core(100+), Agg(200+), Edge(300+)
    as_map = {}
    for i in range(num_core): as_map[f'c{i+1}'] = 100 + i
    for i in range(num_agg):  as_map[f'a{i+1}'] = 200 + i
    for i in range(num_edge): as_map[f'e{i+1}'] = 300 + i

    # 初始化配置字典容器
    confs = {name: {"as": as_map[name], "interfaces": [], "neighbors": [], "networks": []} 
             for name in all_switches}

    # P2P 链路 IP 计数器 (使用 10.X.Y.0/31 按序分配)
    p2p_counter = 0
    def add_p2p_link(sw1, sw2, intf1, intf2):
        nonlocal p2p_counter
        base = f"10.{ (p2p_counter >> 8) & 0xFF }.{ p2p_counter & 0xFF }"
        ip1, ip2 = f"{base}.0/31", f"{base}.1/31"
        p2p_counter += 1
        
        confs[sw1]["interfaces"].append(f"interface {intf1}\n  ip address {ip1}")
        confs[sw2]["interfaces"].append(f"interface {intf2}\n  ip address {ip2}")
        confs[sw1]["neighbors"].append(f"neighbor {base}.1 remote-as {as_map[sw2]}")
        confs[sw2]["neighbors"].append(f"neighbor {base}.0 remote-as {as_map[sw1]}")

    # 接口命名计数器，确保与 Topo 脚本的 alloc_intf 严格同步
    port_cnt = {name: 1 for name in all_switches}
    def get_intf(name):
        res = f"Ethernet1-{port_cnt[name]}"
        port_cnt[name] += 1
        return res

    # --- 拓扑连接逻辑 (必须与 Topo 类中的 addLink 调用顺序完全一致) ---

    # 2. 核心 <-> 汇聚 全互联
    for i in range(num_agg):
        for j in range(k // 2):
            core_idx = j + (i % (k // 2)) * (k // 2)
            add_p2p_link(f'a{i+1}', f'c{core_idx+1}', get_intf(f'a{i+1}'), get_intf(f'c{core_idx+1}'))

    # 3. 汇聚 <-> 边缘 Pod 内全互联
    for p in range(num_pods):
        for a_idx in range(k // 2):
            agg_name = f'a{p * (k//2) + a_idx + 1}'
            for e_idx in range(k // 2):
                edge_name = f'e{p * (k//2) + e_idx + 1}'
                add_p2p_link(agg_name, edge_name, get_intf(agg_name), get_intf(edge_name))

    # 4. 边缘 <-> 主机 (单主机单 /24 子网架构)
    host_id = 1
    for i in range(num_edge):
        edge_name = f'e{i+1}'
        for _ in range(k // 2):
            gw_ip = f"192.168.{host_id}.1/24"
            net_addr = f"192.168.{host_id}.0/24"
            confs[edge_name]["interfaces"].append(f"interface {get_intf(edge_name)}\n  ip address {gw_ip}")
            confs[edge_name]["networks"].append(f"network {net_addr}")
            host_id += 1

    # 5. 持久化配置文件至磁盘
    for name, cfg in confs.items():
        with open(f"config/{name}.conf", "w") as f:
            f.write("frr defaults datacenter\n!\n")
            for iface in cfg["interfaces"]: f.write(iface + "\n!\n")
            f.write(f"router bgp {cfg['as']}\n")
            f.write(f"  bgp router-id {name}\n")
            # 预留 ECMP 策略
            f.write("  bgp bestpath as-path multipath-relax\n")
            for nb in cfg["neighbors"]: f.write(f"  {nb}\n")
            for net in cfg["networks"]: f.write(f"  {net}\n")
            f.write("!\n")
    print(f"成功生成 k={k} Fat-Tree 的 FRR 配置文件至 ./config/ 目录")

if __name__ == "__main__":
    generate_frr_configs(4)