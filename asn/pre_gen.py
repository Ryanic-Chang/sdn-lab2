#!/usr/bin/env python3
import os

def generate_frr_configs_extra(k=4):
    os.makedirs("config", exist_ok=True)
    
    num_pods = k
    num_core = (k // 2) ** 2
    
    # 1. AS 号分配逻辑
    # Core: 65001
    # Agg: 每个 Pod 一个 AS (200 + pod_id)
    # Edge: 每个 Pod 一个 AS (300 + pod_id)
    as_map = {}
    for i in range(num_core):
        as_map[f'c{i+1}'] = 65001
    
    for p in range(num_pods):
        for i in range(k // 2):
            agg_id = p * (k // 2) + i + 1
            edge_id = p * (k // 2) + i + 1
            as_map[f'a{agg_id}'] = 200 + p
            as_map[f'e{edge_id}'] = 300 + p

    all_switches = list(as_map.keys())
    confs = {name: {"as": as_map[name], "interfaces": [], "neighbors": [], "networks": []} 
             for name in all_switches}

    p2p_counter = 0
    def add_p2p_link(sw1, sw2, intf1, intf2):
        nonlocal p2p_counter
        base = f"10.{ (p2p_counter >> 8) & 0xFF }.{ p2p_counter & 0xFF }"
        ip1, ip2 = f"{base}.0/31", f"{base}.1/31"
        p2p_counter += 1
        
        confs[sw1]["interfaces"].append(f"interface {intf1}\n  ip address {ip1}")
        confs[sw2]["interfaces"].append(f"interface {intf2}\n  ip address {ip2}")
        
        # 核心配置：添加 allowas-in 以解决同 ASN 丢弃问题
        confs[sw1]["neighbors"].append(f"neighbor {base}.1 remote-as {as_map[sw2]}")
        confs[sw1]["neighbors"].append(f"neighbor {base}.1 allowas-in 2")
        
        confs[sw2]["neighbors"].append(f"neighbor {base}.0 remote-as {as_map[sw1]}")
        confs[sw2]["neighbors"].append(f"neighbor {base}.0 allowas-in 2")

    port_cnt = {name: 1 for name in all_switches}
    def get_intf(name):
        res = f"Ethernet1-{port_cnt[name]}"
        port_cnt[name] += 1
        return res

    # 2. 连接逻辑
    # Core <-> Agg
    for i in range(k * (k // 2)): # 8个 Agg
        pod = i // (k // 2)
        for j in range(k // 2):
            core_idx = j + (i % (k // 2)) * (k // 2)
            add_p2p_link(f'a{i+1}', f'c{core_idx+1}', get_intf(f'a{i+1}'), get_intf(f'c{core_idx+1}'))

    # Agg <-> Edge
    for p in range(num_pods):
        for a_idx in range(k // 2):
            agg_name = f'a{p * (k//2) + a_idx + 1}'
            for e_idx in range(k // 2):
                edge_name = f'e{p * (k//2) + e_idx + 1}'
                add_p2p_link(agg_name, edge_name, get_intf(agg_name), get_intf(edge_name))

    # Edge <-> Host
    host_id = 1
    for i in range(k * (k // 2)):
        edge_name = f'e{i+1}'
        for _ in range(k // 2):
            gw_ip = f"172.16.{host_id}.1/24"
            net_addr = f"172.16.{host_id}.0/24"
            confs[edge_name]["interfaces"].append(f"interface {get_intf(edge_name)}\n  ip address {gw_ip}")
            confs[edge_name]["networks"].append(f"network {net_addr}")
            host_id += 1

    # 3. 写入文件并添加 ECMP 策略
    for name, cfg in confs.items():
        with open(f"config/{name}.conf", "w") as f:
            f.write("frr defaults datacenter\n!\n")
            for iface in cfg["interfaces"]: f.write(iface + "\n!\n")
            f.write(f"router bgp {cfg['as']}\n")
            f.write("  bgp bestpath as-path multipath-relax\n") # 关键：允许不同 AS_PATH 的 ECMP
            for nb in cfg["neighbors"]: f.write(f"  {nb}\n")
            f.write("  address-family ipv4 unicast\n")
            for net in cfg["networks"]: f.write(f"    network {net}\n")
            f.write("    maximum-paths 64\n") # 开启多路径转发
            f.write("  exit-address-family\n!\n")
    print("Bonus configurations (Shared ASN) generated.")

if __name__ == "__main__":
    generate_frr_configs_extra(4)